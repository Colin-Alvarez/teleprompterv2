# Contributing — TeleprompterV2 🛠️

Thanks for helping improve TeleprompterV2. Follow the minimal, Pi-first rules below to keep the device stable in live use.

## Quick rules (required)
- Read `.github/HOUSE_RULES.md` before changing behavior. Keep changes minimal and targeted.
- Do not change defaults unless explicitly requested — new settings must default to current behavior.
- Avoid unrelated refactors or moving files in the same PR.

## How to run locally (Pi-focused) 🔧
- Create and activate venv:
  - python -m venv venv
  - source venv/bin/activate
- Install runtime deps:
  - pip install -r requirements.txt
- Optionally wait for X and run (useful for system startup scripts):
  - ./wait-for-x.sh && ./run.sh
- Run for development (interactive):
  - python teleprompter.py

## What to test on the Pi (PR checklist) ✅
Include these explicit checks in your PR description (copy the list and mark pass/fail):
- Setup mode
  - `~/teleprompter/charts` populates the Available PDFs list
  - Adding/removing and reordering entries updates the UI correctly
  - `Save Setlist` writes to `~/teleprompter/setlist.json`
- Performance mode
  - App launches fullscreen and hides mouse cursor
  - `d` toggles dark mode; `h` toggles help overlay; `Esc` quits
  - Scrolling: Space/PageDown and Up/PageUp or arrows work as expected
  - Chart navigation: Left/Right or Backspace/Enter work
  - PDF page navigation: `]` and `[` advance/rewind multi-page PDFs
  - Pedal combo: rapid Up+Down (or keys) triggers next chart reliably
  - Check that y-offset clamping and page flips at top/bottom behave consistently
- Persistence & files
  - `~/teleprompter/setlist.json` contains saved setlist entries and valid file paths

## UI / Keyboard changes
- Any change to key mappings, combo windows, or scroll behavior must include:
  - Rationale: why current behavior is insufficient
  - Minimal code change with focused tests for combo timing
  - Manual verification steps (include exact keys and expected result)

## Adding dependencies
- Justify new deps in the PR description and prefer lightweight, well-supported packages.
- Add to `requirements.txt` and include a short install/verification step in the PR.

## PR & commit guidance
- Keep PRs small and scoped to one change/bugfix.
- Use descriptive commit messages (imperative mood): e.g., "fix: clamp y_offset when resizing".
- Include short reproduction steps and one or two screenshots for UI changes.

## Reporting runtime or startup issues
- If something breaks on the Pi (X sessions, DPI, fonts, etc.), add logs and exact commands used to reproduce.
- Use `teleprompter.log` (if present) and include X environment details: `DISPLAY`, `XAUTHORITY`, and `python`/`venv` path.

---
If you'd like, I can add a GitHub Actions workflow to run basic flake8/type checks for PRs. Let me know and I'll propose the smallest, non-disruptive config that won't change runtime behavior.