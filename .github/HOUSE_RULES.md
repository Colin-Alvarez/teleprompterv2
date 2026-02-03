# TeleprompterV2 — House Rules

Short, actionable rules to guide contributors and automated agents working on this repo.

- Preserve behavior: do not change working behavior unless explicitly requested. Small, incremental changes only.
- Minimal edits: prefer the smallest change that accomplishes the goal. Avoid broad refactors or moving files unless there is a clear benefit and it's requested.
- No unrelated restructuring: don't rename or restructure unrelated files or folders in the same PR.
- Default settings must preserve current defaults: if you add a new setting, default it to current behavior (e.g., DEFAULT_CHARTS_DIR, DEFAULT_SETLIST_PATH, dark mode defaults).
- Keep dependencies minimal: this project targets a Pi and uses only PyMuPDF and Pillow (see `requirements.txt`). Add new deps only when necessary and document why.
- GUI and UX: the app uses Tkinter. Changes that affect the UI should include manual verification steps and a screenshot or explicit reproduction steps.
- Keyboard behavior is critical: the AirTurn pedal behavior (scroll combos, PageUp/Down, Left/Right) is relied on in the field. Any change to key handling must include a test plan that verifies combo timing and pedal mappings.
- Logging and runtime: runtime issues often surface on the Pi/X environment. Use `wait-for-x.sh` and `run.sh` conventions when adding start-up hooks or services.

Quick manual test checklist for the Pi ✅
1. Prepare the Pi: ensure a working X session (DISPLAY=:0) and `~/teleprompter/charts` exists with some PDFs.
2. Activate the venv and install deps: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` (if necessary).
3. Run the app: `python teleprompter.py` (or `./run.sh` if you prefer the wrapper script).
4. In Setup mode: verify available PDFs list populates; add at least one PDF to the setlist, Save Setlist, and Start Performance Mode.
5. In Performance mode: verify fullscreen, dark mode (press `d`), help toggles (`h`), and `Esc` quits.
6. Test navigation: Space/PageDown scrolls, PageUp/Up arrow scrolls up, Left/Right or Backspace/Enter change charts, `]` and `[` change PDF pages if applicable.
7. Test combo behavior: quickly press an Up and Down pedal (or corresponding keys) to trigger next chart; verify timing is reasonable.
8. Confirm setlist persistence: `~/teleprompter/setlist.json` should be updated after saving.

If anything in these checks fails, open a focused issue/PR with:
- One-line summary of the behavior change you observed
- Exact reproduction steps you ran on the Pi
- Minimal patch or failing test case (if applicable)

---
These rules are intentionally conservative to keep the device stable in live performance contexts. If you'd like, I can also add a short `CONTRIBUTING.md` that expands on these points. 👌