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
    APP_DIR="/usr/share/applications"
    ICON_SVG_DIR="/usr/share/icons/hicolor/scalable/apps"
    ICON_PNG_DIR="/usr/share/icons/hicolor/128x128/apps"
    META_DIR="/usr/share/metainfo"
    ICON_CACHE_DIR="/usr/share/icons/hicolor"
else
    echo "==> Installing for current user ($USER)..."
    INSTALL_LIB="$HOME/.local/share/thinkcontrol"
    BIN_DIR="$HOME/.local/bin"
    APP_DIR="$HOME/.local/share/applications"
    ICON_SVG_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
    ICON_PNG_DIR="$HOME/.local/share/icons/hicolor/128x128/apps"
    META_DIR="$HOME/.local/share/metainfo"
    ICON_CACHE_DIR="$HOME/.local/share/icons/hicolor"
fi

# 3. Create destination directories
mkdir -p "$INSTALL_LIB" "$BIN_DIR" "$APP_DIR" "$ICON_SVG_DIR" "$ICON_PNG_DIR" "$META_DIR"

# 4. Copy application files to standalone library directory
echo "==> Copying application files to $INSTALL_LIB..."
cp "$SOURCE_DIR/main.py" "$INSTALL_LIB/"
cp "$SOURCE_DIR/controller.py" "$INSTALL_LIB/"
chmod +x "$INSTALL_LIB/main.py"

# 5. Install icons
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.svg" "$ICON_SVG_DIR/"
    echo "✓ Scalable SVG icon installed to $ICON_SVG_DIR"
fi
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol_128.png" "$ICON_PNG_DIR/com.lenovo.thinkcontrol.png"
    echo "✓ 128x128 PNG icon installed to $ICON_PNG_DIR"
fi

# 6. Install AppStream Metainfo
if [ -f "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" ]; then
    cp "$SOURCE_DIR/assets/com.lenovo.thinkcontrol.metainfo.xml" "$META_DIR/"
    echo "✓ AppStream Metainfo installed to $META_DIR"
fi

# 7. Create CLI binary launcher
cat << WRAPPER > "$BIN_DIR/thinkcontrol"
#!/usr/bin/env bash
exec /usr/bin/python3 "$INSTALL_LIB/main.py" "\$@"
WRAPPER
chmod +x "$BIN_DIR/thinkcontrol"
echo "✓ CLI executable launcher created at $BIN_DIR/thinkcontrol"

# 8. Create Desktop Entry
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

# 9. Update desktop & icon caches
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
