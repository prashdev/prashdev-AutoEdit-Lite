"""
Tests for helper functions in main.py.

These functions are pure logic — no video file, no FFmpeg, no API needed.
"""

from main import _format_duration
from main import _parse_args
from main import _validate_final_output


class TestFormatDuration:
    def test_seconds_only(self):
        assert _format_duration(45) == "0:45"

    def test_one_minute(self):
        assert _format_duration(60) == "1:00"

    def test_minutes_and_seconds(self):
        assert _format_duration(90) == "1:30"

    def test_zero(self):
        assert _format_duration(0) == "0:00"

    def test_exactly_one_hour(self):
        assert _format_duration(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert _format_duration(3661) == "1:01:01"

    def test_long_video(self):
        assert _format_duration(7384) == "2:03:04"

    def test_float_is_truncated(self):
        # float seconds should be truncated, not rounded
        assert _format_duration(90.9) == "1:30"


def test_parse_args_accepts_human_decisions(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["autoedit-lite", "--input", "input.mp4", "--human-decisions", "human_labels.json"],
    )

    args = _parse_args()

    assert args.human_decisions == "human_labels.json"


def test_validate_final_output_probes_exported_video(monkeypatch, tmp_path):
    calls = []
    expected = {"valid": True, "checks": {"geometry": {"passed": True}}}

    monkeypatch.setattr(
        "output_validation.validate_output_video",
        lambda video_path, target_duration_seconds, aspect_ratio: calls.append(
            (video_path, target_duration_seconds, aspect_ratio)
        ) or expected,
    )

    report = _validate_final_output(tmp_path / "edited_90s.mp4", 90, "9:16")

    assert report == expected
    assert calls == [(tmp_path / "edited_90s.mp4", 90, "9:16")]


def test_validate_final_output_records_probe_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "output_validation.validate_output_video",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("damaged export")),
    )

    report = _validate_final_output(tmp_path / "edited_90s.mp4", 90, "9:16")

    assert report["valid"] is False
    assert report["checks"]["probe"]["passed"] is False
    assert report["checks"]["probe"]["error"] == "damaged export"
