# Copilot/AI Agent Instructions for teleprompterv2 ✅

Short, actionable notes to get an AI coding agent immediately productive in this repo.

## Project purpose / big picture 🔧
- A small, single-process GUI app for a Raspberry Pi (or Linux desktop) that shows PDF charts in a teleprompter-style fullscreen viewer.
- Two modes: **Setup** (Tkinter list UI to build a setlist) and **Performance** (kiosk fullscreen viewer that scrolls and navigates charts).
- Key libraries: `PyMuPDF` (PDF rendering) and `Pillow` (image processing).

## Important files & locations 📁
- `teleprompter.py` — single-file app containing both Setup and Performance windows (primary source of truth).
- `requirements.txt` — `PyMuPDF` and `Pillow` pinned here.
- `setlist.json` — stored as a JSON array of absolute paths to PDF files; used by Performance mode.
- `charts/` — example chart folder in repo (contains many `.cho` files and PDFs); the app only reads `.pdf` files.
- `run.sh` — example runtime launcher (expects a `venv` and activates it).
- `wait-for-x.sh` — helper to wait for X display availability (used when autostarting on boot).

## How to run / reproduce locally ▶️
1. Create a virtualenv and install deps:
   - `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
2. Ensure you have a running X session (the app requires a GUI / DISPLAY).
3. Add PDFs to `~/teleprompter/charts/` or edit `~/teleprompter/setlist.json` with absolute PDF paths.
4. Start the app: `python teleprompter.py` (or use the provided `run.sh` pattern that activates `venv`).

Notes:
- The app starts in **Setup** mode. Save a setlist there and tap "Start Performance Mode" to enter the fullscreen teleprompter.
- For automated startup on boot, `wait-for-x.sh` is helpful to defer launch until X is ready.

## Key runtime behaviors & patterns to know ⚠️
- Default constants live at top of `teleprompter.py`: `DEFAULT_CHARTS_DIR`, `DEFAULT_SETLIST_PATH`, `RENDER_ZOOM`, dark-mode tuning values. These are the primary knobs for performance and appearance.
- Rendering pipeline: `fitz` → Pixmap → `Pillow.Image` → dark-mode transforms (invert, contrast, brightness) → resize to canvas.
- Scrolling is implemented with a short delay to allow pedal combos: pressing Up+Down (within `combo_window_ms`) triggers a chart flip.
- `KeyMap` dataclass centralizes all keyboard/pedal bindings — change here to remap hardware/controls.

## Project-specific conventions / gotchas ⚙️
- `setlist.json` must be a JSON array of absolute path strings. Setup UI will prune missing files but keep paths absolute.
- Only `.pdf` files are considered by `list_pdfs`; other file types in `charts/` (like `.cho`) are ignored.
- The app is designed for local desktop/X use — it will not run headlessly.
- Performance tuning: reduce `RENDER_ZOOM` on slower Pis; Pi 5 commonly uses 2.0–2.5, Pi 3 may need ~1.6–2.0.

## Debugging & testing tips 🐞
- Reproduce image-loading errors by opening a problematic PDF in `teleprompter.py` via the Setup UI and observe the error text overlay in Performance mode.
- Use `wait-for-x.sh` when writing autostart scripts to ensure X is available before launching the GUI.
- There are no unit tests or CI in this repo — prefer small, manual tests and document any added test files.

## Suggested PR / automation targets (discoverable patterns) 💡
- Add a small CLI or environment variable support to override `DEFAULT_CHARTS_DIR` / `DEFAULT_SETLIST_PATH` for easier testing.
- Add minimal unit tests for helper functions (`list_pdfs`, `load_setlist`, `save_setlist`, `basename_no_ext`). Keep GUI logic separate when possible.

---

If anything above is unclear or you'd like additional explicit examples (e.g., sample `setlist.json` snippets, typical `systemd` autostart example using `wait-for-x.sh`), tell me which section and I'll expand it. 🔍