"""
main.py

AutoEdit-Lite — AI-powered automatic video rough-cut tool.

Usage:
  python main.py --input input/video.mp4
  python main.py --input input/video.mp4 --model medium --quality balanced
  python main.py --input input/video.mp4 --mode premiere
  python main.py --input input/video.mp4 --dry-run
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Windows cp1252 consoles crash on Unicode chars like -> and --. Force UTF-8.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


# ── Supported input formats ────────────────────────────────────────────────
VALID_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}

# ── Defaults ──────────────────────────────────────────────────────────────
DEFAULT_MODEL = "medium"
DEFAULT_QUALITY = "balanced"
DEFAULT_OUTPUT = "output/edited_90s.mp4"
DEFAULT_MODE = "ffmpeg"
DEFAULT_TARGET_DURATION = 90      # seconds
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_PLATFORM = "reels"
DEFAULT_LANGUAGE = "mr-IN"
DEFAULT_GAP_THRESHOLD = 0.5


def _get_video_duration_seconds(path: Path) -> float:
    """Use ffprobe to get the video duration in seconds."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _format_duration(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _validate_final_output(output_path: Path, target_duration: int, aspect_ratio: str) -> dict:
    from output_validation import validate_output_video

    try:
        return validate_output_video(
            video_path=output_path,
            target_duration_seconds=target_duration,
            aspect_ratio=aspect_ratio,
        )
    except Exception as exc:
        return {
            "path": str(output_path),
            "valid": False,
            "checks": {
                "probe": {
                    "passed": False,
                    "error": str(exc),
                },
            },
        }


def _ensure_dirs(output_path: Path) -> None:
    """Create the output folder and a logs subfolder next to it."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    (output_path.parent / "logs").mkdir(parents=True, exist_ok=True)


def _validate_input(input_path: Path) -> None:
    """Exit with a clear error if the input file is invalid."""
    if not input_path.exists():
        print(f"\n[ERROR] Input file not found: {input_path}")
        print("  Make sure the file exists and the path is correct.\n")
        sys.exit(1)
    if not input_path.is_file():
        print(f"\n[ERROR] Input path is not a file: {input_path}\n")
        sys.exit(1)
    if input_path.suffix.lower() not in VALID_EXTENSIONS:
        print(f"\n[ERROR] Unsupported file format: {input_path.suffix}")
        print(f"  Supported formats: {', '.join(sorted(VALID_EXTENSIONS))}\n")
        sys.exit(1)


def _check_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    # Bundled-installer fallback. When this script is shipped via the Windows
    # installer, ffmpeg lives at {install}\ff\bin\ alongside the {install}\app\
    # directory that holds this file. The CLI launcher prepends that dir to
    # PATH already, but the Premiere CEP panel spawns Python via Node's
    # child_process.spawn which doesn't, so without this fallback the panel
    # sees no ffmpeg on a clean machine that lacks a system install.
    bundled_bin = Path(__file__).resolve().parent.parent / "ff" / "bin"
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    if (bundled_bin / exe_name).exists():
        os.environ["PATH"] = str(bundled_bin) + os.pathsep + os.environ.get("PATH", "")
        if shutil.which("ffmpeg") and shutil.which("ffprobe"):
            return

    print("\n[ERROR] FFmpeg or ffprobe was not found on your PATH.")
    print("  Windows: https://github.com/BtbN/FFmpeg-Builds/releases")
    print("           Download, unzip, and add the 'bin' folder to your PATH.")
    print("  Mac:     brew install ffmpeg")
    print("  Then open a NEW terminal and try again.\n")
    sys.exit(1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="autoedit-lite",
        description="AutoEdit-Lite: AI-powered automatic video rough-cut tool",
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to your input video (e.g. input/video.mp4)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size. Larger = more accurate but slower. (default: medium)",
    )
    parser.add_argument(
        "--quality", default=DEFAULT_QUALITY,
        choices=["light", "balanced", "aggressive"],
        help="How aggressively Claude edits. (default: balanced)",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Output video path. (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--mode", default=DEFAULT_MODE,
        choices=["ffmpeg", "premiere"],
        help=(
            "Output mode. 'ffmpeg' cuts the video locally (default). "
            "'premiere' exports an FCP7 XML timeline for Premiere Pro instead."
        ),
    )
    parser.add_argument(
        "--target-duration", type=int, default=DEFAULT_TARGET_DURATION,
        metavar="SECONDS",
        help=(
            f"Target length of the final cut in seconds. "
            f"Claude will aim for this duration. (default: {DEFAULT_TARGET_DURATION})"
        ),
    )
    parser.add_argument(
        "--aspect-ratio", default=DEFAULT_ASPECT_RATIO,
        choices=["9:16", "16:9"],
        help=(
            "Output aspect ratio. '9:16' for vertical (Instagram Reels, TikTok, Shorts). "
            f"'16:9' for horizontal (default: {DEFAULT_ASPECT_RATIO})"
        ),
    )
    parser.add_argument(
        "--platform", default=DEFAULT_PLATFORM,
        choices=["reels", "tiktok", "shorts", "general"],
        help=(
            "Target platform — used to tailor Claude's editing style and pacing. "
            f"(default: {DEFAULT_PLATFORM})"
        ),
    )
    parser.add_argument(
        "--language", default=DEFAULT_LANGUAGE,
        metavar="CODE",
        help=(
            "Speech language code. Sarvam AI is preferred for Indian language codes "
            "such as 'mr-IN', 'hi-IN', and 'en-IN' when SARVAM_API_KEY is set. "
            f"Default: {DEFAULT_LANGUAGE}."
        ),
    )
    parser.add_argument(
        "--gap-threshold", type=float, default=DEFAULT_GAP_THRESHOLD,
        metavar="SECONDS",
        help=(
            "Silence gap (in seconds) treated as a filler pause and removed. "
            "Lower values remove shorter pauses (e.g. 0.5 for fast-paced content). "
            f"Default: {DEFAULT_GAP_THRESHOLD}"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Transcribe and get Claude's plan, but do NOT cut the video.",
    )
    parser.add_argument(
        "--human-decisions",
        default=None,
        metavar="JSON",
        help=(
            "Optional human editor labels JSON. When supplied, accuracy_report.json "
            "includes measured keep/remove and cut-boundary agreement."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    # ── Startup checks ─────────────────────────────────────────────────────
    _ensure_dirs(output_path)
    _check_ffmpeg_available()
    _validate_input(input_path)

    print()
    print("=" * 60)
    print("  AutoEdit-Lite")
    print("=" * 60)
    print(f"  Input   : {input_path}")
    print(f"  Model   : {args.model}")
    print(f"  Quality : {args.quality}")
    lang_display = args.language if args.language else "auto"
    print(f"  Target  : {args.target_duration}s  |  {args.aspect_ratio}  |  {args.platform}")
    print(f"  Language: {lang_display}  |  Gap threshold: {args.gap_threshold}s")
    if args.dry_run:
        print("  Mode    : DRY RUN (no video cutting)")
    elif args.mode == "premiere":
        premiere_xml_path = output_path.with_suffix(".xml")
        print(f"  Mode    : PREMIERE (FCP7 XML export)")
        print(f"  Output  : {premiere_xml_path}")
    else:
        print(f"  Output  : {output_path}")
    print("=" * 60)
    print()

    # ── Step 1: Get original video duration ───────────────────────────────
    original_duration = _get_video_duration_seconds(input_path)
    if original_duration <= 0:
        print("[ERROR] Could not read video duration. Is the file valid?")
        sys.exit(1)

    # ── Step 2: Transcribe ─────────────────────────────────────────────────
    print("[1/4] Transcribing audio...")
    from transcribe import transcribe_video
    transcript_segments = transcribe_video(
        video_path=str(input_path),
        model_name=args.model,
        logs_dir=str(output_path.parent / "logs"),
        language=args.language,
    )

    if not transcript_segments:
        print("[ERROR] Transcription returned no segments. Is there speech in the video?")
        sys.exit(1)

    print(f"  Found {len(transcript_segments)} transcript segment(s).")
    print()

    transcript_log_path = output_path.parent / "logs" / "transcript.json"
    transcription_provider = "unknown"
    detected_language = args.language
    if transcript_log_path.exists():
        try:
            transcript_log = json.loads(transcript_log_path.read_text(encoding="utf-8"))
            transcription_provider = transcript_log.get("provider", transcription_provider)
            detected_language = transcript_log.get("language", detected_language)
        except Exception:
            pass

    # ── Step 3: Analyze with Claude ────────────────────────────────────────
    print("[2/4] Asking Claude for editing decisions...")
    from analyze import analyze_transcript
    kept_segments = analyze_transcript(
        segments=transcript_segments,
        quality_mode=args.quality,
        video_duration=original_duration,
        target_duration=args.target_duration,
        aspect_ratio=args.aspect_ratio,
        platform=args.platform,
        logs_dir=str(output_path.parent / "logs"),
        prompts_dir=str(Path(__file__).parent / "prompts"),
        gap_threshold=args.gap_threshold,
    )

    if not kept_segments:
        print("[WARNING] Claude returned no segments to keep.")
        print("  Check logs/claude_raw.txt to see what Claude said.")
        if not args.dry_run:
            print("  No output video created.")
        sys.exit(0)

    kept_duration = sum(s["end"] - s["start"] for s in kept_segments)
    print(f"  Claude selected {len(kept_segments)} segment(s) to keep.")
    print()

    # ── Step 4a: Output (skip in dry-run; choose ffmpeg or premiere mode) ───
    if args.dry_run:
        print("[3/4] Skipping video cut (--dry-run mode).")
        print()
        print("[4/4] Skipping subtitle generation (--dry-run mode).")
        print()
    elif args.mode == "premiere":
        premiere_xml_path = output_path.with_suffix(".xml")
        print("[3/4] Exporting Premiere Pro XML timeline...")
        from xml_export import export_premiere_xml
        xml_width, xml_height = (1080, 1920) if args.aspect_ratio == "9:16" else (1920, 1080)
        export_premiere_xml(
            input_video_path=str(input_path),
            segments=kept_segments,
            output_xml_path=str(premiere_xml_path),
            width=xml_width,
            height=xml_height,
            target_fps=30,
        )
        print()

        srt_path = output_path.with_suffix(".srt")
        print("[4/4] Generating subtitles...")
        from captions import generate_srt
        generate_srt(
            transcript_segments=transcript_segments,
            kept_segments=kept_segments,
            output_path=str(srt_path),
        )
        print()

        # ── LosslessCut CSV (bonus export — no extra deps) ─────────────────
        csv_path = output_path.with_name(output_path.stem + "_cuts.csv")
        from losslesscut_export import export_losslesscut_csv
        export_losslesscut_csv(
            segments=kept_segments,
            output_csv_path=str(csv_path),
        )
        print()
    else:
        print("[3/4] Cutting and stitching video...")
        from editor import cut_video
        actual_output_duration = cut_video(
            input_path=str(input_path),
            segments=kept_segments,
            output_path=str(output_path),
            dry_run=False,
            aspect_ratio=args.aspect_ratio,
        )
        print()

        # ── Step 4b: Generate subtitles ────────────────────────────────────
        srt_path = output_path.with_suffix(".srt")
        print("[4/4] Generating subtitles...")
        from captions import generate_srt
        generate_srt(
            transcript_segments=transcript_segments,
            kept_segments=kept_segments,
            output_path=str(srt_path),
        )
        print()

        # ── LosslessCut CSV (bonus export — no extra deps) ─────────────────
        csv_path = output_path.with_name(output_path.stem + "_cuts.csv")
        from losslesscut_export import export_losslesscut_csv
        export_losslesscut_csv(
            segments=kept_segments,
            output_csv_path=str(csv_path),
        )
        print()

    # ── Final summary ──────────────────────────────────────────────────────
    output_validation = {
        "valid": None,
        "status": "not_applicable",
        "reason": "No rendered FFmpeg video was produced.",
    }
    if not args.dry_run and args.mode == "ffmpeg":
        print("[Validation] Probing final video geometry, audio, and duration...")
        output_validation = _validate_final_output(
            output_path=output_path,
            target_duration=args.target_duration,
            aspect_ratio=args.aspect_ratio,
        )
        print(f"  Valid final video: {output_validation['valid']}")
        print()

    print("[Artifacts] Writing edit decision, B-roll, and accuracy report JSON...")
    from accuracy_outputs import write_accuracy_outputs
    write_accuracy_outputs(
        transcript_segments=transcript_segments,
        kept_segments=kept_segments,
        output_video_path=str(output_path),
        original_duration=original_duration,
        target_duration=args.target_duration,
        transcription_provider=transcription_provider,
        language=detected_language,
        gap_threshold=args.gap_threshold,
        human_decisions_path=args.human_decisions,
        output_validation=output_validation,
    )
    print(f"  Edit decisions : {output_path.parent / 'edit_decisions.json'}")
    print(f"  B-roll ideas    : {output_path.parent / 'broll_suggestions.json'}")
    print(f"  Accuracy report : {output_path.parent / 'accuracy_report.json'}")
    print()

    print("=" * 60)
    print("  DONE")
    print("=" * 60)

    original_fmt = _format_duration(original_duration)
    kept_fmt = _format_duration(kept_duration)
    reduction_pct = (1.0 - kept_duration / original_duration) * 100 if original_duration > 0 else 0.0

    print(f"  Original duration : {original_fmt}")
    print(f"  Edited duration   : {kept_fmt}")
    print(f"  Reduction         : {reduction_pct:.0f}% shorter")
    print(f"  Segments kept     : {len(kept_segments)}")
    print()

    if args.dry_run:
        print("  (Dry run - video and subtitles were not written)")
        print(f"  Edit decisions : {output_path.parent / 'edit_decisions.json'}")
        print(f"  B-roll ideas    : {output_path.parent / 'broll_suggestions.json'}")
        print(f"  Accuracy report : {output_path.parent / 'accuracy_report.json'}")
    elif args.mode == "premiere":
        csv_path = output_path.with_name(output_path.stem + "_cuts.csv")
        print(f"  Premiere XML  : {output_path.with_suffix('.xml')}")
        print(f"  Subtitles     : {output_path.with_suffix('.srt')}")
        print(f"  LosslessCut   : {csv_path}")
        print(f"  Edit decisions: {output_path.parent / 'edit_decisions.json'}")
        print(f"  B-roll ideas  : {output_path.parent / 'broll_suggestions.json'}")
        print(f"  Accuracy report: {output_path.parent / 'accuracy_report.json'}")
        print()
        print("  Import into Premiere : File -> Import -> select the .xml file")
        print("  Lossless rough cut   : Drag the .csv into LosslessCut")
    else:
        csv_path = output_path.with_name(output_path.stem + "_cuts.csv")
        print(f"  Output video  : {output_path}")
        print(f"  Subtitles     : {output_path.with_suffix('.srt')}")
        print(f"  LosslessCut   : {csv_path}")
        print(f"  Edit decisions: {output_path.parent / 'edit_decisions.json'}")
        print(f"  B-roll ideas  : {output_path.parent / 'broll_suggestions.json'}")
        print(f"  Accuracy report: {output_path.parent / 'accuracy_report.json'}")
        print()
        print("  Lossless rough cut   : Drag the .csv into LosslessCut")

    print(f"  Debug logs    : logs/")
    print("=" * 60)
    print()

    print(f"Reduced {original_fmt} -> {kept_fmt} ({reduction_pct:.0f}% shorter)")


if __name__ == "__main__":
    main()
