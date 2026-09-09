#!/usr/bin/env bash
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SOURCE_DIR/build_deb"
PKG_VERSION="1.1.0"
PKG_NAME="thinkcontrol"
DIST_DIR="$BUILD_DIR/${PKG_NAME}_${PKG_VERSION}_all"

echo "=========================================================="
echo "      Building ThinkControl Debian (.deb) Package         "
echo "=========================================================="

# 1. Clean previous build & set up standard Linux filesystem tree
rm -rf "$BUILD_DIR"
mkdir -p "$DIST_DIR/DEBIAN"
chmod 755 "$DIST_DIR/DEBIAN"
mkdir -p "$DIST_DIR/opt/thinkcontrol"
mkdir -p "$DIST_DIR/usr/bin"
mkdir -p "$DIST_DIR/usr/libexec"
mkdir -p "$DIST_DIR/usr/share/applications"
mkdir -p "$DIST_DIR/usr/share/metainfo"
mkdir -p "$DIST_DIR/usr/share/polkit-1/actions"
mkdir -p "$DIST_DIR/usr/lib/systemd/system"
mkdir -p "$DIST_DIR/usr/lib/systemd/system-sleep"
mkdir -p "$DIST_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$DIST_DIR/usr/share/icons/hicolor/128x128/apps"

# 2. Copy application source code
cp "$SOURCE_DIR/main.py" "$DIST_DIR/opt/thinkcontrol/"
cp "$SOURCE_DIR/controller.py" "$DIST_DIR/opt/thinkcontrol/"
cp "$SOURCE_DIR/thinkcontrol-helper" "$DIST_DIR/usr/libexec/thinkcontrol-helper"
chmod +x "$DIST_DIR/opt/thinkcontrol/main.py"
chmod +x "$DIST_DIR/usr/libexec/thinkcontrol-helper"

# 3. Copy PolicyKit and Systemd Service
# 3. Copy PolicyKit, Systemd Service, and Sleep/Resume Hook
cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.policy" "$DIST_DIR/usr/share/polkit-1/actions/"
cp "$SOURCE_DIR/assets/thinkcontrol-apply.service" "$DIST_DIR/usr/lib/systemd/system/"
if [ -f "$SOURCE_DIR/assets/thinkcontrol-sleep" ]; then
    cp "$SOURCE_DIR/assets/thinkcontrol-sleep" "$DIST_DIR/usr/lib/systemd/system-sleep/thinkcontrol-sleep"
    chmod 755 "$DIST_DIR/usr/lib/systemd/system-sleep/thinkcontrol-sleep"
fi

# 4. Copy icons (Scalable SVG + 128x128 PNG)
cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" "$DIST_DIR/usr/share/icons/hicolor/scalable/apps/"
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" "$DIST_DIR/usr/share/icons/hicolor/128x128/apps/com.lenovo.thinkcontrol.png"
fi

# 5. Copy AppStream Metainfo (Standard GNOME / Zorin Software Store)
cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" "$DIST_DIR/usr/share/metainfo/"

# 6. Create binary wrapper script in /usr/bin/thinkcontrol
cat << 'BIN' > "$DIST_DIR/usr/bin/thinkcontrol"
#!/usr/bin/env bash
exec /usr/bin/python3 /opt/thinkcontrol/main.py "$@"
BIN
chmod +x "$DIST_DIR/usr/bin/thinkcontrol"

# 7. Create Desktop Entry
cat << 'DESK' > "$DIST_DIR/usr/share/applications/com.lenovo.thinkcontrol.desktop"
[Desktop Entry]
Name=ThinkControl
GenericName=Lenovo Vantage Alternative
Comment=Lenovo Vantage Hardware Control Center for Linux (ThinkPad)
Comment[id]=Pusat Kontrol Perangkat Keras ThinkPad untuk Linux
Exec=/usr/bin/thinkcontrol
Icon=com.lenovo.thinkcontrol
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;GTK;System;
StartupNotify=true
Keywords=lenovo;vantage;battery;thinkpad;charge;conservation;hardware;profile;
DESK
chmod 644 "$DIST_DIR/usr/share/applications/com.lenovo.thinkcontrol.desktop"

# 8. Add maintainer scripts (postinst and prerm for systemd service)
cat << 'POSTINST' > "$DIST_DIR/DEBIAN/postinst"
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v systemctl >/dev/null 2>&1; then
        systemctl daemon-reload || true
        systemctl enable thinkcontrol-apply.service || true
        systemctl start thinkcontrol-apply.service || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database /usr/share/applications 2>/dev/null || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    fi
fi
exit 0
POSTINST
chmod 755 "$DIST_DIR/DEBIAN/postinst"

cat << 'PRERM' > "$DIST_DIR/DEBIAN/prerm"
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v systemctl >/dev/null 2>&1; then
        systemctl stop thinkcontrol-apply.service 2>/dev/null || true
        systemctl disable thinkcontrol-apply.service 2>/dev/null || true
    fi
fi
exit 0
PRERM
chmod 755 "$DIST_DIR/DEBIAN/prerm"

cat << 'POSTRM' > "$DIST_DIR/DEBIAN/postrm"
#!/bin/sh
set -e
if [ "$1" = "purge" ]; then
    rm -f /etc/thinkcontrol.json
fi
exit 0
POSTRM
chmod 755 "$DIST_DIR/DEBIAN/postrm"

# 9. Calculate Installed-Size (in KB)
INSTALLED_SIZE=$(du -sk "$DIST_DIR" | cut -f1)

# 10. Write DEBIAN/control package metadata with License field
cat << CTRL > "$DIST_DIR/DEBIAN/control"
Package: thinkcontrol
Version: $PKG_VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Maintainer: Anggiyawan <anggiyawan@local>
License: GPL-3.0
Homepage: https://github.com/anggiyawan/ThinkControl
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec, polkitd
Description: Lenovo Vantage Hardware Control Center for ThinkPad on Linux
 ThinkControl provides an elegant, native Libadwaita interface for ThinkPad
 hardware controls including battery charging thresholds, performance platform
 profiles, dual-battery monitoring, and keyboard backlight.
CTRL

# 11. Build the official .deb package (replace existing deb)
TARGET_DEB="$SOURCE_DIR/${PKG_NAME}_${PKG_VERSION}_all.deb"
EXISTING_DEB="$SOURCE_DIR/thinkcontrol_1.0.0_all.deb"

dpkg-deb --build --root-owner-group "$DIST_DIR" "$TARGET_DEB"

# If user specifically asked to replace the existing deb:
if [ -f "$EXISTING_DEB" ] && [ "$EXISTING_DEB" != "$TARGET_DEB" ]; then
    rm -f "$EXISTING_DEB"
fi
# Also provide thinkcontrol_1.0.0_all.deb link or keep standard versioned name
cp "$TARGET_DEB" "$SOURCE_DIR/thinkcontrol_1.0.0_all.deb"

# Clean temporary build directory
rm -rf "$BUILD_DIR"

echo ""
echo "=========================================================="
echo "🎉 Debian package successfully generated & replaced!"
echo "📁 $TARGET_DEB"
echo "📁 $SOURCE_DIR/thinkcontrol_1.0.0_all.deb"
echo "=========================================================="
