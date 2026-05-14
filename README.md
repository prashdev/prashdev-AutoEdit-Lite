# AutoEdit-Lite

An AI-powered automatic video rough-cut tool. Drop in a talking-head video (interview, podcast, vlog) and get back a clean edited version — filler words removed, repeated takes eliminated, awkward pauses cut out.

---

## What This Tool Does

1. **Transcribes** your video locally on your machine (no audio ever leaves your computer)
2. **Sends the transcript** (text only) to Claude AI, which acts as a senior video editor
3. **Claude decides** exactly which segments to keep — removing "um", "uh", repeated takes, long pauses, and off-topic tangents
4. **FFmpeg cuts and stitches** only the good segments into a clean output video
5. **Generates subtitles** (.srt file) for the kept segments automatically

---

## Windows Setup — Recommended

**Download `AutoEditLite-Setup.exe` from the latest [Release](https://github.com/prashdev/prashdev-AutoEdit-Lite/releases) and double-click it.**

The installer bundles Python, FFmpeg, every pip dependency, and the VC++
runtime. It installs per-user (no admin prompt) into `%LocalAppData%\Programs\AutoEditLite\`,
asks for your Anthropic API key in a wizard page, and creates a Start Menu shortcut.
Total install size ~600 MB; the 1.5 GB Whisper model downloads on first run
(one-time, with a progress dialog).

**No-admin / corporate / RDP environments:** download `AutoEditLite-Portable-<version>.zip`
instead, extract anywhere, and run `AutoEditLite.exe`. Identical behaviour, no installer.

> **First launch:** if SmartScreen says "Windows protected your PC", click
> *More info → Run anyway*. The installer is not code-signed yet.

---

## Windows Setup — From source (developers only)

> Use this path only if you want to hack on the code. End users should use the
> installer above. The source-build path requires Python and FFmpeg on your
> system PATH.

### Step 1 — Install Python

1. Go to: https://www.python.org/downloads/
2. Download Python **3.10 or newer**
3. Run the installer
4. **IMPORTANT:** On the first screen, tick the checkbox that says **"Add Python to PATH"** before clicking Install
5. When done, open Command Prompt and type: `python --version`
   - You should see something like: `Python 3.11.0`

### Step 2 — Install FFmpeg

FFmpeg is the video-cutting engine this tool uses. Windows does not include it by default.

1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases
2. Download: `ffmpeg-master-latest-win64-gpl.zip`
3. Unzip it (right-click → Extract All)
4. Inside the unzipped folder, find the `bin` folder. It contains `ffmpeg.exe`
5. Copy the full path to that `bin` folder (e.g. `C:\Users\YourName\ffmpeg\bin`)
6. Add it to your PATH:
   - Press `Windows key`, search for **"Environment Variables"**
   - Click **"Edit the system environment variables"**
   - Click **"Environment Variables..."** button
   - Under **"System variables"**, find and click **"Path"**, then click **"Edit"**
   - Click **"New"** and paste your `bin` folder path
   - Click OK on all windows
7. Open a **new** Command Prompt and type: `ffmpeg -version`
   - You should see version information. If you see an error, the PATH was not set correctly — repeat step 6.

### Step 3 — Download This Project

If you received this as a ZIP file, extract it to a folder like `C:\Projects\autoedit-lite\`.

Open Command Prompt, then navigate to the project folder:
```
cd C:\Projects\autoedit-lite
```

### Step 4 — Install Python Packages

In Command Prompt (inside the project folder), run:
```
pip install -r requirements.txt
```

This installs: faster-whisper (transcription), anthropic (Claude AI), ffmpeg-python, python-dotenv.

> **Note:** faster-whisper will download AI model files (300MB–1.5GB depending on which Whisper model you choose) on the **first run only**. This is normal and only happens once.

### Step 5 — Set Up Your Anthropic API Key

1. Go to: https://console.anthropic.com/
2. Create a free account (you get some free credits)
3. Go to **API Keys** and create a new key
4. In the project folder, find the file `.env.example`
5. **Copy** that file and rename the copy to `.env` (no `.example` at the end)
6. Open `.env` with Notepad and replace `your_key_here` with your real key:
   ```
   ANTHROPIC_API_KEY=sk-ant-...your-key-here...
   ```
7. Save and close the file

> **IMPORTANT:** Never share your `.env` file or post it online. It contains your private API key.

---

## How to Run the Tool

### Basic Usage

Place your video file in the `input/` folder, then run:

```
python main.py --input input\video.mp4
```

The edited video will appear in `output\edited.mp4`.

### Full Options

```
python main.py --input input\video.mp4 --model medium --quality balanced --output output\final.mp4
```

| Argument | Options | Default | What it does |
|----------|---------|---------|--------------|
| `--input` | any video path | (required) | Your input video |
| `--model` | tiny, base, small, medium, large | medium | Whisper transcription model (larger = more accurate but slower) |
| `--quality` | light, balanced, aggressive | balanced | How aggressively Claude edits |
| `--output` | any path | output/edited.mp4 | Where to save the result |
| `--dry-run` | (flag, no value) | off | Transcribe + get Claude's plan, but do NOT cut the video |

### Quality Modes Explained

- **light** — Only removes obvious mistakes and duplicate takes. Safe choice.
- **balanced** — Removes mistakes, filler words (um/uh/like), minor tangents. Best for most videos.
- **aggressive** — Tightest possible edit. Strong narrative flow. Best for polished content.

### Using the Double-Click Launcher (Easiest Method)

Double-click `run.bat` in the project folder. It will ask you to type or paste your video path, then run with sensible defaults automatically.

---

## What is --dry-run?

The `--dry-run` flag lets you **preview Claude's editing decisions** without actually cutting the video. It:

1. Transcribes your video
2. Sends the transcript to Claude
3. Shows you exactly which segments Claude wants to keep and why
4. Saves all logs to the `logs/` folder
5. Does **not** run FFmpeg — no output video is created

This is great for:
- Testing that everything is set up correctly before processing a long video
- Reviewing Claude's decisions before committing to the cut

```
python main.py --input input\video.mp4 --dry-run
```

---

## Cost Estimate

AutoEdit-Lite uses Claude Sonnet for analysis. Approximate costs:

| Video Length | Estimated Cost |
|---|---|
| 2 minutes | ~$0.002 |
| 10 minutes | ~$0.01–0.03 |
| 30 minutes | ~$0.05–0.15 |
| 1 hour | ~$0.10–0.30 |

Transcription (Whisper) runs **locally** — it is free and uses no API.

---

## Troubleshooting

### Problem 1: `ffmpeg is not recognized as a command`
FFmpeg is not in your PATH. Redo Step 2 of setup carefully. After editing PATH, you must open a **new** Command Prompt window — old windows do not pick up PATH changes.

### Problem 2: `ModuleNotFoundError: No module named 'faster_whisper'`
You haven't installed the requirements yet, or you're in the wrong folder. Run:
```
pip install -r requirements.txt
```
Make sure your Command Prompt is pointed at the project folder first (`cd C:\Projects\autoedit-lite`).

### Problem 3: `AuthenticationError` or `invalid API key`
Your `.env` file is missing or wrong. Check:
- The file is named `.env` (not `.env.example`, not `.env.txt`)
- The key starts with `sk-ant-`
- There are no spaces around the `=` sign

### Problem 4: Transcription is very slow
- Whisper runs on your CPU by default, which is slower than a GPU
- Use a smaller model: add `--model base` or `--model small` to your command
- `tiny` is the fastest (but least accurate), `medium` is a good balance

### Problem 5: Output video has audio/video sync issues
This should not happen with the current setup (we always re-encode). If it does:
- Make sure you are using the latest version of FFmpeg
- Try running with a different input format (convert your video to .mp4 first)

### Problem 6: `UnicodeEncodeError` or strange characters in terminal
Some Windows terminals don't support special characters. Use **Windows Terminal** (downloadable free from Microsoft Store) or **PowerShell 7** instead of old Command Prompt.

---

## Performance Notes

- **First run is slow** — Whisper downloads its AI model files (300MB to 1.5GB) on first use. Subsequent runs are fast.
- **Recommended for beginners:** Test with a short video (under 2 minutes) first to verify everything works before processing a long video.
- **CPU-only machines (no dedicated GPU):** Use `--model base` or `--model small` for much faster transcription. The `medium` model on a CPU-only machine can take 3–5x the video's duration to transcribe.
- **Videos over 30 minutes:** The tool automatically splits the transcript into chunks for Claude. This takes longer but works correctly.

---

## Testing on Mac (Developer Note)

If you are testing this on macOS:
1. Install FFmpeg: `brew install ffmpeg`
2. Use `python3` instead of `python`
3. Use `run.sh` instead of `run.bat`: `bash run.sh`
4. Everything else works identically
# prashdev-AutoEdit-Lite
# prashdev-AutoEdit-Lite
