import json
import subprocess

import output_validation


def _ffprobe_result(payload):
    return subprocess.CompletedProcess(
        ["ffprobe"],
        0,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_validate_output_video_accepts_vertical_90s_video_with_audio(monkeypatch, tmp_path):
    video_path = tmp_path / "edited_90s.mp4"
    video_path.write_bytes(b"video")

    def fake_run(cmd, capture_output, text, timeout):
        return _ffprobe_result({
            "format": {"duration": "89.8"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "duration": "89.80"},
                {"codec_type": "audio", "duration": "89.76"},
            ],
        })

    monkeypatch.setattr(output_validation.subprocess, "run", fake_run)

    report = output_validation.validate_output_video(
        video_path,
        target_duration_seconds=90,
        aspect_ratio="9:16",
    )

    assert report["valid"] is True
    assert report["checks"]["geometry"]["passed"] is True
    assert report["checks"]["duration"]["passed"] is True
    assert report["checks"]["has_audio"]["passed"] is True
    assert report["checks"]["audio_video_sync"]["passed"] is True


def test_validate_output_video_rejects_wrong_geometry_missing_audio_and_overlong_duration(monkeypatch, tmp_path):
    video_path = tmp_path / "edited_90s.mp4"
    video_path.write_bytes(b"video")

    def fake_run(cmd, capture_output, text, timeout):
        return _ffprobe_result({
            "format": {"duration": "110.0"},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080, "duration": "110.0"},
            ],
        })

    monkeypatch.setattr(output_validation.subprocess, "run", fake_run)

    report = output_validation.validate_output_video(
        video_path,
        target_duration_seconds=90,
        aspect_ratio="9:16",
    )

    assert report["valid"] is False
    assert report["checks"]["geometry"]["passed"] is False
    assert report["checks"]["duration"]["passed"] is False
    assert report["checks"]["has_audio"]["passed"] is False


def test_validate_output_video_rejects_audio_video_duration_drift(monkeypatch, tmp_path):
    video_path = tmp_path / "edited_90s.mp4"
    video_path.write_bytes(b"video")

    def fake_run(cmd, capture_output, text, timeout):
        return _ffprobe_result({
            "format": {"duration": "90.0"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "duration": "90.0"},
                {"codec_type": "audio", "duration": "89.1"},
            ],
        })

    monkeypatch.setattr(output_validation.subprocess, "run", fake_run)

    report = output_validation.validate_output_video(video_path)

    assert report["checks"]["audio_video_sync"]["passed"] is False
    assert report["checks"]["audio_video_sync"]["delta_seconds"] == 0.9
    assert report["valid"] is False


def test_validate_output_video_rejects_severely_under_length_export(monkeypatch, tmp_path):
    video_path = tmp_path / "edited_90s.mp4"
    video_path.write_bytes(b"video")

    def fake_run(cmd, capture_output, text, timeout):
        return _ffprobe_result({
            "format": {"duration": "5.0"},
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "duration": "5.0"},
                {"codec_type": "audio", "duration": "5.0"},
            ],
        })

    monkeypatch.setattr(output_validation.subprocess, "run", fake_run)

    report = output_validation.validate_output_video(
        video_path,
        target_duration_seconds=90,
        aspect_ratio="9:16",
    )

    assert report["checks"]["duration"]["passed"] is False
    assert report["checks"]["duration"]["min_seconds"] == 76.5
    assert report["valid"] is False
