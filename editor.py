"""
editor.py

Cuts the input video at the specified segments and stitches them into a
single output file using FFmpeg's concat filter with re-encoding.

WHY re-encode instead of stream copy:
  Stream copy (-c copy) only works correctly when every cut point falls
  exactly on a video keyframe. Claude's timestamps (e.g. 6.1s, 12.0s) will
  almost never align with keyframes, causing black frames and audio desync.
  Re-encoding with libx264/aac is the correct, reliable approach.
"""

import subprocess
import sys
from pathlib import Path


def _has_audio_stream(video_path: Path) -> bool:
    """Return True if the video file contains at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return bool(result.stdout.strip())


def _get_video_duration(video_path: Path) -> float:
    """Use ffprobe to get the total duration of a video in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def cut_video(
    input_path: str,
    segments: list[dict],
    output_path: str,
    dry_run: bool = False,
) -> float:
    """
    Cut the input video to the given segments and stitch into output_path.

    Uses FFmpeg's concat filter for frame-accurate cuts with re-encoding.
    Video: libx264, preset fast, CRF 20 (good quality, reasonable speed)
    Audio: aac, 192k bitrate
    Both streams are synced with -async 1.

    Parameters
    ----------
    input_path : str
        Path to the original video file.
    segments : list[dict]
        List of {"start": float, "end": float} dicts.
    output_path : str
        Path for the output edited video.
    dry_run : bool
        If True, print the FFmpeg command but do not execute it.

    Returns
    -------
    float
        Duration of the output video in seconds (0.0 if dry_run).
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not segments:
        print("  [WARNING] No segments to keep — output video not created.")
        return 0.0

    n = len(segments)
    has_audio = _has_audio_stream(input_path)
    if not has_audio:
        print("  [NOTE] Source video has no audio stream — output will be video-only.")

    # ── Build the filter_complex string ───────────────────────────────────
    # For each segment: trim video (and audio if present), reset timestamps,
    # then concat all segments. Audio path is conditional on stream existence.
    filter_parts = []
    stream_labels = []

    for i, seg in enumerate(segments):
        start = seg["start"]
        end = seg["end"]
        filter_parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
        )
        if has_audio:
            filter_parts.append(
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
            )
            stream_labels.append(f"[v{i}][a{i}]")
        else:
            stream_labels.append(f"[v{i}]")

    concat_inputs = "".join(stream_labels)
    if has_audio:
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]")
    else:
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[outv]")

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg",
        "-y",                          # overwrite output
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-movflags", "+faststart",     # put metadata at front for web playback
        str(output_path),
    ]

    if has_audio:
        # Insert audio map + codec before the output path
        cmd[-1:] = [
            "-map", "[outa]",
            "-c:a", "aac",
            "-b:a", "192k",
            "-async", "1",
            str(output_path),
        ]

    if dry_run:
        print("  [DRY RUN] FFmpeg command that would run:")
        print("  " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
        return 0.0

    print(f"  Cutting {n} segment(s) and stitching into: {output_path.name}")
    print("  (Re-encoding video — this may take a minute...)")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"\n[ERROR] FFmpeg failed during video cutting.")
        print(f"  FFmpeg output:\n{result.stderr[-800:]}")
        sys.exit(1)

    duration = _get_video_duration(output_path)
    print(f"  Video cutting complete.")
    return duration
