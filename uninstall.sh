#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "         ThinkControl Uninstallation Script               "
echo "=========================================================="

echo "==> Removing ThinkControl files..."

# 1. User-level files
USER_BIN="$HOME/.local/bin/thinkcontrol"
USER_DESKTOP="$HOME/.local/share/applications/com.lenovo.thinkcontrol.desktop"
USER_SVG="$HOME/.local/share/icons/hicolor/scalable/apps/com.lenovo.thinkcontrol.svg"
USER_PNG="$HOME/.local/share/icons/hicolor/128x128/apps/com.lenovo.thinkcontrol.png"
USER_META="$HOME/.local/share/metainfo/com.lenovo.thinkcontrol.metainfo.xml"
USER_LIB="$HOME/.local/share/thinkcontrol"

rm -f "$USER_BIN"
rm -f "$USER_DESKTOP"
rm -f "$USER_SVG"
rm -f "$USER_PNG"
rm -f "$USER_META"
rm -rf "$USER_LIB"

# 2. System-wide files (if run with sudo or if present)
if [ "$EUID" -eq 0 ]; then
    rm -f "/usr/local/bin/thinkcontrol"
    rm -f "/usr/share/applications/com.lenovo.thinkcontrol.desktop"
    rm -f "/usr/share/icons/hicolor/scalable/apps/com.lenovo.thinkcontrol.svg"
    rm -f "/usr/share/icons/hicolor/128x128/apps/com.lenovo.thinkcontrol.png"
    rm -f "/usr/share/metainfo/com.lenovo.thinkcontrol.metainfo.xml"
    rm -rf "/opt/thinkcontrol"
fi

# 3. Refresh desktop and icon databases
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    if [ "$EUID" -eq 0 ]; then
        update-desktop-database "/usr/share/applications" 2>/dev/null || true
    fi
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    if [ "$EUID" -eq 0 ]; then
        gtk-update-icon-cache -f -t "/usr/share/icons/hicolor" 2>/dev/null || true
    fi
fi

# 4. Check if Debian package is installed
if command -v dpkg >/dev/null 2>&1 && dpkg -s thinkcontrol >/dev/null 2>&1; then
    echo "ℹ️  Notice: A system-wide .deb package 'thinkcontrol' was detected."
    echo "   To remove it as well, run: sudo apt remove thinkcontrol"
fi

echo ""
echo "=========================================================="
echo "✓ ThinkControl has been completely and cleanly uninstalled!"
echo "All desktop entries, binaries, icons, and libraries were removed."
echo "=========================================================="
