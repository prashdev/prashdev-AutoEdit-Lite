# AutoEdit-Lite

An AI-powered automatic video rough-cut tool. Drop in a talking-head video (interview, podcast, vlog) and get back a clean edited version — filler words removed, repeated takes eliminated, awkward pauses cut out.

---

## Project Status

**Last updated: 2026-06-13**

- Current implementation verification: **322 tests passed**
- Estimated implementation progress: **95% complete; approximately 5%
  remaining**
- Measured progress toward 95% human-editor agreement: **Not yet measurable;
  representative human-labelled evaluation is still required**
- Latest setup size: **234.75 MiB**
- Latest portable size: **315.89 MiB**
- Large speech-model weights bundled: **No; the staged dependencies include a
  1.19 MiB Silero VAD asset and tiny ONNX Runtime samples**
- Markdown status coverage: **Verified across every project Markdown file**
- Current work: **Collect, human-label, render, and evaluate at least 10
  complete actual representative cases for each target language**
- Current iteration steps: **Audit 100% | Markdown status 100% | Failing
  regression 100% | Implementation 100% | Verification/rebuild/docs 100%**
- 95% human-editor agreement: **Not yet proven; representative human-labelled
  video evaluation is still required**

Read [`PROJECT_STATUS.md`](PROJECT_STATUS.md) before starting or continuing
work. It is the authoritative progress ledger, verification record, next-action
list, and new-session handoff. After every meaningful completed step, update
that ledger and every project Markdown status section so future sessions do not
repeat work or overstate completion.

---

## What This Tool Does

1. **Transcribes** your video with Sarvam AI for Indian languages when `SARVAM_API_KEY` is set, otherwise falls back to local Whisper
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
The installer avoids bundled speech models so the setup stays below the 400 MB target. Whisper models download on first local-Whisper use and are cached outside the app; Sarvam AI avoids local model downloads entirely.

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

This installs: sarvamai (Indian-language transcription), faster-whisper (offline fallback), anthropic (Claude AI), ffmpeg-python, python-dotenv.

> **Note:** faster-whisper will download AI model files (300MB-1.5GB depending on which Whisper model you choose) on the **first local-Whisper run only**. For Marathi, Hindi, and Indian English, set `SARVAM_API_KEY` to use Sarvam AI instead.

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

The edited 9:16 90-second video will appear in `output\edited_90s.mp4`.

### Full Options

```
python main.py --input input\video.mp4 --language mr-IN --quality balanced --output output\edited_90s.mp4
```

| Argument | Options | Default | What it does |
|----------|---------|---------|--------------|
| `--input` | any video path | (required) | Your input video |
| `--model` | tiny, base, small, medium, large | medium | Whisper fallback model (larger = more accurate but slower) |
| `--quality` | light, balanced, aggressive | balanced | How aggressively Claude edits |
| `--output` | any path | output/edited_90s.mp4 | Where to save the result |
| `--target-duration` | seconds | 90 | Target final cut duration |
| `--aspect-ratio` | 9:16, 16:9 | 9:16 | Output format |
| `--platform` | reels, tiktok, shorts, general | reels | Pacing and style target |
| `--language` | BCP-47 code | mr-IN | Sarvam-preferred language; use hi-IN or en-IN as needed |
| `--gap-threshold` | seconds | 0.5 | Pause length treated as removable dead air |
| `--human-decisions` | JSON path | off | Optional human labels file; adds measured keep/remove and cut-boundary agreement to `accuracy_report.json` |
| `--dry-run` | (flag, no value) | off | Transcribe + get Claude's plan, but do NOT cut the video |

FFmpeg exports are scaled and center-cropped to the requested aspect ratio
instead of padded, so 9:16 output stays vertical without black bars.
When word-level timestamps are available, selected ranges are snapped to spoken
word boundaries; silence-only selected ranges are dropped so the final cut does
not preserve dead air as a raw timestamp segment.
Adjacent retained ranges are merged before rendering so continuous speech does
not become an unnecessary jump cut. At real edit points, each trimmed audio
branch is asynchronously resampled before concatenation and receives a 10 ms
edge fade to prevent accumulated A/V drift and waveform-click artifacts.

After Claude selects ranges, AutoEdit-Lite runs a deterministic editorial-score
refinement pass to trim clearly off-topic or repeated transcript slices from
selected spans. If the edit is under-length, it can fill toward the target with
high-scoring, non-overlapping transcript segments. `accuracy_report.json`
records both refined and filled segment counts.
Near-duplicate takes are compared by clarity, speaker confidence, transcription
confidence, and filler level so the cleaner delivery is preferred instead of
automatically keeping the first take.
Pause detection defaults to 0.5 seconds across both CLI and analysis entry
points. Strong vocalized fillers are detected in English and Devanagari
Marathi/Hindi, including tokens followed by a danda. Editorial filler scoring
matches complete words and phrases, so clean words such as "human" and
"likely" are not mistaken for "um" or "like", and repeated filler occurrences
receive a stronger penalty.
Sarvam jobs explicitly request word timestamps. Those words are split into
editorial utterances at sentence boundaries, meaningful pauses, and a
12-second maximum, giving keep/remove scoring practical granularity while
preserving precise cut points. Each job uses an isolated download directory so
an older transcript cannot be reused accidentally.
For non-medical videos, the main topic is inferred from recurring content terms
across the transcript rather than one-time opener words. Medical topic profiles
require a domain-specific anchor with repeated transcript support, so an
isolated domain tangent or generic words such as "process" and "support" do not
incorrectly control the video's main-topic scoring.
If Claude returns too few usable ranges, the same score-based fill pass can
recover a first-pass story from the strongest transcript segments instead of
failing the edit outright.
When Claude has already selected a core story, any duration fill is scored
against that surviving story topic rather than unrelated raw-footage tangents.
Strong missing content is added only when it moves the selected duration closer
to the configured target. Duration enforcement avoids removing a long weak
segment when doing so would unnecessarily drop the story below the accepted
minimum and a valid shorter removal exists. It also avoids removing a premise
when that would leave a selected context-dependent conclusion without its
antecedent.
Repetition and false-start detection preserve high-overlap contrasts when one
statement introduces negation, including common contractions such as "isn't".
This prevents a corrective sentence from being removed as a duplicate and
changing the speaker's meaning.
When word-level probabilities are available, transcript confidence is included
in the editorial scores so uncertain words lower clarity/speaker-confidence and
are avoided by the score-based fallback. `accuracy_report.json` also records
average word confidence and low-confidence segment counts. Supported
context-dependent conclusions remain eligible for score-based filling when
their preceding thought is selected, so fallback stories can keep a necessary
premise and conclusion together.
Word-timestamped subtitles include only complete words inside each retained
range, so captions do not display words that the video cuts partway through.
Both post-selection refinement and fallback filling avoid English, Marathi, and Hindi continuation fragments
that begin with context-dependent phrases such as "because", "कारण", or
"क्योंकि" when their preceding thought is not selected.

### Measuring Human-Editor Agreement

To measure the 95% target, pass a labelled human edit file:

```
python main.py --input input\video.mp4 --human-decisions human_labels.json
```

Supported label shapes:

```
{
  "segments_to_keep": [{"start": 4.1, "end": 9.2}],
  "story_meaning_preserved": true
}
```

or:

```
{
  "edit_decisions": [
    {"start": 0.0, "end": 4.0, "decision": "remove"},
    {"start": 4.0, "end": 9.0, "decision": "keep"}
  ],
  "story_meaning_preserved": true
}
```

The measured result is written under `human_editor_agreement` in `accuracy_report.json`.
Keep/remove agreement is duration-weighted over atomic timeline intervals
formed from both the system and human boundaries. It is class-balanced so a
system cannot score highly merely by removing almost everything, cannot omit a
human-labelled region, and cannot change its score by splitting one decision
into many transcript rows. Timeline gaps covered by neither source are not
scored. Cut boundaries use one-to-one system/human matching, so duplicate
system cuts cannot claim the same human cut twice and missed human cuts count
against the score. Empty, malformed, or conflicting human label files are
marked invalid.

`overall_agreement` reports the numeric keep/remove and cut-boundary agreement.
The stricter `meets_95_percent_target` flag also requires
`story_meaning_preserved: true`, because timestamp agreement alone does not
prove that the final 90-second story preserves the speaker's meaning.
`edit_decisions.json` preserves each final selected range as `cut_start` and
`cut_end`. When a cut selects only part of a transcript segment, the decision
artifact splits that segment into explicit remove/keep/remove intervals instead
of incorrectly assigning one decision to the entire transcript row.
`accuracy_report.json` records duration error and whether the selected story is
inside the configured 85%-110% target range.

For a labelled evaluation set, create a manifest that points to each run's
`edit_decisions.json` and the matching human label file:

```
{
  "cases": [
    {
      "name": "ivf-video-001",
      "system_decisions": "ivf-video-001/edit_decisions.json",
      "human_decisions": "ivf-video-001/human_labels.json"
    }
  ]
}
```

Then run:

```
python accuracy_dataset.py --manifest labelled_dataset.json --output dataset_accuracy_report.json
```

The aggregate pass/fail for the 95% target is written to
`aggregate.meets_95_percent_target`. Dataset aggregation pools the
duration-weighted balanced keep/remove confusion matrix and fails the target if
any case has invalid labels, lacks a story-meaning assessment, or is judged not
to preserve meaning.

`broll_suggestions.json` includes source-video timestamps and
edited-timeline timestamps so suggested stock footage can be placed against
the final 90-second sequence without guessing. Unmatched general-topic speech
uses topic-derived stock-footage search phrases instead of clinic-specific
fallback suggestions. Multi-concept kept ranges emit separate suggestions for
each overlapping transcript utterance instead of one broad cue at the start.
With word timestamps, suggestions use only complete retained words and their
exact source and edited-timeline boundaries. Negated statements use neutral
explanatory search terms rather than affirmative promotional service visuals.

### Validating Output Video

Every normal FFmpeg run probes the final artifact automatically. Geometry,
audio presence, duration, and audio/video stream-duration drift checks are
stored under `output_validation` in `accuracy_report.json`. Drift above 100 ms
fails validation. A damaged or unreadable export records a failed probe without
preventing the required JSON artifacts from being written.
The duration check enforces the same 85%-110% target range used by story
accuracy reporting, so severely short exports cannot be marked valid.

The validator can also be run separately:

```
python output_validation.py --video output\edited_90s.mp4 --target-duration 90 --aspect-ratio 9:16 --output output\output_validation_report.json
```

The report checks that the file exists, has video and audio streams, is
1080x1920 for 9:16 output, and stays within the configured duration budget.

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
