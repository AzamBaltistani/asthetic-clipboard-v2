# uninstall.sh — removes Aesthetic Clipboard v2 from the system
set -e

INSTALL_DIR="$HOME/.local/share/clipman"
BIN_DIR="$HOME/.local/bin"
AUTOSTART_DIR="$HOME/.config/autostart"

echo ""
echo "Aesthetic Clipboard v2 — Uninstaller"
echo "────────────────────────────────────"
echo ""

# ── Confirm ───────────────────────────────────────────────────────────────────
read -r -p "This will stop the daemon, remove all files, and delete clipboard history. Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""

# ── Stop running processes ────────────────────────────────────────────────────
echo "==> Stopping daemon…"
if [ -f "$INSTALL_DIR/clipd.pid" ]; then
    PID=$(cat "$INSTALL_DIR/clipd.pid" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "  [✓] Daemon stopped (PID $PID)"
    else
        echo "  [–] Daemon was not running"
    fi
else
    # Try pkill as fallback
    if pkill -f "clipd.py" 2>/dev/null; then
        echo "  [✓] Daemon stopped"
    else
        echo "  [–] Daemon was not running"
    fi
fi

echo "==> Stopping GUI…"
if [ -f "$INSTALL_DIR/clipui.pid" ]; then
    PID=$(cat "$INSTALL_DIR/clipui.pid" 2>/dev/null || true)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "  [✓] GUI stopped (PID $PID)"
    else
        echo "  [–] GUI was not running"
    fi
else
    if pkill -f "clipui.py" 2>/dev/null; then
        echo "  [✓] GUI stopped"
    else
        echo "  [–] GUI was not running"
    fi
fi

sleep 0.5   # let processes exit cleanly

# ── Ask about history ─────────────────────────────────────────────────────────
echo ""
read -r -p "Delete clipboard history and saved images? [y/N] " del_history
echo ""

# ── Remove autostart entry ────────────────────────────────────────────────────
echo "==> Removing autostart entry…"
if [ -f "$AUTOSTART_DIR/clipman-daemon.desktop" ]; then
    rm "$AUTOSTART_DIR/clipman-daemon.desktop"
    echo "  [✓] Removed $AUTOSTART_DIR/clipman-daemon.desktop"
else
    echo "  [–] Not found, skipping"
fi

# ── Remove symlinks from ~/.local/bin ─────────────────────────────────────────
echo "==> Removing symlinks…"
for link in clipd clipui; do
    if [ -L "$BIN_DIR/$link" ]; then
        rm "$BIN_DIR/$link"
        echo "  [✓] Removed $BIN_DIR/$link"
    fi
done

# ── Remove install directory ──────────────────────────────────────────────────
echo "==> Removing files…"
if [ -d "$INSTALL_DIR" ]; then
    if [[ "$del_history" =~ ^[Yy]$ ]]; then
        # Remove everything
        rm -rf "$INSTALL_DIR"
        echo "  [✓] Removed $INSTALL_DIR (including history and images)"
    else
        # Keep history.db and images/, remove only scripts and runtime files
        for f in clipd.py clipui.py ipc_client.py clipd.sock clipui.sock clipd.pid clipui.pid clipd.log; do
            if [ -f "$INSTALL_DIR/$f" ]; then
                rm "$INSTALL_DIR/$f"
                echo "  [✓] Removed $f"
            fi
        done
        echo "  [–] History and images kept at $INSTALL_DIR"
        echo "      (delete manually: rm -rf $INSTALL_DIR)"
    fi
else
    echo "  [–] $INSTALL_DIR not found, skipping"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Aesthetic Clipboard v2 uninstalled.                     ║"
echo "║                                                          ║"
echo "║  Don't forget to remove the Super+V keyboard shortcut    ║"
echo "║  in COSMIC Settings → Keyboard → Custom Shortcuts.       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""