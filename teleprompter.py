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
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageEnhance, ImageTk


APP_TITLE = "PDF Teleprompter"
DEFAULT_CHARTS_DIR = os.path.expanduser("~/teleprompter/charts")
DEFAULT_SETLIST_PATH = os.path.expanduser("~/teleprompter/setlist.json")

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


def list_pdfs(charts_dir: str) -> List[str]:
    if not os.path.isdir(charts_dir):
        return []
    pdfs = [f for f in os.listdir(charts_dir) if f.lower().endswith(".pdf")]
    pdfs.sort(key=lambda s: s.lower())
    return [os.path.join(charts_dir, f) for f in pdfs]


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

        all_pdfs = list_pdfs(self.charts_dir)
        self.available = [p for p in all_pdfs if p not in self.setlist]

        self._build_ui()

    def _build_ui(self):
        self.master.title(f"{APP_TITLE} - Setup")
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

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

        ttk.Label(mid, text="Available PDFs").grid(row=0, column=0, sticky="w")
        self.av_list = tk.Listbox(mid, selectmode="extended", height=18)
        self.av_list.grid(row=1, column=0, sticky="nsew")
        self._refresh_available_box()

        btns = ttk.Frame(mid)
        btns.grid(row=1, column=1, sticky="ns", padx=10)
        ttk.Button(btns, text="Add →", command=self._add).grid(row=0, column=0, pady=6, sticky="ew")
        ttk.Button(btns, text="← Remove", command=self._remove).grid(row=1, column=0, pady=6, sticky="ew")
        ttk.Separator(btns, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=12)
        ttk.Button(btns, text="Move Up", command=lambda: self._move(-1)).grid(row=3, column=0, pady=6, sticky="ew")
        ttk.Button(btns, text="Move Down", command=lambda: self._move(1)).grid(row=4, column=0, pady=6, sticky="ew")

        ttk.Label(mid, text="Setlist").grid(row=0, column=2, sticky="w")
        self.sl_list = tk.Listbox(mid, selectmode="extended", height=18)
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

        self.master.minsize(820, 520)

    def _refresh_available_box(self):
        self.av_list.delete(0, "end")
        for p in self.available:
            self.av_list.insert("end", basename_no_ext(p))

    def _refresh_setlist_box(self):
        self.sl_list.delete(0, "end")
        for p in self.setlist:
            self.sl_list.insert("end", basename_no_ext(p))

    def _rescan(self):
        self.charts_dir = self.dir_var.get().strip()

        # keep setlist valid (remove missing)
        self.setlist = [p for p in self.setlist if os.path.isfile(p)]

        all_pdfs = list_pdfs(self.charts_dir)
        self.available = [p for p in all_pdfs if p not in self.setlist]

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

        # Apply fullscreen/geometry after a short delay so WM can't fight us
        self.after(200, self._apply_kiosk)

        # Catch keys regardless of which widget has focus
        self.bind_all("<KeyPress>", self._on_key)
        self.bind("<Configure>", lambda e: self._redraw())

        self._load_current()

    def _exit_performance(self):
        self.exit_to_setup = True
        self.destroy()

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
            return

        path = self.setlist[self.chart_index]

        try:
            with fitz.open(path) as doc:
                self.page_index = max(0, min(self.page_index, doc.page_count - 1))
                page = doc.load_page(self.page_index)
                mat = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            if self.dark_mode:
                if DARK_INVERT:
                    img = ImageOps.invert(img)
                img = ImageEnhance.Contrast(img).enhance(DARK_CONTRAST)
                img = ImageEnhance.Brightness(img).enhance(DARK_BRIGHTNESS)

            self._img_pil = img
            self.y_offset = 0
            self._clamp_offset()
            self._redraw()

        except Exception as e:
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
            return

        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())

        scale = cw / self._img_pil.width
        new_h = int(self._img_pil.height * scale)
        img_resized = self._img_pil.resize((cw, new_h), Image.LANCZOS)

        top = int(self.y_offset)
        bottom = min(top + ch, new_h)
        crop = img_resized.crop((0, top, cw, bottom))

        if crop.height < ch:
            pad = Image.new("RGB", (cw, ch), (0, 0, 0))
            pad.paste(crop, (0, 0))
            crop = pad

        self._img_tk = ImageTk.PhotoImage(crop)
        self.canvas.create_image(0, 0, anchor="nw", image=self._img_tk)


def run_performance(charts_dir: str, setlist_path: str):
    setlist = load_setlist(setlist_path)
    if not setlist:
        setlist = list_pdfs(charts_dir)

    app = PerformanceWindow(setlist=setlist, keymap=KeyMap())
    app.mainloop()

    # If user tapped Exit Performance, bounce back into setup
    if getattr(app, "exit_to_setup", False):
        launch_setup(charts_dir=charts_dir, setlist_path=setlist_path)


def main():
    launch_setup(charts_dir=DEFAULT_CHARTS_DIR, setlist_path=DEFAULT_SETLIST_PATH)


if __name__ == "__main__":
    main()