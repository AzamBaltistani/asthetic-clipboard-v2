# Aesthetic Clipboard v2

A lightweight, keyboard-driven clipboard history manager for Wayland on PopOS 24 / COSMIC. Built with Python and GTK4.

---

## Features

- Clipboard history for text and images
- Instant popup on `Super+V` (stays resident at ~0% CPU between uses)
- Pin items to keep them at the top permanently
- Search through history
- Save images directly to `~/Downloads`
- Dark and light theme
- Configurable preferences (max history, deduplication, image capture, etc.)
- Optionally clears unpinned history on restart (pinned items always survive)
- Single-instance — pressing `Super+V` again shows the existing window instantly

---

## Requirements

- PopOS 24 / Ubuntu 24.04 (or any Wayland distro with GTK4)
- Python 3.12+
- `wl-clipboard` (`wl-paste`, `wl-copy`)
- `python3-gi` + GTK4 GObject introspection bindings
- `Pillow` (optional — for image thumbnails)

---

## Install

```bash
git clone <your-repo>
cd aesthetic-clipboard-v2

chmod +x install.sh
./install.sh
```

The installer will:
1. Create `~/.local/share/clipman/` and copy all files
2. Check and install missing dependencies (`wl-clipboard`, `python3-gi`, `Pillow`)
3. Install the autostart entry so the daemon launches on login
4. Start the daemon immediately

---

## Bind the keyboard shortcut

Open **COSMIC Settings → Keyboard → Keyboard Shortcuts → Custom Shortcuts** and add:

| Field | Value |
|-------|-------|
| Name | Aesthetic Clipboard |
| Command | `/usr/bin/python3 ~/.local/share/clipman/clipui.py` |
| Shortcut | `Super+V` |

> **Important:** Use `/usr/bin/python3` explicitly, not just `python3`. If you have a virtual environment active in your shell, `python3` may resolve to the venv interpreter which cannot see system GTK4 bindings.

---

## Usage

| Action | How |
|--------|-----|
| Open | `Super+V` |
| Copy item | Click the row |
| Pin / unpin | `◇` button on the row |
| Save image to Downloads | `↓` button on image rows |
| Delete item | `✕` button on the row |
| Search | Type in the search bar at the bottom |
| Copy top search result | Press `Enter` |
| Close | `Escape` or click away |
| Preferences | `⚙` button at bottom right |
| Clear history | `⚙` → Clear history… |
| Stop daemon | `⚙` → Stop daemon… |

---

## Uninstall

```bash
chmod +x uninstall.sh
./uninstall.sh
```

---

## File layout

```
~/.local/share/clipman/
  clipd.py          ← background daemon
  clipui.py         ← GUI
  ipc_client.py     ← IPC client library
  history.db        ← SQLite clipboard history
  images/           ← captured PNG images + thumbnails
  prefs.json        ← user preferences
  clipd.sock        ← daemon IPC socket (exists while daemon runs)
  clipd.pid         ← daemon PID file
  clipui.pid        ← GUI PID file (for single-instance detection)
  clipui.sock       ← GUI toggle socket (exists while GUI runs)
  clipd.log         ← daemon log

~/.config/autostart/
  clipman-daemon.desktop   ← starts clipd on login

~/.local/bin/
  clipd             ← symlink to clipd.py
  clipui            ← symlink to clipui.py
```

---

## Preferences

Accessible via the `⚙` button, or by editing `~/.local/share/clipman/prefs.json` directly.

| Preference | Default | Description |
|------------|---------|-------------|
| `dark_mode` | `true` | Dark or light theme |
| `font_size` | `13` | UI font size |
| `keep_history` | `true` | If `false`, clears unpinned history on daemon restart. Pinned items always survive. |
| `store_images` | `true` | Capture images from clipboard |
| `deduplicate` | `true` | Re-copying an existing item bumps it to the top instead of duplicating |
| `trim_whitespace` | `true` | Strip leading/trailing whitespace from text clips |
| `max_history` | `200` | Maximum number of unpinned items to keep |
| `max_image_size` | `50` | Skip images larger than this many MB |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Wayland compositor                                  │
│  (clipboard events)                                  │
└──────────────────┬──────────────────────────────────┘
                   │ wl-paste --watch
                   ▼
┌─────────────────────────────────────────────────────┐
│  clipd.py  (daemon, always running)                  │
│                                                      │
│  ClipboardWatcher                                    │
│    └─ detects text / image changes                   │
│    └─ saves to SQLite (WAL mode)                     │
│    └─ generates thumbnails via Pillow                │
│                                                      │
│  IPCServer  (Unix socket: clipd.sock)                │
│    └─ responds to GUI commands over JSON             │
└──────────────────┬──────────────────────────────────┘
                   │ Unix socket (line-delimited JSON)
                   ▼
┌─────────────────────────────────────────────────────┐
│  clipui.py  (GUI, shown on Super+V)                  │
│                                                      │
│  AestheticClipboardWindow (Gtk.Window)               │
│    └─ history list with ClipRow widgets              │
│    └─ search, pin, delete, save image                │
│    └─ PrefsPopover for settings                      │
│    └─ hides on Escape/focus-loss (stays in memory)   │
│                                                      │
│  Toggle socket (clipui.sock)                         │
│    └─ second invocation signals first to show        │
└─────────────────────────────────────────────────────┘
```

**Key design decisions:**

- `wl-paste --watch` is used instead of polling — the daemon wakes only when the clipboard actually changes, consuming zero CPU otherwise
- The GUI uses `set_hide_on_close(True)` and hides rather than destroys on close, so `present()` on next Super+V is instant
- Single-instance is enforced with a PID file check (`os.kill(pid, 0)`) plus a Unix socket signal — the PID check is race-free, the socket delivers the "show" command
- Images are saved to disk immediately when captured, because Wayland clipboard data disappears when the source app closes
- SQLite runs in WAL mode so the GUI can read while the daemon is writing

---

## IPC protocol

Line-delimited JSON over `~/.local/share/clipman/clipd.sock`.

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

---

## Manual control

```bash
# Start daemon manually
/usr/bin/python3 ~/.local/share/clipman/clipd.py &

# Start GUI manually
/usr/bin/python3 ~/.local/share/clipman/clipui.py &

# Check if daemon is running
python3 -c "
import sys; sys.path.insert(0, '$HOME/.local/share/clipman')
from ipc_client import ClipmanClient
print('daemon running:', ClipmanClient().is_running())
"

# Stop daemon
python3 -c "
import sys; sys.path.insert(0, '$HOME/.local/share/clipman')
from ipc_client import ClipmanClient
ClipmanClient().stop_daemon()
"

# Kill GUI
pkill -f clipui.py

# View logs
tail -f ~/.local/share/clipman/clipd.log
```

---

## Memory and CPU usage

| State | CPU | Memory |
|-------|-----|--------|
| Daemon idle | ~0% | ~30MB |
| GUI hidden (resident) | ~0% | ~160MB |
| GUI visible | brief spike | ~160MB |

The ~160MB for the GUI is the cost of loading Python + GTK4 libraries, not the app itself. A blank GTK4 Python window costs ~130MB. The tradeoff is instant show on Super+V with no cold-start delay.

The daemon uses ~30MB and wakes only when clipboard content changes.

---

## Troubleshooting

**GUI says "PyGObject / GTK4 not found" inside a venv:**
Use `/usr/bin/python3` explicitly. GTK4 bindings are system packages and not visible to virtual environments.

**Daemon not capturing clipboard:**
Make sure `wl-clipboard` is installed: `sudo apt install wl-clipboard`

**History not persisting after restart:**
Check that `keep_history` is `true` in preferences (`⚙` → Keep history on restart).

**Multiple clipui processes in htop:**
These are threads, not processes. All rows with the same memory size (e.g. 157M) are threads of the same process. Press `H` in htop to hide threads and confirm only one clipui process exists.

**Stale socket preventing startup:**
```bash
rm -f ~/.local/share/clipman/clipui.pid ~/.local/share/clipman/clipui.sock
```