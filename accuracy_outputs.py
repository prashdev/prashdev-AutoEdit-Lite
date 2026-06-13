"""
accuracy_outputs.py

Builds the JSON artifacts that make AutoEdit-Lite's editorial decisions
inspectable: keep/remove decisions, B-roll suggestions, and an accuracy report.
These are deterministic support signals; the true 95% agreement number still
requires comparison against human editor labels.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path


AGREEMENT_GOAL = 0.95

FILLER_TERMS = {
    "um", "uh", "ah", "er", "hmm", "like", "basically", "literally",
    "you know", "kind of", "sort of", "i mean",
    "अं", "अम्", "उम्", "उह", "अह", "हम्म",
}

REPETITION_STOPWORDS = {
    "a", "an", "and", "are", "for", "in", "is", "of", "or", "the", "their",
    "this", "to", "we", "with", "your",
}

GENERAL_TOPIC_STOPWORDS = REPETITION_STOPWORDS | {
    "about", "again", "also", "because", "best", "channel", "everyone", "from",
    "going", "hello", "here", "into", "joining", "just", "know", "long", "more",
    "need", "over", "really", "thanks", "that", "them", "there", "these", "they",
    "thing", "things", "think", "time", "today", "very", "want", "welcome", "when",
    "where", "which", "who", "will", "works", "would",
}

CONTEXT_DEPENDENT_PREFIXES = (
    "and ",
    "because ",
    "but ",
    "he ",
    "however ",
    "it ",
    "she ",
    "so ",
    "that is why ",
    "therefore ",
    "they ",
    "this is why ",
    "which ",
    "और ",
    "इसलिए ",
    "क्योंकि ",
    "लेकिन ",
    "कारण ",
    "त्यामुळे ",
    "पण ",
    "म्हणून ",
)

ANAPHORIC_DEMONSTRATIVES = {"this", "that", "these", "those"}
ANAPHORIC_PREDICATES = {
    "allow", "allows", "are", "can", "cause", "causes", "could", "create",
    "creates", "did", "does", "explain", "explains", "give", "gives", "had",
    "has", "have", "help", "helps", "improve", "improves", "is", "make",
    "makes", "may", "mean", "means", "might", "must", "prevent", "prevents",
    "reduce", "reduces", "show", "shows", "should", "was", "were", "will",
    "would",
}

NEGATION_TERMS = {
    "not", "no", "never", "without", "cannot",
    "isnt", "arent", "wasnt", "werent", "doesnt", "dont", "didnt",
    "hasnt", "havent", "hadnt", "cant", "couldnt", "wont", "wouldnt",
    "shouldnt", "mustnt", "neednt", "shant", "aint",
    "नाही", "नको", "नहीं", "बिना",
}

SEMANTIC_CONTRAST_PAIRS = (
    ({"safe", "safer", "safest"}, {"unsafe", "dangerous", "risky"}),
    (
        {"increase", "increases", "increased", "increasing", "higher", "more"},
        {"decrease", "decreases", "decreased", "decreasing", "lower", "less"},
    ),
    ({"before", "earlier"}, {"after", "later"}),
    (
        {"effective", "successful", "positive"},
        {"ineffective", "unsuccessful", "negative"},
    ),
    (
        {"possible", "available", "allowed"},
        {"impossible", "unavailable", "forbidden"},
    ),
)

QUANTITY_TERMS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred",
    "thousand", "million", "billion", "half", "quarter", "first", "second",
    "third", "fourth", "fifth",
    "शून्य", "एक", "दोन", "दो", "तीन", "चार", "पाच", "पांच", "सहा", "छह",
    "सात", "आठ", "नऊ", "नौ", "दहा", "दस", "अकरा", "ग्यारह", "बारा",
    "बारह", "तेरा", "चौदा", "चौदह", "पंधरा", "पंद्रह", "सोळा", "सोलह",
    "सतरा", "सत्रह", "अठरा", "अठारह", "एकोणीस", "उन्नीस", "वीस", "बीस",
    "तीस", "चाळीस", "चालीस", "पन्नास", "पचास", "साठ", "सत्तर", "ऐंशी",
    "अस्सी", "नव्वद", "नब्बे", "शंभर", "सौ", "हजार", "लाख", "कोटी",
    "करोड़", "अर्धा", "अर्धी", "आधा", "आधी", "पहिला", "पहिली", "पहला",
    "पहली", "दुसरा", "दुसरी", "दूसरा", "दूसरी", "तिसरा", "तिसरी",
    "तीसरा", "तीसरी",
}

TOPIC_PROFILES = {
    "IVF and fertility care": {
        "ivf", "fertility", "embryo", "embryology", "clinic", "treatment",
        "patient", "patients", "couple", "couples", "doctor", "counselling",
        "counseling", "pregnancy", "egg", "sperm", "cycle",
        "आईवीएफ", "आयव्हीएफ", "आईव्हीएफ", "उपचार", "उपचारात",
        "प्रजनन", "फर्टिलिटी", "वंध्यत्व", "बांझपन", "देखभाल",
        "रुग्ण", "रुग्णांना", "मरीज", "समुपदेशन", "परामर्श",
        "क्लिनिक", "डॉक्टर", "भ्रूण", "लॅब",
    },
    "patient support": {
        "support", "care", "patient", "patients", "counselling", "counseling",
        "guidance", "process", "journey", "doctor",
        "साथ", "देखभाल", "रुग्ण", "रुग्णांना", "मरीज", "समुपदेशन",
        "परामर्श", "मार्गदर्शन", "प्रक्रिया", "प्रक्रियेत", "डॉक्टर",
    },
    "treatment process": {
        "process", "step", "steps", "treatment", "consultation", "test",
        "scan", "procedure", "cycle", "result",
        "प्रक्रिया", "प्रक्रियेत", "उपचार", "उपचारात", "सल्ला",
        "टेस्ट", "चाचणी", "स्कॅन", "प्रक्रिया", "सायकल", "निकाल",
    },
}

TOPIC_PROFILE_GENERIC_TERMS = {
    "IVF and fertility care": {
        "clinic", "treatment", "patient", "patients", "couple", "couples",
        "doctor", "counselling", "counseling", "pregnancy", "egg", "sperm",
        "cycle",
    },
    "patient support": {
        "support", "care", "guidance", "process", "journey",
    },
    "treatment process": {
        "process", "step", "steps", "test", "result",
    },
}

BROLL_KEYWORDS = [
    (
        {"ivf", "fertility", "embryo", "embryology", "आईवीएफ", "आयव्हीएफ", "आईव्हीएफ", "प्रजनन", "वंध्यत्व", "बांझपन"},
        [
            "fertility clinic consultation",
            "embryology lab",
            "IVF equipment",
            "doctor-patient counselling",
        ],
    ),
    (
        {
            "counselling", "counseling", "support", "patient", "patients",
            "couple", "couples", "समुपदेशन", "परामर्श", "साथ",
            "रुग्ण", "रुग्णांना", "मरीज",
        },
        [
            "doctor-patient counselling",
            "couple consultation",
            "patient support conversation",
        ],
    ),
    (
        {
            "treatment", "process", "cycle", "procedure", "scan", "test",
            "उपचार", "उपचारात", "प्रक्रिया", "प्रक्रियेत", "चाचणी",
            "टेस्ट", "स्कॅन",
        },
        [
            "fertility treatment process",
            "clinic procedure room",
            "medical scan consultation",
        ],
    ),
]


def _tokens(text: str) -> list[str]:
    tokens = []
    for raw in text.lower().split():
        token = "".join(
            ch for ch in raw
            if not unicodedata.category(ch).startswith("P")
        ).strip()
        if token:
            tokens.append(token)
    return tokens


def _filler_hit_count(text: str) -> int:
    tokens = _tokens(text)
    hits = 0
    for term in FILLER_TERMS:
        term_tokens = _tokens(term)
        width = len(term_tokens)
        if width:
            hits += sum(
                tokens[index:index + width] == term_tokens
                for index in range(len(tokens) - width + 1)
            )
    return hits


def _content_token_set(text: str) -> set[str]:
    return {
        token for token in _tokens(text)
        if len(token) > 2 and token not in REPETITION_STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _quantity_signature(tokens: set[str]) -> set[str]:
    return {
        token
        for token in tokens
        if token in QUANTITY_TERMS or any(character.isdigit() for character in token)
    }


def _has_meaning_contrast(left_text: str, right_text: str) -> bool:
    left_tokens = set(_tokens(left_text))
    right_tokens = set(_tokens(right_text))
    if bool(left_tokens & NEGATION_TERMS) != bool(right_tokens & NEGATION_TERMS):
        return True
    left_quantities = _quantity_signature(left_tokens)
    right_quantities = _quantity_signature(right_tokens)
    if (left_quantities or right_quantities) and left_quantities != right_quantities:
        return True
    for positive, negative in SEMANTIC_CONTRAST_PAIRS:
        left_positive = bool(left_tokens & positive)
        left_negative = bool(left_tokens & negative)
        right_positive = bool(right_tokens & positive)
        right_negative = bool(right_tokens & negative)
        if (
            left_positive and right_negative and not left_negative and not right_positive
            or left_negative and right_positive and not left_positive and not right_negative
        ):
            return True
    return False


def _word_confidence(segment: dict) -> float:
    words = segment.get("words") or []
    probabilities = [
        float(word["probability"])
        for word in words
        if word.get("probability") is not None
    ]
    if not probabilities:
        return 1.0
    return max(0.0, min(1.0, sum(probabilities) / len(probabilities)))


def _context_dependency(text: str) -> float:
    tokens = _tokens(text)
    normalized = " ".join(tokens)
    if any(normalized.startswith(prefix) for prefix in CONTEXT_DEPENDENT_PREFIXES):
        return 1.0
    if (
        len(tokens) >= 2
        and tokens[0] in ANAPHORIC_DEMONSTRATIVES
        and tokens[1] in ANAPHORIC_PREDICATES
    ):
        return 1.0
    return 0.0


def _word_probabilities(transcript_segments: list[dict]) -> list[float]:
    probabilities: list[float] = []
    for seg in transcript_segments:
        for word in seg.get("words") or []:
            if word.get("probability") is not None:
                probabilities.append(max(0.0, min(1.0, float(word["probability"]))))
    return probabilities


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _segment_text_for_range(transcript_segments: list[dict], start: float, end: float) -> str:
    parts = []
    for seg in transcript_segments:
        if _overlap(float(seg["start"]), float(seg["end"]), start, end) > 0:
            parts.append(_transcript_text_for_range(seg, start, end))
    return " ".join(p for p in parts if p)


def _transcript_content_for_range(
    segment: dict,
    start: float,
    end: float,
) -> tuple[float, float, str] | None:
    words = [
        word
        for word in segment.get("words") or []
        if float(word["start"]) >= start - 0.001
        and float(word["end"]) <= end + 0.001
        and word.get("word", "").strip()
    ]
    if words:
        return (
            float(words[0]["start"]),
            float(words[-1]["end"]),
            " ".join(word["word"].strip() for word in words),
        )
    if segment.get("words"):
        return None
    text = segment.get("text", "").strip()
    if not text:
        return None
    return (
        max(start, float(segment["start"])),
        min(end, float(segment["end"])),
        text,
    )


def _transcript_text_for_range(segment: dict, start: float, end: float) -> str:
    """Return only spoken words fully present inside a retained source range."""
    content = _transcript_content_for_range(segment, start, end)
    return content[2] if content else ""


def infer_main_topic(transcript_segments: list[dict]) -> dict:
    text = " ".join(seg.get("text", "") for seg in transcript_segments)
    token_set = set(_tokens(text))
    minimum_profile_support = (
        1
        if len(transcript_segments) <= 2
        else max(2, (len(transcript_segments) + 3) // 4)
    )

    best_label = "general talking-head topic"
    best_matches: set[str] = set()
    for label, keywords in TOPIC_PROFILES.items():
        matches = token_set & keywords
        anchors = matches - TOPIC_PROFILE_GENERIC_TERMS.get(label, set())
        if not anchors:
            continue
        profile_support = sum(
            1
            for segment in transcript_segments
            if set(_tokens(segment.get("text", ""))) & keywords
        )
        if profile_support < minimum_profile_support:
            continue
        if len(matches) > len(best_matches):
            best_label = label
            best_matches = matches

    if not best_matches:
        token_frequency: Counter[str] = Counter()
        document_frequency: Counter[str] = Counter()
        for segment in transcript_segments:
            content_tokens = {
                token for token in _tokens(segment.get("text", ""))
                if len(token) > 2 and token not in GENERAL_TOPIC_STOPWORDS
            }
            document_frequency.update(content_tokens)
            token_frequency.update(
                token for token in _tokens(segment.get("text", ""))
                if token in content_tokens
            )

        ranked = sorted(
            token_frequency,
            key=lambda token: (
                -document_frequency[token],
                -token_frequency[token],
                -len(token),
                token,
            ),
        )
        recurring = [token for token in ranked if document_frequency[token] >= 2]
        best_matches = set((recurring or ranked)[:8])

    return {
        "label": best_label,
        "keywords": sorted(best_matches),
    }


def _score_segment(segment: dict, main_topic: dict, index: int, seen_texts: list[dict]) -> dict:
    text = segment.get("text", "")
    lowered = text.lower()
    tokens = _tokens(text)
    token_set = set(tokens)
    topic_terms = set(main_topic.get("keywords") or [])

    filler_hits = _filler_hit_count(text)
    transcription_confidence = _word_confidence(segment)
    token_similarity = 0.0
    current_content_tokens = _content_token_set(text)
    for seen in seen_texts:
        if _has_meaning_contrast(text, seen["text"]):
            continue
        if lowered.strip() and lowered.strip() == seen["text"]:
            token_similarity = 1.0
            break
        token_similarity = max(token_similarity, _jaccard(current_content_tokens, seen["tokens"]))

    topic_relevance = min(1.0, len(token_set & topic_terms) / max(1, min(4, len(topic_terms))))
    clarity = max(0.0, min(1.0, (1.0 - filler_hits * 0.18) * transcription_confidence))
    hook_strength = 0.35
    if index == 0:
        hook_strength += 0.15
    if token_set & {"most", "why", "how", "important", "problem", "need"}:
        hook_strength += 0.35
    speaker_confidence = max(0.0, min(1.0, clarity - (0.25 if "sorry" in token_set else 0.0)))
    usefulness_terms = (
        "provide", "help", "support", "process", "treatment",
        "देते", "मिळते", "समुपदेशन", "परामर्श", "उपचार", "प्रक्रिया",
    )
    emotional_terms = (
        "support", "care", "hope", "journey", "patient",
        "साथ", "देखभाल", "रुग्ण", "रुग्णांना", "मरीज",
    )
    usefulness = min(1.0, topic_relevance + (0.25 if token_set & set(usefulness_terms) else 0.0))
    emotional_value = 0.65 if token_set & set(emotional_terms) else 0.35
    repetition = token_similarity if token_similarity >= 0.55 else 0.0
    off_topic_drift = max(0.0, 1.0 - topic_relevance)
    context_dependency = _context_dependency(text)

    return {
        "topic_relevance": round(topic_relevance, 3),
        "clarity": round(clarity, 3),
        "hook_strength": round(min(1.0, hook_strength), 3),
        "speaker_confidence": round(speaker_confidence, 3),
        "transcription_confidence": round(transcription_confidence, 3),
        "uniqueness": round(1.0 - repetition, 3),
        "usefulness": round(usefulness, 3),
        "emotional_value": round(emotional_value, 3),
        "repetition": round(repetition, 3),
        "filler": round(min(1.0, filler_hits / 3), 3),
        "off_topic_drift": round(off_topic_drift, 3),
        "context_dependency": round(context_dependency, 3),
    }


def _delivery_quality(scores: dict) -> float:
    return (
        scores["clarity"] * 0.40
        + scores["speaker_confidence"] * 0.35
        + scores["transcription_confidence"] * 0.25
        - scores["filler"] * 0.20
    )


def _prefer_cleaner_duplicate_takes(scored_segments: list[dict]) -> None:
    """Within each near-duplicate group, penalize every take except the cleanest."""
    count = len(scored_segments)
    parents = list(range(count))
    pair_similarity: dict[tuple[int, int], float] = {}
    token_sets = [_content_token_set(segment["text"]) for segment in scored_segments]

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left in range(count):
        for right in range(left + 1, count):
            if _has_meaning_contrast(
                scored_segments[left]["text"],
                scored_segments[right]["text"],
            ):
                continue
            similarity = _jaccard(token_sets[left], token_sets[right])
            if similarity >= 0.55:
                pair_similarity[(left, right)] = similarity
                union(left, right)

    groups: dict[int, list[int]] = {}
    for index in range(count):
        groups.setdefault(find(index), []).append(index)

    for members in groups.values():
        if len(members) < 2:
            continue
        preferred = max(
            members,
            key=lambda index: (_delivery_quality(scored_segments[index]["scores"]), -index),
        )
        preferred_scores = scored_segments[preferred]["scores"]
        preferred_scores["repetition"] = 0.0
        preferred_scores["uniqueness"] = 1.0

        for index in members:
            if index == preferred:
                continue
            pair = (min(index, preferred), max(index, preferred))
            similarity = pair_similarity.get(pair)
            if similarity is None:
                scored_segments[index]["scores"]["repetition"] = 0.0
                scored_segments[index]["scores"]["uniqueness"] = 1.0
                continue
            scored_segments[index]["scores"]["repetition"] = round(similarity, 3)
            scored_segments[index]["scores"]["uniqueness"] = round(1.0 - similarity, 3)


def score_transcript_segments(
    transcript_segments: list[dict],
    main_topic: dict | None = None,
) -> list[dict]:
    """Score every transcript segment before any keep/remove selection happens."""
    main_topic = main_topic or infer_main_topic(transcript_segments)
    scored = []
    seen_texts: list[dict] = []

    for index, seg in enumerate(transcript_segments):
        text = seg.get("text", "")
        scores = _score_segment(seg, main_topic, index, seen_texts)
        normalized = text.lower().strip()
        if normalized:
            seen_texts.append({
                "text": normalized,
                "tokens": _content_token_set(text),
            })

        scored.append({
            "decision_input_index": index,
            "start": round(float(seg["start"]), 3),
            "end": round(float(seg["end"]), 3),
            "text": text,
            "scores": scores,
        })

    _prefer_cleaner_duplicate_takes(scored)
    return scored


def format_editorial_scores(scored_segments: list[dict]) -> str:
    """Format deterministic pre-selection scores compactly for the editor prompt."""
    lines = []
    for scored in scored_segments:
        scores = scored["scores"]
        ordered = [
            "topic_relevance",
            "clarity",
            "hook_strength",
            "speaker_confidence",
            "transcription_confidence",
            "uniqueness",
            "usefulness",
            "emotional_value",
            "repetition",
            "filler",
            "off_topic_drift",
            "context_dependency",
        ]
        score_text = ", ".join(f"{key}={scores[key]}" for key in ordered)
        lines.append(
            f"[decision_input_index={scored['decision_input_index']} "
            f"{scored['start']:.1f}-{scored['end']:.1f}] {score_text}"
        )
    return "\n".join(lines)


def _kept_match(segment: dict, kept_segments: list[dict]) -> dict | None:
    seg_start = float(segment["start"])
    seg_end = float(segment["end"])
    seg_duration = max(0.001, seg_end - seg_start)
    for kept in kept_segments:
        kept_start = float(kept["start"])
        kept_end = float(kept["end"])
        if _overlap(seg_start, seg_end, kept_start, kept_end) / seg_duration >= 0.5:
            return kept
    return None


def _normalize_human_decisions(data: dict | list[dict]) -> list[dict]:
    if isinstance(data, list):
        return data
    if "segments_to_keep" in data:
        return [
            {"start": float(seg["start"]), "end": float(seg["end"]), "decision": "keep"}
            for seg in data.get("segments_to_keep", [])
        ]
    if "edit_decisions" in data:
        return data.get("edit_decisions") or []
    return []


def _decision_issue(
    decisions: list[dict],
    source: str,
    source_duration_seconds: float | None = None,
) -> str | None:
    normalized = []
    for index, decision in enumerate(decisions):
        try:
            start = float(decision["start"])
            end = float(decision["end"])
        except (KeyError, TypeError, ValueError):
            return f"{source} decision {index} must contain numeric start and end values."
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            return f"{source} decision {index} must have a finite positive duration."
        if (
            source_duration_seconds is not None
            and (start < 0 or end > source_duration_seconds)
        ):
            return (
                f"{source} decision {index} must stay within the declared "
                "source duration."
            )
        if "cut_start" in decision or "cut_end" in decision:
            try:
                cut_start = float(decision.get("cut_start", start))
                cut_end = float(decision.get("cut_end", end))
            except (TypeError, ValueError):
                return f"{source} decision {index} actual cut must be numeric."
            if (
                not math.isfinite(cut_start)
                or not math.isfinite(cut_end)
                or cut_end <= cut_start
                or (
                    source_duration_seconds is not None
                    and (cut_start < 0 or cut_end > source_duration_seconds)
                )
            ):
                return (
                    f"{source} decision {index} actual cut must have a finite positive "
                    "duration within the declared source duration."
                )
        value = decision.get("decision", "remove")
        if value not in {"keep", "remove"}:
            return f"{source} decision {index} has unsupported decision '{value}'."
        normalized.append((start, end, value))

    for index, (start, end, value) in enumerate(normalized):
        for other_start, other_end, other_value in normalized[index + 1:]:
            if value != other_value and _overlap(start, end, other_start, other_end) > 0:
                return f"{source} keep/remove decisions overlap with conflicting decisions."
    return None


def _merge_same_decision_ranges(decisions: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for decision in sorted(
        decisions,
        key=lambda item: (float(item["start"]), float(item["end"])),
    ):
        current = {
            "start": float(decision["start"]),
            "end": float(decision["end"]),
            "decision": decision.get("decision", "remove"),
        }
        if (
            merged
            and current["decision"] == merged[-1]["decision"]
            and current["start"] <= merged[-1]["end"]
        ):
            merged[-1]["end"] = max(merged[-1]["end"], current["end"])
        else:
            merged.append(current)
    return merged


def _story_meaning_assessment(data: dict | list[dict]) -> dict:
    value = data.get("story_meaning_preserved") if isinstance(data, dict) else None
    if isinstance(value, bool):
        return {"assessed": True, "preserved": value}
    return {"assessed": False, "preserved": None}


def _invalid_agreement(
    issue: str,
    cut_tolerance_seconds: float,
    *,
    invalid_source: str = "label",
) -> dict:
    report = {
        "label_valid": False,
        "label_issue": issue,
        "system_valid": invalid_source != "system",
        "system_edit_duration_seconds": 0.0,
        "overall_agreement": 0.0,
        "meets_95_percent_target": False,
        "story_meaning": {"assessed": False, "preserved": None},
        "keep_remove": {
            "correct": 0.0,
            "total": 0.0,
            "unit": "seconds",
            "agreement": 0.0,
            "raw_agreement": 0.0,
            "balanced_agreement": 0.0,
            "confusion_matrix": {
                "true_keep": 0.0,
                "true_remove": 0.0,
                "false_keep": 0.0,
                "false_remove": 0.0,
            },
        },
        "cut_boundaries": {
            "correct": 0,
            "total": 0,
            "tolerance_seconds": cut_tolerance_seconds,
            "agreement": 0.0,
        },
    }
    if invalid_source == "system":
        report["label_valid"] = True
        report.pop("label_issue")
        report["system_issue"] = issue
    return report


def _decision_for_segment(segment: dict, decisions: list[dict]) -> str:
    seg_start = float(segment["start"])
    seg_end = float(segment["end"])
    seg_duration = max(0.001, seg_end - seg_start)
    best_overlap = 0.0
    best_decision = "remove"

    for decision in decisions:
        overlap_ratio = _overlap(
            seg_start,
            seg_end,
            float(decision["start"]),
            float(decision["end"]),
        ) / seg_duration
        if overlap_ratio > best_overlap:
            best_overlap = overlap_ratio
            best_decision = decision.get("decision", "remove")

    return "keep" if best_overlap >= 0.5 and best_decision == "keep" else "remove"


def _decision_at_time(timestamp: float, decisions: list[dict]) -> str:
    for decision in decisions:
        if (
            decision.get("decision", "remove") == "keep"
            and float(decision["start"]) <= timestamp < float(decision["end"])
        ):
            return "keep"
    return "remove"


def _covered_at_time(timestamp: float, decisions: list[dict]) -> bool:
    return any(
        float(decision["start"]) <= timestamp < float(decision["end"])
        for decision in decisions
    )


def _timeline_confusion_seconds(
    system_decisions: list[dict],
    human_decisions: list[dict],
    source_duration_seconds: float | None = None,
) -> dict[str, float]:
    points = {
        float(value)
        for decision in [*system_decisions, *human_decisions]
        for value in (decision["start"], decision["end"])
        if float(decision["end"]) > float(decision["start"])
    }
    if source_duration_seconds is not None:
        points.update((0.0, source_duration_seconds))
    points = sorted(points)
    confusion = {
        "true_keep": 0.0,
        "true_remove": 0.0,
        "false_keep": 0.0,
        "false_remove": 0.0,
    }
    for start, end in zip(points, points[1:]):
        duration = end - start
        if duration <= 0.0:
            continue
        midpoint = start + duration / 2
        if source_duration_seconds is None and not (
            _covered_at_time(midpoint, system_decisions)
            or _covered_at_time(midpoint, human_decisions)
        ):
            continue
        system_decision = _decision_at_time(midpoint, system_decisions)
        human_decision = _decision_at_time(midpoint, human_decisions)
        if system_decision == human_decision:
            confusion["true_keep" if system_decision == "keep" else "true_remove"] += duration
        elif system_decision == "keep":
            confusion["false_keep"] += duration
        else:
            confusion["false_remove"] += duration
    return {key: round(value, 3) for key, value in confusion.items()}


def _actual_system_kept_ranges(system_decisions: list[dict]) -> list[dict]:
    """Return unique final cut ranges carried by transcript-level decisions."""
    ranges = []
    seen = set()
    for decision in system_decisions:
        if decision.get("decision", "remove") != "keep":
            continue
        start = round(float(decision.get("cut_start", decision["start"])), 3)
        end = round(float(decision.get("cut_end", decision["end"])), 3)
        key = (start, end)
        if end <= start or key in seen:
            continue
        seen.add(key)
        ranges.append({"start": start, "end": end, "decision": "keep"})
    return ranges


def _matched_boundary_count(
    system_kept: list[dict],
    human_kept: list[dict],
    boundary_name: str,
    tolerance_seconds: float,
) -> int:
    candidates = []
    for system_index, system in enumerate(system_kept):
        for human_index, human in enumerate(human_kept):
            delta = abs(float(system[boundary_name]) - float(human[boundary_name]))
            if delta <= tolerance_seconds:
                candidates.append((delta, system_index, human_index))

    matched_system: set[int] = set()
    matched_human: set[int] = set()
    for _, system_index, human_index in sorted(candidates):
        if system_index in matched_system or human_index in matched_human:
            continue
        matched_system.add(system_index)
        matched_human.add(human_index)
    return len(matched_system)


def evaluate_human_agreement(
    system_decisions: list[dict],
    human_decisions: dict | list[dict],
    cut_tolerance_seconds: float = 0.5,
    source_duration_seconds: float | None = None,
) -> dict:
    story_meaning = _story_meaning_assessment(human_decisions)
    if source_duration_seconds is not None:
        try:
            source_duration_seconds = float(source_duration_seconds)
        except (TypeError, ValueError):
            return _invalid_agreement(
                "Source duration must be a finite positive number.",
                cut_tolerance_seconds,
            )
        if not math.isfinite(source_duration_seconds) or source_duration_seconds <= 0:
            return _invalid_agreement(
                "Source duration must be a finite positive number.",
                cut_tolerance_seconds,
            )
    system_issue = _decision_issue(
        system_decisions,
        "System",
        source_duration_seconds=source_duration_seconds,
    )
    if system_issue:
        return _invalid_agreement(
            system_issue,
            cut_tolerance_seconds,
            invalid_source="system",
        )
    try:
        normalized_human = _normalize_human_decisions(human_decisions)
    except (KeyError, TypeError, ValueError) as exc:
        return _invalid_agreement(f"Invalid human labels: {exc}", cut_tolerance_seconds)
    if not normalized_human:
        return _invalid_agreement(
            "No supported human keep/remove decisions were supplied.",
            cut_tolerance_seconds,
        )
    label_issue = _decision_issue(
        normalized_human,
        "Human",
        source_duration_seconds=source_duration_seconds,
    )
    if label_issue:
        return _invalid_agreement(label_issue, cut_tolerance_seconds)
    normalized_human = _merge_same_decision_ranges(normalized_human)

    system_kept = _actual_system_kept_ranges(system_decisions)
    unique_system_kept = _merge_same_decision_ranges(system_kept)
    system_edit_duration = sum(
        float(segment["end"]) - float(segment["start"])
        for segment in unique_system_kept
    )
    human_kept = [d for d in normalized_human if d.get("decision", "remove") == "keep"]
    confusion = _timeline_confusion_seconds(
        system_decisions,
        normalized_human,
        source_duration_seconds=source_duration_seconds,
    )
    keep_remove_correct = confusion["true_keep"] + confusion["true_remove"]
    keep_remove_total = sum(confusion.values())
    boundary_correct = sum(
        _matched_boundary_count(
            system_kept,
            human_kept,
            boundary_name,
            cut_tolerance_seconds,
        )
        for boundary_name in ("start", "end")
    )
    boundary_total = 2 * max(len(system_kept), len(human_kept))

    raw_keep_remove_score = keep_remove_correct / keep_remove_total if keep_remove_total else 0.0
    keep_total = confusion["true_keep"] + confusion["false_remove"]
    remove_total = confusion["true_remove"] + confusion["false_keep"]
    class_recalls = []
    if keep_total:
        class_recalls.append(confusion["true_keep"] / keep_total)
    if remove_total:
        class_recalls.append(confusion["true_remove"] / remove_total)
    balanced_keep_remove_score = sum(class_recalls) / len(class_recalls) if class_recalls else 0.0
    boundary_score = boundary_correct / boundary_total if boundary_total else 0.0
    overall = (
        (balanced_keep_remove_score + boundary_score) / 2
        if boundary_total
        else balanced_keep_remove_score
    )

    return {
        "label_valid": True,
        "system_valid": True,
        "system_edit_duration_seconds": round(system_edit_duration, 3),
        "overall_agreement": round(overall, 3),
        "meets_95_percent_target": (
            overall >= AGREEMENT_GOAL and story_meaning["preserved"] is True
        ),
        "story_meaning": story_meaning,
        "keep_remove": {
            "correct": round(keep_remove_correct, 3),
            "total": round(keep_remove_total, 3),
            "unit": "seconds",
            "agreement": round(balanced_keep_remove_score, 3),
            "raw_agreement": round(raw_keep_remove_score, 3),
            "balanced_agreement": round(balanced_keep_remove_score, 3),
            "confusion_matrix": confusion,
        },
        "cut_boundaries": {
            "correct": boundary_correct,
            "total": boundary_total,
            "tolerance_seconds": cut_tolerance_seconds,
            "agreement": round(boundary_score, 3),
        },
    }


def build_edit_decisions(transcript_segments: list[dict], kept_segments: list[dict]) -> list[dict]:
    decisions = []
    scored_segments = score_transcript_segments(transcript_segments)

    for index, seg in enumerate(transcript_segments):
        text = seg.get("text", "")
        scores = scored_segments[index]["scores"]
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        overlapping_kept = [
            kept for kept in kept_segments
            if _overlap(seg_start, seg_end, float(kept["start"]), float(kept["end"])) > 0.001
        ]
        split_points = {seg_start, seg_end}
        for kept in overlapping_kept:
            split_points.add(max(seg_start, float(kept["start"])))
            split_points.add(min(seg_end, float(kept["end"])))
        ordered_points = sorted(split_points)

        for start, end in zip(ordered_points, ordered_points[1:]):
            if end - start <= 0.001:
                continue
            interval = {"start": start, "end": end}
            kept = _kept_match(interval, overlapping_kept)
            decision = {
                "start": round(start, 3),
                "end": round(end, 3),
                "source_segment_start": round(seg_start, 3),
                "source_segment_end": round(seg_end, 3),
                "text": text,
                "decision": "keep" if kept else "remove",
                "reason": kept.get("reason", "lower editorial score or outside 90-second story") if kept else "not selected for final 90-second story",
                "importance": int(kept.get("importance", 0)) if kept else 0,
                "scores": scores,
            }
            if kept:
                decision["cut_start"] = round(float(kept["start"]), 3)
                decision["cut_end"] = round(float(kept["end"]), 3)
                decision["cut_boundary_source"] = kept.get("cut_boundary_source", "segment_timestamps")
            decisions.append(decision)

    return decisions


def _topic_broll_fallback(text: str, main_topic: dict) -> list[str]:
    topic_terms = set(main_topic.get("keywords") or [])
    ordered_content_terms = []
    for token in _tokens(text):
        if len(token) <= 2 or token in GENERAL_TOPIC_STOPWORDS or token in ordered_content_terms:
            continue
        ordered_content_terms.append(token)

    matched_topic_terms = [token for token in ordered_content_terms if token in topic_terms]
    search_terms = (matched_topic_terms or ordered_content_terms)[:4]
    if search_terms:
        phrase = " ".join(search_terms)
        return [f"{phrase} stock footage", f"{phrase} visual explainer"]
    return ["professional talking-head support footage"]


def _has_affirmative_broll_clause(text: str) -> bool:
    trigger_terms = set().union(*(terms for terms, _ in BROLL_KEYWORDS))
    clauses = re.split(
        r"[.;!?।]+|\b(?:but|however|while)\b|,\s+and\s+(?=(?:we|i|they|he|she|you)\b)",
        text,
        flags=re.IGNORECASE,
    )
    return any(
        (clause_tokens := set(_tokens(clause))) & trigger_terms
        and not clause_tokens & NEGATION_TERMS
        for clause in clauses
    )


def _broll_keywords(text: str, main_topic: dict) -> list[str]:
    token_set = set(_tokens(text))
    if token_set & NEGATION_TERMS and not _has_affirmative_broll_clause(text):
        topic_terms = [
            token
            for token in _tokens(text)
            if token in set(main_topic.get("keywords") or [])
        ]
        content_terms = [
            token
            for token in _tokens(text)
            if len(token) > 2
            and token not in GENERAL_TOPIC_STOPWORDS
            and token not in NEGATION_TERMS
        ]
        phrase = " ".join(dict.fromkeys(topic_terms or content_terms[:3]))
        if phrase:
            return [
                f"{phrase} limitations visual explainer",
                f"{phrase} patient education",
            ]
    keywords: list[str] = []
    for trigger_terms, mapped_keywords in BROLL_KEYWORDS:
        if token_set & trigger_terms:
            keywords.extend(keyword for keyword in mapped_keywords if keyword not in keywords)
    return keywords or _topic_broll_fallback(text, main_topic)


def generate_broll_suggestions(transcript_segments: list[dict], kept_segments: list[dict]) -> list[dict]:
    suggestions = []
    edited_timeline_cursor = 0.0
    main_topic = infer_main_topic(transcript_segments)
    for kept in kept_segments:
        start = float(kept["start"])
        end = float(kept["end"])
        duration = max(0.0, end - start)
        concept_ranges = []
        for segment in transcript_segments:
            if _overlap(start, end, float(segment["start"]), float(segment["end"])) <= 0:
                continue
            concept_start = max(start, float(segment["start"]))
            concept_end = min(end, float(segment["end"]))
            content = _transcript_content_for_range(segment, concept_start, concept_end)
            if content:
                concept_ranges.append(content)
        if not concept_ranges:
            fallback_text = _segment_text_for_range(transcript_segments, start, end)
            if fallback_text:
                concept_ranges = [(start, end, fallback_text)]

        for concept_start, concept_end, text in concept_ranges:
            suggestions.append({
                "timestamp": round(concept_start, 3),
                "source_timestamp": round(concept_start, 3),
                "end": round(concept_end, 3),
                "source_end": round(concept_end, 3),
                "edited_timeline_timestamp": round(edited_timeline_cursor + concept_start - start, 3),
                "edited_timeline_end": round(edited_timeline_cursor + concept_end - start, 3),
                "spoken_text": text,
                "keywords": _broll_keywords(text, main_topic),
                "insert_mode": "suggest_only",
                "rationale": "Matched spoken content to relevant B-roll search keywords.",
            })
        edited_timeline_cursor += duration

    return suggestions


def build_accuracy_report(
    transcript_segments: list[dict],
    kept_segments: list[dict],
    original_duration: float,
    target_duration: int,
    transcription_provider: str,
    language: str | None,
    gap_threshold: float,
    human_decisions_path: str | None = None,
    edit_decisions: list[dict] | None = None,
    output_validation: dict | None = None,
) -> dict:
    selected_duration = sum(float(s["end"]) - float(s["start"]) for s in kept_segments)
    minimum_duration = target_duration * 0.85
    maximum_duration = target_duration * 1.10
    word_timestamp_segments = sum(1 for s in transcript_segments if s.get("words"))
    total_segments = len(transcript_segments)
    word_probabilities = _word_probabilities(transcript_segments)

    report = {
        "target": {
            "agreement_goal": AGREEMENT_GOAL,
            "target_duration_seconds": target_duration,
            "input_profile": "3-7 minute vertical talking-head video",
        },
        "transcription": {
            "provider": transcription_provider,
            "language": language or "auto",
            "word_timestamp_coverage": round(word_timestamp_segments / total_segments, 3) if total_segments else 0.0,
            "average_word_confidence": round(sum(word_probabilities) / len(word_probabilities), 3) if word_probabilities else None,
            "low_confidence_segments": sum(
                1 for segment in transcript_segments
                if segment.get("words") and _word_confidence(segment) < 0.55
            ),
        },
        "cutting": {
            "gap_threshold_seconds": gap_threshold,
            "word_boundary_aligned_segments": sum(1 for s in kept_segments if s.get("cut_boundary_source") == "word_timestamps"),
            "editorial_score_refined_segments": sum(1 for s in kept_segments if s.get("refinement_source") == "editorial_scores"),
            "editorial_score_filled_segments": sum(1 for s in kept_segments if s.get("refinement_source") == "editorial_score_fill"),
        },
        "story": {
            "main_topic": infer_main_topic(transcript_segments),
            "original_duration_seconds": round(float(original_duration), 3),
            "selected_duration_seconds": round(selected_duration, 3),
            "duration_error_seconds": round(abs(selected_duration - target_duration), 3),
            "minimum_duration_seconds": round(minimum_duration, 3),
            "maximum_duration_seconds": round(maximum_duration, 3),
            "within_target_range": minimum_duration <= selected_duration <= maximum_duration,
            "kept_segments": len(kept_segments),
            "removed_segments": max(0, len(transcript_segments) - len(kept_segments)),
        },
        "output_validation": output_validation or {
            "valid": None,
            "status": "not_run",
        },
        "measurement_note": (
            "This report records proxy signals and decisions. Actual 95% human-editor "
            "agreement must be measured by comparing edit_decisions.json with labelled human edits."
        ),
    }

    if human_decisions_path:
        label_path = Path(human_decisions_path)
        human_payload = json.loads(label_path.read_text(encoding="utf-8"))
        report["human_editor_agreement"] = evaluate_human_agreement(
            system_decisions=edit_decisions or build_edit_decisions(transcript_segments, kept_segments),
            human_decisions=human_payload,
        )
        report["human_editor_agreement"]["label_source"] = str(label_path)
        report["measurement_note"] = (
            "Human-editor agreement was computed from labelled decisions. The 95% target "
            "is met only when interval agreement reaches the goal and the human labels "
            "confirm that the final story preserves the speaker's meaning."
        )

    return report


def write_accuracy_outputs(
    transcript_segments: list[dict],
    kept_segments: list[dict],
    output_video_path: str,
    original_duration: float,
    target_duration: int,
    transcription_provider: str,
    language: str | None,
    gap_threshold: float,
    human_decisions_path: str | None = None,
    output_validation: dict | None = None,
) -> None:
    output_dir = Path(output_video_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    edit_decisions = build_edit_decisions(transcript_segments, kept_segments)
    broll_suggestions = generate_broll_suggestions(transcript_segments, kept_segments)
    accuracy_report = build_accuracy_report(
        transcript_segments=transcript_segments,
        kept_segments=kept_segments,
        original_duration=original_duration,
        target_duration=target_duration,
        transcription_provider=transcription_provider,
        language=language,
        gap_threshold=gap_threshold,
        human_decisions_path=human_decisions_path,
        edit_decisions=edit_decisions,
        output_validation=output_validation,
    )

    (output_dir / "edit_decisions.json").write_text(
        json.dumps(edit_decisions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "broll_suggestions.json").write_text(
        json.dumps(broll_suggestions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "accuracy_report.json").write_text(
        json.dumps(accuracy_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
