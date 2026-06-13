"""
output_validation.py

Small ffprobe-based validator for final video artifacts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


TARGET_DIMENSIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}
MAX_AUDIO_VIDEO_SYNC_DELTA_SECONDS = 0.1
MIN_DURATION_RATIO = 0.85


def _check(passed: bool, details: dict | None = None) -> dict:
    return {"passed": bool(passed), **(details or {})}


def _ffprobe(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height,duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    return json.loads(result.stdout)


def validate_output_video(
    video_path: str | Path,
    target_duration_seconds: int = 90,
    aspect_ratio: str = "9:16",
    duration_slack_ratio: float = 0.10,
) -> dict:
    path = Path(video_path)
    expected_width, expected_height = TARGET_DIMENSIONS[aspect_ratio]

    report = {
        "path": str(path),
        "valid": False,
        "checks": {
            "exists": _check(path.exists()),
        },
    }
    if not path.exists():
        return report

    metadata = _ffprobe(path)
    streams = metadata.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(metadata.get("format", {}).get("duration") or 0.0)
    min_duration = target_duration_seconds * MIN_DURATION_RATIO
    max_duration = target_duration_seconds * (1.0 + duration_slack_ratio)

    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    video_duration = float(video_stream.get("duration") or duration) if video_stream else 0.0
    audio_duration = float(audio_stream.get("duration") or duration) if audio_stream else 0.0
    sync_delta = abs(video_duration - audio_duration) if video_stream and audio_stream else None

    report["metadata"] = {
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "target_duration_seconds": target_duration_seconds,
        "min_duration_seconds": round(min_duration, 3),
        "max_duration_seconds": round(max_duration, 3),
        "video_duration_seconds": round(video_duration, 3),
        "audio_duration_seconds": round(audio_duration, 3) if audio_stream else None,
    }
    report["checks"].update({
        "has_video": _check(video_stream is not None),
        "has_audio": _check(audio_stream is not None),
        "audio_video_sync": _check(
            sync_delta is not None and sync_delta <= MAX_AUDIO_VIDEO_SYNC_DELTA_SECONDS,
            {
                "delta_seconds": round(sync_delta, 3) if sync_delta is not None else None,
                "max_delta_seconds": MAX_AUDIO_VIDEO_SYNC_DELTA_SECONDS,
            },
        ),
        "geometry": _check(
            width == expected_width and height == expected_height,
            {
                "expected_width": expected_width,
                "expected_height": expected_height,
                "actual_width": width,
                "actual_height": height,
            },
        ),
        "duration": _check(
            min_duration <= duration <= max_duration,
            {
                "actual_seconds": round(duration, 3),
                "min_seconds": round(min_duration, 3),
                "max_seconds": round(max_duration, 3),
            },
        ),
    })
    report["valid"] = all(check["passed"] for check in report["checks"].values())
    return report


def write_output_validation_report(
    video_path: str | Path,
    output_path: str | Path,
    target_duration_seconds: int = 90,
    aspect_ratio: str = "9:16",
) -> dict:
    report = validate_output_video(
        video_path=video_path,
        target_duration_seconds=target_duration_seconds,
        aspect_ratio=aspect_ratio,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="output-validation",
        description="Validate an AutoEdit-Lite output video with ffprobe.",
    )
    parser.add_argument("--video", required=True, help="Edited video path.")
    parser.add_argument(
        "--output",
        default="output_validation_report.json",
        help="Where to write validation JSON.",
    )
    parser.add_argument("--target-duration", type=int, default=90)
    parser.add_argument("--aspect-ratio", choices=sorted(TARGET_DIMENSIONS), default="9:16")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = write_output_validation_report(
        video_path=args.video,
        output_path=args.output,
        target_duration_seconds=args.target_duration,
        aspect_ratio=args.aspect_ratio,
    )
    print(f"Wrote {args.output}")
    print(f"Valid output: {report['valid']}")


if __name__ == "__main__":
    main()
