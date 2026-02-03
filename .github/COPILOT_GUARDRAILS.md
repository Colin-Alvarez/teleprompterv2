# Teleprompter V2 — Copilot Guardrails

Purpose: Short, concrete guardrails for automated agents and contributors working on TeleprompterV2.

Core rules (must follow)
- Prefer minimal, local changes. Make the smallest change that accomplishes the goal. ✅
- Do not refactor or move unrelated code/files in the same PR. ⚠️
- Preserve all existing PDF behavior: rendering, paging, and setlist persistence must remain unchanged unless a deliberate, documented change is requested. 📄
- Default behavior must match the current (V1-compatible) defaults unless explicitly updated in a PR and justified with a Pi test. 🔁
- Optimize for Raspberry Pi touchscreen performance: prefer lightweight changes, avoid adding heavy dependencies, and validate responsiveness on realistic Pi hardware. 🪙

Concrete code signals you must not change without justification and Pi testing
- Constants and defaults in `teleprompter.py`: `DEFAULT_CHARTS_DIR`, `DEFAULT_SETLIST_PATH`, `RENDER_ZOOM` (2.0), `DARK_INVERT`, `DARK_CONTRAST`, `DARK_BRIGHTNESS` — keep them as-is unless performance or UX testing on a Pi shows a need.
- Key handling & combos: `KeyMap`, `combo_window_ms = 350`, `scroll_step = 80`. Changes to these must include step-by-step combo timing tests.
- Fullscreen/kiosk behavior: `overrideredirect(True)`, `attributes("-topmost", True)`, `attributes("-fullscreen", True)`, and `config(cursor="none")` are part of the production UI flow and should be preserved.
- Rendering pipeline: keep using PyMuPDF (`fitz`) at `RENDER_ZOOM` and PIL `Image.resize(..., Image.LANCZOS)` as the default. Avoid per-frame expensive ops; prefer caching decoded images in memory (`self._img_pil`) as the code already does.
- File locations and persistence: `~/teleprompter/charts` and `~/teleprompter/setlist.json` are canonical; `load_setlist` cleans missing files on load — do not change that semantics.
- Startup scripts: `wait-for-x.sh` and `run.sh` are used in Pi startup contexts; preserve their purpose and environment usage (DISPLAY=:0, XAUTHORITY).
- Dependencies: requirements are in `requirements.txt` (PyMuPDF, Pillow). Add deps only with clear justification and Pi install/test steps.

Performance testing checklist (required for any change that may affect runtime)
- Test on an actual Raspberry Pi (3/4/5 if available) with a touchscreen attached.
- Verify: smooth scrolling (no visible stutter), quick chart change, and <1s startup into Performance mode from Setup exit.
- Check CPU and memory while scrolling through a large PDF: note any regressions vs baseline.
- Validate combo pedal behavior (Up+Down within the combo window) triggers next-chart reliably.
- Confirm setlist save/load continues to work and that missing PDFs are ignored on load.

PR requirements
- Small, focused PR with a one-line rationale and short manual test steps (copy the performance checklist and mark pass/fail).
- If changing defaults, in the PR body include: exact file changes, why default changed, and explicit Pi-test results demonstrating improved behavior.

If you are unsure about a change, open an issue and ask for a small, reviewer-approved change. Keep the device stable and predictable — that's the top priority.