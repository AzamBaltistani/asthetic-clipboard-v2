"""
clipui.py — Aesthetic Clipboard v2
GTK4 clipboard history viewer for Wayland/COSMIC (PopOS 24).

Bind to Super+V in COSMIC Settings → Keyboard → Custom Shortcuts:
  /usr/bin/python3 ~/.local/share/clipman/clipui.py
"""

import sys
import os
import shutil
import threading
import subprocess
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / ".local" / "share" / "clipman"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
except ImportError:
    print("PyGObject / GTK4 not found.")
    print("Run with system Python: /usr/bin/python3 ~/.local/share/clipman/clipui.py")
    print("Or install: sudo apt install python3-gi gir1.2-gtk-4.0")
    sys.exit(1)

try:
    from ipc_client import ClipmanClient
except ImportError:
    print("ipc_client.py not found — make sure clipd is installed.")
    sys.exit(1)

DAEMON_SCRIPT = Path.home() / ".local" / "share" / "clipman" / "clipd.py"
DOWNLOADS_DIR = Path.home() / "Downloads"
APP_ID        = "io.github.aesthetic-clipboard"

# ─── Themes ───────────────────────────────────────────────────────────────────

DARK = {
    "bg":          "#0f0f11",
    "bg2":         "#0c0c0e",
    "bg3":         "#17171d",
    "bg4":         "#1e1e28",
    "border":      "#1e1e24",
    "border2":     "#2a2a35",
    "text":        "#e8e6e3",
    "text2":       "#c4c2bf",
    "muted":       "#4a4a5a",
    "faint":       "#38384a",
    "accent":      "#5b5bd6",
    "green":       "#2da44e",
    "green_bg":    "#0d1f13",
    "red":         "#e05454",
    "red_bg":      "#2a1515",
    "orange":      "#d4823a",
    "orange_bg":   "#1a1208",
    "row_hover":   "#17171d",
    "pin_border":  "#5b5bd6",
}

LIGHT = {
    "bg":          "#f5f5f7",
    "bg2":         "#eaeaec",
    "bg3":         "#ffffff",
    "bg4":         "#e0e0e8",
    "border":      "#d0d0d8",
    "border2":     "#b8b8c8",
    "text":        "#18182a",
    "text2":       "#38385a",
    "muted":       "#6868a0",
    "faint":       "#9898b8",
    "accent":      "#4040c0",
    "green":       "#1a6e38",
    "green_bg":    "#e0f5e8",
    "red":         "#b01818",
    "red_bg":      "#fde8e8",
    "orange":      "#a04800",
    "orange_bg":   "#fdeee0",
    "row_hover":   "#ebebf3",
    "pin_border":  "#4040c0",
}


def make_css(t: dict) -> bytes:
    return f"""
window {{
    background-color: {t['bg']};
}}
.ac-window {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
}}

/* ── Banner ── */
.daemon-banner {{
    background-color: {t['red_bg']};
    border-bottom: 1px solid {t['red']};
    padding: 7px 12px;
}}
.daemon-banner-label {{
    color: {t['red']};
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
}}
.banner-start-btn {{
    background-color: transparent;
    border: 1px solid {t['red']};
    border-radius: 4px;
    color: {t['red']};
    font-size: 11px;
    padding: 2px 9px;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}}
.banner-start-btn:hover {{
    background-color: {t['red_bg']};
}}

/* ── List ── */
.ac-scroll, .ac-list {{
    background-color: {t['bg']};
}}

/* ── Row ── */
.ac-row {{
    background-color: transparent;
    border-bottom: 1px solid {t['border']};
    padding: 0;
    min-height: 0;
}}
.ac-row:hover {{
    background-color: {t['row_hover']};
}}
.ac-row.pinned-row {{
    border-left: 2px solid {t['pin_border']};
}}
.ac-row-inner {{
    padding: 8px 12px;
    min-height: 0;
}}

/* ── Row text ── */
.ac-preview {{
    font-size: 12px;
    color: {t['text2']};
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}}
.ac-preview.image-preview {{
    color: {t['muted']};
    font-style: italic;
}}
.ac-meta {{
    font-size: 10px;
    color: {t['faint']};
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}}

/* ── Row buttons ── */
.row-btn {{
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 3px 5px;
    min-height: 0;
    min-width: 0;
    font-size: 13px;
    color: {t['muted']};
}}
.row-btn:hover {{
    background-color: {t['bg4']};
    color: {t['text']};
}}
.row-btn.pin-active {{
    color: {t['accent']};
}}
.row-btn.danger:hover {{
    background-color: {t['red_bg']};
    color: {t['red']};
}}
.row-btn.save-btn:hover {{
    background-color: {t['green_bg']};
    color: {t['green']};
}}

/* ── Thumbnail ── */
.thumb-image {{
    border-radius: 3px;
    border: 1px solid {t['border2']};
}}

/* ── Footer ── */
.ac-footer {{
    background-color: {t['bg2']};
    border-top: 1px solid {t['border']};
    padding: 3px 8px;
    min-height: 0;
}}

/* tighter search box height */
.ac-search {{
    background-color: {t['bg3']};
    border: 1px solid {t['border2']};
    border-radius: 5px;
    color: {t['text']};
    padding: 0px 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    caret-color: {t['accent']};
    min-height: 0;
    -gtk-icon-size: 14px;
}}
.ac-search:focus {{
    border-color: {t['accent']};
}}
.ac-search placeholder {{
    color: {t['muted']};
}}

/* prefs button — no arrow, just the gear icon */
.prefs-btn {{
    background-color: transparent;
    border: 1px solid {t['border2']};
    border-radius: 5px;
    color: {t['muted']};
    padding: 0px 8px;
    font-size: 14px;
    min-height: 0;
    min-width: 0;
}}
.prefs-btn:hover {{
    background-color: {t['bg4']};
    color: {t['text']};
}}

/* ── Preferences popover ── */
.prefs-popover contents {{
    background-color: {t['bg2']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 2px 0;
}}
.prefs-section-title {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {t['muted']};
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    padding: 10px 14px 4px 14px;
}}
.prefs-row {{
    padding: 5px 14px;
    min-height: 0;
    background-color: transparent;
}}
.prefs-label {{
    font-size: 12px;
    color: {t['text2']};
    font-family: 'JetBrains Mono', monospace;
}}
.prefs-sep {{
    background-color: {t['border']};
    min-height: 1px;
    margin: 4px 10px;
}}
.prefs-spinner {{
    background-color: {t['bg3']};
    border: 1px solid {t['border2']};
    border-radius: 4px;
    color: {t['text']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    min-width: 64px;
    min-height: 0;
}}
.danger-item {{
    color: {t['red']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 5px 14px;
    border-radius: 0;
}}
.danger-item:hover {{
    background-color: {t['red_bg']};
}}
.stop-item {{
    color: {t['orange']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 5px 14px;
    border-radius: 0;
}}
.stop-item:hover {{
    background-color: {t['orange_bg']};
}}

/* ── Empty state ── */
.empty-label {{
    color: {t['muted']};
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
    padding: 40px 20px;
}}
.empty-sub {{
    color: {t['faint']};
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 4px;
}}

/* ── Scrollbar ── */
scrollbar {{
    background-color: transparent;
    min-width: 5px;
}}
scrollbar slider {{
    background-color: {t['border2']};
    border-radius: 3px;
    min-width: 4px;
    min-height: 20px;
}}
scrollbar slider:hover {{
    background-color: {t['muted']};
}}

/* AlertDialog — force dark text in light theme */
messagedialog .message-dialog-body label,
messagedialog label,
dialog label,
.dialog-body label,
alertdialog label {{
    color: {t['text']};
}}
""".encode()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def relative_time(ts: int) -> str:
    diff = int(time.time()) - ts
    if diff < 5:     return "just now"
    if diff < 60:    return f"{diff}s ago"
    if diff < 3600:  return f"{diff // 60}m ago"
    if diff < 86400: return f"{diff // 3600}h ago"
    return f"{diff // 86400}d ago"


def truncate(text: str, n=90) -> str:
    text = text.replace("\n", "↵ ").replace("\t", "→")
    return text[:n] + "…" if len(text) > n else text


def start_daemon():
    subprocess.Popen(
        ["python3", str(DAEMON_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def save_image_to_downloads(src_path: str) -> str | None:
    src = Path(src_path)
    if not src.exists():
        return None
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest  = DOWNLOADS_DIR / f"clipboard_{stamp}.png"
    shutil.copy2(src, dest)
    return str(dest)


# ─── CSS provider ─────────────────────────────────────────────────────────────

_css_provider: Gtk.CssProvider | None = None


def apply_css(dark: bool):
    global _css_provider
    t = DARK if dark else LIGHT
    if _css_provider is None:
        _css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            _css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
    _css_provider.load_from_data(make_css(t))


# ─── Row widget ───────────────────────────────────────────────────────────────

class ClipRow(Gtk.ListBoxRow):
    def __init__(self, item: dict, on_copy, on_pin, on_delete, on_save):
        super().__init__()
        self.item       = item
        self._on_copy   = on_copy
        self._on_pin    = on_pin
        self._on_delete = on_delete
        self._on_save   = on_save

        self.add_css_class("ac-row")
        if item["pinned"]:
            self.add_css_class("pinned-row")

        self._build()

    def _build(self):
        item      = self.item
        is_image  = item["type"] == "image"
        is_pinned = bool(item["pinned"])

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.add_css_class("ac-row-inner")

        # ── Left: preview + meta ──
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.CENTER)

        if is_image:
            preview_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            preview_row.set_valign(Gtk.Align.CENTER)

            thumb_path = item.get("preview") or item.get("content")
            if thumb_path and Path(thumb_path).exists():
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        thumb_path, 48, 48, True
                    )
                    img_w = Gtk.Picture()
                    img_w.set_pixbuf(pixbuf)
                    img_w.set_size_request(48, 48)
                    img_w.add_css_class("thumb-image")
                    img_w.set_content_fit(Gtk.ContentFit.CONTAIN)
                    preview_row.append(img_w)
                except Exception:
                    pass

            lbl = Gtk.Label(label="image")
            lbl.add_css_class("ac-preview")
            lbl.add_css_class("image-preview")
            lbl.set_halign(Gtk.Align.START)
            preview_row.append(lbl)
            left.append(preview_row)
        else:
            preview = truncate(item.get("preview") or item.get("content", ""))
            lbl = Gtk.Label(label=preview)
            lbl.add_css_class("ac-preview")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(85)
            lbl.set_xalign(0)
            left.append(lbl)

        # Meta line: "7m ago · img · pinned"
        meta_parts = [relative_time(item["created_at"])]
        if is_image:
            meta_parts.append("img")
        if is_pinned:
            meta_parts.append("pinned")
        meta_lbl = Gtk.Label(label=" · ".join(meta_parts))
        meta_lbl.add_css_class("ac-meta")
        meta_lbl.set_halign(Gtk.Align.START)
        left.append(meta_lbl)

        outer.append(left)

        # ── Right: action buttons ──
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
        actions.set_valign(Gtk.Align.CENTER)
        actions.set_margin_start(8)

        self._pin_btn = Gtk.Button(label="◆" if is_pinned else "◇")
        self._pin_btn.set_tooltip_text("Unpin" if is_pinned else "Pin")
        self._pin_btn.add_css_class("row-btn")
        if is_pinned:
            self._pin_btn.add_css_class("pin-active")
        self._pin_btn.connect("clicked", lambda _: self._on_pin(item["id"], self))
        actions.append(self._pin_btn)

        if is_image:
            save_btn = Gtk.Button(label="↓")
            save_btn.set_tooltip_text("Save image to ~/Downloads")
            save_btn.add_css_class("row-btn")
            save_btn.add_css_class("save-btn")
            save_btn.connect("clicked", lambda _: self._on_save(item["content"], self))
            actions.append(save_btn)

        del_btn = Gtk.Button(label="✕")
        del_btn.set_tooltip_text("Delete")
        del_btn.add_css_class("row-btn")
        del_btn.add_css_class("danger")
        del_btn.connect("clicked", lambda _: self._on_delete(item["id"], self))
        actions.append(del_btn)

        outer.append(actions)
        self.set_child(outer)

    def update_pin_state(self, pinned: bool):
        self.item["pinned"] = int(pinned)
        self._pin_btn.set_label("◆" if pinned else "◇")
        self._pin_btn.set_tooltip_text("Unpin" if pinned else "Pin")
        if pinned:
            self._pin_btn.add_css_class("pin-active")
            self.add_css_class("pinned-row")
        else:
            self._pin_btn.remove_css_class("pin-active")
            self.remove_css_class("pinned-row")


# ─── Preferences popover ──────────────────────────────────────────────────────

class PrefsPopover(Gtk.Popover):
    def __init__(self, client: ClipmanClient, on_prefs_changed, on_clear, on_stop):
        super().__init__()
        self.client           = client
        self.on_prefs_changed = on_prefs_changed
        self._on_clear        = on_clear
        self._on_stop         = on_stop
        self.add_css_class("prefs-popover")
        self.set_has_arrow(False)
        self._build()

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_size_request(240, -1)

        prefs = self.client.get_prefs()

        # ── Appearance ──
        self._section(box, "APPEARANCE")
        self._add_toggle(box, "Dark mode",             "dark_mode",       prefs)
        self._add_spinner(box, "Font size",            "font_size",       prefs, 8, 24)

        self._sep(box)

        # ── Behaviour ──
        self._section(box, "BEHAVIOUR")
        self._add_toggle(box, "Keep history on restart", "keep_history",    prefs)
        self._add_toggle(box, "Store images",            "store_images",    prefs)
        self._add_toggle(box, "Deduplicate",             "deduplicate",     prefs)
        self._add_toggle(box, "Trim whitespace",         "trim_whitespace", prefs)
        self._add_spinner(box, "Max history",            "max_history",     prefs, 20, 2000)

        self._sep(box)

        # ── Actions ──
        self._section(box, "ACTIONS")

        clear_btn = Gtk.Button(label="Clear history…")
        clear_btn.add_css_class("danger-item")
        clear_btn.set_has_frame(False)
        clear_btn.connect("clicked", lambda _: (self.popdown(), self._on_clear()))
        box.append(clear_btn)

        stop_btn = Gtk.Button(label="Stop daemon…")
        stop_btn.add_css_class("stop-item")
        stop_btn.set_has_frame(False)
        stop_btn.connect("clicked", lambda _: (self.popdown(), self._on_stop()))
        box.append(stop_btn)

        pad = Gtk.Box()
        pad.set_size_request(-1, 6)
        box.append(pad)

        self.set_child(box)

    def _section(self, box, label):
        lbl = Gtk.Label(label=label)
        lbl.add_css_class("prefs-section-title")
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

    def _sep(self, box):
        s = Gtk.Separator()
        s.add_css_class("prefs-sep")
        box.append(s)

    def _add_toggle(self, box, label_text, key, prefs):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("prefs-row")

        lbl = Gtk.Label(label=label_text)
        lbl.add_css_class("prefs-label")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        row.append(lbl)

        sw = Gtk.Switch()
        sw.set_active(bool(prefs.get(key, False)))
        sw.set_valign(Gtk.Align.CENTER)
        sw.connect("state-set", lambda s, state, k=key: self._on_toggle(k, state))
        row.append(sw)
        box.append(row)

    def _add_spinner(self, box, label_text, key, prefs, lo, hi):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("prefs-row")

        lbl = Gtk.Label(label=label_text)
        lbl.add_css_class("prefs-label")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        row.append(lbl)

        adj  = Gtk.Adjustment(value=prefs.get(key, lo), lower=lo, upper=hi,
                              step_increment=1, page_increment=10)
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        spin.add_css_class("prefs-spinner")
        spin.set_valign(Gtk.Align.CENTER)
        spin.connect("value-changed", lambda s, k=key: self._on_spin(k, int(s.get_value())))
        row.append(spin)
        box.append(row)

    def _on_toggle(self, key, state):
        self.client.set_prefs({key: state})
        self.on_prefs_changed(key, state)

    def _on_spin(self, key, value):
        self.client.set_prefs({key: value})
        self.on_prefs_changed(key, value)


# ─── Main window ──────────────────────────────────────────────────────────────

class AestheticClipboardWindow(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.client        = ClipmanClient()
        self._search_query = ""
        self._daemon_ok    = False
        self._dark_mode    = True

        self.set_title("Aesthetic Clipboard v2")
        self.set_default_size(360, 520)
        self.set_resizable(True)
        self.set_hide_on_close(True)   # hide instead of destroy on close
        self.add_css_class("ac-window")

        # track popover open state so focus-leave doesn't close
        # the window when the settings popover is open
        self._prefs_popover_open = False

        # Close on focus loss
        fc = Gtk.EventControllerFocus()
        fc.connect("leave", self._on_focus_leave)
        self.add_controller(fc)

        # Escape to close
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_key)
        self.add_controller(kc)

        self._build_ui()
        self._check_daemon()

        # Read prefs and apply correct theme before showing anything
        prefs = self.client.get_prefs()
        self._dark_mode = prefs.get("dark_mode", True)
        apply_css(self._dark_mode)

        self._load_history()
        self._start_toggle_server()

    # ── Toggle socket (single-instance) ───────────────────────────────────

    def _start_toggle_server(self):
        import socket as _socket
        TOGGLE_SOCK.unlink(missing_ok=True)
        srv = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        srv.bind(str(TOGGLE_SOCK))
        srv.listen(1)

        def _listen():
            while True:
                try:
                    conn, _ = srv.accept()
                    conn.recv(64)
                    conn.close()
                    GLib.idle_add(self.show_and_refresh)
                except Exception:
                    break

        t = threading.Thread(target=_listen, daemon=True)
        t.start()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ── Daemon warning banner ──
        self._banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._banner.add_css_class("daemon-banner")
        self._banner.set_visible(False)

        banner_lbl = Gtk.Label(label="⚠  daemon not running")
        banner_lbl.add_css_class("daemon-banner-label")
        banner_lbl.set_hexpand(True)
        banner_lbl.set_halign(Gtk.Align.START)
        self._banner.append(banner_lbl)

        start_btn = Gtk.Button(label="start")
        start_btn.add_css_class("banner-start-btn")
        start_btn.connect("clicked", self._on_start_daemon)
        self._banner.append(start_btn)

        root.append(self._banner)

        # ── History list ──
        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("ac-scroll")
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("ac-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)

        scroll.set_child(self._listbox)
        root.append(scroll)

        # ── Footer: search left, prefs right ──
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.add_css_class("ac-footer")

        self._search = Gtk.SearchEntry()
        self._search.add_css_class("ac-search")
        self._search.set_placeholder_text("search…")
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search_changed)
        self._search.connect("activate", self._on_search_enter)
        footer.append(self._search)

        #  3: Use a plain Button instead of MenuButton so no
        # dropdown arrow is rendered, and manually popup/popdown the
        # popover. This also lets us track open state for the focus fix.
        prefs_btn = Gtk.Button(label="⚙")
        prefs_btn.add_css_class("prefs-btn")
        prefs_btn.set_valign(Gtk.Align.CENTER)
        prefs_btn.set_tooltip_text("Preferences")

        self._prefs_popover = PrefsPopover(
            self.client,
            on_prefs_changed=self._on_pref_changed,
            on_clear=self._on_clear,
            on_stop=self._on_stop,
        )
        self._prefs_popover.set_parent(prefs_btn)

        # Track popover open/close so focus-leave doesn't hide the window
        self._prefs_popover.connect("closed", self._on_popover_closed)

        prefs_btn.connect("clicked", self._on_prefs_btn_clicked)
        footer.append(prefs_btn)

        root.append(footer)
        self.set_child(root)

    def _on_prefs_btn_clicked(self, btn):
        """Toggle the prefs popover open/closed."""
        if self._prefs_popover.is_visible():
            self._prefs_popover.popdown()
            self._prefs_popover_open = False
        else:
            self._prefs_popover_open = True
            self._prefs_popover.popup()

    def _on_popover_closed(self, popover):
        self._prefs_popover_open = False

    # ── Daemon ────────────────────────────────────────────────────────────

    def _check_daemon(self):
        self._daemon_ok = self.client.is_running()
        self._banner.set_visible(not self._daemon_ok)

    def _on_start_daemon(self, _):
        start_daemon()
        GLib.timeout_add(800, self._after_start_daemon)

    def _after_start_daemon(self):
        self._check_daemon()
        if self._daemon_ok:
            self._load_history()
        return False

    # ── History ───────────────────────────────────────────────────────────

    def _load_history(self, query=""):
        while True:
            row = self._listbox.get_row_at_index(0)
            if row is None:
                break
            self._listbox.remove(row)

        if not self._daemon_ok:
            self._check_daemon()
            if not self._daemon_ok:
                self._show_empty("daemon not running", "press 'start' above")
                return

        items = self.client.get_history(limit=200, query=query)

        if not items:
            msg = "no clips yet" if not query else "nothing found"
            sub = "copy something to get started" if not query else f"no results for '{query}'"
            self._show_empty(msg, sub)
            return

        for item in items:
            self._listbox.append(ClipRow(
                item,
                on_copy=self._on_copy,
                on_pin=self._on_pin,
                on_delete=self._on_delete,
                on_save=self._on_save_image,
            ))

    def _show_empty(self, line1, line2):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        l1 = Gtk.Label(label=line1)
        l1.add_css_class("empty-label")
        box.append(l1)

        l2 = Gtk.Label(label=line2)
        l2.add_css_class("empty-sub")
        box.append(l2)

        wrapper = Gtk.ListBoxRow()
        wrapper.set_child(box)
        wrapper.set_activatable(False)
        wrapper.set_selectable(False)
        self._listbox.append(wrapper)

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_copy(self, item_id: int):
        threading.Thread(target=lambda: self.client.copy(item_id), daemon=True).start()
        self.set_visible(False)

    def _on_pin(self, item_id: int, row: ClipRow):
        def do():
            new_state = self.client.pin(item_id)
            GLib.idle_add(row.update_pin_state, bool(new_state))
        threading.Thread(target=do, daemon=True).start()

    def _on_delete(self, item_id: int, row: ClipRow):
        self.client.delete(item_id)
        self._listbox.remove(row)
        if sum(1 for _ in self._iter_clip_rows()) == 0:
            self._show_empty("no clips yet", "copy something to get started")

    def _on_save_image(self, content_path: str, row: ClipRow):
        def do():
            dest = save_image_to_downloads(content_path)
            msg  = f"Saved → ~/Downloads/{Path(dest).name}" if dest else "Save failed"
            GLib.idle_add(self._toast, msg)
        threading.Thread(target=do, daemon=True).start()

    def _toast(self, msg: str):
        self.set_title(msg)
        GLib.timeout_add(2500, lambda: self.set_title("Aesthetic Clipboard v2") or False)

    def _iter_clip_rows(self):
        i = 0
        while True:
            row = self._listbox.get_row_at_index(i)
            if row is None:
                break
            if isinstance(row, ClipRow):
                yield row
            i += 1

    def _on_row_activated(self, listbox, row):
        if isinstance(row, ClipRow):
            self._on_copy(row.item["id"])

    def _on_clear(self):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Clear history?")
        dialog.set_detail("Pinned items will be kept. This cannot be undone.")
        dialog.set_buttons(["Cancel", "Clear"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self, None, self._on_clear_response)

    def _on_clear_response(self, dialog, result):
        try:
            if dialog.choose_finish(result) == 1:
                self.client.clear(keep_pinned=True)
                self._load_history(self._search_query)
        except Exception:
            pass

    def _on_stop(self):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Stop daemon?")
        dialog.set_detail("Clipboard history will stop being recorded.")
        dialog.set_buttons(["Cancel", "Stop"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self, None, self._on_stop_response)

    def _on_stop_response(self, dialog, result):
        try:
            if dialog.choose_finish(result) == 1:
                self.client.stop_daemon()
                self._daemon_ok = False
                self._banner.set_visible(True)
                self._load_history()
        except Exception:
            pass

    # ── Prefs callback ────────────────────────────────────────────────────

    def _on_pref_changed(self, key, value):
        if key == "dark_mode":
            self._dark_mode = bool(value)
            apply_css(self._dark_mode)

    # ── Search ────────────────────────────────────────────────────────────

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text().strip()
        if getattr(self, "_search_timer", None) is not None:
            GLib.source_remove(self._search_timer)
            self._search_timer = None
        self._search_timer = GLib.timeout_add(200, self._do_search)

    def _do_search(self):
        self._search_timer = None
        self._load_history(self._search_query)
        return False

    def _on_search_enter(self, _):
        row = self._listbox.get_row_at_index(0)
        if isinstance(row, ClipRow):
            self._on_copy(row.item["id"])

    # ── Window events ─────────────────────────────────────────────────────

    def _on_focus_leave(self, ctrl):
        # don't hide if the prefs popover is open — the popover
        # temporarily steals window focus, which would otherwise trigger
        # an unwanted hide. We also use a small idle delay so the popover
        # has time to report its new visibility state before we decide.
        def _maybe_hide():
            if not self._prefs_popover_open and not self._prefs_popover.is_visible():
                self.set_visible(False)
        GLib.idle_add(_maybe_hide)

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            # If prefs are open, close them first; second Escape hides window
            if self._prefs_popover.is_visible():
                self._prefs_popover.popdown()
            else:
                self.set_visible(False)
            return True
        return False

    def show_and_refresh(self):
        """Called each time Super+V is pressed. Reload history and show."""
        self._search.set_text("")
        self._search_query = ""
        self._check_daemon()
        self._load_history()
        prefs = self.client.get_prefs()
        if prefs.get("dark_mode", True) != self._dark_mode:
            self._dark_mode = prefs.get("dark_mode", True)
            apply_css(self._dark_mode)
        self.present()
        self._search.grab_focus()


# ─── Application ──────────────────────────────────────────────────────────────

TOGGLE_SOCK = Path.home() / ".local" / "share" / "clipman" / "clipui.sock"
UI_PID_FILE = Path.home() / ".local" / "share" / "clipman" / "clipui.pid"


def _signal_existing() -> bool:
    """
    Check PID file first (race-free), then try the socket.
    Returns True if a live instance was signalled.
    """
    import socket as _socket

    if UI_PID_FILE.exists():
        try:
            pid = int(UI_PID_FILE.read_text().strip())
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError, PermissionError):
            UI_PID_FILE.unlink(missing_ok=True)
            TOGGLE_SOCK.unlink(missing_ok=True)
            return False

        try:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(str(TOGGLE_SOCK))
            s.sendall(b"show")
            s.close()
            return True
        except Exception:
            pass

    return False


def main():
    import signal as _signal

    if _signal_existing():
        sys.exit(0)

    UI_PID_FILE.write_text(str(os.getpid()))

    win = AestheticClipboardWindow()
    win.present()

    loop = GLib.MainLoop()

    def on_quit(*_):
        TOGGLE_SOCK.unlink(missing_ok=True)
        UI_PID_FILE.unlink(missing_ok=True)
        loop.quit()

    _signal.signal(_signal.SIGTERM, on_quit)
    _signal.signal(_signal.SIGINT,  on_quit)

    loop.run()


if __name__ == "__main__":
    main()