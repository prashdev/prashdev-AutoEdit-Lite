import subprocess

import editor


def _capture_cut_command(monkeypatch, aspect_ratio):
    captured = {}

    monkeypatch.setattr(editor, "_has_audio_stream", lambda path: True)
    monkeypatch.setattr(editor, "_get_video_duration", lambda path: 9.0)

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(editor.subprocess, "run", fake_run)

    result = editor.cut_video(
        input_path="input.mp4",
        segments=[{"start": 1.0, "end": 4.0}, {"start": 6.0, "end": 9.0}],
        output_path="output/edited_90s.mp4",
        aspect_ratio=aspect_ratio,
    )

    return result, captured["cmd"]


def test_cut_video_enforces_vertical_9_16_geometry_without_padding(monkeypatch):
    duration, cmd = _capture_cut_command(monkeypatch, "9:16")

    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert duration == 9.0
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in filter_complex
    assert "crop=1080:1920" in filter_complex
    assert "pad=" not in filter_complex
    assert "-map" in cmd
    assert "[outv]" in cmd


def test_cut_video_enforces_horizontal_16_9_geometry_without_padding(monkeypatch):
    _, cmd = _capture_cut_command(monkeypatch, "16:9")

    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=1920:1080:force_original_aspect_ratio=increase" in filter_complex
    assert "crop=1920:1080" in filter_complex
    assert "pad=" not in filter_complex


def test_cut_video_resamples_each_trimmed_audio_segment_for_sync(monkeypatch):
    _, cmd = _capture_cut_command(monkeypatch, "9:16")

    filter_complex = cmd[cmd.index("-filter_complex") + 1]

    assert filter_complex.count("aresample=async=1:first_pts=0") == 2
    assert "-async" not in cmd


def test_cut_video_applies_short_audio_edge_fades_to_avoid_clicks(monkeypatch):
    _, cmd = _capture_cut_command(monkeypatch, "9:16")

    filter_complex = cmd[cmd.index("-filter_complex") + 1]

    assert filter_complex.count("afade=t=in:st=0:d=0.01") == 2
    assert "afade=t=out:st=2.99:d=0.01[a0]" in filter_complex
