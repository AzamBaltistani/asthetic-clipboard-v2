"""
ipc_client.py — thin wrapper around the clipd Unix socket.
Used by the GUI to send commands and get responses.
"""

import json
import socket
from pathlib import Path

SOCKET_PATH = Path.home() / ".local" / "share" / "clipman" / "clipd.sock"


class ClipmanClient:
    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout

    def _send(self, msg: dict) -> dict:
        """Send one JSON message, return parsed response."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(str(SOCKET_PATH))
            sock.sendall(json.dumps(msg).encode() + b"\n")
            buf = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    line, _ = buf.split(b"\n", 1)
                    return json.loads(line.decode())
        except (ConnectionRefusedError, FileNotFoundError):
            return {"ok": False, "error": "daemon not running"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            sock.close()
        return {"ok": False, "error": "no response"}

    # ── Convenience methods ─────────────────────────────────────────────────

    def ping(self) -> bool:
        return self._send({"cmd": "ping"}).get("ok", False)

    def get_history(self, limit=100, offset=0, query="") -> list[dict]:
        r = self._send({"cmd": "get_history", "limit": limit,
                        "offset": offset, "query": query})
        return r.get("items", [])

    def copy(self, item_id: int) -> bool:
        return self._send({"cmd": "copy", "id": item_id}).get("ok", False)

    def delete(self, item_id: int) -> bool:
        return self._send({"cmd": "delete", "id": item_id}).get("ok", False)

    def pin(self, item_id: int) -> bool | None:
        r = self._send({"cmd": "pin", "id": item_id})
        if r.get("ok"):
            return r.get("pinned")
        return None

    def clear(self, keep_pinned=True) -> bool:
        return self._send({"cmd": "clear", "keep_pinned": keep_pinned}).get("ok", False)

    def get_prefs(self) -> dict:
        r = self._send({"cmd": "get_prefs"})
        return r.get("prefs", {})

    def set_prefs(self, prefs: dict) -> bool:
        return self._send({"cmd": "set_prefs", "prefs": prefs}).get("ok", False)

    def stop_daemon(self) -> bool:
        return self._send({"cmd": "stop"}).get("ok", False)

    def is_running(self) -> bool:
        return self.ping()