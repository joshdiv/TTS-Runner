# MiniMax TTS Runner

Electron + Vite + React UI, Python + Playwright engine.
Reads your recording script (PDF/Word, via your `audio_engine.py` parser), types each line into
MiniMax Text-to-Speech, clicks Generate, then lets you Regenerate or Download. Files are saved as `<ID>.mp3`.

## Setup
    pip install playwright pypdf rapidfuzz
    npm install
    npm run dev          # or: npm start  (built version)

No `playwright install` is needed: it attaches to your own Chrome.
Set `PYTHON=py` (Windows) or a venv path if `python` isn't the right interpreter.

## Use
1. **Choose script**: IDs like `W06-HEN-001` are listed by segment.
2. **Open MiniMax in Chrome**: opens a separate Chrome profile (login is remembered). Log in, pick voice/speed/etc.
   in the page, then **Connect**.
3. **Choose output folder**: files already there count as done, so you can stop and resume.
4. Per line: **Generate** -> listen in the browser -> **Download & next** or **Regenerate**.
   Or **Auto-run from here** to generate + download everything without review (Stop any time).

## If something doesn't click
MiniMax's page can change. Press **Diagnose page** (shows buttons / text boxes it can see), then edit
`python/minimax_selectors.json`. No code changes needed.

## Layout
    electron/main.cjs        window, Python bridge, Chrome launcher
    src/App.jsx              UI
    python/minimax_server.py Playwright automation (JSON-lines protocol like your server.py)
    python/audio_engine.py   your existing script parser (unchanged)
