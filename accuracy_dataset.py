"""
accuracy_dataset.py

Batch evaluator for measuring AutoEdit-Lite decisions against human-editor
labels across a labelled dataset.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import unicodedata
from pathlib import Path

from accuracy_outputs import AGREEMENT_GOAL, evaluate_human_agreement
from output_validation import validate_output_video


REQUIRED_TARGET_LANGUAGES = ("mr-IN", "hi-IN", "en-IN")
MIN_SOURCE_DURATION_SECONDS = 180.0
MAX_SOURCE_DURATION_SECONDS = 420.0
TARGET_ASPECT_RATIO = "9:16"
TARGET_EDIT_DURATION_SECONDS = 90.0
MIN_EDIT_DURATION_RATIO = 0.85
MAX_EDIT_DURATION_RATIO = 1.10
MIN_DISTINCT_CASES_PER_LANGUAGE = 10
SRT_TIMING_PATTERN = re.compile(
    r"(?m)^\d+\s*\n"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*\n(.+)$"
)


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _load_json(path: Path) -> dict | list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _probe_source_video(path: Path) -> dict:
    result = {
        "path": str(path),
        "probe_valid": False,
        "has_video": False,
        "has_audio": False,
        "duration_seconds": None,
        "width": None,
        "height": None,
        "is_9_16": False,
        "duration_in_target_range": False,
        "meets_target_requirements": False,
        "issues": [],
    }
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "ffprobe failed")
        payload = json.loads(completed.stdout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        result["issues"].append(f"source media probe failed: {exc}")
        return result

    streams = payload.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "video"),
        None,
    )
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    try:
        duration = float(payload.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = None
    try:
        width = int(video_stream.get("width")) if video_stream else None
        height = int(video_stream.get("height")) if video_stream else None
    except (TypeError, ValueError):
        width = None
        height = None

    probe_valid = duration is not None and math.isfinite(duration) and duration > 0
    is_9_16 = (
        width is not None
        and height is not None
        and width > 0
        and height > 0
        and abs(width / height - 9 / 16) <= 0.01
    )
    duration_in_target_range = (
        probe_valid
        and MIN_SOURCE_DURATION_SECONDS <= duration <= MAX_SOURCE_DURATION_SECONDS
    )
    issues = []
    if not probe_valid:
        issues.append("source media duration could not be measured")
    if video_stream is None:
        issues.append("source media must contain video")
    if not has_audio:
        issues.append("source media must contain audio")
    if not is_9_16:
        issues.append("source media geometry must be 9:16")
    if not duration_in_target_range:
        issues.append("actual source duration must be between 180 and 420 seconds")

    result.update({
        "probe_valid": probe_valid,
        "has_video": video_stream is not None,
        "has_audio": has_audio,
        "duration_seconds": round(duration, 3) if probe_valid else None,
        "width": width,
        "height": height,
        "is_9_16": is_9_16,
        "duration_in_target_range": duration_in_target_range,
        "meets_target_requirements": not issues,
        "issues": issues,
    })
    return result


def _validate_rendered_output(
    path: Path | None,
    target_duration_seconds: float | int | None,
) -> dict:
    if path is None or not path.is_file():
        return {
            "path": str(path) if path else None,
            "valid": False,
            "reason": "rendered output video must reference an existing file",
        }
    try:
        target_duration = int(float(target_duration_seconds))
        return validate_output_video(
            path,
            target_duration_seconds=target_duration,
            aspect_ratio=TARGET_ASPECT_RATIO,
        )
    except (TypeError, ValueError, OSError, RuntimeError) as exc:
        return {
            "path": str(path),
            "valid": False,
            "reason": f"rendered output validation failed: {exc}",
        }


def _srt_seconds(parts: tuple[str, str, str, str]) -> float:
    hours, minutes, seconds, milliseconds = (int(part) for part in parts)
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def _validate_subtitles(path: Path | None, rendered_output: dict) -> dict:
    issues = []
    if path is None or not path.is_file():
        issues.append("edited subtitle must reference an existing file")
        return {"path": str(path) if path else None, "valid": False, "issues": issues}
    content = path.read_text(encoding="utf-8-sig")
    matches = list(SRT_TIMING_PATTERN.finditer(content))
    rendered_duration = (
        rendered_output.get("metadata", {}).get("duration_seconds")
        if isinstance(rendered_output, dict)
        else None
    )
    previous_end = 0.0
    for match in matches:
        start = _srt_seconds(match.groups()[0:4])
        end = _srt_seconds(match.groups()[4:8])
        text = match.group(9).strip()
        if not text or end <= start or start < previous_end - 0.001:
            issues.append("subtitle cues must be nonempty, chronological, and positive")
            break
        if rendered_duration is not None and end > float(rendered_duration) + 0.1:
            issues.append("subtitle cue extends beyond rendered output duration")
            break
        previous_end = end
    if not matches:
        issues.append("edited subtitle must contain at least one valid SRT cue")
    return {
        "path": str(path),
        "valid": not issues,
        "cue_count": len(matches),
        "issues": issues,
    }


def _validate_accuracy_report(path: Path | None, target_duration_seconds: object) -> dict:
    issues = []
    if path is None or not path.is_file():
        issues.append("accuracy report must reference an existing file")
        return {"path": str(path) if path else None, "valid": False, "issues": issues}
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "valid": False,
            "issues": [f"accuracy report could not be loaded: {exc}"],
        }
    if not isinstance(payload, dict):
        issues.append("accuracy report must be a JSON object")
    else:
        try:
            report_target = float(payload.get("target", {}).get("target_duration_seconds"))
            expected_target = float(target_duration_seconds)
        except (TypeError, ValueError):
            report_target = expected_target = None
        if report_target is None or report_target != expected_target:
            issues.append("accuracy report target duration must match the dataset case")
        if payload.get("output_validation", {}).get("valid") is not True:
            issues.append("accuracy report must record valid rendered output")
    return {"path": str(path), "valid": not issues, "issues": issues}


def _transcript_text(payload: dict | list[dict] | str) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return " ".join(
            str(segment.get("text", "")).strip()
            for segment in payload
            if isinstance(segment, dict) and str(segment.get("text", "")).strip()
        )
    if isinstance(payload, dict):
        if isinstance(payload.get("text"), str):
            return payload["text"]
        if isinstance(payload.get("transcript"), str):
            return payload["transcript"]
        return _transcript_text(payload.get("segments", []))
    return ""


def _load_transcript_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return _transcript_text(json.loads(content))
    return content


def _transcript_words(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = []
    current = []
    for character in normalized:
        if unicodedata.category(character)[:1] in {"L", "M", "N"}:
            current.append(character)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _word_error_count(reference_words: list[str], system_words: list[str]) -> int:
    previous = list(range(len(system_words) + 1))
    for reference_index, reference_word in enumerate(reference_words, start=1):
        current = [reference_index]
        for system_index, system_word in enumerate(system_words, start=1):
            current.append(min(
                current[-1] + 1,
                previous[system_index] + 1,
                previous[system_index - 1] + (reference_word != system_word),
            ))
        previous = current
    return previous[-1]


def _evaluate_transcription_accuracy(
    system_text: str | None,
    reference_text: str | None,
) -> dict:
    system_words = _transcript_words(system_text or "")
    reference_words = _transcript_words(reference_text or "")
    valid = system_text is not None and reference_text is not None and bool(reference_words)
    errors = _word_error_count(reference_words, system_words) if valid else 0
    accuracy = max(0.0, 1.0 - errors / len(reference_words)) if valid else 0.0
    return {
        "valid": valid,
        "reference_words": len(reference_words),
        "system_words": len(system_words),
        "word_errors": errors,
        "word_error_rate": round(errors / len(reference_words), 3) if valid else None,
        "accuracy": round(accuracy, 3),
        "meets_95_percent_target": valid and accuracy >= AGREEMENT_GOAL,
    }


def _pooled_transcription_accuracy(case_reports: list[dict]) -> dict:
    reference_words = sum(
        case["transcription_accuracy"]["reference_words"]
        for case in case_reports
    )
    system_words = sum(
        case["transcription_accuracy"]["system_words"]
        for case in case_reports
    )
    word_errors = sum(
        case["transcription_accuracy"]["word_errors"]
        for case in case_reports
    )
    all_valid = bool(case_reports) and all(
        case["transcription_accuracy"]["valid"]
        for case in case_reports
    )
    all_cases_meet_target = bool(case_reports) and all(
        case["transcription_accuracy"]["meets_95_percent_target"]
        for case in case_reports
    )
    accuracy = (
        max(0.0, 1.0 - word_errors / reference_words)
        if all_valid and reference_words
        else 0.0
    )
    return {
        "all_valid": all_valid,
        "all_cases_meet_target": all_cases_meet_target,
        "reference_words": reference_words,
        "system_words": system_words,
        "word_errors": word_errors,
        "word_error_rate": round(word_errors / reference_words, 3)
        if all_valid and reference_words
        else None,
        "accuracy": round(accuracy, 3),
        "meets_95_percent_target": (
            all_valid
            and all_cases_meet_target
            and accuracy >= AGREEMENT_GOAL
        ),
    }


def _aggregate_transcription_accuracy(case_reports: list[dict]) -> dict:
    pooled = _pooled_transcription_accuracy(case_reports)
    languages = {}
    below_target_languages = []
    for language in REQUIRED_TARGET_LANGUAGES:
        language_cases = [
            case
            for case in case_reports
            if (case.get("metadata") or {}).get("language") == language
        ]
        language_result = _pooled_transcription_accuracy(language_cases)
        languages[language] = language_result
        if not language_result["meets_95_percent_target"]:
            below_target_languages.append(language)
    return {
        **pooled,
        "all_languages_meet_target": not below_target_languages,
        "below_target_languages": below_target_languages,
        "languages": languages,
        "meets_95_percent_target": (
            pooled["meets_95_percent_target"] and not below_target_languages
        ),
    }


def _representative_coverage(case_reports: list[dict]) -> dict:
    covered_languages: set[str] = set()
    distinct_source_videos = {
        language: set()
        for language in REQUIRED_TARGET_LANGUAGES
    }
    invalid_cases: list[dict] = []
    invalid_source_media_cases: list[dict] = []

    for case in case_reports:
        metadata = case.get("metadata") or {}
        issues = []
        language = metadata.get("language")
        if language in REQUIRED_TARGET_LANGUAGES:
            covered_languages.add(language)
        else:
            issues.append("missing or unsupported target language")

        source_video_value = case.get("source_video")
        source_video = Path(source_video_value) if source_video_value else None
        if source_video is None or not source_video.is_file():
            issues.append("source video must reference an existing file")
        elif language in distinct_source_videos:
            distinct_source_videos[language].add(str(source_video.resolve()).casefold())

        source_media = case.get("source_media") or {}
        if not source_media.get("meets_target_requirements", False):
            invalid_source_media_cases.append({
                "name": case["name"],
                "issues": source_media.get("issues", ["source media was not validated"]),
            })

        try:
            source_duration = float(metadata["source_duration_seconds"])
        except (KeyError, TypeError, ValueError):
            source_duration = None
        if (
            source_duration is None
            or not math.isfinite(source_duration)
            or not MIN_SOURCE_DURATION_SECONDS <= source_duration <= MAX_SOURCE_DURATION_SECONDS
        ):
            issues.append("source duration must be between 180 and 420 seconds")

        if metadata.get("aspect_ratio") != TARGET_ASPECT_RATIO:
            issues.append("aspect ratio must be 9:16")

        try:
            target_duration = float(metadata["target_duration_seconds"])
        except (KeyError, TypeError, ValueError):
            target_duration = None
        if (
            target_duration is None
            or not math.isfinite(target_duration)
            or target_duration != TARGET_EDIT_DURATION_SECONDS
        ):
            issues.append("target duration must be 90 seconds")

        if issues:
            invalid_cases.append({"name": case["name"], "issues": issues})

    missing_languages = sorted(set(REQUIRED_TARGET_LANGUAGES) - covered_languages)
    distinct_case_counts = {
        language: len(distinct_source_videos[language])
        for language in REQUIRED_TARGET_LANGUAGES
    }
    insufficient_distinct_languages = sorted(
        language
        for language, count in distinct_case_counts.items()
        if count < MIN_DISTINCT_CASES_PER_LANGUAGE
    )
    complete = (
        bool(case_reports)
        and not invalid_cases
        and not invalid_source_media_cases
        and not missing_languages
        and not insufficient_distinct_languages
    )
    return {
        "complete": complete,
        "required_languages": list(REQUIRED_TARGET_LANGUAGES),
        "covered_languages": sorted(covered_languages),
        "missing_languages": missing_languages,
        "all_source_media_valid": bool(case_reports) and not invalid_source_media_cases,
        "invalid_source_media_cases": invalid_source_media_cases,
        "minimum_distinct_cases_per_language": MIN_DISTINCT_CASES_PER_LANGUAGE,
        "distinct_case_counts": distinct_case_counts,
        "insufficient_distinct_languages": insufficient_distinct_languages,
        "target_source_duration_seconds": {
            "minimum": MIN_SOURCE_DURATION_SECONDS,
            "maximum": MAX_SOURCE_DURATION_SECONDS,
        },
        "target_aspect_ratio": TARGET_ASPECT_RATIO,
        "target_edit_duration_seconds": TARGET_EDIT_DURATION_SECONDS,
        "invalid_cases": invalid_cases,
    }


def _pooled_agreement(case_reports: list[dict]) -> dict:
    keep_correct = sum(c["agreement"]["keep_remove"]["correct"] for c in case_reports)
    keep_total = sum(c["agreement"]["keep_remove"]["total"] for c in case_reports)
    boundary_correct = sum(c["agreement"]["cut_boundaries"]["correct"] for c in case_reports)
    boundary_total = sum(c["agreement"]["cut_boundaries"]["total"] for c in case_reports)
    confusion = {
        key: sum(
            c["agreement"]["keep_remove"]["confusion_matrix"][key]
            for c in case_reports
        )
        for key in ("true_keep", "true_remove", "false_keep", "false_remove")
    }
    raw_keep_score = keep_correct / keep_total if keep_total else 0.0
    keep_class_total = confusion["true_keep"] + confusion["false_remove"]
    remove_class_total = confusion["true_remove"] + confusion["false_keep"]
    class_recalls = []
    if keep_class_total:
        class_recalls.append(confusion["true_keep"] / keep_class_total)
    if remove_class_total:
        class_recalls.append(confusion["true_remove"] / remove_class_total)
    balanced_keep_score = sum(class_recalls) / len(class_recalls) if class_recalls else 0.0
    boundary_score = boundary_correct / boundary_total if boundary_total else 0.0
    overall = (
        (balanced_keep_score + boundary_score) / 2
        if boundary_total
        else balanced_keep_score
    )
    return {
        "_overall_agreement": overall,
        "overall_agreement": round(overall, 3),
        "keep_remove": {
            "correct": keep_correct,
            "total": keep_total,
            "unit": "seconds",
            "agreement": round(balanced_keep_score, 3),
            "raw_agreement": round(raw_keep_score, 3),
            "balanced_agreement": round(balanced_keep_score, 3),
            "confusion_matrix": confusion,
        },
        "cut_boundaries": {
            "correct": boundary_correct,
            "total": boundary_total,
            "agreement": round(boundary_score, 3),
        },
    }


def _language_reliability(case_reports: list[dict]) -> dict:
    languages = {}
    below_target_languages = []
    for language in REQUIRED_TARGET_LANGUAGES:
        language_cases = [
            case
            for case in case_reports
            if (case.get("metadata") or {}).get("language") == language
        ]
        metrics = _pooled_agreement(language_cases)
        labels_valid = bool(language_cases) and all(
            case["agreement"].get("label_valid", False)
            for case in language_cases
        )
        systems_valid = bool(language_cases) and all(
            case["agreement"].get("system_valid", False)
            for case in language_cases
        )
        stories_preserved = bool(language_cases) and all(
            case["agreement"].get("story_meaning", {}).get("preserved") is True
            for case in language_cases
        )
        meets_target = (
            labels_valid
            and systems_valid
            and stories_preserved
            and metrics["_overall_agreement"] >= AGREEMENT_GOAL
        )
        languages[language] = {
            "case_count": len(language_cases),
            "overall_agreement": metrics["overall_agreement"],
            "meets_95_percent_target": meets_target,
            "labels_valid": labels_valid,
            "systems_valid": systems_valid,
            "all_stories_preserved": stories_preserved,
            "keep_remove": metrics["keep_remove"],
            "cut_boundaries": metrics["cut_boundaries"],
        }
        if not meets_target:
            below_target_languages.append(language)

    return {
        "all_languages_meet_target": not below_target_languages,
        "below_target_languages": below_target_languages,
        "languages": languages,
    }


def _edit_duration_reliability(case_reports: list[dict]) -> dict:
    invalid_cases = []
    for case in case_reports:
        metadata = case.get("metadata") or {}
        try:
            target_duration = float(metadata["target_duration_seconds"])
        except (KeyError, TypeError, ValueError):
            target_duration = None
        actual_duration = float(
            case.get("agreement", {}).get("system_edit_duration_seconds", 0.0)
        )
        if (
            target_duration is None
            or not math.isfinite(target_duration)
            or target_duration <= 0
            or not target_duration * MIN_EDIT_DURATION_RATIO
            <= actual_duration
            <= target_duration * MAX_EDIT_DURATION_RATIO
        ):
            invalid_cases.append({
                "name": case["name"],
                "actual_seconds": round(actual_duration, 3),
            })

    return {
        "all_within_target_range": bool(case_reports) and not invalid_cases,
        "minimum_ratio": MIN_EDIT_DURATION_RATIO,
        "maximum_ratio": MAX_EDIT_DURATION_RATIO,
        "invalid_cases": invalid_cases,
    }


def _rendered_output_reliability(case_reports: list[dict]) -> dict:
    invalid_cases = [
        {
            "name": case["name"],
            "path": case.get("system_output_video"),
            "reason": case.get("rendered_output", {}).get(
                "reason",
                "rendered output failed final video validation",
            ),
        }
        for case in case_reports
        if not case.get("rendered_output", {}).get("valid", False)
    ]
    return {
        "all_rendered_outputs_valid": bool(case_reports) and not invalid_cases,
        "valid_cases": len(case_reports) - len(invalid_cases),
        "invalid_cases": invalid_cases,
    }


def _required_output_reliability(case_reports: list[dict]) -> dict:
    invalid_cases = []
    for case in case_reports:
        issues = []
        if not case.get("subtitles", {}).get("valid", False):
            issues.extend(case.get("subtitles", {}).get("issues", ["invalid subtitles"]))
        if not case.get("accuracy_report", {}).get("valid", False):
            issues.extend(
                case.get("accuracy_report", {}).get("issues", ["invalid accuracy report"])
            )
        if issues:
            invalid_cases.append({"name": case["name"], "issues": issues})
    return {
        "all_required_outputs_valid": bool(case_reports) and not invalid_cases,
        "valid_cases": len(case_reports) - len(invalid_cases),
        "invalid_cases": invalid_cases,
    }


def _evaluate_broll_relevance(
    system_suggestions: list[dict] | None,
    human_decisions: dict | list[dict],
    tolerance_seconds: float = 0.5,
) -> dict:
    ratings = (
        human_decisions.get("broll_relevance_ratings", [])
        if isinstance(human_decisions, dict)
        else []
    )
    suggestions = system_suggestions if isinstance(system_suggestions, list) else []
    valid_ratings = []
    labels_valid = isinstance(ratings, list)
    if labels_valid:
        for rating in ratings:
            try:
                start = float(rating["source_timestamp"])
                end = float(rating["source_end"])
            except (KeyError, TypeError, ValueError):
                labels_valid = False
                break
            if (
                not math.isfinite(start)
                or not math.isfinite(end)
                or end <= start
                or not isinstance(rating.get("relevant"), bool)
            ):
                labels_valid = False
                break
            valid_ratings.append({
                "source_timestamp": start,
                "source_end": end,
                "relevant": rating["relevant"],
            })

    candidates = []
    if labels_valid:
        for suggestion_index, suggestion in enumerate(suggestions):
            try:
                suggestion_start = float(suggestion["source_timestamp"])
                suggestion_end = float(suggestion["source_end"])
            except (KeyError, TypeError, ValueError):
                continue
            for rating_index, rating in enumerate(valid_ratings):
                start_delta = abs(suggestion_start - rating["source_timestamp"])
                end_delta = abs(suggestion_end - rating["source_end"])
                if start_delta <= tolerance_seconds and end_delta <= tolerance_seconds:
                    candidates.append((
                        start_delta + end_delta,
                        suggestion_index,
                        rating_index,
                    ))

    matched_suggestions: set[int] = set()
    matched_ratings: set[int] = set()
    relevant_suggestions = 0
    for _, suggestion_index, rating_index in sorted(candidates):
        if suggestion_index in matched_suggestions or rating_index in matched_ratings:
            continue
        matched_suggestions.add(suggestion_index)
        matched_ratings.add(rating_index)
        if valid_ratings[rating_index]["relevant"]:
            relevant_suggestions += 1

    suggestion_count = len(suggestions)
    rated_suggestions = len(matched_suggestions)
    all_suggestions_rated = (
        suggestion_count > 0
        and labels_valid
        and rated_suggestions == suggestion_count
    )
    relevance_agreement = (
        relevant_suggestions / suggestion_count
        if suggestion_count
        else 0.0
    )
    return {
        "labels_valid": labels_valid,
        "system_suggestion_count": suggestion_count,
        "human_rating_count": len(valid_ratings),
        "rated_suggestions": rated_suggestions,
        "relevant_suggestions": relevant_suggestions,
        "all_suggestions_rated": all_suggestions_rated,
        "relevance_agreement": round(relevance_agreement, 3),
        "meets_95_percent_target": (
            all_suggestions_rated and relevance_agreement >= AGREEMENT_GOAL
        ),
        "tolerance_seconds": tolerance_seconds,
    }


def _pooled_broll_relevance(case_reports: list[dict]) -> dict:
    suggestion_count = sum(
        case["broll_relevance"]["system_suggestion_count"]
        for case in case_reports
    )
    rated_suggestions = sum(
        case["broll_relevance"]["rated_suggestions"]
        for case in case_reports
    )
    relevant_suggestions = sum(
        case["broll_relevance"]["relevant_suggestions"]
        for case in case_reports
    )
    labels_valid = bool(case_reports) and all(
        case["broll_relevance"]["labels_valid"]
        for case in case_reports
    )
    all_suggestions_rated = suggestion_count > 0 and all(
        case["broll_relevance"]["all_suggestions_rated"]
        for case in case_reports
    )
    relevance_agreement = (
        relevant_suggestions / suggestion_count
        if suggestion_count
        else 0.0
    )
    return {
        "labels_valid": labels_valid,
        "system_suggestion_count": suggestion_count,
        "rated_suggestions": rated_suggestions,
        "relevant_suggestions": relevant_suggestions,
        "all_suggestions_rated": all_suggestions_rated,
        "relevance_agreement": round(relevance_agreement, 3),
        "meets_95_percent_target": (
            labels_valid
            and all_suggestions_rated
            and relevance_agreement >= AGREEMENT_GOAL
        ),
    }


def _aggregate_broll_relevance(case_reports: list[dict]) -> dict:
    pooled = _pooled_broll_relevance(case_reports)
    languages = {}
    below_target_languages = []
    for language in REQUIRED_TARGET_LANGUAGES:
        language_cases = [
            case
            for case in case_reports
            if (case.get("metadata") or {}).get("language") == language
        ]
        language_result = _pooled_broll_relevance(language_cases)
        languages[language] = language_result
        if not language_result["meets_95_percent_target"]:
            below_target_languages.append(language)

    return {
        **pooled,
        "all_languages_meet_target": not below_target_languages,
        "below_target_languages": below_target_languages,
        "languages": languages,
        "meets_95_percent_target": (
            pooled["meets_95_percent_target"] and not below_target_languages
        ),
    }


def _aggregate_case_reports(case_reports: list[dict]) -> dict:
    pooled = _pooled_agreement(case_reports)
    invalid_label_cases = sum(
        1 for case in case_reports if not case["agreement"].get("label_valid", False)
    )
    labels_valid = bool(case_reports) and invalid_label_cases == 0
    invalid_system_cases = sum(
        1 for case in case_reports if not case["agreement"].get("system_valid", False)
    )
    systems_valid = bool(case_reports) and invalid_system_cases == 0
    assessed_story_cases = sum(
        1 for case in case_reports
        if case["agreement"].get("story_meaning", {}).get("assessed") is True
    )
    preserved_story_cases = sum(
        1 for case in case_reports
        if case["agreement"].get("story_meaning", {}).get("preserved") is True
    )
    all_stories_assessed = bool(case_reports) and assessed_story_cases == len(case_reports)
    all_stories_preserved = bool(case_reports) and preserved_story_cases == len(case_reports)
    representative_coverage = _representative_coverage(case_reports)
    language_reliability = _language_reliability(case_reports)
    edit_duration_reliability = _edit_duration_reliability(case_reports)
    rendered_output_reliability = _rendered_output_reliability(case_reports)
    required_output_reliability = _required_output_reliability(case_reports)
    broll_relevance = _aggregate_broll_relevance(case_reports)
    transcription_accuracy = _aggregate_transcription_accuracy(case_reports)

    return {
        "overall_agreement": pooled["overall_agreement"],
        "meets_95_percent_target": (
            labels_valid
            and systems_valid
            and all_stories_assessed
            and all_stories_preserved
            and representative_coverage["complete"]
            and language_reliability["all_languages_meet_target"]
            and edit_duration_reliability["all_within_target_range"]
            and rendered_output_reliability["all_rendered_outputs_valid"]
            and required_output_reliability["all_required_outputs_valid"]
            and broll_relevance["meets_95_percent_target"]
            and transcription_accuracy["meets_95_percent_target"]
            and pooled["_overall_agreement"] >= AGREEMENT_GOAL
        ),
        "labels_valid": labels_valid,
        "invalid_label_cases": invalid_label_cases,
        "systems_valid": systems_valid,
        "invalid_system_cases": invalid_system_cases,
        "story_meaning": {
            "assessed_cases": assessed_story_cases,
            "preserved_cases": preserved_story_cases,
            "all_assessed": all_stories_assessed,
            "all_preserved": all_stories_preserved,
        },
        "representative_coverage": representative_coverage,
        "language_reliability": language_reliability,
        "edit_duration_reliability": edit_duration_reliability,
        "rendered_output_reliability": rendered_output_reliability,
        "required_output_reliability": required_output_reliability,
        "broll_relevance": broll_relevance,
        "transcription_accuracy": transcription_accuracy,
        "keep_remove": pooled["keep_remove"],
        "cut_boundaries": pooled["cut_boundaries"],
    }


def evaluate_accuracy_dataset(
    manifest_path: str | Path,
    cut_tolerance_seconds: float = 0.5,
) -> dict:
    """
    Evaluate a manifest of labelled edit cases.

    Manifest format:
    {
      "cases": [
        {
          "name": "video-001",
          "system_decisions": "video-001/edit_decisions.json",
          "human_decisions": "video-001/human_labels.json"
        }
      ]
    }
    """
    manifest = Path(manifest_path)
    payload = _load_json(manifest)
    if not isinstance(payload, dict):
        raise ValueError("Dataset manifest must be a JSON object.")

    case_reports = []
    for index, case in enumerate(payload.get("cases", []), start=1):
        name = case.get("name") or f"case_{index}"
        system_path = _resolve_manifest_path(manifest, case["system_decisions"])
        human_path = _resolve_manifest_path(manifest, case["human_decisions"])
        system_decisions = _load_json(system_path)
        human_decisions = _load_json(human_path)
        broll_path_value = case.get("system_broll_suggestions")
        broll_path = (
            _resolve_manifest_path(manifest, broll_path_value)
            if broll_path_value
            else None
        )
        system_broll_suggestions = _load_json(broll_path) if broll_path else None
        system_transcript_value = case.get("system_transcript")
        reference_transcript_value = case.get("reference_transcript")
        system_transcript_path = (
            _resolve_manifest_path(manifest, system_transcript_value)
            if system_transcript_value
            else None
        )
        reference_transcript_path = (
            _resolve_manifest_path(manifest, reference_transcript_value)
            if reference_transcript_value
            else None
        )
        system_transcript_text = (
            _load_transcript_text(system_transcript_path)
            if system_transcript_path
            else None
        )
        reference_transcript_text = (
            _load_transcript_text(reference_transcript_path)
            if reference_transcript_path
            else None
        )
        source_video_value = case.get("source_video")
        source_video_path = (
            _resolve_manifest_path(manifest, source_video_value)
            if source_video_value
            else None
        )
        source_media = (
            _probe_source_video(source_video_path)
            if source_video_path and source_video_path.is_file()
            else {
                "path": str(source_video_path) if source_video_path else None,
                "probe_valid": False,
                "meets_target_requirements": False,
                "issues": ["source video must reference an existing file"],
            }
        )
        system_output_video_value = case.get("system_output_video")
        system_output_video_path = (
            _resolve_manifest_path(manifest, system_output_video_value)
            if system_output_video_value
            else None
        )
        rendered_output = _validate_rendered_output(
            system_output_video_path,
            case.get("target_duration_seconds"),
        )
        system_subtitles_value = case.get("system_subtitles")
        system_subtitles_path = (
            _resolve_manifest_path(manifest, system_subtitles_value)
            if system_subtitles_value
            else None
        )
        system_accuracy_report_value = case.get("system_accuracy_report")
        system_accuracy_report_path = (
            _resolve_manifest_path(manifest, system_accuracy_report_value)
            if system_accuracy_report_value
            else None
        )
        subtitles = _validate_subtitles(system_subtitles_path, rendered_output)
        accuracy_report = _validate_accuracy_report(
            system_accuracy_report_path,
            case.get("target_duration_seconds"),
        )
        source_duration = case.get("source_duration_seconds")
        try:
            source_duration = float(source_duration)
        except (TypeError, ValueError):
            source_duration = None
        if (
            source_duration is not None
            and (not math.isfinite(source_duration) or source_duration <= 0)
        ):
            source_duration = None
        if source_media.get("probe_valid"):
            source_duration = source_media["duration_seconds"]

        agreement = evaluate_human_agreement(
            system_decisions=system_decisions,
            human_decisions=human_decisions,
            cut_tolerance_seconds=cut_tolerance_seconds,
            source_duration_seconds=source_duration,
        )
        case_reports.append({
            "name": name,
            "source_video": str(source_video_path) if source_video_path else None,
            "source_media": source_media,
            "system_output_video": (
                str(system_output_video_path) if system_output_video_path else None
            ),
            "rendered_output": rendered_output,
            "system_subtitles": str(system_subtitles_path) if system_subtitles_path else None,
            "subtitles": subtitles,
            "system_accuracy_report": (
                str(system_accuracy_report_path) if system_accuracy_report_path else None
            ),
            "accuracy_report": accuracy_report,
            "system_decisions": str(system_path),
            "system_broll_suggestions": str(broll_path) if broll_path else None,
            "system_transcript": str(system_transcript_path) if system_transcript_path else None,
            "reference_transcript": (
                str(reference_transcript_path) if reference_transcript_path else None
            ),
            "human_decisions": str(human_path),
            "metadata": {
                "language": case.get("language"),
                "source_duration_seconds": case.get("source_duration_seconds"),
                "aspect_ratio": case.get("aspect_ratio"),
                "target_duration_seconds": case.get("target_duration_seconds"),
            },
            "agreement": agreement,
            "broll_relevance": _evaluate_broll_relevance(
                system_broll_suggestions,
                human_decisions,
                tolerance_seconds=cut_tolerance_seconds,
            ),
            "transcription_accuracy": _evaluate_transcription_accuracy(
                system_transcript_text,
                reference_transcript_text,
            ),
        })

    return {
        "target": {
            "agreement_goal": AGREEMENT_GOAL,
            "cut_tolerance_seconds": cut_tolerance_seconds,
        },
        "case_count": len(case_reports),
        "aggregate": _aggregate_case_reports(case_reports),
        "cases": case_reports,
        "measurement_note": (
            "Dataset-level 95% agreement is met only when aggregate."
            "meets_95_percent_target is true, representative coverage is complete, "
            "every required target language independently meets 95%, and every human "
            "reviewer confirms that the final story preserves meaning. Actual retained "
            "edit durations must also stay within 85%-110% of the declared target, and "
            "all B-roll suggestions must be human-rated with at least 95% relevance. "
            "Generated transcripts must reach at least 95% word accuracy against human "
            "references overall, per case, and independently per target language."
            f" Representative coverage requires at least "
            f"{MIN_DISTINCT_CASES_PER_LANGUAGE} distinct source videos per target "
            "language, and ffprobe must confirm that every source contains video and "
            "audio, is 9:16, and lasts 180-420 seconds. Every case must also include "
            "a rendered output that passes final duration, 9:16 geometry, audio "
            "presence, and audio/video sync validation, plus a valid nonempty SRT and "
            "per-run accuracy report whose target and output validation match the case."
        ),
    }


def write_accuracy_dataset_report(
    manifest_path: str | Path,
    output_path: str | Path,
    cut_tolerance_seconds: float = 0.5,
) -> dict:
    report = evaluate_accuracy_dataset(
        manifest_path=manifest_path,
        cut_tolerance_seconds=cut_tolerance_seconds,
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
        prog="accuracy-dataset",
        description="Evaluate AutoEdit-Lite edit decisions against human labels.",
    )
    parser.add_argument("--manifest", required=True, help="Dataset manifest JSON path.")
    parser.add_argument(
        "--output",
        default="dataset_accuracy_report.json",
        help="Where to write the aggregate accuracy report.",
    )
    parser.add_argument(
        "--cut-tolerance",
        type=float,
        default=0.5,
        help="Allowed start/end timestamp error in seconds for kept segments.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = write_accuracy_dataset_report(
        manifest_path=args.manifest,
        output_path=args.output,
        cut_tolerance_seconds=args.cut_tolerance,
    )
    print(f"Wrote {args.output}")
    print(f"Cases: {report['case_count']}")
    print(f"Aggregate agreement: {report['aggregate']['overall_agreement']:.3f}")
    print(f"Meets 95% target: {report['aggregate']['meets_95_percent_target']}")


if __name__ == "__main__":
    main()
