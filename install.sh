#!/usr/bin/env bash
set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================="
echo "         ThinkControl Installation Script                 "
echo "=========================================================="

# 1. Dependency Check
echo "==> Checking system dependencies..."
MISSING_DEPS=()

if ! command -v python3 >/dev/null 2>&1; then
    MISSING_DEPS+=("python3")
fi

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw" >/dev/null 2>&1; then
    MISSING_DEPS+=("python3-gi" "gir1.2-gtk-4.0" "gir1.2-adw-1")
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "❌ Error: Missing required dependencies: ${MISSING_DEPS[*]}"
    echo "Please install them by running:"
    echo "  sudo apt update && sudo apt install -y ${MISSING_DEPS[*]}"
    exit 1
fi
echo "✓ All dependencies are satisfied."

# 2. Determine target paths (User vs System-wide)
if [ "$EUID" -eq 0 ]; then
    echo "==> Installing system-wide (Root mode)..."
    INSTALL_LIB="/opt/thinkcontrol"
    BIN_DIR="/usr/local/bin"
    HELPER_DIR="/usr/libexec"
    APP_DIR="/usr/share/applications"
    ICON_SVG_DIR="/usr/share/icons/hicolor/scalable/apps"
    ICON_PNG_DIR="/usr/share/icons/hicolor/128x128/apps"
    META_DIR="/usr/share/metainfo"
    ICON_CACHE_DIR="/usr/share/icons/hicolor"
    POLKIT_DIR="/usr/share/polkit-1/actions"
    SYSTEMD_DIR="/usr/lib/systemd/system"
    SLEEP_DIR="/usr/lib/systemd/system-sleep"
else
    echo "==> Installing for current user ($USER)..."
    INSTALL_LIB="$HOME/.local/share/thinkcontrol"
    BIN_DIR="$HOME/.local/bin"
    HELPER_DIR="$HOME/.local/bin"
    APP_DIR="$HOME/.local/share/applications"
    ICON_SVG_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
    ICON_PNG_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
    META_DIR="$HOME/.local/share/metainfo"
    ICON_CACHE_DIR="$HOME/.local/share/icons/hicolor"
    POLKIT_DIR=""
    SYSTEMD_DIR=""
    SLEEP_DIR=""
fi

# 3. Create destination directories
mkdir -p "$INSTALL_LIB" "$BIN_DIR" "$HELPER_DIR" "$APP_DIR" "$ICON_SVG_DIR" "$ICON_PNG_DIR" "$META_DIR"

# 4. Copy application files to standalone library directory
echo "==> Copying application files to $INSTALL_LIB..."
cp "$SOURCE_DIR/main.py" "$INSTALL_LIB/"
cp "$SOURCE_DIR/controller.py" "$INSTALL_LIB/"
cp "$SOURCE_DIR/thinkcontrol-helper" "$INSTALL_LIB/"
chmod +x "$INSTALL_LIB/main.py"
chmod +x "$INSTALL_LIB/thinkcontrol-helper"

# Copy helper to executable path
cp "$SOURCE_DIR/thinkcontrol-helper" "$HELPER_DIR/thinkcontrol-helper"
chmod +x "$HELPER_DIR/thinkcontrol-helper"

# 5. Install Polkit Policy & Systemd Service if root
if [ "$EUID" -eq 0 ]; then
    if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.policy" ]; then
        mkdir -p "$POLKIT_DIR"
        cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.policy" "$POLKIT_DIR/"
        echo "✓ PolicyKit action policy installed to $POLKIT_DIR"
    fi
    if [ -f "$SOURCE_DIR/assets/thinkcontrol-apply.service" ]; then
        mkdir -p "$SYSTEMD_DIR"
        cp "$SOURCE_DIR/assets/thinkcontrol-apply.service" "$SYSTEMD_DIR/"
        if command -v systemctl >/dev/null 2>&1; then
            systemctl daemon-reload || true
            systemctl enable thinkcontrol-apply.service || true
        fi
        echo "✓ Systemd persistence service enabled"
    fi
    if [ -f "$SOURCE_DIR/assets/thinkcontrol-sleep" ]; then
        mkdir -p "$SLEEP_DIR"
        cp "$SOURCE_DIR/assets/thinkcontrol-sleep" "$SLEEP_DIR/"
        chmod +x "$SLEEP_DIR/thinkcontrol-sleep"
        echo "✓ Systemd sleep/resume restoration hook installed to $SLEEP_DIR"
    fi
fi

# 6. Install icons
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" "$ICON_SVG_DIR/"
    echo "✓ Scalable SVG icon installed to $ICON_SVG_DIR"
fi
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" "$ICON_PNG_DIR/com.lenovo.thinkcontrol.png"
    echo "✓ 128x128 PNG icon installed to $ICON_PNG_DIR"
fi

# 7. Install AppStream Metainfo
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" "$META_DIR/"
    echo "✓ AppStream Metainfo installed to $META_DIR"
fi

# 8. Create CLI binary launcher
cat << WRAPPER > "$BIN_DIR/thinkcontrol"
#!/usr/bin/env bash
exec /usr/bin/python3 "$INSTALL_LIB/main.py" "\$@"
WRAPPER
chmod +x "$BIN_DIR/thinkcontrol"
echo "✓ CLI executable launcher created at $BIN_DIR/thinkcontrol"

# 9. Create Desktop Entry
cat << DESKTOP > "$APP_DIR/com.lenovo.thinkcontrol.desktop"
[Desktop Entry]
Name=ThinkControl
GenericName=Lenovo Vantage Alternative
Comment=Lenovo Vantage Hardware Control Center for Linux (ThinkPad)
Comment[id]=Pusat Kontrol Perangkat Keras ThinkPad untuk Linux
Exec=$BIN_DIR/thinkcontrol
Icon=com.lenovo.thinkcontrol
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;GTK;System;
StartupNotify=true
Keywords=lenovo;vantage;battery;thinkpad;charge;conservation;hardware;profile;
DESKTOP
chmod 644 "$APP_DIR/com.lenovo.thinkcontrol.desktop"
echo "✓ Desktop launcher entry created at $APP_DIR"

# 10. Update desktop & icon caches
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_CACHE_DIR" 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "🎉 ThinkControl has been successfully installed!"
echo "You can launch it via:"
echo "  1. System Application Menu (Search for 'ThinkControl')"
echo "  2. Terminal command: thinkcontrol"
echo "=========================================================="
