# install.sh — installs Clipman on PopOS / any Wayland distro
set -e

INSTALL_DIR="$HOME/.local/share/clipman"
BIN_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"

echo "==> Creating directories…"
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$AUTOSTART_DIR"

echo "==> Copying files…"
cp clipd.py      "$INSTALL_DIR/clipd.py"
cp ipc_client.py "$INSTALL_DIR/ipc_client.py"

# Symlink the daemon into PATH
ln -sf "$INSTALL_DIR/clipd.py" "$BIN_DIR/clipd"
chmod +x "$INSTALL_DIR/clipd.py"

echo "==> Installing autostart entry…"
# Replace %h placeholder with real home
sed "s|%h|$HOME|g" clipman-daemon.desktop > "$AUTOSTART_DIR/clipman-daemon.desktop"

echo "==> Checking dependencies…"

if ! command -v wl-paste &>/dev/null; then
    echo "  [!] wl-clipboard not found. Installing…"
    sudo apt install -y wl-clipboard
else
    echo "  [✓] wl-clipboard"
fi

# Optional: Pillow for image thumbnails
if python3 -c "from PIL import Image" 2>/dev/null; then
    echo "  [✓] Pillow"
else
    echo "  [!] Pillow not found. Installing for image thumbnails…"
    pip3 install --user Pillow --break-system-packages
fi

echo ""
echo "==> Starting daemon…"
if python3 "$INSTALL_DIR/clipd.py" &
then
    sleep 0.5
    echo "  [✓] Daemon started (PID stored in $INSTALL_DIR/clipd.pid)"
else
    echo "  [!] Daemon may already be running."
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Clipman daemon installed and running!               ║"
echo "║                                                      ║"
echo "║  Next step: install the GUI (clipui.py)              ║"
echo "║  Then bind Super+V to:                               ║"
echo "║    python3 ~/.local/share/clipman/clipui.py          ║"
echo "╚══════════════════════════════════════════════════════╝"