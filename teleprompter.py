#!/usr/bin/env python3
"""
Raspberry Pi PDF Teleprompter
- Setup mode: build/reorder setlist from PDFs in a folder
- Performance mode: fullscreen dark mode viewer with scroll + next/prev chart
- AirTurn BT500: typically sends keyboard events (PageUp/PageDown/Arrows/Space/Enter)
"""

import os
import json
import time
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageEnhance, ImageTk, ImageDraw, ImageFont


APP_TITLE = "PDF Teleprompter"
DEFAULT_CHARTS_DIR = os.path.expanduser("~/teleprompterv2/charts")
DEFAULT_SETLIST_PATH = os.path.expanduser("~/teleprompterv2/setlist.json")

# Render quality: higher = sharper, slower. Pi 5 can do 2.0-2.5, Pi 3 maybe 1.6-2.0
RENDER_ZOOM = 2.0

# Dark mode tuning
DARK_INVERT = True
DARK_CONTRAST = 1.15
DARK_BRIGHTNESS = 0.85


@dataclass
class KeyMap:
    # Scroll within page image
    scroll_down: Tuple[str, ...] = ("Down", "Next", "space")  # Down Arrow, PageDown(Next), Space
    scroll_up: Tuple[str, ...] = ("Up", "Prior")              # Up Arrow, PageUp(Prior)

    # Chart navigation
    next_chart: Tuple[str, ...] = ("Right", "Return")         # Right Arrow, Enter
    prev_chart: Tuple[str, ...] = ("Left", "BackSpace")       # Left Arrow, Backspace

    # Page navigation within the same PDF (if multi-page PDFs)
    next_page: Tuple[str, ...] = ("bracketright",)            # ]
    prev_page: Tuple[str, ...] = ("bracketleft",)             # [

    # Utility
    quit_app: Tuple[str, ...] = ("Escape", "q")
    toggle_help: Tuple[str, ...] = ("h",)
    toggle_dark: Tuple[str, ...] = ("d",)

    # .cho controls (zoom and transpose)
    cho_zoom_in: Tuple[str, ...] = ("plus", "equal")  # + or =
    cho_zoom_out: Tuple[str, ...] = ("minus",)
    cho_zoom_reset: Tuple[str, ...] = ("0",)

    cho_transpose_up: Tuple[str, ...] = ("u",)
    cho_transpose_down: Tuple[str, ...] = ("j",)
    cho_transpose_reset: Tuple[str, ...] = ("r",)

    cho_toggle_edit: Tuple[str, ...] = ("e",)


def list_pdfs(charts_dir: str) -> List[str]:
    if not os.path.isdir(charts_dir):
        return []
    pdfs = [f for f in os.listdir(charts_dir) if f.lower().endswith(".pdf")]
    pdfs.sort(key=lambda s: s.lower())
    return [os.path.join(charts_dir, f) for f in pdfs]


def list_charts(charts_dir: str) -> List[str]:
    """Return a list of chart file paths found in `charts_dir`.

    Rules:
    - Prefer `.cho` over `.pdf` when both exist for the same base filename.
    - Only one entry is exposed per base filename (case-insensitive).
    """
    if not os.path.isdir(charts_dir):
        return []

    files = [f for f in os.listdir(charts_dir) if f.lower().endswith(".pdf") or f.lower().endswith(".cho")]

    mapping: dict = {}
    for f in files:
        base, ext = os.path.splitext(f)
        key = base.lower()
        # prefer .cho over .pdf
        if key not in mapping:
            mapping[key] = f
        else:
            # If currently mapped to .pdf and this is .cho, replace
            cur = mapping[key]
            if cur.lower().endswith('.pdf') and f.lower().endswith('.cho'):
                mapping[key] = f

    chosen = sorted(mapping.values(), key=lambda s: s.lower())
    return [os.path.join(charts_dir, f) for f in chosen]


def load_setlist(path: str) -> List[str]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        return []
    return []


def save_setlist(path: str, items: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def debug_log(obj: dict) -> None:
    """Append debug information to a persistent file in the project and also write a /tmp snapshot.
    This is guarded by TELEPROMPTER_DEBUG_RENDER to avoid noisy logs in production.
    """
    try:
        if not os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
            return
    except Exception:
        return

    try:
        # append to project-local log for easy inspection
        base = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(base, "tele_debug.log")
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, default=str) + "\n")
    except Exception:
        pass

    try:
        # keep compatibility with the temporary snapshot we used earlier
        tmp = "/tmp/tele_debug.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, default=str)
    except Exception:
        pass


def basename_no_ext(p: str) -> str:
    return os.path.splitext(os.path.basename(p))[0]


def launch_setup(charts_dir: str, setlist_path: str):
    root = tk.Tk()

    # Start maximized (Setup mode)
    try:
        root.state("zoomed")  # Windows + some Linux WMs
    except Exception:
        # Fallback: fill the screen
        try:
            w = root.winfo_screenwidth()
            h = root.winfo_screenheight()
            root.geometry(f"{w}x{h}+0+0")
        except Exception:
            pass

    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass

    SetupWindow(root, charts_dir=charts_dir, setlist_path=setlist_path)
    root.mainloop()


class SetupWindow(ttk.Frame):
    def __init__(self, master: tk.Tk, charts_dir: str, setlist_path: str):
        super().__init__(master, padding=10)
        self.master = master
        self.charts_dir = charts_dir
        self.setlist_path = setlist_path

        self.setlist = load_setlist(self.setlist_path)
        self.setlist = [p for p in self.setlist if os.path.isfile(p)]  # clean missing

        # Use chart-aware listing (prefer .cho over .pdf) and expose one entry per base filename.
        all_charts = list_charts(self.charts_dir)
        setlist_bases = {basename_no_ext(p).lower() for p in self.setlist}
        # Expose only entries whose base name isn't already in the setlist
        self.available = [p for p in all_charts if basename_no_ext(p).lower() not in setlist_bases]

        self._build_ui()

    def _build_ui(self):
        self.master.title(f"{APP_TITLE} - Setup")
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        # V2: Expand dialog dimensions for portrait touchscreen.
        # Target ~90% width, ~80% height of screen. Increase visible rows in list boxes.
        try:
            screen_w = self.master.winfo_screenwidth()
            screen_h = self.master.winfo_screenheight()
            # Choose listbox rows proportionally (larger on tall screens)
            listbox_rows = min(40, max(18, int(screen_h / 60)))

            # If portrait (taller than wide), set dialog to ~90% x 80% and center it
            if screen_h > screen_w:
                dlg_w = int(screen_w * 0.9)
                dlg_h = int(screen_h * 0.8)
                x = (screen_w - dlg_w) // 2
                y = (screen_h - dlg_h) // 2
                try:
                    self.master.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
                except Exception:
                    pass
                # Make sure minimum size keeps controls reachable on smaller screens
                try:
                    self.master.minsize(max(820, int(dlg_w * 0.6)), max(520, int(dlg_h * 0.4)))
                except Exception:
                    self.master.minsize(820, 520)
            else:
                listbox_rows = 18
                self.master.minsize(820, 520)
        except Exception:
            listbox_rows = 18
            self.master.minsize(820, 520)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Charts folder:").grid(row=0, column=0, sticky="w")
        self.dir_var = tk.StringVar(value=self.charts_dir)
        ttk.Entry(top, textvariable=self.dir_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="Rescan", command=self._rescan).grid(row=0, column=2)

        mid = ttk.Frame(self)
        mid.grid(row=1, column=0, sticky="nsew", pady=10)
        mid.columnconfigure(0, weight=1)
        mid.columnconfigure(2, weight=1)
        mid.rowconfigure(1, weight=1)

        ttk.Label(mid, text="Available Charts").grid(row=0, column=0, sticky="w")
        self.av_list = tk.Listbox(mid, selectmode="extended", height=listbox_rows)
        self.av_list.grid(row=1, column=0, sticky="nsew")
        # Informational hint shown when no charts are present in the charts folder
        self.empty_label = ttk.Label(
            mid,
            text=f"No charts found in {self.charts_dir}.\nAdd .pdf or .cho files to this folder or change it and click Rescan.",
            foreground="#a00",
            wraplength=500,
            justify="left",
        )
        self.empty_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        # Initial visibility update based on current available charts
        self._refresh_available_box()

        btns = ttk.Frame(mid)
        btns.grid(row=1, column=1, sticky="ns", padx=10)
        ttk.Button(btns, text="Add →", command=self._add).grid(row=0, column=0, pady=6, sticky="ew")
        ttk.Button(btns, text="← Remove", command=self._remove).grid(row=1, column=0, pady=6, sticky="ew")
        ttk.Separator(btns, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=12)
        ttk.Button(btns, text="Move Up", command=lambda: self._move(-1)).grid(row=3, column=0, pady=6, sticky="ew")
        ttk.Button(btns, text="Move Down", command=lambda: self._move(1)).grid(row=4, column=0, pady=6, sticky="ew")

        ttk.Label(mid, text="Setlist").grid(row=0, column=2, sticky="w")
        self.sl_list = tk.Listbox(mid, selectmode="extended", height=listbox_rows)
        self.sl_list.grid(row=1, column=2, sticky="nsew")
        self._refresh_setlist_box()

        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Save Setlist", command=self._save).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Start Performance Mode", command=self._start).grid(row=0, column=1, sticky="e")

        hint = ttk.Label(
            self,
            text="Performance keys: H help, D dark, Esc quit. Scroll: PgUp/PgDn or arrows/space. Charts: Left/Right or Backspace/Enter.",
            foreground="#555"
        )
        hint.grid(row=3, column=0, sticky="w", pady=(10, 0))

        # Legend: make it easy to identify .cho vs .pdf entries
        legend = tk.Label(self, text="Legend: .cho = blue, .pdf = black", fg="#555")
        legend.grid(row=4, column=0, sticky="w", pady=(6, 0))

    def _refresh_available_box(self):
        self.av_list.delete(0, "end")
        for idx, p in enumerate(self.available):
            self.av_list.insert("end", basename_no_ext(p))
            # Color .cho files differently from .pdf files for easier identification
            try:
                color = "blue" if p.lower().endswith('.cho') else "black"
                # itemconfig accepts fg/foreground depending on Tk version
                try:
                    self.av_list.itemconfig(idx, foreground=color)
                except Exception:
                    try:
                        self.av_list.itemconfig(idx, fg=color)
                    except Exception:
                        pass
            except Exception:
                pass

        # Show or hide the empty-folder hint
        try:
            if not self.available:
                self.empty_label.grid()
            else:
                # Remove the hint when charts are available to keep UI clean
                self.empty_label.grid_remove()
        except Exception:
            pass

    def _refresh_setlist_box(self):
        self.sl_list.delete(0, "end")
        for idx, p in enumerate(self.setlist):
            self.sl_list.insert("end", basename_no_ext(p))
            try:
                color = "blue" if p.lower().endswith('.cho') else "black"
                try:
                    self.sl_list.itemconfig(idx, foreground=color)
                except Exception:
                    try:
                        self.sl_list.itemconfig(idx, fg=color)
                    except Exception:
                        pass
            except Exception:
                pass

    def _rescan(self):
        self.charts_dir = self.dir_var.get().strip()

        # keep setlist valid (remove missing)
        self.setlist = [p for p in self.setlist if os.path.isfile(p)]

        all_charts = list_charts(self.charts_dir)
        setlist_bases = {basename_no_ext(p).lower() for p in self.setlist}
        self.available = [p for p in all_charts if basename_no_ext(p).lower() not in setlist_bases]

        self._refresh_available_box()
        self._refresh_setlist_box()

    def _add(self):
        sel = list(self.av_list.curselection())
        if not sel:
            return

        to_add = []
        for idx in sel:
            p = self.available[idx]
            if p not in self.setlist:
                to_add.append(p)

        if not to_add:
            return

        self.setlist.extend(to_add)
        self.available = [p for p in self.available if p not in to_add]

        self._refresh_available_box()
        self._refresh_setlist_box()

    def _remove(self):
        sel = list(self.sl_list.curselection())
        if not sel:
            return

        removed = []
        for idx in reversed(sel):
            removed.append(self.setlist[idx])
            del self.setlist[idx]

        for p in removed:
            if p not in self.available and os.path.isfile(p):
                self.available.append(p)

        self.available.sort(key=lambda s: os.path.basename(s).lower())

        self._refresh_available_box()
        self._refresh_setlist_box()

    def _move(self, delta: int):
        sel = list(self.sl_list.curselection())
        if not sel:
            return

        if delta < 0:
            for i in sel:
                if i == 0:
                    continue
                self.setlist[i - 1], self.setlist[i] = self.setlist[i], self.setlist[i - 1]
            new_sel = [max(0, i - 1) for i in sel]
        else:
            for i in reversed(sel):
                if i >= len(self.setlist) - 1:
                    continue
                self.setlist[i + 1], self.setlist[i] = self.setlist[i], self.setlist[i + 1]
            new_sel = [min(len(self.setlist) - 1, i + 1) for i in sel]

        self._refresh_setlist_box()
        for i in new_sel:
            self.sl_list.selection_set(i)

    def _save(self):
        self._rescan()
        save_setlist(self.setlist_path, self.setlist)

    def _start(self):
        self._save()
        if not self.setlist:
            messagebox.showwarning("No setlist", "Your setlist is empty, man. Add a few PDFs first.")
            return
        self.master.destroy()
        run_performance(self.charts_dir, self.setlist_path)


class PerformanceWindow(tk.Tk):
    def __init__(self, setlist: List[str], keymap: KeyMap):
        super().__init__()
        self.title(f"{APP_TITLE} - Performance")
        self.configure(background="black")

        self.setlist = [p for p in setlist if os.path.isfile(p)]
        self.keymap = keymap

        self.chart_index = 0
        self.page_index = 0

        # Exit button flow
        self.exit_to_setup = False

        # Combo detection (Up + Down = next chart)
        self.combo_window_ms = 350  # 250 tighter, 450 more forgiving
        self._pending_scroll_job = None
        self._pending_scroll_dir = 0  # +1 down, -1 up
        self._last_pedal_key = None
        self._last_pedal_time = 0.0

        self.dark_mode = True
        self.help_visible = False

        # .cho state
        self.cho_font_size = max(14, int(14 * RENDER_ZOOM))
        self.cho_min_font_size = 8
        self.cho_max_font_size = 48
        self.cho_transpose_semitones = 0

        # editor state
        self.cho_edit_mode = False
        self.cho_edit_window: Optional[tk.Toplevel] = None
        self._last_cho_text: Optional[str] = None

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.y_offset = 0
        self.scroll_step = 80  # pixels per tap

        self._img_tk: Optional[ImageTk.PhotoImage] = None
        self._img_pil: Optional[Image.Image] = None

        # Kiosk fullscreen (no title bar, no decorations)
        self.overrideredirect(True)        # removes window chrome
        self.attributes("-topmost", True)  # stay above panels
        self.config(cursor="none")         # hide mouse cursor

        # Big touchscreen exit button (top-right)
        self.exit_btn = tk.Button(
            self,
            text="Exit Performance",
            command=self._exit_performance,
            bg="#222",
            fg="white",
            activebackground="#444",
            activeforeground="white",
            font=("Arial", 18, "bold"),
            relief="flat",
            padx=16,
            pady=10,
            takefocus=0
        )
        self.exit_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=20)

        # Toolbar under Exit button
        self.toolbar = tk.Frame(self, bg="#222")
        self.toolbar.place(relx=1.0, rely=0.0, anchor="ne", x=-20, y=80)

        # Transpose controls
        self.transpose_label = tk.Label(self.toolbar, text="Transpose:", bg="#222", fg="white", font=("Arial", 14))
        self.transpose_label.pack(side="left", padx=(0, 4))
        self.transpose_down_btn = tk.Button(self.toolbar, text="-", command=lambda: self._toolbar_transpose(-1), width=2, font=("Arial", 14, "bold"), bg="#333", fg="white", relief="flat")
        self.transpose_down_btn.pack(side="left", padx=2)
        self.transpose_up_btn = tk.Button(self.toolbar, text="+", command=lambda: self._toolbar_transpose(1), width=2, font=("Arial", 14, "bold"), bg="#333", fg="white", relief="flat")
        self.transpose_up_btn.pack(side="left", padx=2)
        self.transpose_reset_btn = tk.Button(self.toolbar, text="Reset", command=lambda: self._toolbar_transpose(0), font=("Arial", 12), bg="#333", fg="white", relief="flat")
        self.transpose_reset_btn.pack(side="left", padx=(2, 8))

        # Edit button
        self.edit_btn = tk.Button(self.toolbar, text="Edit", command=self._toolbar_edit, font=("Arial", 12), bg="#333", fg="white", relief="flat")
        self.edit_btn.pack(side="left", padx=8)

        # Note button (placeholder)
        self.note_btn = tk.Button(self.toolbar, text="Note", command=self._toolbar_note, font=("Arial", 12), bg="#333", fg="white", relief="flat")
        self.note_btn.pack(side="left", padx=8)

        # Apply fullscreen/geometry after a short delay so WM can't fight us
        self.after(200, self._apply_kiosk)

        # Catch keys regardless of which widget has focus
        self.bind_all("<KeyPress>", self._on_key)
        # Use captured reference to self to avoid attribute lookup issues in Tk callbacks
        self.bind("<Configure>", lambda e, _s=self: _s._redraw())

        self._load_current()

    def _exit_performance(self):
        self.exit_to_setup = True
        self.destroy()

    def _toolbar_transpose(self, direction: int):
        # Only applies to .cho
        path = None
        try:
            path = self.setlist[self.chart_index]
        except Exception:
            path = None
        if not (path and path.lower().endswith('.cho')):
            return
        if direction == 0:
            self.cho_transpose_semitones = 0
        elif direction > 0:
            self.cho_transpose_semitones = (self.cho_transpose_semitones + 1) % 12
        else:
            self.cho_transpose_semitones = (self.cho_transpose_semitones - 1) % 12
        self._load_current()

    def _toolbar_edit(self):
        # Only applies to .cho
        path = None
        try:
            path = self.setlist[self.chart_index]
        except Exception:
            path = None
        if not (path and path.lower().endswith('.cho')):
            return
        if self.cho_edit_mode:
            self._close_cho_editor()
        else:
            self._open_cho_editor()

    def _toolbar_note(self):
        # Placeholder: show a modal for user notes/markup (future: persist per chart)
        note_win = tk.Toplevel(self)
        note_win.title("Chart Note")
        note_win.geometry("500x300")
        note_win.transient(self)
        note_win.grab_set()
        tk.Label(note_win, text="Add a note or markup for this chart:", font=("Arial", 13)).pack(pady=10)
        note_text = tk.Text(note_win, font=("DejaVu Sans Mono", 12), wrap="word")
        note_text.pack(fill="both", expand=True, padx=12, pady=6)
        tk.Button(note_win, text="Close", command=note_win.destroy).pack(pady=10)

    def _apply_kiosk(self):
        """Force true fullscreen."""
        try:
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
            self.geometry(f"{w}x{h}+0+0")
            self.attributes("-fullscreen", True)
            self.focus_force()
            self.canvas.focus_set()
        except Exception:
            pass

    def _max_offset(self) -> int:
        """Max y_offset for the currently rendered page (0 if page fits)."""
        if not self._img_pil:
            return 0
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())

        scale = w / self._img_pil.width
        scaled_h = int(self._img_pil.height * scale)

        return max(0, scaled_h - h)

    def _on_key(self, event: tk.Event):
        k = event.keysym

        if k in self.keymap.quit_app:
            self.destroy()
            return

        if k in self.keymap.toggle_help:
            self.help_visible = not self.help_visible
            self._redraw()
            return

        if k in self.keymap.toggle_dark:
            self.dark_mode = not self.dark_mode
            self._load_current()
            return

        # .cho zoom controls (only applies to .cho files)
        path = None
        try:
            path = self.setlist[self.chart_index]
        except Exception:
            path = None

        if path and path.lower().endswith('.cho'):
            if k in self.keymap.cho_zoom_in:
                self.cho_font_size = min(self.cho_max_font_size, self.cho_font_size + 2)
                self._load_current()
                return
            if k in self.keymap.cho_zoom_out:
                self.cho_font_size = max(self.cho_min_font_size, self.cho_font_size - 2)
                self._load_current()
                return
            if k in self.keymap.cho_zoom_reset:
                self.cho_font_size = max(14, int(14 * RENDER_ZOOM))
                self._load_current()
                return

            # transpose chords inside [brackets]
            if k in self.keymap.cho_transpose_up:
                self.cho_transpose_semitones = (self.cho_transpose_semitones + 1) % 12
                self._load_current()
                return
            if k in self.keymap.cho_transpose_down:
                self.cho_transpose_semitones = (self.cho_transpose_semitones - 1) % 12
                self._load_current()
                return
            if k in self.keymap.cho_transpose_reset:
                self.cho_transpose_semitones = 0
                self._load_current()
                return

            # Toggle edit mode for .cho
            if k in self.keymap.cho_toggle_edit:
                if self.cho_edit_mode:
                    self._close_cho_editor()
                else:
                    self._open_cho_editor()
                return

        # --- Scroll / Combo handling ---
        if k in self.keymap.scroll_down or k in self.keymap.scroll_up:
            now = time.time()
            is_down = k in self.keymap.scroll_down
            is_up = k in self.keymap.scroll_up

            # If we saw the other pedal very recently, it's a combo -> next chart
            if (
                self._last_pedal_key is not None
                and (now - self._last_pedal_time) <= (self.combo_window_ms / 1000.0)
            ):
                last_was_down = self._last_pedal_key in self.keymap.scroll_down
                last_was_up = self._last_pedal_key in self.keymap.scroll_up

                if (is_down and last_was_up) or (is_up and last_was_down):
                    # Cancel pending scroll, fire next chart
                    if self._pending_scroll_job is not None:
                        try:
                            self.after_cancel(self._pending_scroll_job)
                        except Exception:
                            pass
                        self._pending_scroll_job = None

                    self._last_pedal_key = None
                    self._next_chart()
                    return

            # Not a combo (yet): queue the scroll and wait briefly
            self._last_pedal_key = k
            self._last_pedal_time = now
            self._schedule_scroll(direction=+1 if is_down else -1)
            return

        if k in self.keymap.next_page:
            self._next_page()
            return
        if k in self.keymap.prev_page:
            self._prev_page()
            return

        if k in self.keymap.next_chart:
            self._next_chart()
            return
        if k in self.keymap.prev_chart:
            self._prev_chart()
            return

    def _schedule_scroll(self, direction: int):
        """Delay scroll slightly so a second pedal can form a combo."""
        if self._pending_scroll_job is not None:
            try:
                self.after_cancel(self._pending_scroll_job)
            except Exception:
                pass
            self._pending_scroll_job = None

        self._pending_scroll_dir = direction
        self._pending_scroll_job = self.after(self.combo_window_ms, self._do_pending_scroll)

    def _do_pending_scroll(self):
        """Execute the queued scroll if no combo occurred.
        If we're at the top/bottom of the page, automatically flip PDF pages.
        """
        self._pending_scroll_job = None

        max_off = self._max_offset()

        # Scrolling down
        if self._pending_scroll_dir > 0:
            # If already at bottom (or page fits), go to next PDF page if possible
            if self.y_offset >= max_off:
                try:
                    doc_path = self.setlist[self.chart_index]
                    with fitz.open(doc_path) as doc:
                        if self.page_index < doc.page_count - 1:
                            self.page_index += 1
                            self.y_offset = 0
                            self._load_current()
                            return
                except Exception:
                    pass

            self.y_offset += self.scroll_step

        # Scrolling up
        else:
            # If already at top, go to previous PDF page if possible
            if self.y_offset <= 0:
                if self.page_index > 0:
                    self.page_index -= 1
                    self.y_offset = 0
                    self._load_current()
                    return

            self.y_offset -= self.scroll_step

        self._clamp_offset()
        self._redraw()

    def _next_chart(self):
        if not self.setlist:
            return
        self.chart_index = (self.chart_index + 1) % len(self.setlist)
        self.page_index = 0
        self.y_offset = 0
        self._load_current()

    def _prev_chart(self):
        if not self.setlist:
            return
        self.chart_index = (self.chart_index - 1) % len(self.setlist)
        self.page_index = 0
        self.y_offset = 0
        self._load_current()

    def _next_page(self):
        doc_path = self.setlist[self.chart_index]
        try:
            with fitz.open(doc_path) as doc:
                if self.page_index < doc.page_count - 1:
                    self.page_index += 1
                    self.y_offset = 0
                    self._load_current()
        except Exception:
            pass

    def _prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self.y_offset = 0
            self._load_current()

    def _load_current(self):
        if not self.setlist:
            # Nothing to show — give a friendly message instead of silently doing nothing.
            try:
                # Debug write so we can see this branch exercised
                if os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
                    debug_log({
                        "ts": time.time(),
                        "event": "no_setlist",
                        "setlist_len": 0,
                        "chart_index": self.chart_index
                    })
            except Exception:
                pass

            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", fill="white",
                                    text="No charts available. Open Setup to add charts.")
            return

        path = self.setlist[self.chart_index]
        # Debug: record which path we're about to load and whether it exists
        try:
            if os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
                with open("/tmp/tele_debug.json", "w") as f:
                    json.dump({
                        "ts": time.time(),
                        "event": "load_attempt",
                        "path": path,
                        "exists": os.path.isfile(path),
                        "ext": os.path.splitext(path)[1].lower(),
                        "chart_index": self.chart_index,
                        "setlist_len": len(self.setlist),
                    }, f)
        except Exception:
            pass

        try:
            cho_rendered = False

            # If it's a .cho (ChordPro-style) file, render the plain text into an image using a monospaced font.
            if path.lower().endswith('.cho'):
                cho_rendered = True
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        text = f.read()
                except Exception:
                    raise

                # Apply transpose to chords inside brackets if requested
                if self.cho_transpose_semitones != 0:
                    text = transpose_chords_in_text(text, self.cho_transpose_semitones)

                # Prefer a common monospaced system font; fall back to default.
                font_size = self.cho_font_size
                font = None
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
                except Exception:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf", font_size)
                    except Exception:
                        font = ImageFont.load_default()

                # Determine base width using screen width so text fills the screen width by default
                try:
                    screen_w = max(800, int(self.winfo_screenwidth()))
                    base_w = screen_w
                except Exception:
                    base_w = max(800, int(1200))

                # Content padding so text doesn't touch edges
                padding = 24

                # Estimate characters per line and wrap using available content width
                try:
                    char_w = max(4, font.getsize('M')[0])
                except Exception:
                    char_w = 8
                max_chars = max(40, (base_w - (padding * 2)) // char_w)

                import textwrap
                wrapped_lines = []
                for line in text.splitlines():
                    if not line.strip():
                        wrapped_lines.append('')
                    else:
                        wrapped_lines.extend(textwrap.wrap(line, width=max_chars))

                # Line height and padding (a bit more spacing for touch readability)
                try:
                    fh = font.getsize('A')[1]
                except Exception:
                    fh = 12
                base_line_h = max(18, int(fh * 1.4))
                # Double spacing so there is an empty line between lyrics to accommodate chord lines above
                lyric_spacing = base_line_h * 2
                # The image height uses lyric_spacing per wrapped line
                # Continuous flow: height equals the content height (no enforced page minimum)
                img_h = padding * 2 + max(300, lyric_spacing * len(wrapped_lines))

                # Background/text colors respect dark_mode without additional transforms
                if self.dark_mode:
                    bg = (0, 0, 0)
                    fg = (255, 255, 255)
                    chord_color = (255, 209, 64)  # warm accent for chords on dark bg
                else:
                    bg = (255, 255, 255)
                    fg = (0, 0, 0)
                    chord_color = (0, 102, 204)   # blue accent for chords on light bg

                img = Image.new('RGB', (base_w, img_h), color=bg)
                draw = ImageDraw.Draw(img)
                y = padding
                import re
                # Try to use a bold monospaced font for chords if available
                chord_font = font
                try:
                    for bold_candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                                            "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"):
                        try:
                            chord_font = ImageFont.truetype(bold_candidate, font_size)
                            break
                        except Exception:
                            continue
                except Exception:
                    chord_font = font

                # Notation and chord handling: support {notation} (above) and [chords] (above lyrics)
                # Notation font for {..} blocks (use a clear proportional bold font if available)
                notation_font = font
                try:
                    for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                 "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"):
                        try:
                            notation_font = ImageFont.truetype(cand, max(12, int(font_size * 0.9)))
                            break
                        except Exception:
                            continue
                except Exception:
                    notation_font = font

                notation_color = (30, 144, 255)  # bvright-like blue

                # Add a small chord_margin so chords don't sit flush at the top of the slot
                chord_margin = max(6, int(lyric_spacing * 0.15))
                chord_offset = max(8, int(base_line_h * 0.6))  # vertical offset between chord line and lyric

                # Pre-count notation occurrences so image height can include extra lines
                extra_notation_lines = sum(1 if '{' in l else 0 for l in wrapped_lines)

                for l in wrapped_lines:
                    x = padding
                    # split into segments capturing chords and notation
                    parts = re.split(r'(\[[^]]+\]|\{[^}]+\})', l)
                    has_notation = any(seg.startswith('{') and seg.endswith('}') for seg in parts)
                    has_chord = any(seg.startswith('[') and seg.endswith(']') for seg in parts)

                    # Establish vertical positions
                    if has_notation:
                        ny = y  # notation y (top of slot)
                        cy = ny + base_line_h + chord_margin
                        ly = cy + chord_offset
                    elif has_chord:
                        cy = y + chord_margin
                        ly = cy + chord_offset
                    else:
                        ly = y + max(0, (lyric_spacing - base_line_h) // 2)

                    # Draw notation line(s) centered
                    if has_notation:
                        notes = [seg[1:-1].strip() for seg in parts if seg.startswith('{') and seg.endswith('}')]
                        note_text = '   '.join(notes)
                        try:
                            nw = notation_font.getsize(note_text)[0]
                        except Exception:
                            nw = len(note_text) * char_w
                        note_x = padding + max(0, (base_w - padding * 2 - nw) // 2)
                        draw.text((note_x, ny), note_text, font=notation_font, fill=notation_color)

                    # First pass: draw lyrics (skip bracketed chords and notation blocks)
                    for seg in parts:
                        if not seg:
                            continue
                        if seg.startswith('[') and seg.endswith(']'):
                            try:
                                seg_w = font.getsize(seg)[0]
                            except Exception:
                                seg_w = len(seg) * char_w
                            x += seg_w
                            continue
                        if seg.startswith('{') and seg.endswith('}'):
                            try:
                                seg_w = notation_font.getsize(seg)[0]
                            except Exception:
                                seg_w = len(seg) * char_w
                            x += seg_w
                            continue
                        else:
                            draw.text((x, ly), seg, font=font, fill=fg)
                            try:
                                seg_w = font.getsize(seg)[0]
                            except Exception:
                                seg_w = len(seg) * char_w
                            x += seg_w

                    # Second pass: draw chords above at their respective x positions
                    if has_chord:
                        x = padding
                        for seg in parts:
                            if not seg:
                                continue
                            if seg.startswith('[') and seg.endswith(']'):
                                chord_text = seg[1:-1].strip()
                                if not chord_text:
                                    continue
                                draw.text((x, cy), chord_text, font=chord_font, fill=chord_color)
                                try:
                                    seg_w = chord_font.getsize(seg)[0]
                                except Exception:
                                    seg_w = len(seg) * char_w
                                x += seg_w
                            else:
                                try:
                                    seg_w = font.getsize(seg)[0]
                                except Exception:
                                    seg_w = len(seg) * char_w
                                x += seg_w

                    # Advance y: add extra space if we drew a notation line
                    if has_notation:
                        y += lyric_spacing + base_line_h
                    else:
                        y += lyric_spacing

            else:
                with fitz.open(path) as doc:
                    self.page_index = max(0, min(self.page_index, doc.page_count - 1))
                    page = doc.load_page(self.page_index)
                    mat = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Apply PDF-only dark-mode transforms (CHO images already rendered with correct colors above).
            if not cho_rendered and self.dark_mode:
                if DARK_INVERT:
                    img = ImageOps.invert(img)
                img = ImageEnhance.Contrast(img).enhance(DARK_CONTRAST)
                img = ImageEnhance.Brightness(img).enhance(DARK_BRIGHTNESS)

            self._img_pil = img
            # Debug: write image info so we can inspect what was rendered
            try:
                if os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
                    debug_log({
                        "ts": time.time(),
                        "event": "render_ok",
                        "path": path,
                        "cho_rendered": cho_rendered,
                        "img_size": [img.width, img.height],
                        "dark_mode": self.dark_mode,
                        "cho_font_size": self.cho_font_size,
                        "cho_transpose_semitones": self.cho_transpose_semitones,
                    })
            except Exception:
                pass

            # keep current y_offset when re-rendering cho on zoom/transpose if possible
            try:
                # leave y_offset unchanged; clamp it to the new image size
                self._clamp_offset()
            except Exception:
                self.y_offset = 0
            self._redraw()

        except Exception as e:
            # Log error details to help debug headless/black-screen issues
            try:
                if os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
                    debug_log({
                        "ts": time.time(),
                        "event": "render_error",
                        "path": path,
                        "cho_rendered": cho_rendered,
                        "error": str(e)
                    })
            except Exception:
                pass

            self._img_pil = None
            self.canvas.delete("all")
            self.canvas.create_text(
                20, 20, anchor="nw", fill="white",
                text=f"Error loading:\n{path}\n\n{e}"
            )

    def _clamp_offset(self):
        if not self._img_pil:
            self.y_offset = 0
            return
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())

        scale = w / self._img_pil.width
        scaled_h = int(self._img_pil.height * scale)

        max_off = max(0, scaled_h - h)
        self.y_offset = max(0, min(self.y_offset, max_off))

    def _redraw(self):
        self.canvas.delete("all")
        if not self._img_pil:
            # Visible fallback + debug logging so we can see whether the canvas draws
            try:
                cw = max(1, self.canvas.winfo_width())
                ch = max(1, self.canvas.winfo_height())
                if os.environ.get("TELEPROMPTER_DEBUG_RENDER"):
                    debug_log({
                        "ts": time.time(),
                        "event": "no_img",
                        "canvas_size": [cw, ch],
                        "y_offset": self.y_offset,
                        "chart_index": self.chart_index,
                        "setlist_len": len(self.setlist),
                    })
                # Draw a clear fallback so we know canvas works
                try:
                    self.canvas.create_rectangle(0, 0, cw, ch, fill="#800", outline="")
                    self.canvas.create_text(cw // 2, ch // 2, text="NO IMAGE", fill="white", font=("Arial", 48, "bold"))
                except Exception:
                    pass
            except Exception:
                pass
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        scale = cw / self._img_pil.width
        # Ensure computed height is at least 1 to avoid PIL errors when canvas is temporarily tiny
        new_h = max(1, int(self._img_pil.height * scale))
        try:
            img_resized = self._img_pil.resize((cw, new_h), Image.LANCZOS)
        except Exception as e:
            # Log and show a visible error fallback instead of raising
            try:
                debug_log({
                    "ts": time.time(),
                    "event": "resize_error",
                    "error": str(e),
                    "cw": cw,
                    "new_h": new_h,
                    "img_size": [self._img_pil.width, self._img_pil.height]
                })
            except Exception:
                pass
            # Draw visible fallback and return
            try:
                self.canvas.create_rectangle(0, 0, cw, ch, fill="#800", outline="")
                self.canvas.create_text(cw // 2, ch // 2, text="RENDER ERROR", fill="white", font=("Arial", 48, "bold"))
            except Exception:
                pass
            return

        top = int(self.y_offset)
        bottom = min(top + ch, new_h)
        # Ensure crop has a positive height
        if bottom <= top:
            bottom = min(top + 1, new_h)
        crop = img_resized.crop((0, top, cw, bottom))

        if crop.height < ch:
            pad = Image.new("RGB", (cw, ch), (0, 0, 0))
            pad.paste(crop, (0, 0))
            crop = pad

        self._img_tk = ImageTk.PhotoImage(crop)
        self.canvas.create_image(0, 0, anchor="nw", image=self._img_tk)




def transpose_chords_in_text(text: str, semitones: int) -> str:
    """Transpose chords inside [brackets] by `semitones`.

    Rules:
    - Only transpose tokens inside square brackets.
    - Transpose root notes and slash/bass notes, preserve chord qualities (m, 7, maj7, etc).
    - Operates on a copy of the text (does not modify files on disk).
    """
    import re

    NOTE_MAP = {
        'C':0,'B#':0,'C#':1,'DB':1,'D':2,'D#':3,'EB':3,'E':4,'FB':4,'F':5,'E#':5,
        'F#':6,'GB':6,'G':7,'G#':8,'AB':8,'A':9,'A#':10,'BB':10,'B':11,'CB':11
    }
    NOTES_SHARP = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    NOTES_FLAT = ['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B']

    def transpose_root_token(tok: str) -> str:
        # Match root (letter), optional accidental (# or b), rest (qualities)
        m = re.match(r'^([A-Ga-g])([#b♯♭]?)(.*)$', tok)
        if not m:
            return tok
        root = m.group(1).upper()
        acc = m.group(2).replace('♯','#').replace('♭','b')
        rest = m.group(3)
        key = root + (acc if acc else '')
        key_u = key.upper()
        idx = NOTE_MAP.get(key_u)
        if idx is None:
            # try natural note
            idx = NOTE_MAP.get(root)
            if idx is None:
                return tok
        new_idx = (idx + semitones) % 12
        # prefer flats if original used 'b', sharps if used '#', otherwise sharps
        if 'b' in acc:
            new_root = NOTES_FLAT[new_idx]
        elif '#' in acc:
            new_root = NOTES_SHARP[new_idx]
        else:
            new_root = NOTES_SHARP[new_idx]
        return new_root + rest

    def repl(m: re.Match) -> str:
        content = m.group(1)
        parts = content.split()
        new_parts = []
        for token in parts:
            # handle slash chords like D/F#
            if '/' in token:
                subs = token.split('/')
                new_subs = [transpose_root_token(s) for s in subs]
                new_parts.append('/'.join(new_subs))
            else:
                new_parts.append(transpose_root_token(token))
        return '[' + ' '.join(new_parts) + ']'

    return re.sub(r'\[([^]]+)\]', repl, text)



def run_performance(charts_dir: str, setlist_path: str):
    # Load saved setlist, but prefer on-disk files: filter missing entries and
    # fall back to scanning the charts folder if nothing is available.
    setlist = load_setlist(setlist_path)
    # filter out missing files (user may have renamed/moved files)
    setlist = [p for p in setlist if os.path.isfile(p)]
    if not setlist:
        # prefer .cho files if present, otherwise .pdfs
        setlist = list_charts(charts_dir)

    app = PerformanceWindow(setlist=setlist, keymap=KeyMap())
    app.mainloop()

    # If user tapped Exit Performance, bounce back into setup
    if getattr(app, "exit_to_setup", False):
        launch_setup(charts_dir=charts_dir, setlist_path=setlist_path)


def main():
    launch_setup(charts_dir=DEFAULT_CHARTS_DIR, setlist_path=DEFAULT_SETLIST_PATH)


if __name__ == "__main__":
    main()