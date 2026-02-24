"""
clipui.py — Clipman GUI
GTK4 clipboard history viewer for Wayland/COSMIC (PopOS 24).

Launch with: python3 clipui.py
Bind to Super+V in COSMIC Settings → Keyboard → Custom Shortcuts.

If the daemon isn't running, this will offer to start it.
"""

import sys
import os
import threading
import subprocess
import time
from pathlib import Path

# Ensure ipc_client is importable
sys.path.insert(0, str(Path.home() / ".local" / "share" / "clipman"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango
except ImportError:
    print("PyGObject / GTK4 not found. Install with: sudo apt install python3-gi gir1.2-gtk-4.0")
    sys.exit(1)

try:
    from ipc_client import ClipmanClient
except ImportError:
    print("ipc_client.py not found — make sure clipd is installed.")
    sys.exit(1)

DAEMON_SCRIPT = Path.home() / ".local" / "share" / "clipman" / "clipd.py"
APP_ID = "io.github.clipman"

# ─── CSS ──────────────────────────────────────────────────────────────────────

CSS_STR = """
/* ── Root variables ── */
window {
    background-color: #0f0f11;
}

/* ── Main window ── */
.clipman-window {
    background-color: #0f0f11;
    color: #e8e6e3;
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
    font-size: 13px;
}

/* ── Header bar ── */
.clip-header {
    background-color: #0f0f11;
    border-bottom: 1px solid #1e1e24;
    padding: 10px 14px 8px 14px;
    min-height: 0;
}

.clip-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 3px;
    color: #5b5bd6;
    text-transform: uppercase;
}

.clip-subtitle {
    font-size: 10px;
    color: #4a4a5a;
    margin-top: 1px;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Search ── */
.search-row {
    padding: 8px 12px 6px 12px;
    background-color: #0f0f11;
    border-bottom: 1px solid #1a1a20;
}

.clip-search {
    background-color: #17171d;
    border: 1px solid #2a2a35;
    border-radius: 6px;
    color: #e8e6e3;
    padding: 6px 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    caret-color: #5b5bd6;
    min-height: 0;
}

.clip-search:focus {
    border-color: #5b5bd6;
    outline: none;
}

.clip-search placeholder {
    color: #3a3a4a;
}

/* ── Scrolled list ── */
.clip-scroll {
    background-color: #0f0f11;
}

.clip-list {
    background-color: transparent;
}

/* ── History row ── */
.clip-row {
    background-color: transparent;
    border-bottom: 1px solid #141418;
    padding: 0;
    min-height: 0;
    transition: background-color 80ms ease;
}

.clip-row:hover {
    background-color: #17171d;
}

.clip-row.pinned-row {
    border-left: 2px solid #5b5bd6;
}

.clip-row-inner {
    padding: 9px 12px;
    min-height: 0;
}

.clip-type-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 2px 5px;
    border-radius: 3px;
    background-color: #1e1e28;
    color: #5b5bd6;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}

.clip-type-badge.image-badge {
    color: #b35900;
    background-color: #1f1710;
}

.clip-type-badge.pinned-badge {
    color: #2da44e;
    background-color: #0d1f13;
}

.clip-preview {
    font-size: 12px;
    color: #c4c2bf;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}

.clip-preview.image-preview {
    color: #5a5a6a;
    font-style: italic;
}

.clip-time {
    font-size: 9px;
    color: #32323f;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}

/* ── Action buttons on row ── */
.row-btn {
    background-color: transparent;
    border: none;
    border-radius: 4px;
    padding: 3px 5px;
    min-height: 0;
    min-width: 0;
    font-size: 13px;
    color: #38384a;
    transition: all 80ms ease;
}

.row-btn:hover {
    background-color: #22222c;
    color: #c4c2bf;
}

.row-btn.pin-active {
    color: #5b5bd6;
}

.row-btn.danger:hover {
    background-color: #2a1515;
    color: #e05454;
}

/* ── Footer toolbar ── */
.clip-footer {
    background-color: #0c0c0e;
    border-top: 1px solid #1a1a20;
    padding: 7px 12px;
    min-height: 0;
}

.footer-btn {
    background-color: transparent;
    border: 1px solid #22222c;
    border-radius: 5px;
    color: #5a5a72;
    padding: 4px 10px;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
    transition: all 100ms ease;
}

.footer-btn:hover {
    background-color: #17171d;
    border-color: #3a3a4a;
    color: #c4c2bf;
}

.footer-btn.danger-btn:hover {
    border-color: #5a1f1f;
    color: #e05454;
    background-color: #1a0d0d;
}

.footer-btn.stop-btn:hover {
    border-color: #5a3a1f;
    color: #d4823a;
    background-color: #1a1208;
}

/* ── Count label ── */
.clip-count {
    font-size: 10px;
    color: #2a2a38;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Empty state ── */
.empty-label {
    color: #2a2a3a;
    font-size: 13px;
    font-family: 'JetBrains Mono', monospace;
    padding: 40px 20px;
}

.empty-sub {
    color: #1e1e28;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
    margin-top: 6px;
}

/* ── No-daemon banner ── */
.daemon-banner {
    background-color: #1a0d0d;
    border-bottom: 1px solid #5a1f1f;
    padding: 8px 14px;
}

.daemon-banner-label {
    color: #e05454;
    font-size: 11px;
    font-family: 'JetBrains Mono', monospace;
}

.banner-start-btn {
    background-color: #2a1010;
    border: 1px solid #5a2020;
    border-radius: 4px;
    color: #e05454;
    font-size: 11px;
    padding: 3px 10px;
    font-family: 'JetBrains Mono', monospace;
    min-height: 0;
}

.banner-start-btn:hover {
    background-color: #3a1515;
}

/* ── Preferences popover ── */
.prefs-popover {
    background-color: #13131a;
    border: 1px solid #22222c;
    border-radius: 8px;
    padding: 4px 0;
}

.prefs-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #38384a;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    padding: 10px 14px 6px 14px;
}

.prefs-row {
    padding: 6px 14px;
    min-height: 0;
}

.prefs-label {
    font-size: 12px;
    color: #8a8a9a;
    font-family: 'JetBrains Mono', monospace;
}

.prefs-switch {
    min-height: 0;
}

.prefs-spinner {
    background-color: #1e1e28;
    border: 1px solid #2a2a38;
    border-radius: 4px;
    color: #e8e6e3;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    min-width: 60px;
    min-height: 0;
}

.prefs-sep {
    background-color: #1e1e26;
    min-height: 1px;
    margin: 4px 10px;
}

/* ── Thumbnail ── */
.thumb-image {
    border-radius: 3px;
    border: 1px solid #2a2a35;
}

/* ── Scrollbar ── */
scrollbar {
    background-color: transparent;
    min-width: 6px;
}

scrollbar slider {
    background-color: #22222c;
    border-radius: 3px;
    min-width: 4px;
    min-height: 20px;
}

scrollbar slider:hover {
    background-color: #2e2e3e;
}
"""

CSS = CSS_STR.encode()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def relative_time(ts: int) -> str:
    diff = int(time.time()) - ts
    if diff < 5:     return "just now"
    if diff < 60:    return f"{diff}s ago"
    if diff < 3600:  return f"{diff//60}m ago"
    if diff < 86400: return f"{diff//3600}h ago"
    return f"{diff//86400}d ago"


def truncate(text: str, n=80) -> str:
    text = text.replace("\n", "↵ ").replace("\t", "→")
    return text[:n] + "…" if len(text) > n else text


def start_daemon():
    subprocess.Popen(
        ["python3", str(DAEMON_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ─── Row widget ───────────────────────────────────────────────────────────────

class ClipRow(Gtk.ListBoxRow):
    def __init__(self, item: dict, on_copy, on_pin, on_delete):
        super().__init__()
        self.item = item
        self.on_copy = on_copy
        self.on_pin = on_pin
        self.on_delete = on_delete

        self.add_css_class("clip-row")
        if item["pinned"]:
            self.add_css_class("pinned-row")

        self._build()

    def _build(self):
        item = self.item
        is_image = item["type"] == "image"
        is_pinned = bool(item["pinned"])

        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        outer.add_css_class("clip-row-inner")

        # Left: type badge + preview
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.CENTER)

        # Top row: badges + time
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        if is_pinned:
            pin_badge = Gtk.Label(label="● pinned")
            pin_badge.add_css_class("clip-type-badge")
            pin_badge.add_css_class("pinned-badge")
            top_row.append(pin_badge)

        type_badge = Gtk.Label(label="img" if is_image else "txt")
        type_badge.add_css_class("clip-type-badge")
        if is_image:
            type_badge.add_css_class("image-badge")
        top_row.append(type_badge)

        time_label = Gtk.Label(label=relative_time(item["created_at"]))
        time_label.add_css_class("clip-time")
        time_label.set_hexpand(True)
        time_label.set_halign(Gtk.Align.END)
        top_row.append(time_label)

        left.append(top_row)

        # Preview row (thumbnail for image, text for text)
        if is_image:
            preview_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            preview_row.set_valign(Gtk.Align.CENTER)

            thumb_path = item.get("preview") or item.get("content")
            if thumb_path and Path(thumb_path).exists():
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        thumb_path, 48, 48, True
                    )
                    img_widget = Gtk.Picture.new_for_pixbuf(pixbuf)
                    img_widget.set_size_request(48, 48)
                    img_widget.add_css_class("thumb-image")
                    img_widget.set_content_fit(Gtk.ContentFit.CONTAIN)
                    preview_row.append(img_widget)
                except Exception:
                    pass

            lbl = Gtk.Label(label="image — click to copy")
            lbl.add_css_class("clip-preview")
            lbl.add_css_class("image-preview")
            lbl.set_halign(Gtk.Align.START)
            preview_row.append(lbl)
            left.append(preview_row)
        else:
            preview = truncate(item.get("preview") or item.get("content", ""), 90)
            lbl = Gtk.Label(label=preview)
            lbl.add_css_class("clip-preview")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_max_width_chars(80)
            lbl.set_xalign(0)
            left.append(lbl)

        outer.append(left)

        # Right: action buttons (shown on hover via CSS opacity trick)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        actions.set_valign(Gtk.Align.CENTER)
        actions.set_margin_start(8)

        copy_btn = Gtk.Button(label="⎘")
        copy_btn.set_tooltip_text("Copy to clipboard")
        copy_btn.add_css_class("row-btn")
        copy_btn.connect("clicked", lambda _: on_copy(item["id"]))
        actions.append(copy_btn)

        self._pin_btn = Gtk.Button(label="◆" if is_pinned else "◇")
        self._pin_btn.set_tooltip_text("Unpin" if is_pinned else "Pin")
        self._pin_btn.add_css_class("row-btn")
        if is_pinned:
            self._pin_btn.add_css_class("pin-active")
        self._pin_btn.connect("clicked", lambda _: on_pin(item["id"], self))
        actions.append(self._pin_btn)

        del_btn = Gtk.Button(label="✕")
        del_btn.set_tooltip_text("Delete")
        del_btn.add_css_class("row-btn")
        del_btn.add_css_class("danger")
        del_btn.connect("clicked", lambda _: on_delete(item["id"], self))
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
    def __init__(self, client: ClipmanClient, on_prefs_changed):
        super().__init__()
        self.client = client
        self.on_prefs_changed = on_prefs_changed
        self.add_css_class("prefs-popover")
        self.set_has_arrow(False)
        self._build()

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_size_request(220, -1)

        title = Gtk.Label(label="PREFERENCES")
        title.add_css_class("prefs-title")
        title.set_halign(Gtk.Align.START)
        box.append(title)

        sep = Gtk.Separator()
        sep.add_css_class("prefs-sep")
        box.append(sep)

        prefs = self.client.get_prefs()

        # Dark mode
        self._add_toggle(box, "Dark mode", "dark_mode", prefs)

        # Store images
        self._add_toggle(box, "Store images", "store_images", prefs)

        # Deduplication
        self._add_toggle(box, "Deduplicate", "deduplicate", prefs)

        # Trim whitespace
        self._add_toggle(box, "Trim whitespace", "trim_whitespace", prefs)

        sep2 = Gtk.Separator()
        sep2.add_css_class("prefs-sep")
        box.append(sep2)

        # Font size
        self._add_spinner(box, "Font size", "font_size", prefs, 8, 24)

        # Max history
        self._add_spinner(box, "Max history", "max_history", prefs, 20, 2000)

        self.set_child(box)

    def _add_toggle(self, box, label_text, key, prefs):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("prefs-row")

        lbl = Gtk.Label(label=label_text)
        lbl.add_css_class("prefs-label")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        row.append(lbl)

        sw = Gtk.Switch()
        sw.add_css_class("prefs-switch")
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

        adj = Gtk.Adjustment(value=prefs.get(key, lo), lower=lo, upper=hi,
                             step_increment=1, page_increment=10)
        spin = Gtk.SpinButton(adjustment=adj, climb_rate=1, digits=0)
        spin.add_css_class("prefs-spinner")
        spin.set_valign(Gtk.Align.CENTER)
        spin.connect("value-changed", lambda s, k=key: self._on_spin(k, int(s.get_value())))
        row.append(spin)

        box.append(row)

    def _on_toggle(self, key, state):
        self.client.set_prefs({key: state})
        self.on_prefs_changed()

    def _on_spin(self, key, value):
        self.client.set_prefs({key: value})
        self.on_prefs_changed()


# ─── Main window ──────────────────────────────────────────────────────────────

class ClipmanWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.client = ClipmanClient()
        self._items = []
        self._search_query = ""
        self._daemon_ok = False

        self.set_title("Clipman")
        self.set_default_size(480, 580)
        self.set_resizable(True)
        self.add_css_class("clipman-window")

        # Close on focus loss (like a real launcher)
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("leave", self._on_focus_leave)
        self.add_controller(focus_ctrl)

        # Escape to close
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.connect("key-pressed", self._on_key)
        self.add_controller(key_ctrl)

        self._build_ui()
        self._check_daemon()
        self._load_history()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ── Header ──
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.add_css_class("clip-header")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        title_box.set_hexpand(True)

        title = Gtk.Label(label="CLIPMAN")
        title.add_css_class("clip-title")
        title.set_halign(Gtk.Align.START)
        title_box.append(title)

        self._subtitle = Gtk.Label(label="clipboard history")
        self._subtitle.add_css_class("clip-subtitle")
        self._subtitle.set_halign(Gtk.Align.START)
        title_box.append(self._subtitle)

        header.append(title_box)

        # Prefs button
        prefs_btn = Gtk.MenuButton()
        prefs_btn.set_label("⚙")
        prefs_btn.add_css_class("row-btn")
        prefs_btn.set_valign(Gtk.Align.CENTER)
        prefs_btn.set_tooltip_text("Preferences")

        self._prefs_popover = PrefsPopover(self.client, self._load_history)
        prefs_btn.set_popover(self._prefs_popover)
        header.append(prefs_btn)

        root.append(header)

        # ── Daemon warning banner (hidden initially) ──
        self._banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._banner.add_css_class("daemon-banner")
        self._banner.set_visible(False)

        banner_lbl = Gtk.Label(label="⚠ daemon not running")
        banner_lbl.add_css_class("daemon-banner-label")
        banner_lbl.set_hexpand(True)
        banner_lbl.set_halign(Gtk.Align.START)
        self._banner.append(banner_lbl)

        start_btn = Gtk.Button(label="start")
        start_btn.add_css_class("banner-start-btn")
        start_btn.connect("clicked", self._on_start_daemon)
        self._banner.append(start_btn)

        root.append(self._banner)

        # ── Search ──
        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_row.add_css_class("search-row")

        self._search = Gtk.SearchEntry()
        self._search.add_css_class("clip-search")
        self._search.set_placeholder_text("/ search history…")
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_search_changed)
        self._search.connect("activate", self._on_search_enter)
        search_row.append(self._search)

        root.append(search_row)

        # ── History list ──
        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("clip-scroll")
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("clip-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.connect("row-activated", self._on_row_activated)

        scroll.set_child(self._listbox)
        root.append(scroll)

        # ── Footer ──
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.add_css_class("clip-footer")

        self._count_label = Gtk.Label(label="0 items")
        self._count_label.add_css_class("clip-count")
        self._count_label.set_hexpand(True)
        self._count_label.set_halign(Gtk.Align.START)
        footer.append(self._count_label)

        clear_btn = Gtk.Button(label="clear")
        clear_btn.add_css_class("footer-btn")
        clear_btn.add_css_class("danger-btn")
        clear_btn.set_tooltip_text("Clear history (keeps pinned)")
        clear_btn.connect("clicked", self._on_clear)
        footer.append(clear_btn)

        stop_btn = Gtk.Button(label="stop daemon")
        stop_btn.add_css_class("footer-btn")
        stop_btn.add_css_class("stop-btn")
        stop_btn.set_tooltip_text("Kill the background daemon")
        stop_btn.connect("clicked", self._on_stop)
        footer.append(stop_btn)

        root.append(footer)

        self.set_child(root)

    # ── Daemon management ──────────────────────────────────────────────────

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
        return False   # don't repeat

    # ── History loading ────────────────────────────────────────────────────

    def _load_history(self, query=""):
        # Clear existing rows
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
        self._items = items

        n = len(items)
        self._count_label.set_label(f"{n} item{'s' if n != 1 else ''}")
        self._subtitle.set_label(f"{n} item{'s' if n != 1 else ''} in history")

        if not items:
            self._show_empty(
                "no clips yet" if not query else "nothing found",
                "copy something to get started" if not query else f"no results for '{query}'"
            )
            return

        for item in items:
            row = ClipRow(
                item,
                on_copy=self._on_copy,
                on_pin=self._on_pin,
                on_delete=self._on_delete,
            )
            self._listbox.append(row)

    def _show_empty(self, line1, line2):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)

        lbl = Gtk.Label(label=line1)
        lbl.add_css_class("empty-label")
        box.append(lbl)

        sub = Gtk.Label(label=line2)
        sub.add_css_class("empty-sub")
        box.append(sub)

        wrapper = Gtk.ListBoxRow()
        wrapper.set_child(box)
        wrapper.set_activatable(False)
        wrapper.set_selectable(False)
        self._listbox.append(wrapper)

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_copy(self, item_id: int):
        def do():
            self.client.copy(item_id)
        threading.Thread(target=do, daemon=True).start()
        self.close()

    def _on_pin(self, item_id: int, row: ClipRow):
        def do():
            new_state = self.client.pin(item_id)
            GLib.idle_add(row.update_pin_state, bool(new_state))
        threading.Thread(target=do, daemon=True).start()

    def _on_delete(self, item_id: int, row: ClipRow):
        self.client.delete(item_id)
        self._listbox.remove(row)
        remaining = self._listbox.get_row_at_index(0)
        count = sum(1 for _ in self._iter_rows())
        self._count_label.set_label(f"{count} item{'s' if count != 1 else ''}")
        if remaining is None or count == 0:
            self._show_empty("no clips yet", "copy something to get started")

    def _iter_rows(self):
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

    def _on_clear(self, _):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Clear history?")
        dialog.set_detail("Pinned items will be kept. This cannot be undone.")
        dialog.set_buttons(["Cancel", "Clear"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self, None, self._on_clear_response)

    def _on_clear_response(self, dialog, result):
        try:
            idx = dialog.choose_finish(result)
            if idx == 1:
                self.client.clear(keep_pinned=True)
                self._load_history(self._search_query)
        except Exception:
            pass

    def _on_stop(self, _):
        dialog = Gtk.AlertDialog()
        dialog.set_message("Stop daemon?")
        dialog.set_detail("Clipboard history will stop being recorded until you start it again.")
        dialog.set_buttons(["Cancel", "Stop"])
        dialog.set_default_button(0)
        dialog.set_cancel_button(0)
        dialog.choose(self, None, self._on_stop_response)

    def _on_stop_response(self, dialog, result):
        try:
            idx = dialog.choose_finish(result)
            if idx == 1:
                self.client.stop_daemon()
                self._daemon_ok = False
                self._banner.set_visible(True)
                self._load_history()
        except Exception:
            pass

    # ── Search ────────────────────────────────────────────────────────────

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text().strip()
        # Debounce: use GLib timer
        if hasattr(self, "_search_timer"):
            GLib.source_remove(self._search_timer)
        self._search_timer = GLib.timeout_add(200, self._do_search)

    def _do_search(self):
        self._load_history(self._search_query)
        return False

    def _on_search_enter(self, _):
        # Copy top result on Enter
        row = self._listbox.get_row_at_index(0)
        if isinstance(row, ClipRow):
            self._on_copy(row.item["id"])

    # ── Window events ─────────────────────────────────────────────────────

    def _on_focus_leave(self, ctrl):
        # Close when window loses focus (like a launcher)
        self.close()

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def present_focused(self):
        self.present()
        # Focus search box immediately
        GLib.idle_add(self._search.grab_focus)


# ─── Application ──────────────────────────────────────────────────────────────

class ClipmanApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = ClipmanWindow(self)
        self.window.present_focused()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self._load_css()

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def main():
    app = ClipmanApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()