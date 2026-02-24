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
cp clipui.py     "$INSTALL_DIR/clipui.py"
chmod +x "$INSTALL_DIR/clipui.py"
ln -sf "$INSTALL_DIR/clipui.py" "$BIN_DIR/clipui"

# Symlink the daemon into PATH
ln -sf "$INSTALL_DIR/clipd.py" "$BIN_DIR/clipd"
chmod +x "$INSTALL_DIR/clipd.py"

echo "==> Installing autostart entry…"
# Replace %h placeholder with real home
sed "s|%h|$HOME|g" clipman-daemon.desktop > "$AUTOSTART_DIR/clipman-daemon.desktop"

echo "==> Checking dependencies…"

if python3 -c "import gi; gi.require_version('Gtk','4.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "  [✓] PyGObject / GTK4"
else
    echo "  [!] GTK4 bindings not found. Installing…"
    sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-gdkpixbuf-2.0
fi
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
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Clipman installed and running!                          ║"
echo "║                                                          ║"
echo "║  Bind Super+V in COSMIC Settings → Keyboard:             ║"
echo "║    python3 ~/.local/share/clipman/clipui.py              ║"
echo "║                                                          ║"
echo "║  Or test the GUI right now:                              ║"
echo "║    python3 ~/.local/share/clipman/clipui.py              ║"
echo "╚══════════════════════════════════════════════════════════╝"