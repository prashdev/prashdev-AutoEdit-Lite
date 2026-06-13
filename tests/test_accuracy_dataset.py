import json

import accuracy_dataset
from accuracy_dataset import evaluate_accuracy_dataset, write_accuracy_dataset_report


def test_evaluate_accuracy_dataset_pools_human_agreement_counts(tmp_path):
    case1 = tmp_path / "case1"
    case2 = tmp_path / "case2"
    case1.mkdir()
    case2.mkdir()

    (case1 / "edit_decisions.json").write_text(
        json.dumps([
            {"start": 0.0, "end": 5.0, "decision": "remove"},
            {"start": 5.0, "end": 10.0, "decision": "keep"},
        ]),
        encoding="utf-8",
    )
    (case1 / "human_labels.json").write_text(
        json.dumps({"segments_to_keep": [{"start": 5.1, "end": 10.2}]}),
        encoding="utf-8",
    )

    (case2 / "edit_decisions.json").write_text(
        json.dumps([
            {"start": 0.0, "end": 5.0, "decision": "keep"},
            {"start": 5.0, "end": 10.0, "decision": "remove"},
        ]),
        encoding="utf-8",
    )
    (case2 / "human_labels.json").write_text(
        json.dumps({"segments_to_keep": [{"start": 5.0, "end": 10.0}]}),
        encoding="utf-8",
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": "perfect",
                    "system_decisions": "case1/edit_decisions.json",
                    "human_decisions": "case1/human_labels.json",
                },
                {
                    "name": "missed_story",
                    "system_decisions": "case2/edit_decisions.json",
                    "human_decisions": "case2/human_labels.json",
                },
            ]
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["case_count"] == 2
    assert report["aggregate"]["keep_remove"]["correct"] == 9.9
    assert report["aggregate"]["keep_remove"]["total"] == 20.2
    assert report["aggregate"]["keep_remove"]["unit"] == "seconds"
    assert report["aggregate"]["cut_boundaries"]["correct"] == 2
    assert report["aggregate"]["cut_boundaries"]["total"] == 4
    assert report["aggregate"]["overall_agreement"] == 0.495
    assert report["aggregate"]["meets_95_percent_target"] is False
    assert report["cases"][0]["name"] == "perfect"
    assert report["cases"][0]["agreement"]["overall_agreement"] == 0.985


def test_write_accuracy_dataset_report_writes_json(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 4.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({"segments_to_keep": [{"start": 0.0, "end": 4.0}]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "name": "single_case",
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }]
        }),
        encoding="utf-8",
    )

    output_path = tmp_path / "dataset_accuracy_report.json"

    write_accuracy_dataset_report(manifest_path, output_path)

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["case_count"] == 1
    assert report["aggregate"]["meets_95_percent_target"] is False
    assert report["aggregate"]["story_meaning"]["all_assessed"] is False


def test_evaluate_accuracy_dataset_requires_all_stories_to_preserve_meaning(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 5.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["story_meaning"] == {
        "assessed_cases": 1,
        "preserved_cases": 1,
        "all_assessed": True,
        "all_preserved": True,
    }
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_cannot_pass_without_representative_target_coverage(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 5.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "name": "short_unrepresentative_case",
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["overall_agreement"] == 1.0
    assert report["aggregate"]["representative_coverage"]["complete"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_can_pass_with_complete_target_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        accuracy_dataset,
        "_probe_source_video",
        lambda path: {
            "path": str(path),
            "probe_valid": True,
            "has_video": True,
            "has_audio": True,
            "duration_seconds": 240.0,
            "width": 1080,
            "height": 1920,
            "is_9_16": True,
            "duration_in_target_range": True,
            "meets_target_requirements": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(
        accuracy_dataset,
        "validate_output_video",
        lambda path, target_duration_seconds, aspect_ratio: {
            "path": str(path),
            "valid": True,
        },
    )
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    transcript_path = tmp_path / "transcript.json"
    reference_transcript_path = tmp_path / "reference_transcript.txt"
    labels_path = tmp_path / "human_labels.json"
    output_video_path = tmp_path / "edited_90s.mp4"
    subtitles_path = tmp_path / "edited_90s.srt"
    accuracy_report_path = tmp_path / "accuracy_report.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    transcript_path.write_text(
        json.dumps({
            "provider": "sarvam",
            "segments": [{"start": 0.0, "end": 3.0, "text": "We provide IVF care"}],
        }),
        encoding="utf-8",
    )
    reference_transcript_path.write_text("We provide IVF care", encoding="utf-8")
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    output_video_path.write_bytes(b"rendered-video-placeholder")
    subtitles_path.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nWe provide IVF care\n",
        encoding="utf-8",
    )
    accuracy_report_path.write_text(
        json.dumps({
            "target": {"target_duration_seconds": 90},
            "output_validation": {"valid": True},
        }),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        for index in range(10):
            source_video = tmp_path / f"{language}-{index}.mp4"
            source_video.write_bytes(b"representative-video-placeholder")
            cases.append({
                "name": f"{language}-{index}",
                "language": language,
                "source_video": source_video.name,
                "system_output_video": output_video_path.name,
                "system_subtitles": subtitles_path.name,
                "system_accuracy_report": accuracy_report_path.name,
                "source_duration_seconds": 240,
                "aspect_ratio": "9:16",
                "target_duration_seconds": 90,
                "system_decisions": "edit_decisions.json",
                "system_broll_suggestions": "broll_suggestions.json",
                "system_transcript": "transcript.json",
                "reference_transcript": "reference_transcript.txt",
                "human_decisions": "human_labels.json",
            })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"cases": cases}),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["representative_coverage"]["complete"] is True
    assert report["aggregate"]["meets_95_percent_target"] is True


def test_evaluate_accuracy_dataset_cannot_pass_without_rendered_output_videos(monkeypatch, tmp_path):
    monkeypatch.setattr(
        accuracy_dataset,
        "_probe_source_video",
        lambda path: {
            "path": str(path),
            "probe_valid": True,
            "has_video": True,
            "has_audio": True,
            "duration_seconds": 240.0,
            "width": 1080,
            "height": 1920,
            "is_9_16": True,
            "duration_in_target_range": True,
            "meets_target_requirements": True,
            "issues": [],
        },
    )
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    transcript_path = tmp_path / "transcript.json"
    reference_transcript_path = tmp_path / "reference_transcript.txt"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    transcript_path.write_text(
        json.dumps({"segments": [{"text": "We provide IVF care"}]}),
        encoding="utf-8",
    )
    reference_transcript_path.write_text("We provide IVF care", encoding="utf-8")
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        for index in range(10):
            source_video = tmp_path / f"{language}-{index}.mp4"
            source_video.write_bytes(b"representative-video-placeholder")
            cases.append({
                "name": f"{language}-{index}",
                "language": language,
                "source_video": source_video.name,
                "source_duration_seconds": 240,
                "aspect_ratio": "9:16",
                "target_duration_seconds": 90,
                "system_decisions": "edit_decisions.json",
                "system_broll_suggestions": "broll_suggestions.json",
                "system_transcript": "transcript.json",
                "reference_transcript": "reference_transcript.txt",
                "human_decisions": "human_labels.json",
            })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    rendered = report["aggregate"]["rendered_output_reliability"]
    assert rendered["all_rendered_outputs_valid"] is False
    assert len(rendered["invalid_cases"]) == 30
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_cannot_pass_without_subtitles_and_accuracy_reports(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        accuracy_dataset,
        "_probe_source_video",
        lambda path: {
            "path": str(path),
            "probe_valid": True,
            "has_video": True,
            "has_audio": True,
            "duration_seconds": 240.0,
            "width": 1080,
            "height": 1920,
            "is_9_16": True,
            "duration_in_target_range": True,
            "meets_target_requirements": True,
            "issues": [],
        },
    )
    monkeypatch.setattr(
        accuracy_dataset,
        "validate_output_video",
        lambda path, target_duration_seconds, aspect_ratio: {
            "path": str(path),
            "valid": True,
            "metadata": {"duration_seconds": 90.0},
        },
    )
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    transcript_path = tmp_path / "transcript.json"
    reference_transcript_path = tmp_path / "reference_transcript.txt"
    labels_path = tmp_path / "human_labels.json"
    output_video_path = tmp_path / "edited_90s.mp4"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    transcript_path.write_text(
        json.dumps({"segments": [{"text": "We provide IVF care"}]}),
        encoding="utf-8",
    )
    reference_transcript_path.write_text("We provide IVF care", encoding="utf-8")
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    output_video_path.write_bytes(b"rendered-video-placeholder")
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        for index in range(10):
            source_video = tmp_path / f"{language}-{index}.mp4"
            source_video.write_bytes(b"representative-video-placeholder")
            cases.append({
                "name": f"{language}-{index}",
                "language": language,
                "source_video": source_video.name,
                "system_output_video": output_video_path.name,
                "source_duration_seconds": 240,
                "aspect_ratio": "9:16",
                "target_duration_seconds": 90,
                "system_decisions": "edit_decisions.json",
                "system_broll_suggestions": "broll_suggestions.json",
                "system_transcript": "transcript.json",
                "reference_transcript": "reference_transcript.txt",
                "human_decisions": "human_labels.json",
            })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    outputs = report["aggregate"]["required_output_reliability"]
    assert outputs["all_required_outputs_valid"] is False
    assert len(outputs["invalid_cases"]) == 30
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_requires_ten_distinct_source_videos_per_language(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    transcript_path = tmp_path / "transcript.json"
    reference_transcript_path = tmp_path / "reference_transcript.txt"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    transcript_path.write_text(
        json.dumps({"segments": [{"text": "We provide IVF care"}]}),
        encoding="utf-8",
    )
    reference_transcript_path.write_text("We provide IVF care", encoding="utf-8")
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        source_video = tmp_path / f"{language}.mp4"
        source_video.write_bytes(b"representative-video-placeholder")
        cases.extend({
            "name": f"{language}-{index}",
            "language": language,
            "source_video": source_video.name,
            "source_duration_seconds": 240,
            "aspect_ratio": "9:16",
            "target_duration_seconds": 90,
            "system_decisions": "edit_decisions.json",
            "system_broll_suggestions": "broll_suggestions.json",
            "system_transcript": "transcript.json",
            "reference_transcript": "reference_transcript.txt",
            "human_decisions": "human_labels.json",
        } for index in range(10))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    coverage = report["aggregate"]["representative_coverage"]
    assert coverage["minimum_distinct_cases_per_language"] == 10
    assert coverage["distinct_case_counts"] == {
        "mr-IN": 1,
        "hi-IN": 1,
        "en-IN": 1,
    }
    assert coverage["insufficient_distinct_languages"] == ["en-IN", "hi-IN", "mr-IN"]
    assert coverage["complete"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_rejects_unprobeable_source_media(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    transcript_path = tmp_path / "transcript.json"
    reference_transcript_path = tmp_path / "reference_transcript.txt"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    transcript_path.write_text(
        json.dumps({"segments": [{"text": "We provide IVF care"}]}),
        encoding="utf-8",
    )
    reference_transcript_path.write_text("We provide IVF care", encoding="utf-8")
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        for index in range(10):
            source_video = tmp_path / f"{language}-{index}.mp4"
            source_video.write_bytes(b"not-a-real-video")
            cases.append({
                "name": f"{language}-{index}",
                "language": language,
                "source_video": source_video.name,
                "source_duration_seconds": 240,
                "aspect_ratio": "9:16",
                "target_duration_seconds": 90,
                "system_decisions": "edit_decisions.json",
                "system_broll_suggestions": "broll_suggestions.json",
                "system_transcript": "transcript.json",
                "reference_transcript": "reference_transcript.txt",
                "human_decisions": "human_labels.json",
            })
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    coverage = report["aggregate"]["representative_coverage"]
    assert coverage["all_source_media_valid"] is False
    assert len(coverage["invalid_source_media_cases"]) == 30
    assert coverage["complete"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_cannot_pass_without_reference_transcripts(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["fertility clinic consultation"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
            "broll_relevance_ratings": [{
                "source_timestamp": 0.0,
                "source_end": 90.0,
                "relevant": True,
            }],
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": language,
                    "language": language,
                    "source_duration_seconds": 240,
                    "aspect_ratio": "9:16",
                    "target_duration_seconds": 90,
                    "system_decisions": "edit_decisions.json",
                    "system_broll_suggestions": "broll_suggestions.json",
                    "human_decisions": "human_labels.json",
                }
                for language in ("mr-IN", "hi-IN", "en-IN")
            ],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["overall_agreement"] == 1.0
    assert report["aggregate"]["transcription_accuracy"]["all_cases_meet_target"] is False
    assert report["aggregate"]["transcription_accuracy"]["meets_95_percent_target"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_requires_transcription_accuracy_per_target_language(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    broll_path = tmp_path / "broll_suggestions.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    broll_path.write_text(
        json.dumps([{
            "source_timestamp": 0.0,
            "source_end": 90.0,
            "keywords": ["topic visual"],
            "insert_mode": "suggest_only",
        }]),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        case_dir = tmp_path / language
        case_dir.mkdir()
        reference_words = [f"word{index}" for index in range(100)]
        system_words = list(reference_words)
        if language == "hi-IN":
            reference_words = ["एक", "दो", "तीन", "चार"]
            system_words = ["एक", "दो", "गलत", "चार"]
        (case_dir / "transcript.json").write_text(
            json.dumps({"segments": [{"text": " ".join(system_words)}]}),
            encoding="utf-8",
        )
        (case_dir / "reference.txt").write_text(
            " ".join(reference_words),
            encoding="utf-8",
        )
        (case_dir / "human_labels.json").write_text(
            json.dumps({
                "segments_to_keep": [{"start": 0.0, "end": 90.0}],
                "story_meaning_preserved": True,
                "broll_relevance_ratings": [{
                    "source_timestamp": 0.0,
                    "source_end": 90.0,
                    "relevant": True,
                }],
            }),
            encoding="utf-8",
        )
        cases.append({
            "name": language,
            "language": language,
            "source_duration_seconds": 240,
            "aspect_ratio": "9:16",
            "target_duration_seconds": 90,
            "system_decisions": "edit_decisions.json",
            "system_broll_suggestions": "broll_suggestions.json",
            "system_transcript": f"{language}/transcript.json",
            "reference_transcript": f"{language}/reference.txt",
            "human_decisions": f"{language}/human_labels.json",
        })

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["transcription_accuracy"]["accuracy"] > 0.95
    assert report["aggregate"]["transcription_accuracy"]["below_target_languages"] == ["hi-IN"]
    assert report["aggregate"]["transcription_accuracy"]["all_languages_meet_target"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_cannot_pass_without_human_rated_broll(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": language,
                    "language": language,
                    "source_duration_seconds": 240,
                    "aspect_ratio": "9:16",
                    "target_duration_seconds": 90,
                    "system_decisions": "edit_decisions.json",
                    "human_decisions": "human_labels.json",
                }
                for language in ("mr-IN", "hi-IN", "en-IN")
            ],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["overall_agreement"] == 1.0
    assert report["aggregate"]["broll_relevance"]["all_suggestions_rated"] is False
    assert report["aggregate"]["broll_relevance"]["meets_95_percent_target"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_requires_broll_relevance_per_target_language(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    cases = []
    for language in ("mr-IN", "hi-IN", "en-IN"):
        case_dir = tmp_path / language
        case_dir.mkdir()
        suggestion_count = 1 if language == "hi-IN" else 20
        suggestions = [
            {
                "source_timestamp": float(index * 4),
                "source_end": float(index * 4 + 3),
                "keywords": ["topic visual"],
                "insert_mode": "suggest_only",
            }
            for index in range(suggestion_count)
        ]
        ratings = [
            {
                "source_timestamp": suggestion["source_timestamp"],
                "source_end": suggestion["source_end"],
                "relevant": language != "hi-IN",
            }
            for suggestion in suggestions
        ]
        (case_dir / "broll_suggestions.json").write_text(
            json.dumps(suggestions),
            encoding="utf-8",
        )
        (case_dir / "human_labels.json").write_text(
            json.dumps({
                "segments_to_keep": [{"start": 0.0, "end": 90.0}],
                "story_meaning_preserved": True,
                "broll_relevance_ratings": ratings,
            }),
            encoding="utf-8",
        )
        cases.append({
            "name": language,
            "language": language,
            "source_duration_seconds": 240,
            "aspect_ratio": "9:16",
            "target_duration_seconds": 90,
            "system_decisions": "edit_decisions.json",
            "system_broll_suggestions": f"{language}/broll_suggestions.json",
            "human_decisions": f"{language}/human_labels.json",
        })

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["broll_relevance"]["relevance_agreement"] > 0.95
    assert report["aggregate"]["broll_relevance"]["below_target_languages"] == ["hi-IN"]
    assert report["aggregate"]["broll_relevance"]["all_languages_meet_target"] is False
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_requires_each_target_language_to_meet_goal(tmp_path):
    perfect_decisions_path = tmp_path / "perfect_decisions.json"
    weak_decisions_path = tmp_path / "weak_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    perfect_decisions_path.write_text(
        json.dumps([
            {
                "start": 0.0,
                "end": 90.0,
                "decision": "keep",
                "cut_start": 0.0,
                "cut_end": 90.0,
            },
        ]),
        encoding="utf-8",
    )
    weak_decisions_path.write_text(
        json.dumps([
            {
                "start": 0.0,
                "end": 70.0,
                "decision": "keep",
                "cut_start": 0.0,
                "cut_end": 90.0,
            },
        ]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": language,
                    "language": language,
                    "source_duration_seconds": 240,
                    "aspect_ratio": "9:16",
                    "target_duration_seconds": 90,
                    "system_decisions": (
                        "weak_decisions.json"
                        if language == "hi-IN"
                        else "perfect_decisions.json"
                    ),
                    "human_decisions": "human_labels.json",
                }
                for language in ("mr-IN", "hi-IN", "en-IN")
            ],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["overall_agreement"] > 0.95
    assert report["aggregate"]["language_reliability"]["all_languages_meet_target"] is False
    assert report["aggregate"]["language_reliability"]["below_target_languages"] == ["hi-IN"]
    assert (
        report["aggregate"]["language_reliability"]["languages"]["hi-IN"][
            "overall_agreement"
        ]
        < 0.95
    )
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_rejects_materially_short_actual_edits(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 5.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": language,
                    "language": language,
                    "source_duration_seconds": 240,
                    "aspect_ratio": "9:16",
                    "target_duration_seconds": 90,
                    "system_decisions": "edit_decisions.json",
                    "human_decisions": "human_labels.json",
                }
                for language in ("mr-IN", "hi-IN", "en-IN")
            ],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["overall_agreement"] == 1.0
    assert report["aggregate"]["edit_duration_reliability"]["all_within_target_range"] is False
    assert report["aggregate"]["edit_duration_reliability"]["invalid_cases"] == [
        {"name": "mr-IN", "actual_seconds": 5.0},
        {"name": "hi-IN", "actual_seconds": 5.0},
        {"name": "en-IN", "actual_seconds": 5.0},
    ]
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_scores_each_case_full_source_duration(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 90.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 90.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "language": "mr-IN",
                "source_duration_seconds": 240,
                "aspect_ratio": "9:16",
                "target_duration_seconds": 90,
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }],
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["cases"][0]["agreement"]["keep_remove"]["total"] == 240.0
    assert (
        report["cases"][0]["agreement"]["keep_remove"]["confusion_matrix"]["true_remove"]
        == 150.0
    )


def test_evaluate_accuracy_dataset_uses_balanced_keep_remove_agreement(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([
            {"start": float(index), "end": float(index + 1), "decision": "remove"}
            for index in range(10)
        ]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({"segments_to_keep": [{"start": 9.0, "end": 10.0}]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "name": "all_remove_bias",
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }]
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["keep_remove"]["raw_agreement"] == 0.9
    assert report["aggregate"]["keep_remove"]["balanced_agreement"] == 0.5
    assert report["aggregate"]["overall_agreement"] == 0.25
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_cannot_pass_with_invalid_label_case(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    valid_labels_path = tmp_path / "valid_labels.json"
    invalid_labels_path = tmp_path / "invalid_labels.json"
    decisions_path.write_text(
        json.dumps([{"start": 0.0, "end": 5.0, "decision": "keep"}]),
        encoding="utf-8",
    )
    valid_labels_path.write_text(
        json.dumps({"segments_to_keep": [{"start": 0.0, "end": 5.0}]}),
        encoding="utf-8",
    )
    invalid_labels_path.write_text(
        json.dumps({"segments_to_keep": []}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [
                {
                    "name": "valid",
                    "system_decisions": "edit_decisions.json",
                    "human_decisions": "valid_labels.json",
                },
                {
                    "name": "invalid",
                    "system_decisions": "edit_decisions.json",
                    "human_decisions": "invalid_labels.json",
                },
            ]
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["labels_valid"] is False
    assert report["aggregate"]["invalid_label_cases"] == 1
    assert report["aggregate"]["meets_95_percent_target"] is False


def test_evaluate_accuracy_dataset_reports_invalid_system_case(tmp_path):
    decisions_path = tmp_path / "edit_decisions.json"
    labels_path = tmp_path / "human_labels.json"
    decisions_path.write_text(
        json.dumps([
            {"start": 0.0, "end": 5.0, "decision": "keep"},
            {"start": 2.0, "end": 5.0, "decision": "remove"},
        ]),
        encoding="utf-8",
    )
    labels_path.write_text(
        json.dumps({
            "segments_to_keep": [{"start": 0.0, "end": 5.0}],
            "story_meaning_preserved": True,
        }),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "cases": [{
                "name": "contradictory_system",
                "system_decisions": "edit_decisions.json",
                "human_decisions": "human_labels.json",
            }]
        }),
        encoding="utf-8",
    )

    report = evaluate_accuracy_dataset(manifest_path)

    assert report["aggregate"]["systems_valid"] is False
    assert report["aggregate"]["invalid_system_cases"] == 1
    assert report["aggregate"]["meets_95_percent_target"] is False
