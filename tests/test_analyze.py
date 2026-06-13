"""
Tests for analyze.py helper functions.

No Claude API call is made — we test the pure logic functions directly
by feeding them fake data and checking the output.
"""

import json
import inspect
import pytest
from analyze import (
    _analyze_chunk,
    _analyze_in_chunks,
    _build_editor_prompt,
    _enforce_duration_budget,
    _fmt_time,
    _format_transcript,
    _estimate_tokens,
    _fill_duration_with_high_scoring_segments,
    _merge_contiguous_segments,
    _parse_and_validate_json,
    _refine_selected_segments_by_editorial_scores,
    _snap_to_word_boundaries,
    analyze_transcript,
)


def test_merge_contiguous_segments_avoids_unnecessary_render_cut():
    segments = [
        {"start": 1.0, "end": 4.0, "reason": "hook", "importance": 5},
        {"start": 4.0, "end": 7.0, "reason": "support", "importance": 4},
        {"start": 9.0, "end": 12.0, "reason": "close", "importance": 5},
    ]

    merged = _merge_contiguous_segments(segments)

    assert merged == [
        {
            "start": 1.0,
            "end": 7.0,
            "reason": "hook; support",
            "importance": 5,
        },
        {"start": 9.0, "end": 12.0, "reason": "close", "importance": 5},
    ]


def test_analysis_entry_points_default_to_short_form_pause_threshold():
    assert inspect.signature(_analyze_chunk).parameters["gap_threshold"].default == 0.5
    assert inspect.signature(_analyze_in_chunks).parameters["gap_threshold"].default == 0.5
    assert inspect.signature(analyze_transcript).parameters["gap_threshold"].default == 0.5


class TestFmtTime:
    def test_zero(self):
        assert _fmt_time(0) == "00:00.0"

    def test_seconds(self):
        assert _fmt_time(5.5) == "00:05.5"

    def test_one_minute(self):
        assert _fmt_time(60) == "01:00.0"

    def test_minutes_and_seconds(self):
        assert _fmt_time(90.3) == "01:30.3"

    def test_large_value(self):
        assert _fmt_time(600) == "10:00.0"


class TestFormatTranscript:
    def test_single_segment(self):
        segments = [{"start": 0.0, "end": 5.0, "text": "Hello world"}]
        result = _format_transcript(segments)
        assert "Hello world" in result
        assert "00:00.0" in result
        assert "00:05.0" in result

    def test_multiple_segments(self):
        segments = [
            {"start": 0.0, "end": 3.0, "text": "First line"},
            {"start": 3.0, "end": 6.0, "text": "Second line"},
        ]
        result = _format_transcript(segments)
        assert "First line" in result
        assert "Second line" in result
        assert result.count("\n") == 1  # two lines separated by one newline

    def test_empty_segments(self):
        assert _format_transcript([]) == ""


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_four_chars_equals_one_token(self):
        assert _estimate_tokens("abcd") == 1

    def test_longer_text(self):
        text = "a" * 100
        assert _estimate_tokens(text) == 25


class TestBuildEditorPrompt:
    def test_includes_pre_selection_editorial_scores(self):
        template = (
            "Target {target_duration} {min_duration} {max_duration}\n"
            "Format {aspect_ratio} {platform_label}\n"
            "{platform_context}\n"
            "Scores:\n{editorial_scores}\n"
            "Transcript:\n{transcript}\n"
            "{quality_mode}"
        )
        segments = [
            {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
            {"start": 4.0, "end": 9.0, "text": "IVF treatment helps patients understand options."},
        ]

        prompt, transcript_str = _build_editor_prompt(
            segments=segments,
            quality_mode="balanced",
            prompt_template=template,
            target_duration=90,
            aspect_ratio="9:16",
            platform="reels",
        )

        assert transcript_str in prompt
        assert "decision_input_index=1" in prompt
        assert "topic_relevance=" in prompt
        assert "off_topic_drift=" in prompt
        assert "IVF treatment helps patients understand options." in prompt


class TestDurationBudget:
    def test_does_not_remove_substantive_antecedent_when_rejected_filler_intervenes(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 7.0,
                "text": "Welcome everyone.",
            },
            {
                "start": 7.0,
                "end": 12.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
            {
                "start": 12.0,
                "end": 17.0,
                "text": "Our clinic reception was renovated last year.",
            },
        ]
        segments = [
            {"start": 0.0, "end": 5.0, "importance": 1, "reason": "premise"},
            {"start": 7.0, "end": 12.0, "importance": 5, "reason": "dependent conclusion"},
            {"start": 12.0, "end": 17.0, "importance": 2, "reason": "weak standalone"},
        ]

        result = _enforce_duration_budget(
            segments,
            target_duration=10,
            transcript_segments=transcript,
        )

        assert result == segments[:2]

    def test_does_not_remove_antecedent_and_leave_context_dependent_fragment(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "Because of this, our clinic explains every treatment step.",
            },
            {
                "start": 10.0,
                "end": 15.0,
                "text": "Our clinic reception was renovated last year.",
            },
        ]
        segments = [
            {"start": 0.0, "end": 5.0, "importance": 1, "reason": "premise"},
            {"start": 5.0, "end": 10.0, "importance": 5, "reason": "dependent conclusion"},
            {"start": 10.0, "end": 15.0, "importance": 2, "reason": "weak standalone"},
        ]

        result = _enforce_duration_budget(
            segments,
            target_duration=10,
            transcript_segments=transcript,
        )

        assert result == segments[:2]

    def test_avoids_removal_that_would_make_story_under_length(self):
        segments = [
            {"start": 0.0, "end": 30.0, "importance": 1, "reason": "long weak context"},
            {"start": 30.0, "end": 98.0, "importance": 5, "reason": "core story"},
            {"start": 98.0, "end": 105.0, "importance": 2, "reason": "short supporting point"},
        ]

        result = _enforce_duration_budget(segments, target_duration=90)

        assert result == [
            {"start": 0.0, "end": 30.0, "importance": 1, "reason": "long weak context"},
            {"start": 30.0, "end": 98.0, "importance": 5, "reason": "core story"},
        ]
        assert sum(segment["end"] - segment["start"] for segment in result) == 98.0

    def test_keeps_over_budget_story_when_every_whole_removal_would_be_under_minimum(self):
        segments = [
            {"start": 0.0, "end": 6.0, "importance": 5, "reason": "core premise"},
            {"start": 6.0, "end": 12.0, "importance": 4, "reason": "core conclusion"},
        ]

        result = _enforce_duration_budget(segments, target_duration=10)

        assert result == segments

    def test_removes_lowest_importance_segment_when_over_budget(self):
        segments = [
            {"start": 0.0, "end": 9.0, "importance": 5, "reason": "core"},
            {"start": 9.0, "end": 14.0, "importance": 2, "reason": "nice to have"},
        ]

        result = _enforce_duration_budget(segments, target_duration=10)

        assert result == [{"start": 0.0, "end": 9.0, "importance": 5, "reason": "core"}]

    def test_word_boundary_snapping_is_followed_by_duration_enforcement(self):
        transcript = [
            {
                "start": 0.0,
                "end": 12.0,
                "text": "first second",
                "words": [
                    {"word": "first", "start": 0.0, "end": 6.0},
                    {"word": "second", "start": 6.0, "end": 12.0},
                ],
            }
        ]
        selected = [
            {"start": 0.2, "end": 5.8, "importance": 5, "reason": "core"},
            {"start": 6.2, "end": 11.8, "importance": 1, "reason": "weak"},
        ]

        snapped = _snap_to_word_boundaries(selected, transcript)
        result = _enforce_duration_budget(snapped, target_duration=10)

        assert sum(seg["end"] - seg["start"] for seg in snapped) == 12.0
        assert result == snapped

    def test_word_boundary_snapping_does_not_start_next_segment_mid_word(self):
        transcript = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "alpha beta gamma",
                "words": [
                    {"word": "alpha", "start": 0.0, "end": 0.7},
                    {"word": "beta", "start": 0.7, "end": 1.4},
                    {"word": "gamma", "start": 1.4, "end": 2.0},
                ],
            }
        ]
        selected = [
            {"start": 0.2, "end": 1.0, "importance": 5, "reason": "first"},
            {"start": 1.1, "end": 1.8, "importance": 4, "reason": "second"},
        ]

        snapped = _snap_to_word_boundaries(selected, transcript)

        assert snapped == [
            {
                "start": 0.0,
                "end": 1.4,
                "importance": 5,
                "reason": "first",
                "cut_boundary_source": "word_timestamps",
            },
            {
                "start": 1.4,
                "end": 2.0,
                "importance": 4,
                "reason": "second",
                "cut_boundary_source": "word_timestamps",
            },
        ]

    def test_word_boundary_snapping_drops_silence_only_selected_ranges(self):
        transcript = [
            {
                "start": 0.0,
                "end": 3.0,
                "text": "alpha beta",
                "words": [
                    {"word": "alpha", "start": 0.0, "end": 0.5},
                    {"word": "beta", "start": 2.0, "end": 2.5},
                ],
            }
        ]
        selected = [
            {"start": 0.8, "end": 1.4, "importance": 3, "reason": "silence"},
            {"start": 2.0, "end": 2.5, "importance": 5, "reason": "spoken"},
        ]

        snapped = _snap_to_word_boundaries(selected, transcript)

        assert snapped == [
            {
                "start": 2.0,
                "end": 2.5,
                "importance": 5,
                "reason": "spoken",
                "cut_boundary_source": "word_timestamps",
            }
        ]


class TestEditorialScoreRefinement:
    def test_keeps_context_dependent_fragment_when_rejected_filler_separates_selected_antecedent(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 7.0,
                "text": "Welcome everyone.",
            },
            {
                "start": 7.0,
                "end": 12.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 5.0, "reason": "necessary premise", "importance": 5},
            {"start": 7.0, "end": 12.0, "reason": "supported conclusion", "importance": 5},
        ]

        refined = _refine_selected_segments_by_editorial_scores(selected, transcript, "balanced")

        assert [(segment["start"], segment["end"]) for segment in refined] == [
            (0.0, 5.0),
            (7.0, 12.0),
        ]

    def test_removes_context_dependent_fragment_when_antecedent_is_not_selected(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
        ]
        selected = [
            {
                "start": 5.0,
                "end": 10.0,
                "reason": "supporting explanation",
                "importance": 4,
            },
        ]

        refined = _refine_selected_segments_by_editorial_scores(selected, transcript, "balanced")

        assert refined == []

    def test_trims_off_topic_opening_from_selected_range(self):
        transcript = [
            {"start": 0.0, "end": 4.0, "text": "Welcome everyone, thanks for joining today."},
            {"start": 4.0, "end": 10.0, "text": "IVF treatment helps patients understand fertility options."},
            {"start": 10.0, "end": 16.0, "text": "Our clinic supports patients through the treatment process."},
        ]
        selected = [
            {"start": 0.0, "end": 10.0, "reason": "hook plus topic", "importance": 5},
        ]

        refined = _refine_selected_segments_by_editorial_scores(selected, transcript, "balanced")

        assert refined == [
            {
                "start": 4.0,
                "end": 10.0,
                "reason": "hook plus topic",
                "importance": 5,
                "refinement_source": "editorial_scores",
            }
        ]

    def test_removes_duplicate_selected_take_after_clean_first_delivery(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment helps couples understand options.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "IVF treatment helps patients understand their options.",
            },
            {
                "start": 10.0,
                "end": 15.0,
                "text": "Embryology lab monitoring gives doctors better information.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 5.0, "reason": "clean core point", "importance": 5},
            {"start": 5.0, "end": 10.0, "reason": "same point repeated", "importance": 4},
            {"start": 10.0, "end": 15.0, "reason": "new supporting detail", "importance": 4},
        ]

        refined = _refine_selected_segments_by_editorial_scores(selected, transcript, "balanced")

        assert refined == [
            {
                "start": 0.0,
                "end": 5.0,
                "reason": "clean core point",
                "importance": 5,
                "refinement_source": "editorial_scores",
            },
            {
                "start": 10.0,
                "end": 15.0,
                "reason": "new supporting detail",
                "importance": 4,
                "refinement_source": "editorial_scores",
            },
        ]

    def test_keeps_cleaner_later_take_when_first_selected_take_is_false_start(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "Um sorry IVF treatment helps couples understand options.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "IVF treatment helps couples understand options.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 5.0, "reason": "first take", "importance": 4},
            {"start": 5.0, "end": 10.0, "reason": "clean take", "importance": 5},
        ]

        refined = _refine_selected_segments_by_editorial_scores(selected, transcript, "balanced")

        assert refined == [
            {
                "start": 5.0,
                "end": 10.0,
                "reason": "clean take",
                "importance": 5,
                "refinement_source": "editorial_scores",
            }
        ]


class TestEditorialScoreStoryFill:
    def test_adds_context_dependent_conclusion_when_rejected_filler_separates_selected_antecedent(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 7.0,
                "text": "Welcome everyone.",
            },
            {
                "start": 7.0,
                "end": 12.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 5.0, "reason": "necessary premise", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert [(segment["start"], segment["end"]) for segment in filled] == [
            (0.0, 5.0),
            (7.0, 12.0),
        ]

    def test_adds_context_dependent_conclusion_when_antecedent_is_selected(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 5.0, "reason": "necessary premise", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert filled == [
            selected[0],
            {
                "start": 5.0,
                "end": 10.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            },
        ]

    def test_fallback_story_can_add_antecedent_then_dependent_conclusion(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment can feel confusing without clear guidance.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "Because of this, our clinic explains every IVF treatment step.",
            },
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=[],
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert [(segment["start"], segment["end"]) for segment in filled] == [
            (0.0, 5.0),
            (5.0, 10.0),
        ]

    def test_adds_strong_content_when_already_above_minimum_but_below_target(self):
        transcript = [
            {
                "start": 0.0,
                "end": 9.0,
                "text": "IVF treatment gives patients clear fertility options and support.",
            },
            {
                "start": 9.0,
                "end": 10.0,
                "text": "IVF counselling explains the next treatment step.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 9.0, "reason": "core story", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert filled[-1]["start"] == 9.0
        assert filled[-1]["end"] == 10.0
        assert sum(segment["end"] - segment["start"] for segment in filled) == 10.0

    def test_does_not_fill_when_candidate_moves_duration_farther_from_target(self):
        transcript = [
            {
                "start": 0.0,
                "end": 9.0,
                "text": "IVF treatment gives patients clear fertility options and support.",
            },
            {
                "start": 9.0,
                "end": 11.0,
                "text": "IVF counselling explains every treatment step.",
            },
        ]
        selected = [
            {"start": 0.0, "end": 9.0, "reason": "core story", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert filled == selected

    def test_builds_fallback_story_when_claude_returns_no_segments(self):
        transcript = [
            {"start": 0.0, "end": 3.0, "text": "Welcome everyone, thanks for joining."},
            {"start": 3.0, "end": 7.0, "text": "IVF treatment helps patients understand fertility options."},
            {"start": 7.0, "end": 11.0, "text": "Our clinic supports patients through the treatment process."},
            {"start": 11.0, "end": 15.0, "text": "Yesterday I went shopping for a phone."},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=[],
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=8,
        )

        assert filled == [
            {
                "start": 3.0,
                "end": 7.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            },
            {
                "start": 7.0,
                "end": 11.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            },
        ]

    def test_adds_high_scoring_missing_segment_when_selection_is_under_minimum_duration(self):
        transcript = [
            {"start": 0.0, "end": 2.0, "text": "Welcome everyone."},
            {"start": 2.0, "end": 4.0, "text": "IVF treatment helps patients understand options."},
            {"start": 4.0, "end": 9.0, "text": "Our clinic supports patients through the treatment process."},
            {"start": 9.0, "end": 14.0, "text": "Yesterday I went shopping for a phone."},
        ]
        selected = [
            {"start": 2.0, "end": 4.0, "reason": "core point", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=8,
        )

        assert filled == [
            {"start": 2.0, "end": 4.0, "reason": "core point", "importance": 5},
            {
                "start": 4.0,
                "end": 9.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            },
        ]

    def test_does_not_fill_with_off_topic_segments_when_under_minimum_duration(self):
        transcript = [
            {"start": 0.0, "end": 2.0, "text": "IVF treatment helps patients."},
            {"start": 2.0, "end": 7.0, "text": "Yesterday I went shopping for a phone."},
            {"start": 7.0, "end": 12.0, "text": "The weather was nice near my house."},
        ]
        selected = [
            {"start": 0.0, "end": 2.0, "reason": "core point", "importance": 5},
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=selected,
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=8,
        )

        assert filled == selected

    def test_does_not_fill_with_low_transcription_confidence_segments(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "IVF treatment helps patients understand options.",
                "words": [
                    {"word": "IVF", "start": 0.0, "end": 0.4, "probability": 0.28},
                    {"word": "treatment", "start": 0.5, "end": 1.0, "probability": 0.30},
                    {"word": "helps", "start": 1.1, "end": 1.4, "probability": 0.32},
                    {"word": "patients", "start": 1.5, "end": 2.0, "probability": 0.29},
                ],
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "Yesterday I went shopping for a phone.",
            },
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=[],
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=8,
        )

        assert filled == []

    def test_does_not_fill_with_context_dependent_fragment(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "Because it helps patients understand the IVF treatment process.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "IVF treatment gives patients clear options.",
            },
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=[],
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert filled == [
            {
                "start": 5.0,
                "end": 10.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            }
        ]

    def test_does_not_fill_with_orphaned_anaphoric_pronoun_fragment(self):
        transcript = [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "This helps patients understand the IVF treatment process.",
            },
            {
                "start": 5.0,
                "end": 10.0,
                "text": "IVF treatment gives patients clear options.",
            },
        ]

        filled = _fill_duration_with_high_scoring_segments(
            kept_segments=[],
            transcript_segments=transcript,
            quality_mode="balanced",
            target_duration=10,
        )

        assert filled == [
            {
                "start": 5.0,
                "end": 10.0,
                "reason": "editorial score fill: relevant missing context",
                "importance": 4,
                "refinement_source": "editorial_score_fill",
            }
        ]


class TestParseAndValidateJson:
    VIDEO_DURATION = 120.0

    def _make_raw(self, segments):
        return json.dumps({"segments_to_keep": segments})

    def test_valid_segments(self):
        raw = self._make_raw([{"start": 0.0, "end": 10.0, "reason": "good"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 10.0

    def test_strips_markdown_fences(self):
        raw = "```json\n" + self._make_raw([{"start": 1.0, "end": 5.0, "reason": "ok"}]) + "\n```"
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert len(result) == 1

    def test_rejects_start_greater_than_end(self):
        raw = self._make_raw([{"start": 10.0, "end": 5.0, "reason": "bad"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    def test_rejects_too_short_segment(self):
        # duration = 0.3s which is below MIN_SEGMENT_DURATION (0.5s)
        raw = self._make_raw([{"start": 1.0, "end": 1.3, "reason": "too short"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    def test_clamps_segment_beyond_video_duration(self):
        raw = self._make_raw([{"start": 100.0, "end": 150.0, "reason": "past end"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert len(result) == 1
        assert result[0]["end"] == self.VIDEO_DURATION

    def test_rejects_segment_that_becomes_too_short_after_source_end_clamp(self):
        raw = self._make_raw([{"start": 119.8, "end": 125.0, "reason": "micro cut"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    def test_rejects_segment_starting_past_video(self):
        raw = self._make_raw([{"start": 130.0, "end": 140.0, "reason": "out of bounds"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    def test_rejects_segment_starting_before_video(self):
        raw = self._make_raw([{"start": -2.0, "end": 3.0, "reason": "negative source time"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    @pytest.mark.parametrize(
        ("start", "end"),
        [
            ("NaN", 3.0),
            (1.0, "Infinity"),
            ("-Infinity", 3.0),
        ],
    )
    def test_rejects_non_finite_segment_timestamps(self, start, end):
        raw = self._make_raw([{"start": start, "end": end, "reason": "invalid timestamp"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert result == []

    def test_multiple_valid_segments(self):
        raw = self._make_raw([
            {"start": 0.0, "end": 10.0, "reason": "first"},
            {"start": 20.0, "end": 30.0, "reason": "second"},
        ])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION)
        assert len(result) == 2

    def test_chunk_offset_applied(self):
        # Chunk offset shifts timestamps (used when processing long videos in chunks)
        raw = self._make_raw([{"start": 0.0, "end": 10.0, "reason": "chunk"}])
        result = _parse_and_validate_json(raw, self.VIDEO_DURATION, chunk_start_offset=60.0)
        assert result[0]["start"] == 60.0
        assert result[0]["end"] == 70.0

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            _parse_and_validate_json("not json at all", self.VIDEO_DURATION)
