# TTS Runner

A desktop app that turns a voiceover recording script into finished audio clips. Load your script, let the app generate every dialogue line with text-to-speech, review each take, regenerate the ones you don't like, and export everything named by its dialogue ID.

Built with Electron, React (Vite), and a Python backend.

---

## Features

- **Script parsing** – Load a script (PDF or Word) and the app detects every numbered dialogue line (e.g. `W05-HEN-001`, `ADD-W01-BIL-001`). Bracketed directions like `[whispers]` are not spoken.
- **Scene and character grouping** – Lines are grouped by scene heading (`Scene N`, `STATE W2-01`, etc.) and by character, which is read from the ID code. View and export sorted either way.
- **Auto-generate the whole script** – Run through every line automatically, then choose **Regenerate** or **Download** for each take.
- **Per-line editing** – Tweak any line before generating. Bracketed reaction lines such as `[Laughter]` load as lines you can edit into sound tags.
- **Emotion buttons** – Wrap a line in an emotion tag: Happy, Angry, Sad, Fearful, Disgusted, Surprised, Neutral, Fluent. Click the same emotion again to remove it, or pick a different one to replace it. Emotions apply to the whole line.
- **Sound tag buttons** – Insert tags at the cursor while editing a line: `(laugh)`, `(chuckle)`, `(cough)`, `(clear-throat)`, `(groans)`, `(breath)`, `(pant)`, `(inhale)`.
- **Custom ID formats** – If your script uses a different ID pattern, define it on the Setup page with simple masks (e.g. `AAA-AAA-AAA-###` or `AA#-AAA-###`).
- **Group lines** – Lines spoken by several characters at once (`GRP`) are mixed from each character's individual take using ffmpeg and saved to a `GRP` folder.
- **Organized export** – Audio files are named by dialogue ID and exported into folders grouped by scene or by character.

## Engines

Choose the voice engine in the app's settings:

| Engine | How it works |
| --- | --- |
| **MiniMax API** | Generates speech over HTTP with the MiniMax text-to-speech API. |
| **ElevenLabs API** | Generates speech with ElevenLabs. Assign a voice to each character. |

## Tech stack

- **Frontend:** React + Vite
- **Desktop shell:** Electron
- **Backend:** Python (`minimax_server.py`, `minimax_api.py`, `audio_engine.py` for script parsing)
- **Audio mixing:** ffmpeg

## Getting started

### Prerequisites

- Node.js (LTS)
- Python 3.10+
- ffmpeg available on your `PATH`
- A MiniMax and/or ElevenLabs API key

### Installation

```bash
git clone https://github.com/raein-dev/tts-runner.git
cd tts-runner

# Frontend / Electron dependencies
npm install

# Python dependencies
pip install -r requirements.txt
```

### Run in development

```bash
npm run dev
```

### Build

```bash
npm run build
```

> Adjust the commands above to match your project's scripts.

## Usage

1. **Setup** – Open the Setup page, add your API key(s), pick an engine, and assign voices to characters. Add a custom ID format if your script doesn't use the default pattern.
2. **Load a script** – Choose your recording script. The app lists every detected dialogue line, grouped by scene or character.
3. **Edit (optional)** – Adjust wording, apply an emotion, or insert sound tags.
4. **Run** – Start the runner. Each line is generated automatically.
5. **Review** – For each take, choose **Regenerate** or **Download**. Group lines go through **Generate → Save/Regenerate** before download.
6. **Export** – Save all clips named by dialogue ID, in folders grouped by scene or character.

## Script format

TTS Runner expects each line to have an ID, followed by the dialogue:

```
W05-HEN-001
Henry: "Dialogue goes here."
[Direction that is not spoken]
```

- Only the quoted dialogue is read. The `CHARACTER:` label is not spoken.
- Dialogue can span multiple paragraphs.
- Anything in `[brackets]` after a line is treated as a direction and skipped.

## Project structure

```
tts-runner/
├── src/                 # React UI (App.jsx, Setup page, etc.)
├── electron/            # Electron main process
├── minimax_server.py    # Local backend server
├── minimax_api.py       # MiniMax API client
├── audio_engine.py      # Script parsing and ID detection
└── ...
```

> Update this tree to match your actual folders.

## Roadmap

- [ ] More engines
- [ ] Per-line voice overrides
- [ ] Batch regenerate for flagged lines

## License

Add your license here (e.g. MIT).

## Author

Built by [raein-dev](https://github.com/raein-dev).