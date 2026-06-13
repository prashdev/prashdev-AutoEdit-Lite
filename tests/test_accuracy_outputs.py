import json

from analyze import _snap_to_word_boundaries
from accuracy_outputs import (
    build_accuracy_report,
    build_edit_decisions,
    evaluate_human_agreement,
    generate_broll_suggestions,
    infer_main_topic,
    score_transcript_segments,
    write_accuracy_outputs,
)


def test_snap_to_word_boundaries_uses_word_timestamps_without_cutting_mid_word():
    transcript = [
        {
            "start": 0.0,
            "end": 3.0,
            "text": "we provide IVF treatment",
            "words": [
                {"word": "we", "start": 0.0, "end": 0.2},
                {"word": "provide", "start": 0.3, "end": 0.8},
                {"word": "IVF", "start": 0.9, "end": 1.2},
                {"word": "treatment", "start": 1.3, "end": 2.0},
            ],
        }
    ]
    selected = [{"start": 0.35, "end": 1.05, "reason": "core point", "importance": 5}]

    snapped = _snap_to_word_boundaries(selected, transcript)

    assert snapped[0]["start"] == 0.3
    assert snapped[0]["end"] == 1.2
    assert snapped[0]["cut_boundary_source"] == "word_timestamps"


def test_infer_main_topic_prefers_ivf_domain_terms():
    segments = [
        {"text": "We provide IVF treatment and fertility care."},
        {"text": "Patients need counselling during the treatment process."},
    ]

    topic = infer_main_topic(segments)

    assert topic["label"] == "IVF and fertility care"
    assert "ivf" in topic["keywords"]


def test_infer_main_topic_recognizes_devanagari_ivf_and_fertility_terms():
    segments = [
        {"text": "हम आईवीएफ उपचार और प्रजनन देखभाल देते हैं."},
        {"text": "रुग्णांना उपचार प्रक्रियेत समुपदेशन आणि साथ मिळते."},
    ]

    topic = infer_main_topic(segments)

    assert topic["label"] == "IVF and fertility care"
    assert "आईवीएफ" in topic["keywords"]


def test_infer_main_topic_uses_recurring_terms_for_general_content():
    segments = [
        {"text": "Welcome everyone and thanks for joining this channel."},
        {"text": "Retirement investing works best when savings are consistent."},
        {"text": "Your retirement savings need a long term investing plan."},
        {"text": "Consistent investing protects retirement savings over time."},
    ]

    topic = infer_main_topic(segments)

    assert topic["label"] == "general talking-head topic"
    assert {"retirement", "investing", "savings"} <= set(topic["keywords"])
    assert "welcome" not in topic["keywords"]
    assert "joining" not in topic["keywords"]


def test_general_topic_scoring_penalizes_unrelated_opener():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone and thanks for joining this channel."},
        {"start": 4.0, "end": 9.0, "text": "Retirement investing works best when savings are consistent."},
        {"start": 9.0, "end": 14.0, "text": "Your retirement savings need a long term investing plan."},
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["topic_relevance"] > scored[0]["scores"]["topic_relevance"]
    assert scored[2]["scores"]["topic_relevance"] > scored[0]["scores"]["topic_relevance"]


def test_infer_main_topic_does_not_treat_generic_process_as_medical_treatment():
    segments = [
        {"text": "Our software release process has three clear steps."},
        {"text": "Each release process includes tests and a final result."},
        {"text": "The engineering team reviews every release step."},
    ]

    topic = infer_main_topic(segments)

    assert topic["label"] == "general talking-head topic"
    assert "release" in topic["keywords"]
    assert "process" in topic["keywords"]


def test_infer_main_topic_ignores_isolated_specialized_tangent():
    segments = [
        {"text": "Retirement investing works best with a long-term plan."},
        {"text": "Regular investing helps retirement savings compound."},
        {"text": "Review your retirement investing plan every year."},
        {"text": "My friend once visited an IVF clinic."},
    ]

    topic = infer_main_topic(segments)

    assert topic["label"] == "general talking-head topic"
    assert {"retirement", "investing"} <= set(topic["keywords"])


def test_generate_broll_suggestions_maps_spoken_ivf_content_to_relevant_keywords():
    kept = [{"start": 4.0, "end": 9.0, "reason": "core service", "importance": 5}]
    transcript = [
        {"start": 4.0, "end": 9.0, "text": "We provide IVF and counselling for couples."}
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    assert suggestions[0]["timestamp"] == 4.0
    assert "fertility clinic consultation" in suggestions[0]["keywords"]
    assert "doctor-patient counselling" in suggestions[0]["keywords"]
    assert suggestions[0]["insert_mode"] == "suggest_only"


def test_generate_broll_suggestions_includes_edited_timeline_timestamps():
    kept = [
        {"start": 20.0, "end": 25.0, "reason": "hook", "importance": 5},
        {"start": 40.0, "end": 47.0, "reason": "process", "importance": 4},
    ]
    transcript = [
        {"start": 20.0, "end": 25.0, "text": "We provide IVF treatment."},
        {"start": 40.0, "end": 47.0, "text": "The treatment process includes scans."},
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    assert suggestions[0]["source_timestamp"] == 20.0
    assert suggestions[0]["edited_timeline_timestamp"] == 0.0
    assert suggestions[0]["edited_timeline_end"] == 5.0
    assert suggestions[1]["source_timestamp"] == 40.0
    assert suggestions[1]["edited_timeline_timestamp"] == 5.0
    assert suggestions[1]["edited_timeline_end"] == 12.0


def test_generate_broll_suggestions_uses_spoken_general_topic_instead_of_clinic_fallback():
    kept = [{"start": 4.0, "end": 9.0, "reason": "core point", "importance": 5}]
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Retirement investing needs a clear plan."},
        {"start": 4.0, "end": 9.0, "text": "Consistent retirement savings grow through investing."},
        {"start": 9.0, "end": 14.0, "text": "Retirement savings work best with regular investing."},
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    keywords = " ".join(suggestions[0]["keywords"]).lower()
    assert "retirement" in keywords
    assert "investing" in keywords
    assert "clinic" not in keywords


def test_generate_broll_suggestions_maps_devanagari_ivf_content_to_relevant_keywords():
    kept = [{"start": 4.0, "end": 9.0, "reason": "core service", "importance": 5}]
    transcript = [
        {"start": 4.0, "end": 9.0, "text": "हम आईवीएफ उपचार और समुपदेशन देते हैं."}
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    assert "fertility clinic consultation" in suggestions[0]["keywords"]
    assert "doctor-patient counselling" in suggestions[0]["keywords"]


def test_generate_broll_suggestions_splits_multi_concept_kept_range_by_transcript_segment():
    kept = [{"start": 4.0, "end": 14.0, "reason": "core story", "importance": 5}]
    transcript = [
        {"start": 4.0, "end": 9.0, "text": "We provide IVF treatment."},
        {"start": 9.0, "end": 14.0, "text": "Couples receive patient counselling and support."},
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    assert [suggestion["source_timestamp"] for suggestion in suggestions] == [4.0, 9.0]
    assert [suggestion["edited_timeline_timestamp"] for suggestion in suggestions] == [0.0, 5.0]
    assert "IVF equipment" in suggestions[0]["keywords"]
    assert "patient support conversation" in suggestions[1]["keywords"]


def test_generate_broll_suggestions_uses_only_words_inside_partial_kept_range():
    kept = [{"start": 2.0, "end": 4.0, "reason": "core service", "importance": 5}]
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "Yesterday I went shopping. We provide IVF.",
            "words": [
                {"word": "Yesterday", "start": 0.0, "end": 0.5},
                {"word": "I", "start": 0.5, "end": 0.7},
                {"word": "went", "start": 0.7, "end": 1.0},
                {"word": "shopping.", "start": 1.0, "end": 1.5},
                {"word": "We", "start": 2.0, "end": 2.3},
                {"word": "provide", "start": 2.3, "end": 2.8},
                {"word": "IVF.", "start": 2.8, "end": 3.3},
            ],
        }
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    assert suggestions[0]["spoken_text"] == "We provide IVF."
    assert suggestions[0]["source_timestamp"] == 2.0
    assert suggestions[0]["source_end"] == 3.3
    assert suggestions[0]["edited_timeline_timestamp"] == 0.0
    assert suggestions[0]["edited_timeline_end"] == 1.3
    assert "shopping" not in " ".join(suggestions[0]["keywords"]).lower()
    assert "IVF equipment" in suggestions[0]["keywords"]


def test_generate_broll_suggestions_does_not_map_negated_ivf_service_to_promotional_visuals():
    kept = [{"start": 0.0, "end": 4.0, "reason": "service limitation", "importance": 5}]
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "We do not provide IVF treatment."},
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    keywords = " ".join(suggestions[0]["keywords"]).lower()
    assert "ivf" in keywords
    assert "ivf equipment" not in keywords
    assert "fertility clinic consultation" not in keywords


def test_generate_broll_suggestions_keeps_affirmative_service_visuals_after_unrelated_negation():
    kept = [{"start": 0.0, "end": 6.0, "reason": "core service", "importance": 5}]
    transcript = [
        {
            "start": 0.0,
            "end": 6.0,
            "text": "We do not rush patients; we provide IVF treatment and counselling.",
        },
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    keywords = suggestions[0]["keywords"]
    assert "IVF equipment" in keywords
    assert "fertility clinic consultation" in keywords
    assert not any("limitations" in keyword for keyword in keywords)


def test_generate_broll_suggestions_keeps_affirmative_service_visuals_after_comma_conjunction():
    kept = [{"start": 0.0, "end": 6.0, "reason": "core service", "importance": 5}]
    transcript = [
        {
            "start": 0.0,
            "end": 6.0,
            "text": "We do not rush patients, and we provide IVF treatment and counselling.",
        },
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    keywords = suggestions[0]["keywords"]
    assert "IVF equipment" in keywords
    assert "fertility clinic consultation" in keywords
    assert not any("limitations" in keyword for keyword in keywords)


def test_generate_broll_suggestions_keeps_negated_comma_separated_service_list_neutral():
    kept = [{"start": 0.0, "end": 5.0, "reason": "service limitation", "importance": 5}]
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "We do not provide IVF, fertility care, and counselling.",
        },
    ]

    suggestions = generate_broll_suggestions(transcript, kept)

    keywords = suggestions[0]["keywords"]
    assert any("limitations" in keyword for keyword in keywords)
    assert "IVF equipment" not in keywords
    assert "fertility clinic consultation" not in keywords


def test_build_edit_decisions_scores_kept_and_removed_segments():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
        {"start": 4.0, "end": 9.0, "text": "IVF treatment helps patients understand options."},
    ]
    kept = [{"start": 4.0, "end": 9.0, "reason": "topic relevant", "importance": 5}]

    decisions = build_edit_decisions(transcript, kept)

    assert decisions[0]["decision"] == "remove"
    assert decisions[1]["decision"] == "keep"
    assert decisions[1]["scores"]["topic_relevance"] > decisions[0]["scores"]["topic_relevance"]


def test_build_edit_decisions_preserves_actual_selected_cut_boundaries():
    transcript = [
        {"start": 4.0, "end": 9.0, "text": "IVF treatment helps patients understand options."},
    ]
    kept = [{"start": 4.4, "end": 8.6, "reason": "word-snapped core point", "importance": 5}]

    decisions = build_edit_decisions(transcript, kept)
    kept_decision = next(decision for decision in decisions if decision["decision"] == "keep")

    assert kept_decision["cut_start"] == 4.4
    assert kept_decision["cut_end"] == 8.6


def test_build_edit_decisions_splits_partial_transcript_selection():
    transcript = [
        {"start": 0.0, "end": 10.0, "text": "A long transcript segment containing one useful sentence."},
    ]
    kept = [{"start": 4.0, "end": 6.0, "reason": "useful sentence", "importance": 5}]

    decisions = build_edit_decisions(transcript, kept)

    assert [
        (decision["start"], decision["end"], decision["decision"])
        for decision in decisions
    ] == [
        (0.0, 4.0, "remove"),
        (4.0, 6.0, "keep"),
        (6.0, 10.0, "remove"),
    ]


def test_score_transcript_segments_runs_before_selection_without_kept_segments():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
        {"start": 4.0, "end": 9.0, "text": "IVF treatment helps patients understand options."},
    ]

    scored = score_transcript_segments(transcript)

    assert [s["decision_input_index"] for s in scored] == [0, 1]
    assert scored[1]["scores"]["topic_relevance"] > scored[0]["scores"]["topic_relevance"]
    assert scored[1]["scores"]["usefulness"] > scored[0]["scores"]["usefulness"]


def test_score_transcript_segments_scores_devanagari_ivf_as_topic_relevant():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "नमस्कार सगळ्यांना."},
        {"start": 4.0, "end": 9.0, "text": "आयव्हीएफ उपचारात रुग्णांना समुपदेशन मिळते."},
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["topic_relevance"] > scored[0]["scores"]["topic_relevance"]
    assert scored[1]["scores"]["usefulness"] > scored[0]["scores"]["usefulness"]


def test_score_transcript_segments_penalizes_low_word_confidence():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "IVF treatment helps patients understand options.",
            "words": [
                {"word": "IVF", "start": 0.0, "end": 0.3, "probability": 0.95},
                {"word": "treatment", "start": 0.4, "end": 1.0, "probability": 0.95},
                {"word": "helps", "start": 1.1, "end": 1.4, "probability": 0.95},
                {"word": "patients", "start": 1.5, "end": 2.0, "probability": 0.95},
            ],
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "IVF treatment helps patients understand options.",
            "words": [
                {"word": "IVF", "start": 5.0, "end": 5.3, "probability": 0.35},
                {"word": "treatment", "start": 5.4, "end": 6.0, "probability": 0.35},
                {"word": "helps", "start": 6.1, "end": 6.4, "probability": 0.35},
                {"word": "patients", "start": 6.5, "end": 7.0, "probability": 0.35},
            ],
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["transcription_confidence"] == 0.95
    assert scored[1]["scores"]["transcription_confidence"] == 0.35
    assert scored[1]["scores"]["clarity"] < scored[0]["scores"]["clarity"]
    assert scored[1]["scores"]["speaker_confidence"] < scored[0]["scores"]["speaker_confidence"]


def test_score_transcript_segments_penalizes_devanagari_fillers():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "आईवीएफ उपचार रुग्णांना स्पष्ट पर्याय देतो.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "अं आईवीएफ उपचार रुग्णांना स्पष्ट पर्याय देतो.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["filler"] > scored[0]["scores"]["filler"]
    assert scored[1]["scores"]["clarity"] < scored[0]["scores"]["clarity"]


def test_score_transcript_segments_does_not_match_fillers_inside_clean_words():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Human care is likely to improve treatment outcomes.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["filler"] == 0.0
    assert scored[0]["scores"]["clarity"] == 1.0


def test_score_transcript_segments_matches_editorial_signals_as_whole_words():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "A neutral opening statement.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "We showcase the clinic for scared visitors.",
        },
        {
            "start": 8.0,
            "end": 12.0,
            "text": "How patient care improves treatment.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["hook_strength"] == 0.35
    assert scored[1]["scores"]["emotional_value"] == 0.35
    assert scored[2]["scores"]["hook_strength"] == 0.7
    assert scored[2]["scores"]["emotional_value"] == 0.65


def test_score_transcript_segments_counts_repeated_filler_occurrences():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Um IVF treatment helps patients.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "Um um um IVF treatment helps patients.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["filler"] > scored[0]["scores"]["filler"]
    assert scored[1]["scores"]["clarity"] < scored[0]["scores"]["clarity"]


def test_score_transcript_segments_marks_context_dependent_fragments():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "IVF treatment gives patients clear options.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "Because it helps them understand the next step.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["context_dependency"] == 0.0
    assert scored[1]["scores"]["context_dependency"] == 1.0


def test_score_transcript_segments_marks_anaphoric_pronoun_fragment_as_context_dependent():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "Our clinic explains every IVF treatment step.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "This helps patients understand their options.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["context_dependency"] == 0.0
    assert scored[1]["scores"]["context_dependency"] == 1.0


def test_score_transcript_segments_keeps_explicit_demonstrative_noun_phrase_independent():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "This video explains the IVF treatment process.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["context_dependency"] == 0.0


def test_score_transcript_segments_marks_devanagari_context_dependent_fragments():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "आईवीएफ उपचार रुग्णांना स्पष्ट पर्याय देतो.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "कारण त्यामुळे रुग्णांना पुढची पायरी समजते.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["context_dependency"] == 0.0
    assert scored[1]["scores"]["context_dependency"] == 1.0


def test_score_transcript_segments_penalizes_near_duplicate_repeated_takes():
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

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] > 0.5
    assert scored[1]["scores"]["uniqueness"] < 0.5
    assert scored[2]["scores"]["repetition"] < scored[1]["scores"]["repetition"]
    assert scored[2]["scores"]["uniqueness"] > scored[1]["scores"]["uniqueness"]


def test_score_transcript_segments_prefers_cleaner_later_duplicate_take():
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

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["repetition"] > 0.5
    assert scored[0]["scores"]["uniqueness"] < 0.5
    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0
    assert scored[1]["scores"]["clarity"] > scored[0]["scores"]["clarity"]


def test_score_transcript_segments_does_not_penalize_transitive_duplicate_without_direct_similarity():
    transcript = [
        {
            "start": 0.0,
            "end": 5.0,
            "text": "IVF treatment helps patients understand options.",
        },
        {
            "start": 5.0,
            "end": 10.0,
            "text": "IVF treatment helps patients understand options with support and guidance.",
        },
        {
            "start": 10.0,
            "end": 15.0,
            "text": "IVF patients receive options support and guidance.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] > 0.5
    assert scored[2]["scores"]["repetition"] == 0.0
    assert scored[2]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_does_not_penalize_negated_contrast_as_repetition():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "IVF treatment is suitable for every patient.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "IVF treatment is not suitable for every patient.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_recognizes_contracted_negation_contrast():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "IVF is suitable for every patient."},
        {"start": 4.0, "end": 8.0, "text": "IVF isn't suitable for every patient."},
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_recognizes_didnt_as_negation_contrast():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "IVF treatment worked for every patient."},
        {"start": 4.0, "end": 8.0, "text": "IVF treatment didn't work for every patient."},
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_does_not_penalize_semantic_opposites_as_repetition():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "IVF treatment is safe effective and reliable for patients.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "IVF treatment is unsafe effective and reliable for patients.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_still_penalizes_duplicate_with_both_contrast_terms():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "We support patients before and after treatment.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "We support patients before and after treatment.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] == 1.0
    assert scored[1]["scores"]["uniqueness"] == 0.0


def test_score_transcript_segments_does_not_penalize_different_numeric_claims_as_repetition():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "IVF treatment succeeds for 30 percent of patients.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "IVF treatment succeeds for 70 percent of patients.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_still_penalizes_duplicate_numeric_claim():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "Take this medicine for five days after treatment.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "Take this medicine for five days after treatment.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] == 1.0
    assert scored[1]["scores"]["uniqueness"] == 0.0


def test_score_transcript_segments_does_not_penalize_different_marathi_quantities():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "औषध उपचारानंतर पाच दिवस घ्या.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "औषध उपचारानंतर दहा दिवस घ्या.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[0]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["repetition"] == 0.0
    assert scored[1]["scores"]["uniqueness"] == 1.0


def test_score_transcript_segments_still_penalizes_duplicate_marathi_quantity():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "औषध उपचारानंतर पाच दिवस घ्या.",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "औषध उपचारानंतर पाच दिवस घ्या.",
        },
    ]

    scored = score_transcript_segments(transcript)

    assert scored[1]["scores"]["repetition"] == 1.0
    assert scored[1]["scores"]["uniqueness"] == 0.0


def test_write_accuracy_outputs_creates_expected_json_artifacts(tmp_path):
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
        {"start": 4.0, "end": 9.0, "text": "We provide IVF treatment and patient support."},
    ]
    kept = [{"start": 4.0, "end": 9.0, "reason": "topic relevant", "importance": 5}]

    write_accuracy_outputs(
        transcript_segments=transcript,
        kept_segments=kept,
        output_video_path=str(tmp_path / "edited_90s.mp4"),
        original_duration=120.0,
        target_duration=90,
        transcription_provider="sarvam",
        language="mr-IN",
        gap_threshold=0.5,
    )

    for name in ["edit_decisions.json", "broll_suggestions.json", "accuracy_report.json"]:
        assert (tmp_path / name).exists()

    report = json.loads((tmp_path / "accuracy_report.json").read_text(encoding="utf-8"))
    assert report["target"]["agreement_goal"] == 0.95
    assert report["transcription"]["provider"] == "sarvam"
    assert report["cutting"]["gap_threshold_seconds"] == 0.5


def test_build_accuracy_report_counts_editorial_score_refined_segments():
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
        {"start": 4.0, "end": 9.0, "text": "We provide IVF treatment."},
    ]
    kept = [
        {
            "start": 4.0,
            "end": 9.0,
            "reason": "topic relevant",
            "importance": 5,
            "refinement_source": "editorial_scores",
        },
        {
            "start": 9.0,
            "end": 14.0,
            "reason": "editorial score fill: relevant missing context",
            "importance": 4,
            "refinement_source": "editorial_score_fill",
        },
    ]

    report = build_accuracy_report(
        transcript_segments=transcript,
        kept_segments=kept,
        original_duration=120.0,
        target_duration=90,
        transcription_provider="sarvam",
        language="mr-IN",
        gap_threshold=0.5,
    )

    assert report["cutting"]["editorial_score_refined_segments"] == 1
    assert report["cutting"]["editorial_score_filled_segments"] == 1


def test_build_accuracy_report_records_story_duration_accuracy():
    transcript = [
        {"start": 0.0, "end": 95.0, "text": "A focused story."},
    ]
    kept = [{"start": 0.0, "end": 95.0, "reason": "story", "importance": 5}]

    report = build_accuracy_report(
        transcript_segments=transcript,
        kept_segments=kept,
        original_duration=240.0,
        target_duration=90,
        transcription_provider="sarvam",
        language="en-IN",
        gap_threshold=0.5,
    )

    assert report["story"]["duration_error_seconds"] == 5.0
    assert report["story"]["minimum_duration_seconds"] == 76.5
    assert report["story"]["maximum_duration_seconds"] == 99.0
    assert report["story"]["within_target_range"] is True


def test_build_accuracy_report_includes_export_validation():
    output_validation = {
        "valid": True,
        "checks": {
            "geometry": {"passed": True},
            "has_audio": {"passed": True},
            "duration": {"passed": True},
        },
    }

    report = build_accuracy_report(
        transcript_segments=[],
        kept_segments=[],
        original_duration=240.0,
        target_duration=90,
        transcription_provider="sarvam",
        language="mr-IN",
        gap_threshold=0.5,
        output_validation=output_validation,
    )

    assert report["output_validation"] == output_validation


def test_build_accuracy_report_summarizes_word_confidence():
    transcript = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "IVF treatment helps patients.",
            "words": [
                {"word": "IVF", "start": 0.0, "end": 0.3, "probability": 0.90},
                {"word": "treatment", "start": 0.4, "end": 1.0, "probability": 0.80},
            ],
        },
        {
            "start": 4.0,
            "end": 9.0,
            "text": "This transcript is uncertain.",
            "words": [
                {"word": "uncertain", "start": 4.0, "end": 4.6, "probability": 0.30},
                {"word": "words", "start": 4.7, "end": 5.1, "probability": 0.40},
            ],
        },
    ]

    report = build_accuracy_report(
        transcript_segments=transcript,
        kept_segments=[],
        original_duration=120.0,
        target_duration=90,
        transcription_provider="whisper",
        language="mr-IN",
        gap_threshold=0.5,
    )

    assert report["transcription"]["average_word_confidence"] == 0.6
    assert report["transcription"]["low_confidence_segments"] == 1


def test_evaluate_human_agreement_scores_keep_remove_and_cut_boundaries():
    system_decisions = [
        {"start": 0.0, "end": 4.0, "decision": "remove"},
        {"start": 4.0, "end": 9.0, "decision": "keep"},
        {"start": 9.0, "end": 14.0, "decision": "keep"},
    ]
    human_decisions = [
        {"start": 0.0, "end": 4.0, "decision": "remove"},
        {"start": 4.2, "end": 9.2, "decision": "keep"},
        {"start": 9.2, "end": 13.2, "decision": "remove"},
    ]

    report = evaluate_human_agreement(system_decisions, human_decisions, cut_tolerance_seconds=0.5)

    assert report["keep_remove"]["correct"] == 9.0
    assert report["keep_remove"]["total"] == 14.0
    assert report["keep_remove"]["unit"] == "seconds"
    assert report["keep_remove"]["raw_agreement"] == 0.643
    assert report["keep_remove"]["balanced_agreement"] == 0.722
    assert report["cut_boundaries"]["correct"] == 2
    assert report["cut_boundaries"]["total"] == 4
    assert report["overall_agreement"] == 0.611
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_uses_balanced_decision_agreement():
    system_decisions = [
        {"start": 0.0, "end": 1.0, "decision": "remove"},
        {"start": 1.0, "end": 2.0, "decision": "remove"},
        {"start": 2.0, "end": 3.0, "decision": "remove"},
        {"start": 3.0, "end": 4.0, "decision": "remove"},
        {"start": 4.0, "end": 5.0, "decision": "remove"},
        {"start": 5.0, "end": 6.0, "decision": "remove"},
        {"start": 6.0, "end": 7.0, "decision": "remove"},
        {"start": 7.0, "end": 8.0, "decision": "remove"},
        {"start": 8.0, "end": 9.0, "decision": "remove"},
        {"start": 9.0, "end": 10.0, "decision": "remove"},
    ]
    human_decisions = {"segments_to_keep": [{"start": 9.0, "end": 10.0}]}

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["keep_remove"]["raw_agreement"] == 0.9
    assert report["keep_remove"]["balanced_agreement"] == 0.5
    assert report["keep_remove"]["confusion_matrix"] == {
        "true_keep": 0,
        "true_remove": 9,
        "false_keep": 0,
        "false_remove": 1,
    }
    assert report["overall_agreement"] == 0.25
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_penalizes_human_labelled_region_missing_from_system_rows():
    system_decisions = [
        {"start": 0.0, "end": 5.0, "decision": "remove"},
    ]
    human_decisions = {
        "segments_to_keep": [{"start": 5.0, "end": 10.0}],
    }

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["keep_remove"]["confusion_matrix"] == {
        "true_keep": 0.0,
        "true_remove": 5.0,
        "false_keep": 0.0,
        "false_remove": 5.0,
    }
    assert report["keep_remove"]["balanced_agreement"] == 0.5
    assert report["overall_agreement"] == 0.25


def test_evaluate_human_agreement_is_invariant_to_system_row_segmentation():
    human_decisions = {
        "segments_to_keep": [{"start": 5.0, "end": 10.0}],
    }
    coarse_system = [
        {"start": 0.0, "end": 5.0, "decision": "remove"},
        {"start": 5.0, "end": 10.0, "decision": "keep"},
    ]
    fragmented_system = [
        *[
            {"start": index / 10, "end": (index + 1) / 10, "decision": "remove"}
            for index in range(50)
        ],
        {"start": 5.0, "end": 10.0, "decision": "keep"},
    ]

    coarse = evaluate_human_agreement(coarse_system, human_decisions)
    fragmented = evaluate_human_agreement(fragmented_system, human_decisions)

    assert fragmented["keep_remove"] == coarse["keep_remove"]
    assert fragmented["overall_agreement"] == coarse["overall_agreement"]


def test_evaluate_human_agreement_does_not_score_gap_uncovered_by_either_source():
    system_decisions = [
        {"start": 0.0, "end": 5.0, "decision": "remove"},
    ]
    human_decisions = {
        "segments_to_keep": [{"start": 10.0, "end": 15.0}],
    }

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["keep_remove"]["total"] == 10.0
    assert report["keep_remove"]["confusion_matrix"]["true_remove"] == 5.0
    assert report["keep_remove"]["confusion_matrix"]["false_remove"] == 5.0


def test_evaluate_human_agreement_scores_full_declared_source_timeline():
    system_decisions = [
        {"start": 0.0, "end": 5.0, "decision": "keep"},
    ]
    human_decisions = {
        "segments_to_keep": [{"start": 0.0, "end": 5.0}],
    }

    report = evaluate_human_agreement(
        system_decisions,
        human_decisions,
        source_duration_seconds=10.0,
    )

    assert report["keep_remove"]["total"] == 10.0
    assert report["keep_remove"]["confusion_matrix"] == {
        "true_keep": 5.0,
        "true_remove": 5.0,
        "false_keep": 0.0,
        "false_remove": 0.0,
    }


def test_evaluate_human_agreement_rejects_system_range_outside_declared_source():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 12.0, "decision": "keep"}],
        {"segments_to_keep": [{"start": 0.0, "end": 10.0}]},
        source_duration_seconds=10.0,
    )

    assert report["system_valid"] is False
    assert "source duration" in report["system_issue"].lower()
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_rejects_actual_cut_range_outside_declared_source():
    report = evaluate_human_agreement(
        [{
            "start": 0.0,
            "end": 10.0,
            "decision": "keep",
            "cut_start": 0.0,
            "cut_end": 12.0,
        }],
        {"segments_to_keep": [{"start": 0.0, "end": 10.0}]},
        source_duration_seconds=10.0,
    )

    assert report["system_valid"] is False
    assert "actual cut" in report["system_issue"].lower()
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_rejects_human_range_outside_declared_source():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 10.0, "decision": "keep"}],
        {"segments_to_keep": [{"start": -1.0, "end": 10.0}]},
        source_duration_seconds=10.0,
    )

    assert report["label_valid"] is False
    assert "source duration" in report["label_issue"].lower()
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_matches_each_human_boundary_once():
    system_decisions = [
        {"start": 0.0, "end": 5.0, "decision": "keep"},
        {"start": 0.1, "end": 5.1, "decision": "keep"},
    ]
    human_decisions = {"segments_to_keep": [{"start": 0.0, "end": 5.0}]}

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["cut_boundaries"]["correct"] == 2
    assert report["cut_boundaries"]["total"] == 4
    assert report["cut_boundaries"]["agreement"] == 0.5


def test_evaluate_human_agreement_scores_start_and_end_boundaries_separately():
    system_decisions = [
        {
            "start": 4.0,
            "end": 10.0,
            "decision": "keep",
            "cut_start": 4.0,
            "cut_end": 10.0,
        },
    ]
    human_decisions = {"segments_to_keep": [{"start": 4.2, "end": 12.0}]}

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["cut_boundaries"]["correct"] == 1
    assert report["cut_boundaries"]["total"] == 2
    assert report["cut_boundaries"]["agreement"] == 0.5


def test_evaluate_human_agreement_uses_actual_cut_boundaries_from_decisions():
    system_decisions = [
        {
            "start": 4.0,
            "end": 9.0,
            "decision": "keep",
            "cut_start": 4.4,
            "cut_end": 8.6,
        },
    ]
    human_decisions = {"segments_to_keep": [{"start": 4.4, "end": 8.6}]}

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["cut_boundaries"]["correct"] == 2
    assert report["cut_boundaries"]["total"] == 2
    assert report["cut_boundaries"]["agreement"] == 1.0


def test_evaluate_human_agreement_counts_shared_actual_cut_range_once():
    system_decisions = [
        {
            "start": 0.0,
            "end": 5.0,
            "decision": "keep",
            "cut_start": 0.0,
            "cut_end": 10.0,
        },
        {
            "start": 5.0,
            "end": 10.0,
            "decision": "keep",
            "cut_start": 0.0,
            "cut_end": 10.0,
        },
    ]
    human_decisions = {"segments_to_keep": [{"start": 0.0, "end": 10.0}]}

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["cut_boundaries"]["correct"] == 2
    assert report["cut_boundaries"]["total"] == 2
    assert report["system_edit_duration_seconds"] == 10.0


def test_evaluate_human_agreement_requires_story_meaning_assessment_to_pass_target():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 5.0, "decision": "keep"}],
        {"segments_to_keep": [{"start": 0.0, "end": 5.0}]},
    )

    assert report["overall_agreement"] == 1.0
    assert report["story_meaning"]["assessed"] is False
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_passes_perfect_edit_with_preserved_story_meaning():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 5.0, "decision": "keep"}],
        {
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": True,
        },
    )

    assert report["story_meaning"] == {"assessed": True, "preserved": True}
    assert report["meets_95_percent_target"] is True


def test_evaluate_human_agreement_fails_target_when_story_meaning_is_not_preserved():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 5.0, "decision": "keep"}],
        {
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": False,
        },
    )

    assert report["overall_agreement"] == 1.0
    assert report["story_meaning"] == {"assessed": True, "preserved": False}
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_rejects_empty_human_labels():
    system_decisions = [
        {"start": 0.0, "end": 5.0, "decision": "remove"},
        {"start": 5.0, "end": 10.0, "decision": "remove"},
    ]

    report = evaluate_human_agreement(system_decisions, {"segments_to_keep": []})

    assert report["label_valid"] is False
    assert report["overall_agreement"] == 0.0
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_rejects_overlapping_conflicting_human_labels():
    system_decisions = [
        {"start": 0.0, "end": 10.0, "decision": "keep"},
    ]
    human_decisions = [
        {"start": 0.0, "end": 6.0, "decision": "keep"},
        {"start": 5.0, "end": 10.0, "decision": "remove"},
    ]

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["label_valid"] is False
    assert "overlap" in report["label_issue"].lower()
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_merges_overlapping_same_decision_human_labels():
    system_decisions = [
        {"start": 0.0, "end": 10.0, "decision": "keep"},
    ]
    human_decisions = [
        {"start": 0.0, "end": 6.0, "decision": "keep"},
        {"start": 5.0, "end": 10.0, "decision": "keep"},
    ]

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["label_valid"] is True
    assert report["cut_boundaries"]["correct"] == 2
    assert report["cut_boundaries"]["total"] == 2
    assert report["cut_boundaries"]["agreement"] == 1.0
    assert report["overall_agreement"] == 1.0


def test_evaluate_human_agreement_rejects_overlapping_conflicting_system_decisions():
    system_decisions = [
        {"start": 0.0, "end": 10.0, "decision": "keep"},
        {"start": 5.0, "end": 10.0, "decision": "remove"},
    ]
    human_decisions = {
        "segments_to_keep": [{"start": 0.0, "end": 10.0}],
        "story_meaning_preserved": True,
    }

    report = evaluate_human_agreement(system_decisions, human_decisions)

    assert report["system_valid"] is False
    assert "system" in report["system_issue"].lower()
    assert "overlap" in report["system_issue"].lower()
    assert report["overall_agreement"] == 0.0
    assert report["meets_95_percent_target"] is False


def test_evaluate_human_agreement_rejects_invalid_human_ranges():
    report = evaluate_human_agreement(
        [{"start": 0.0, "end": 5.0, "decision": "remove"}],
        [{"start": 5.0, "end": 4.0, "decision": "keep"}],
    )

    assert report["label_valid"] is False
    assert "positive duration" in report["label_issue"].lower()


def test_write_accuracy_outputs_includes_human_agreement_when_labels_are_supplied(tmp_path):
    transcript = [
        {"start": 0.0, "end": 4.0, "text": "Welcome everyone."},
        {"start": 4.0, "end": 9.0, "text": "We provide IVF treatment and patient support."},
    ]
    kept = [{"start": 4.0, "end": 9.0, "reason": "topic relevant", "importance": 5}]
    labels_path = tmp_path / "human_labels.json"
    labels_path.write_text(
        json.dumps({"segments_to_keep": [{"start": 4.1, "end": 9.2}]}),
        encoding="utf-8",
    )

    write_accuracy_outputs(
        transcript_segments=transcript,
        kept_segments=kept,
        output_video_path=str(tmp_path / "edited_90s.mp4"),
        original_duration=120.0,
        target_duration=90,
        transcription_provider="sarvam",
        language="mr-IN",
        gap_threshold=0.5,
        human_decisions_path=str(labels_path),
    )

    report = json.loads((tmp_path / "accuracy_report.json").read_text(encoding="utf-8"))
    assert report["human_editor_agreement"]["overall_agreement"] == 0.984
    assert report["human_editor_agreement"]["label_source"] == str(labels_path)
