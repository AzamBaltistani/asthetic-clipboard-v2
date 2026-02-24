"""
clipd.py — Clipman Daemon
Watches the Wayland clipboard and saves history to SQLite.
Exposes a Unix socket for IPC with the GUI.
"""

import os
import sys
import json
import time
import signal
import socket
import hashlib
import logging
import sqlite3
import threading
import subprocess
from pathlib import Path
from datetime import datetime

# ─── Paths ────────────────────────────────────────────────────────────────────

HOME = Path.home()
DATA_DIR   = HOME / ".local" / "share" / "clipman"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH    = DATA_DIR / "history.db"
PREFS_PATH = DATA_DIR / "prefs.json"
SOCKET_PATH = DATA_DIR / "clipd.sock"
PID_FILE    = DATA_DIR / "clipd.pid"
LOG_FILE    = DATA_DIR / "clipd.log"

# ─── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_PREFS = {
    "max_history":    50,
    "max_image_size": 50,      # MB — images larger than this are skipped
    "store_images":   True,
    "dark_mode":      True,
    "font_size":      13,
    "trim_whitespace": True,
    "deduplicate":    True,
    "keep_history":   True,    # if False, clears non-pinned history on startup
}

# ─── Logging ──────────────────────────────────────────────────────────────────

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("clipd")

# ─── Preferences ──────────────────────────────────────────────────────────────

def load_prefs() -> dict:
    if PREFS_PATH.exists():
        try:
            with open(PREFS_PATH) as f:
                data = json.load(f)
                return {**DEFAULT_PREFS, **data}
        except Exception:
            pass
    return dict(DEFAULT_PREFS)


def save_prefs(prefs: dict):
    with open(PREFS_PATH, "w") as f:
        json.dump(prefs, f, indent=2)

# ─── Database ─────────────────────────────────────────────────────────────────

def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            type       TEXT    NOT NULL,          -- 'text' | 'image'
            content    TEXT,                       -- text content OR image file path
            hash       TEXT    NOT NULL,           -- sha256 for dedup
            preview    TEXT,                       -- short snippet or thumbnail path
            pinned     INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL            -- unix timestamp
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON history(hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON history(created_at DESC)")
    conn.commit()
    return conn


def add_item(conn: sqlite3.Connection, prefs: dict,
             item_type: str, content: str, preview: str, item_hash: str):
    """Insert a new clipboard item, enforcing dedup and max history."""

    if prefs["deduplicate"]:
        row = conn.execute(
            "SELECT id FROM history WHERE hash = ?", (item_hash,)
        ).fetchone()
        if row:
            # Bump to top by updating timestamp
            conn.execute(
                "UPDATE history SET created_at = ? WHERE id = ?",
                (int(time.time()), row["id"])
            )
            conn.commit()
            log.debug("Duplicate — bumped existing item to top.")
            return

    conn.execute(
        """INSERT INTO history (type, content, hash, preview, pinned, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (item_type, content, item_hash, preview, int(time.time()))
    )

    # Trim history — keep pinned items, prune oldest unpinned
    max_h = prefs["max_history"]
    conn.execute("""
        DELETE FROM history
        WHERE pinned = 0
          AND id NOT IN (
            SELECT id FROM history
            WHERE pinned = 0
            ORDER BY created_at DESC
            LIMIT ?
          )
    """, (max_h,))

    conn.commit()
    log.info(f"Saved {item_type} item (hash={item_hash[:8]}…)")


def delete_item(conn: sqlite3.Connection, item_id: int):
    row = conn.execute("SELECT type, content FROM history WHERE id = ?", (item_id,)).fetchone()
    if row and row["type"] == "image":
        try:
            Path(row["content"]).unlink(missing_ok=True)
        except Exception:
            pass
    conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
    conn.commit()


def clear_history(conn: sqlite3.Connection, keep_pinned=True):
    if keep_pinned:
        rows = conn.execute("SELECT content FROM history WHERE pinned = 0 AND type = 'image'").fetchall()
    else:
        rows = conn.execute("SELECT content FROM history WHERE type = 'image'").fetchall()
    for row in rows:
        try:
            Path(row["content"]).unlink(missing_ok=True)
        except Exception:
            pass
    if keep_pinned:
        conn.execute("DELETE FROM history WHERE pinned = 0")
    else:
        conn.execute("DELETE FROM history")
    conn.commit()


def toggle_pin(conn: sqlite3.Connection, item_id: int) -> bool:
    row = conn.execute("SELECT pinned FROM history WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return False
    new_val = 0 if row["pinned"] else 1
    conn.execute("UPDATE history SET pinned = ? WHERE id = ?", (new_val, item_id))
    conn.commit()
    return bool(new_val)

# ─── Clipboard watching ───────────────────────────────────────────────────────

def get_clipboard_types() -> list[str]:
    """Ask wl-paste which MIME types are available on the clipboard."""
    try:
        result = subprocess.run(
            ["wl-paste", "--list-types"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return [t.strip() for t in result.stdout.splitlines() if t.strip()]
    except Exception:
        pass
    return []


def read_clipboard_text() -> str | None:
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline", "--type", "text/plain"],
            capture_output=True, timeout=3
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def read_clipboard_image() -> bytes | None:
    """Try to grab a PNG from the clipboard."""
    try:
        result = subprocess.run(
            ["wl-paste", "--type", "image/png"],
            capture_output=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
    except Exception:
        pass
    return None


def save_image(data: bytes) -> tuple[str, str]:
    """Save PNG bytes to disk, return (file_path, thumbnail_path)."""
    img_hash = hashlib.sha256(data).hexdigest()
    img_path = IMAGES_DIR / f"{img_hash}.png"
    thumb_path = IMAGES_DIR / f"{img_hash}_thumb.png"

    if not img_path.exists():
        img_path.write_bytes(data)
        # Generate thumbnail with Pillow if available
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            img.thumbnail((200, 200))
            img.save(str(thumb_path), "PNG")
        except ImportError:
            # No Pillow — use full image as thumb
            thumb_path = img_path
        except Exception as e:
            log.warning(f"Thumbnail generation failed: {e}")
            thumb_path = img_path

    return str(img_path), str(thumb_path)


class ClipboardWatcher:
    """
    Uses `wl-paste --watch` to get event-driven clipboard updates.
    Falls back to polling every 500 ms if wl-paste --watch isn't available.
    """

    def __init__(self, conn: sqlite3.Connection, prefs_ref: list):
        self.conn = conn
        self.prefs_ref = prefs_ref   # mutable list so daemon can swap prefs live
        self._stop = threading.Event()
        self._last_hash = ""

    @property
    def prefs(self):
        return self.prefs_ref[0]

    def _process_clipboard(self):
        types = get_clipboard_types()
        if not types:
            return

        # Prefer image if present
        image_types = [t for t in types if t.startswith("image/")]
        has_text = any(t in types for t in ("text/plain", "text/plain;charset=utf-8", "UTF8_STRING", "STRING"))

        if image_types and self.prefs["store_images"]:
            data = read_clipboard_image()
            if data:
                size_mb = len(data) / (1024 * 1024)
                if size_mb > self.prefs["max_image_size"]:
                    log.info(f"Image too large ({size_mb:.1f} MB), skipping.")
                    return
                item_hash = hashlib.sha256(data).hexdigest()
                if item_hash == self._last_hash:
                    return
                self._last_hash = item_hash
                img_path, thumb_path = save_image(data)
                add_item(self.conn, self.prefs, "image", img_path, thumb_path, item_hash)
                return

        if has_text:
            text = read_clipboard_text()
            if not text:
                return
            if self.prefs["trim_whitespace"]:
                text = text.strip()
            if not text:
                return
            item_hash = hashlib.sha256(text.encode()).hexdigest()
            if item_hash == self._last_hash:
                return
            self._last_hash = item_hash
            preview = text[:200].replace("\n", " ")
            add_item(self.conn, self.prefs, "text", text, preview, item_hash)

    def run_watch(self):
        """Use wl-paste --watch for event-driven updates."""
        log.info("Starting wl-paste --watch loop…")
        try:
            proc = subprocess.Popen(
                ["wl-paste", "--watch", "echo", "CLIP_CHANGED"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            for line in proc.stdout:
                if self._stop.is_set():
                    proc.terminate()
                    break
                if b"CLIP_CHANGED" in line:
                    time.sleep(0.05)   # tiny settle delay
                    try:
                        self._process_clipboard()
                    except Exception as e:
                        log.error(f"Error processing clipboard: {e}")
        except FileNotFoundError:
            log.warning("wl-paste not found — falling back to polling.")
            self.run_poll()

    def run_poll(self):
        """Fallback: poll every 500 ms."""
        log.info("Starting polling loop (500 ms)…")
        while not self._stop.is_set():
            try:
                self._process_clipboard()
            except Exception as e:
                log.error(f"Poll error: {e}")
            self._stop.wait(0.5)

    def stop(self):
        self._stop.set()

# ─── IPC Server (Unix socket) ─────────────────────────────────────────────────

class IPCServer:
    """
    Simple line-delimited JSON protocol over a Unix domain socket.
    GUI sends commands; daemon replies with JSON.

    Commands:
      {"cmd": "ping"}
      {"cmd": "get_history", "limit": 50, "offset": 0, "query": ""}
      {"cmd": "copy",    "id": <int>}
      {"cmd": "delete",  "id": <int>}
      {"cmd": "pin",     "id": <int>}
      {"cmd": "clear",   "keep_pinned": true}
      {"cmd": "get_prefs"}
      {"cmd": "set_prefs", "prefs": {...}}
      {"cmd": "stop"}
    """

    def __init__(self, conn: sqlite3.Connection, prefs_ref: list, stop_event: threading.Event):
        self.conn = conn
        self.prefs_ref = prefs_ref
        self.stop_event = stop_event

    def handle(self, data: str) -> dict:
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid JSON"}

        cmd = msg.get("cmd", "")

        if cmd == "ping":
            return {"ok": True, "pong": True}

        elif cmd == "get_history":
            limit  = msg.get("limit", 100)
            offset = msg.get("offset", 0)
            query  = msg.get("query", "").strip()

            if query:
                rows = self.conn.execute("""
                    SELECT id, type, content, preview, pinned, created_at
                    FROM history
                    WHERE (type = 'text' AND content LIKE ?)
                       OR (type = 'text' AND preview LIKE ?)
                    ORDER BY pinned DESC, created_at DESC
                    LIMIT ? OFFSET ?
                """, (f"%{query}%", f"%{query}%", limit, offset)).fetchall()
            else:
                rows = self.conn.execute("""
                    SELECT id, type, content, preview, pinned, created_at
                    FROM history
                    ORDER BY pinned DESC, created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset)).fetchall()

            items = [dict(r) for r in rows]
            return {"ok": True, "items": items}

        elif cmd == "copy":
            row = self.conn.execute(
                "SELECT type, content FROM history WHERE id = ?", (msg["id"],)
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not found"}
            if row["type"] == "text":
                try:
                    proc = subprocess.run(
                        ["wl-copy"], input=row["content"].encode(), timeout=3
                    )
                    return {"ok": proc.returncode == 0}
                except Exception as e:
                    return {"ok": False, "error": str(e)}
            else:
                try:
                    with open(row["content"], "rb") as f:
                        data = f.read()
                    proc = subprocess.run(
                        ["wl-copy", "--type", "image/png"],
                        input=data, timeout=5
                    )
                    return {"ok": proc.returncode == 0}
                except Exception as e:
                    return {"ok": False, "error": str(e)}

        elif cmd == "delete":
            delete_item(self.conn, msg["id"])
            return {"ok": True}

        elif cmd == "pin":
            new_state = toggle_pin(self.conn, msg["id"])
            return {"ok": True, "pinned": new_state}

        elif cmd == "clear":
            keep = msg.get("keep_pinned", True)
            clear_history(self.conn, keep_pinned=keep)
            return {"ok": True}

        elif cmd == "get_prefs":
            return {"ok": True, "prefs": self.prefs_ref[0]}

        elif cmd == "set_prefs":
            new_prefs = {**self.prefs_ref[0], **msg.get("prefs", {})}
            self.prefs_ref[0] = new_prefs
            save_prefs(new_prefs)
            return {"ok": True}

        elif cmd == "stop":
            log.info("Stop command received — shutting down.")
            self.stop_event.set()
            return {"ok": True}

        else:
            return {"ok": False, "error": f"unknown command: {cmd}"}

    def serve(self):
        # Clean up stale socket
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(SOCKET_PATH))
        srv.listen(5)
        srv.settimeout(1.0)
        log.info(f"IPC socket listening at {SOCKET_PATH}")

        while not self.stop_event.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            threading.Thread(target=self._client, args=(conn,), daemon=True).start()

        srv.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

    def _client(self, conn: socket.socket):
        try:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    response = self.handle(line.decode())
                    conn.sendall(json.dumps(response).encode() + b"\n")
                    break
        except Exception as e:
            log.debug(f"IPC client error: {e}")
        finally:
            conn.close()

# ─── Main ─────────────────────────────────────────────────────────────────────

def write_pid():
    PID_FILE.write_text(str(os.getpid()))


def already_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)   # signal 0 = just check existence
        return True
    except (ProcessLookupError, ValueError):
        return False


def main():
    if already_running():
        print("clipd is already running.", file=sys.stderr)
        sys.exit(1)

    write_pid()
    log.info(f"clipd starting (PID {os.getpid()})")

    prefs = load_prefs()
    prefs_ref = [prefs]   # mutable container so threads share live prefs
    conn = open_db()

    # Honour keep_history: if disabled, wipe unpinned items on each startup
    if not prefs.get("keep_history", True):
        log.info("keep_history=False — clearing unpinned history on startup.")
        clear_history(conn, keep_pinned=True)

    stop_event = threading.Event()

    def on_signal(sig, _):
        log.info(f"Signal {sig} received — stopping.")
        stop_event.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT,  on_signal)

    # Start IPC server thread
    ipc = IPCServer(conn, prefs_ref, stop_event)
    ipc_thread = threading.Thread(target=ipc.serve, daemon=True, name="ipc")
    ipc_thread.start()

    # Start clipboard watcher thread
    watcher = ClipboardWatcher(conn, prefs_ref)
    watch_thread = threading.Thread(target=watcher.run_watch, daemon=True, name="watcher")
    watch_thread.start()

    log.info("clipd ready.")

    # Block main thread until stop
    stop_event.wait()

    log.info("Shutting down…")
    watcher.stop()
    conn.close()
    if PID_FILE.exists():
        PID_FILE.unlink()
    log.info("clipd stopped.")


if __name__ == "__main__":
    main()