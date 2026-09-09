#!/usr/bin/env bash
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SOURCE_DIR/build_deb"
PKG_VERSION="1.0.0"
PKG_NAME="thinkcontrol"
DIST_DIR="$BUILD_DIR/${PKG_NAME}_${PKG_VERSION}_all"

echo "=========================================================="
echo "      Building ThinkControl Debian (.deb) Package         "
echo "=========================================================="

# 1. Clean previous build & set up standard Linux filesystem tree
rm -rf "$BUILD_DIR"
mkdir -p "$DIST_DIR/DEBIAN"
mkdir -p "$DIST_DIR/opt/thinkcontrol"
mkdir -p "$DIST_DIR/usr/bin"
mkdir -p "$DIST_DIR/usr/share/applications"
mkdir -p "$DIST_DIR/usr/share/metainfo"
mkdir -p "$DIST_DIR/usr/share/icons/hicolor/scalable/apps"
mkdir -p "$DIST_DIR/usr/share/icons/hicolor/128x128/apps"

# 2. Copy application source code
cp "$SOURCE_DIR/main.py" "$DIST_DIR/opt/thinkcontrol/"
cp "$SOURCE_DIR/controller.py" "$DIST_DIR/opt/thinkcontrol/"
chmod +x "$DIST_DIR/opt/thinkcontrol/main.py"

# 3. Copy icons (Scalable SVG + 128x128 PNG)
cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" "$DIST_DIR/usr/share/icons/hicolor/scalable/apps/"
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" "$DIST_DIR/usr/share/icons/hicolor/128x128/apps/com.lenovo.thinkcontrol.png"
fi

# 4. Copy AppStream Metainfo (Standard GNOME / Zorin Software Store)
cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" "$DIST_DIR/usr/share/metainfo/"

# 5. Create binary wrapper script in /usr/bin/thinkcontrol
cat << 'BIN' > "$DIST_DIR/usr/bin/thinkcontrol"
#!/usr/bin/env bash
exec /usr/bin/python3 /opt/thinkcontrol/main.py "$@"
BIN
chmod +x "$DIST_DIR/usr/bin/thinkcontrol"

# 6. Create Desktop Entry
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

# 7. Calculate Installed-Size (in KB)
INSTALLED_SIZE=$(du -sk "$DIST_DIR" | cut -f1)

# 8. Write DEBIAN/control package metadata with License field
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
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec
Description: Lenovo Vantage Hardware Control Center for ThinkPad on Linux
 ThinkControl provides an elegant, native Libadwaita interface for ThinkPad
 hardware controls including battery charging thresholds, performance platform
 profiles, and keyboard backlight.
CTRL

# 9. Build the official .deb package
dpkg-deb --build --root-owner-group "$DIST_DIR" "$SOURCE_DIR/${PKG_NAME}_${PKG_VERSION}_all.deb"

# Clean temporary build directory
rm -rf "$BUILD_DIR"

echo ""
echo "=========================================================="
echo "🎉 Debian package successfully generated!"
echo "📁 $SOURCE_DIR/${PKG_NAME}_${PKG_VERSION}_all.deb"
echo "=========================================================="
