"""
Tests for xml_export.py.

No real video or Premiere needed — we feed fake segments and verify the
XML file is created, is valid XML, and can be read back by OpenTimelineIO.
"""

import xml.etree.ElementTree as ET
from unittest.mock import patch

import opentimelineio as otio
import pytest

from xml_export import _detect_fps, _inject_sequence_settings, _to_file_uri, export_premiere_xml


FAKE_SEGMENTS = [
    {"start": 0.0, "end": 5.0, "reason": "strong intro"},
    {"start": 10.0, "end": 20.0, "reason": "main point"},
]


def _export(tmp_path, segments=None):
    """Helper: run export with mocked fps=25 and return the xml path."""
    out = tmp_path / "output.xml"
    with patch("xml_export._detect_fps", return_value=25.0):
        export_premiere_xml("/fake/video.mp4", segments or FAKE_SEGMENTS, str(out))
    return out


class TestToFileUri:
    def test_produces_file_scheme(self):
        uri = _to_file_uri("/tmp/video.mp4")
        assert uri.startswith("file://")

    def test_absolute_path_encoded(self):
        uri = _to_file_uri("/Users/foo/bar.mp4")
        assert "foo" in uri
        assert "bar.mp4" in uri


class TestDetectFps:
    def test_fallback_when_ffprobe_fails(self):
        with patch("xml_export.subprocess.run", side_effect=Exception("not found")):
            assert _detect_fps("fake.mp4") == 25.0

    def test_parses_fraction_format(self):
        # ffprobe returns "30000/1001" for 29.97 fps
        mock = type("R", (), {"stdout": "30000/1001", "returncode": 0})()
        with patch("xml_export.subprocess.run", return_value=mock):
            assert abs(_detect_fps("fake.mp4") - 29.970) < 0.01

    def test_parses_integer_format(self):
        mock = type("R", (), {"stdout": "25", "returncode": 0})()
        with patch("xml_export.subprocess.run", return_value=mock):
            assert _detect_fps("fake.mp4") == 25.0

    def test_fallback_on_empty_output(self):
        mock = type("R", (), {"stdout": "", "returncode": 0})()
        with patch("xml_export.subprocess.run", return_value=mock):
            assert _detect_fps("fake.mp4") == 25.0


class TestExportPremiereXml:
    def test_file_is_created(self, tmp_path):
        out = _export(tmp_path)
        assert out.exists()

    def test_output_is_valid_xml(self, tmp_path):
        out = _export(tmp_path)
        ET.parse(str(out))  # raises if invalid

    def test_otio_can_read_it_back(self, tmp_path):
        out = _export(tmp_path)
        timeline = otio.adapters.read_from_file(str(out), adapter_name="fcp_xml")
        assert isinstance(timeline, otio.schema.Timeline)

    def test_correct_clip_count(self, tmp_path):
        out = _export(tmp_path)
        timeline = otio.adapters.read_from_file(str(out), adapter_name="fcp_xml")
        video_tracks = [t for t in timeline.tracks if t.kind == otio.schema.TrackKind.Video]
        assert len(video_tracks) >= 1
        clips = [c for c in video_tracks[0] if isinstance(c, otio.schema.Clip)]
        assert len(clips) == len(FAKE_SEGMENTS)

    def test_empty_segments_creates_file(self, tmp_path):
        out = _export(tmp_path, segments=[])
        assert out.exists()

    def test_zero_duration_segment_is_skipped(self, tmp_path):
        segs = [
            {"start": 5.0, "end": 5.0, "reason": "zero duration"},
            {"start": 10.0, "end": 15.0, "reason": "valid"},
        ]
        out = _export(tmp_path, segments=segs)
        timeline = otio.adapters.read_from_file(str(out), adapter_name="fcp_xml")
        video_tracks = [t for t in timeline.tracks if t.kind == otio.schema.TrackKind.Video]
        clips = [c for c in video_tracks[0] if isinstance(c, otio.schema.Clip)]
        assert len(clips) == 1

    def test_nested_output_dirs_are_created(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "output.xml"
        with patch("xml_export._detect_fps", return_value=25.0):
            export_premiere_xml("/fake/video.mp4", FAKE_SEGMENTS, str(out))
        assert out.exists()

    def test_segment_without_reason_uses_fallback_label(self, tmp_path):
        segs = [{"start": 1.0, "end": 4.0}]  # no "reason" key
        out = _export(tmp_path, segments=segs)
        assert out.exists()

    def test_timeline_has_video_and_audio_tracks(self, tmp_path):
        out = _export(tmp_path)
        timeline = otio.adapters.read_from_file(str(out), adapter_name="fcp_xml")
        kinds = {t.kind for t in timeline.tracks}
        assert otio.schema.TrackKind.Video in kinds
        assert otio.schema.TrackKind.Audio in kinds

    def test_vertical_resolution_injected(self, tmp_path):
        out = tmp_path / "vertical.xml"
        with patch("xml_export._detect_fps", return_value=30.0):
            export_premiere_xml(
                "/fake/video.mp4", FAKE_SEGMENTS, str(out),
                width=1080, height=1920, target_fps=30,
            )
        content = out.read_text()
        assert "<width>1080</width>" in content
        assert "<height>1920</height>" in content
        assert "<timebase>30</timebase>" in content

    def test_horizontal_resolution_injected(self, tmp_path):
        out = tmp_path / "horizontal.xml"
        with patch("xml_export._detect_fps", return_value=25.0):
            export_premiere_xml(
                "/fake/video.mp4", FAKE_SEGMENTS, str(out),
                width=1920, height=1080,
            )
        content = out.read_text()
        assert "<width>1920</width>" in content
        assert "<height>1080</height>" in content

    def test_target_fps_overrides_detected(self, tmp_path):
        out = tmp_path / "fps30.xml"
        with patch("xml_export._detect_fps", return_value=25.0):
            export_premiere_xml(
                "/fake/video.mp4", FAKE_SEGMENTS, str(out),
                target_fps=30,
            )
        content = out.read_text()
        assert "<timebase>30</timebase>" in content

    def test_pathurl_uses_file_uri(self, tmp_path):
        out = _export(tmp_path)
        content = out.read_text()
        # pathurl must have file:// scheme so Premiere can find the media
        assert "file://" in content

    def test_otio_empty_format_replaced(self, tmp_path):
        out = _export(tmp_path)
        content = out.read_text()
        # OTIO generates <format/> — we must replace it, not duplicate it
        assert "<format/>" not in content

    def test_audio_format_injected(self, tmp_path):
        out = _export(tmp_path)
        content = out.read_text()
        assert "<samplerate>48000</samplerate>" in content
