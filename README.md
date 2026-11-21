> [!NOTE]
> Download only from this official repository: [github.com/joshdiv/tts-runner](https://github.com/joshdiv/tts-runner).

# TTS Runner: Turn a Voiceover Script into Finished Audio Clips

Load your recording script, and TTS Runner generates every line with ElevenLabs or MiniMax, then saves each clip named by its dialogue ID, ready to drop into your project.

![Latest Release](https://img.shields.io/github/v/release/joshdiv/tts-runner)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue)

[⬇ Download (Installer)](https://github.com/joshdiv/tts-runner/releases/latest) · [Quick start](#quick-start) · [Screenshots](#see-it-in-action) · [FAQ](#faq) · [Get help](#help-and-support)

<p align="center">
  <img src="src/assets/ttsrunner-icon.png" alt="TTS Runner main window" width="300">
</p>


TTS Runner is a free, open-source (MIT) desktop app for Windows. It reads a numbered recording script (Word or PDF), lists every dialogue line, sends each one to the text-to-speech engine you choose, and saves the audio as `DIALOGUE-001.mp3`, `LINE-003-001.mp3`, and so on. You listen, regenerate the takes you don't like, and export the lot.

## Why TTS Runner?

Generating a few lines in a web-based TTS tool is easy. Generating a few hundred is not. If you've ever voiced a whole script this way, these will sound familiar:

| The pain | What TTS Runner does |
| --- | --- |
| **Copy-pasting hundreds of lines** into a web page, one at a time | Reads the whole script and generates every line for you, in order |
| **Renaming every download by hand** so files match your script IDs | Saves each clip as `<dialogue ID>.mp3` automatically |
| **Losing your place** after a crash, a rate limit, or closing the tab | Detects clips you've already saved so you can pick up where you stopped |
| **Hunting for the one bad take** in a folder of near-identical files | Plays each take in the app, with one-click **Regenerate** or **Save** |
| **Re-typing lines to change the delivery** (angry, sad, laughing) | Emotion and sound-tag buttons, applied to the line right in the app |
| **Switching voices for every character** | Assign a voice per character once; the runner uses the right one for each line |
| **Crowd and group lines** that need several voices at once | Generates each character's take and mixes them into one clip with ffmpeg |
| **Messy output folders** | Exports grouped by scene or by character, whichever your editor needs |
| **Scripts that don't match any tool's format** | Define your own ID patterns, or load scripts that use character names instead of IDs |
| **Setting up Python, ffmpeg, and dependencies** just to run a tool | One installer. Python and ffmpeg are bundled, nothing else to install |

## Quick start

1. **Download the installer** from the [latest release](https://github.com/joshdiv/tts-runner/releases/latest) and run it.
2. **Open Setup.** Add your ElevenLabs and/or MiniMax API key and assign a voice to each character.
3. **Load your script** (`.docx` or `.pdf`). The app lists every detected line.
4. **Press run.** Each line is generated automatically. Regenerate or save each take as you review.
5. **Export** your clips, named by dialogue ID.

> [!NOTE]
> The installer is not code-signed, so Windows SmartScreen may show "Windows protected your PC." Click **More info**, then **Run anyway**.

## How it works

TTS Runner is an Electron desktop app. Its interface talks to a small bundled Python engine that parses your script, calls the voice service, and handles saving and mixing audio. Your script and your audio files stay on your computer. Only the text of each line is sent to the voice service you pick, using your own API key.

## See it in action


*Screenshots coming soon.*

## Features

### Scripts
- Reads **Word (`.docx`) and PDF** recording scripts
- Detects numbered dialogue IDs such as `W05-HEN-001` and `ADD-W01-BIL-001`
- **Custom ID formats** on the Setup page, written as simple masks (`A` = letter, `#` = digit, `*` = letter or digit)
- Understands scene headings (`Scene N`, `STATE W2-01`, `Segment N`) and groups lines under them
- Reads only the quoted dialogue. Speaker labels and `[bracketed]` directions are not spoken
- Also loads scripts **without IDs**, in `Henry: dialogue` or standard screenplay layout, and generates IDs for them
- Choose which characters to **omit** from a script

### Voice generation
- **Two engines:** ElevenLabs and MiniMax (bring your own API key)
- Pick a **voice for each character**
- Generate the whole script, or one line at a time
- **Preview** every take before keeping it
- **Regenerate** or **Save** per line
- **Resume** a session: clips already saved in your output folder are recognized

### Editing and delivery
- **Emotion buttons:** Happy, Angry, Sad, Fearful, Disgusted, Surprised, Neutral, Fluent. Click again to remove, or pick another to replace
- **Sound tag buttons**, inserted at the cursor: `(laugh)`, `(chuckle)`, `(cough)`, `(clear-throat)`, `(groans)`, `(breath)`, `(pant)`, `(inhale)`
- Edit any line before generating it

### Group lines
- Mark characters as **group** speakers (for example `GRP`)
- Each voice is generated separately, then **mixed into one clip** with ffmpeg
- Optionally delete the individual takes after mixing

### Output and projects
- Files saved as `<dialogue ID>.mp3`
- Output organized **by scene or by character**
- Save your work as a **`.ttsrunner` project** file and reopen it later, with a recent-projects list

## Installation

**Requires:** Windows 10 or 11 (64-bit), an internet connection, and an API key for at least one supported voice service.

Download `TTS Runner Setup x.x.x.exe` from the [latest release](https://github.com/joshdiv/tts-runner/releases/latest) and run it. You can choose the install folder. Python and ffmpeg are included.

## How to use

### Set up your engine
Open **Setup**, choose ElevenLabs or MiniMax, and paste your API key. Load the voice list and assign a voice to each character.

### Prepare your script
Each line needs an ID, followed by the dialogue:

```
W05-HEN-001
Henry: "Dialogue goes here."
[A direction that is not spoken]
```

- Only the quoted dialogue is read
- Dialogue can run across several paragraphs
- If your IDs look different, add your pattern under **Customize** on the Setup page

### Generate and review
Load the script and start the run. For each take, listen, then **Regenerate** or **Save**. To change the delivery, edit the line and apply an emotion or insert a sound tag first.

### Group lines
Generate each character's take, then mix. The mixed clip is saved under its dialogue ID, and the individual takes can be removed.

### Export
Choose an output folder and whether to organize by scene or by character.

## Build from source

You'll need Node.js, Python 3.10+, and ffmpeg.

```bash
git clone https://github.com/joshdiv/tts-runner.git
cd tts-runner
npm install
pip install pypdf pyinstaller
```

**Run in development:**

```bash
npm run dev
```

**Build the installer:**

```bash
# 1. Bundle the Python engine
python -m PyInstaller --onefile --name tts_server --distpath backend --paths python python/tts_server.py

# 2. Put ffmpeg.exe in resources/bin/
# 3. Build
npm run dist
```

The installer is created in the `release` folder. Your window icon needs `electron/icon.ico` with a 256×256 image inside.

## Project structure

```
tts-runner/
├── electron/          # Electron main process and preload
├── python/
│   ├── tts_server.py      # Engine server (JSON over stdin/stdout)
│   ├── audio_engine.py    # Script parsing and ID detection
│   ├── elevenlabs_api.py  # ElevenLabs client
│   └── minimax_api.py     # MiniMax client
├── src/               # React interface (pages, components, hooks)
└── package.json
```

## FAQ

**Is TTS Runner free?**
Yes, it's free and open source under the MIT License. The voice services have their own pricing, and you pay them directly through your own API key.

**Do I need to install Python or ffmpeg?**
Not with the installer. Both are bundled. They're only needed if you build from source.

**Where do my script and audio go?**
They stay on your computer. Only the text of each line is sent to ElevenLabs or MiniMax to generate speech.

**Which script formats work?**
Word (`.docx`) and PDF.

**My script's IDs aren't detected.**
Add your ID format under **Customize** on the Setup page. For example, `AAA-AAA-###` matches `DB-HEN-001`-style IDs. Use `A` for a letter, `#` for a digit, and `*` for either.

**Can I use it with a script that has no IDs?**
Yes. Scripts with `Name: dialogue` lines or standard screenplay layout are read by character name, and IDs are generated for each line.

**Can I generate group or crowd lines?**
Yes. Mark the character as a group speaker. Each voice is generated separately and mixed into one clip.

**Can I pick up where I left off?**
Yes. Save a `.ttsrunner` project, and clips already saved in your output folder are recognized.

**Windows says "protected your PC."**
The installer isn't code-signed. Click **More info**, then **Run anyway**.

## Help and support

- Bug or feature request: [GitHub Issues](https://github.com/joshdiv/tts-runner/issues)
- Questions and discussion: [GitHub Discussions](https://github.com/joshdiv/tts-runner/discussions)

If TTS Runner saved you time, starring the repo helps others find it. ⭐

## License

Released under the [MIT License](LICENSE).