# Clipman — Phase 1: Daemon

A lightweight clipboard history daemon for Wayland/COSMIC (PopOS 24).

## Files

| File | Purpose |
|------|---------|
| `clipd.py` | Background daemon — watches clipboard, stores history |
| `ipc_client.py` | Python client library for GUI ↔ daemon communication |
| `install.sh` | One-shot installer |
| `clipman-daemon.desktop` | Autostart entry (placed in `~/.config/autostart/`) |

## Install

```bash
chmod +x install.sh
./install.sh
```

That's it. The daemon auto-starts on login going forward.

## Manual daemon control

```bash
# Start
python3 ~/.local/share/clipman/clipd.py &

# Check it's alive
python3 - <<'EOF'
from ipc_client import ClipmanClient
c = ClipmanClient()
print("running:", c.is_running())
EOF

# View recent history
python3 - <<'EOF'
import sys; sys.path.insert(0, "/home/$USER/.local/share/clipman")
from ipc_client import ClipmanClient
c = ClipmanClient()
for item in c.get_history(limit=10):
    print(item)
EOF

# Stop
python3 - <<'EOF'
from ipc_client import ClipmanClient
ClipmanClient().stop_daemon()
EOF
```

## IPC Protocol

Line-delimited JSON over a Unix socket at `~/.local/share/clipman/clipd.sock`.

| Command | Payload | Response |
|---------|---------|----------|
| `ping` | — | `{ok, pong}` |
| `get_history` | `limit, offset, query` | `{ok, items[]}` |
| `copy` | `id` | `{ok}` |
| `delete` | `id` | `{ok}` |
| `pin` | `id` | `{ok, pinned}` |
| `clear` | `keep_pinned` | `{ok}` |
| `get_prefs` | — | `{ok, prefs}` |
| `set_prefs` | `prefs{}` | `{ok}` |
| `stop` | — | `{ok}` |

## Data locations

```
~/.local/share/clipman/
  clipd.py          ← daemon script
  ipc_client.py     ← client lib
  history.db        ← SQLite database
  images/           ← PNG snapshots + thumbnails
  prefs.json        ← user preferences
  clipd.sock        ← IPC socket (live only)
  clipd.pid         ← PID file
  clipd.log         ← log file
```

## Default preferences (prefs.json)

```json
{
  "max_history": 200,
  "max_image_size": 50,
  "store_images": true,
  "dark_mode": true,
  "font_size": 13,
  "trim_whitespace": true,
  "deduplicate": true
}
```

## Architecture notes

- Uses `wl-paste --watch` for event-driven clipboard changes (no busy-polling)
- Falls back to 500 ms polling if `wl-paste --watch` isn't available  
- Images are saved as full PNGs; thumbnails (200×200) generated with Pillow
- Dedup bumps existing item to top rather than creating a duplicate
- History trimming preserves all pinned items; prunes oldest unpinned entries
- WAL mode SQLite for safe concurrent reads from GUI