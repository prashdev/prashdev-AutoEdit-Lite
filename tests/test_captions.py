"""
Tests for captions.py.

We feed fake transcript + kept segments and verify the .srt file content.
No video file needed — just plain Python dicts and a temp file.
"""

import pytest
from pathlib import Path
from captions import _seconds_to_srt_time, generate_srt


class TestSecondsToSrtTime:
    def test_zero(self):
        assert _seconds_to_srt_time(0) == "00:00:00,000"

    def test_milliseconds(self):
        assert _seconds_to_srt_time(0.5) == "00:00:00,500"

    def test_one_minute(self):
        assert _seconds_to_srt_time(60) == "00:01:00,000"

    def test_one_hour(self):
        assert _seconds_to_srt_time(3600) == "01:00:00,000"

    def test_complex(self):
        assert _seconds_to_srt_time(3723.456) == "01:02:03,456"


class TestGenerateSrt:
    def test_basic_output(self, tmp_path):
        transcript = [{"start": 0.0, "end": 5.0, "text": "Hello world"}]
        kept = [{"start": 0.0, "end": 5.0, "reason": "good"}]
        out = tmp_path / "test.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        assert "Hello world" in content
        assert "00:00:00,000 --> 00:00:05,000" in content

    def test_srt_index_starts_at_one(self, tmp_path):
        transcript = [{"start": 0.0, "end": 3.0, "text": "First"}]
        kept = [{"start": 0.0, "end": 3.0, "reason": "good"}]
        out = tmp_path / "test.srt"

        generate_srt(transcript, kept, str(out))

        lines = out.read_text().strip().split("\n")
        assert lines[0] == "1"

    def test_empty_kept_segments(self, tmp_path):
        transcript = [{"start": 0.0, "end": 5.0, "text": "Hello"}]
        out = tmp_path / "empty.srt"

        generate_srt(transcript, [], str(out))

        assert out.read_text() == ""

    def test_timestamps_reset_for_edited_video(self, tmp_path):
        # Original video: keep segment starting at 30s
        # In the edited video this segment starts at 0s
        transcript = [{"start": 30.0, "end": 35.0, "text": "Kept part"}]
        kept = [{"start": 30.0, "end": 35.0, "reason": "good"}]
        out = tmp_path / "test.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        # Output timestamps should start at 00:00:00,000 not 00:00:30,000
        assert "00:00:00,000 --> 00:00:05,000" in content

    def test_skips_empty_text(self, tmp_path):
        transcript = [
            {"start": 0.0, "end": 3.0, "text": "   "},   # whitespace only
            {"start": 3.0, "end": 6.0, "text": "Real text"},
        ]
        kept = [{"start": 0.0, "end": 6.0, "reason": "good"}]
        out = tmp_path / "test.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        assert "Real text" in content
        # Only one subtitle entry (index "1" appears once at the start)
        assert content.count("\n1\n") == 0  # no second entry
        assert content.startswith("1\n")    # first and only entry

    def test_uses_word_timestamps_to_clip_partial_kept_segment_text(self, tmp_path):
        transcript = [
            {
                "start": 0.0,
                "end": 1.2,
                "text": "um IVF helps",
                "words": [
                    {"word": "um", "start": 0.0, "end": 0.3},
                    {"word": "IVF", "start": 0.4, "end": 0.7},
                    {"word": "helps", "start": 0.7, "end": 1.2},
                ],
            }
        ]
        kept = [{"start": 0.4, "end": 1.2, "reason": "trim filler"}]
        out = tmp_path / "partial.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        assert "IVF helps" in content
        assert "um IVF helps" not in content
        assert "00:00:00,000 --> 00:00:00,800" in content

    def test_includes_overlapping_word_timestamp_segment_that_starts_before_kept_cut(self, tmp_path):
        transcript = [
            {
                "start": 10.0,
                "end": 13.0,
                "text": "cut this keep this",
                "words": [
                    {"word": "cut", "start": 10.0, "end": 10.4},
                    {"word": "this", "start": 10.4, "end": 10.8},
                    {"word": "keep", "start": 11.0, "end": 11.4},
                    {"word": "this", "start": 11.4, "end": 11.8},
                ],
            }
        ]
        kept = [{"start": 11.0, "end": 11.8, "reason": "clean phrase"}]
        out = tmp_path / "overlap.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        assert "keep this" in content
        assert "cut this" not in content

    def test_excludes_words_only_partially_inside_kept_cut(self, tmp_path):
        transcript = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "alpha beta gamma",
                "words": [
                    {"word": "alpha", "start": 0.0, "end": 0.6},
                    {"word": "beta", "start": 0.7, "end": 1.3},
                    {"word": "gamma", "start": 1.4, "end": 2.0},
                ],
            }
        ]
        kept = [{"start": 0.3, "end": 1.7, "reason": "partial phrase"}]
        out = tmp_path / "whole_words_only.srt"

        generate_srt(transcript, kept, str(out))

        content = out.read_text()
        assert "\nbeta\n" in content
        assert "alpha" not in content
        assert "gamma" not in content
        assert "00:00:00,400 --> 00:00:01,000" in content
