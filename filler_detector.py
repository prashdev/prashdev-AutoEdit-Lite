"""
filler_detector.py

O(n) rule-based filler detection over word-level timestamps from faster-whisper.

Detects and tags:
  - Long silences (gaps between spoken words)
  - Strong verbal fillers: um, uh, ah, er, hmm ...
  - Sentence-start soft fillers: so, okay, right ... (only after a sentence boundary)
  - False starts: near-duplicate consecutive utterances (Jaccard + bigram similarity)

apply_removals_to_segments() uses bisect for O(s log r) lookup per segment —
faster than a two-pointer O(s + r) scan when the removal list is short.
"""

import bisect

# ── Tunable constants ─────────────────────────────────────────────────────────

STRONG_FILLERS = frozenset({
    "um", "uh", "ah", "er", "hmm", "hm", "ugh", "mhm", "mm",
    "अं", "अम्", "उम्", "उह", "अह", "हम्म",
})

# Only removed when appearing at the very start of a new sentence
SENTENCE_START_FILLERS = frozenset({
    "so", "okay", "ok", "right", "well", "anyway", "basically", "alright", "now",
})
AMBIGUOUS_SENTENCE_START_FILLERS = frozenset({"right", "well", "now"})

GAP_THRESHOLD_DEFAULT = 0.5   # silences longer than this (seconds) are flagged
JACCARD_THRESHOLD     = 0.6   # word-set Jaccard for false-start detection
BIGRAM_THRESHOLD      = 0.5   # bigram Jaccard for false-start detection
OVERLAP_RATIO         = 0.60  # drop segment if >= 60% of its duration is filler

_MIN_UTT_TOKENS = 3           # minimum tokens per utterance for false-start check
_EOS_CHARS      = frozenset(".?!।")
_PUNCT_STRIP    = str.maketrans("", "", ".,!?;:-'\"।")
_CORRECTION_TOKENS = frozenset({"sorry", "restart", "rephrase"})
_NEGATION_TOKENS = frozenset({
    "not", "no", "never", "without", "cannot",
    "isnt", "arent", "wasnt", "werent", "doesnt", "dont", "didnt",
    "hasnt", "havent", "hadnt", "cant", "couldnt", "wont", "wouldnt",
    "shouldnt", "mustnt", "neednt", "shant", "aint",
    "नाही", "नको", "नहीं", "बिना",
})


_SEMANTIC_CONTRAST_PAIRS = (
    (frozenset({"safe", "safer", "safest"}), frozenset({"unsafe", "dangerous", "risky"})),
    (
        frozenset({"increase", "increases", "increased", "increasing", "higher", "more"}),
        frozenset({"decrease", "decreases", "decreased", "decreasing", "lower", "less"}),
    ),
    (frozenset({"before", "earlier"}), frozenset({"after", "later"})),
    (
        frozenset({"effective", "successful", "positive"}),
        frozenset({"ineffective", "unsuccessful", "negative"}),
    ),
    (
        frozenset({"possible", "available", "allowed"}),
        frozenset({"impossible", "unavailable", "forbidden"}),
    ),
)
_QUANTITY_TOKENS = frozenset({
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
})


def _token(word_str: str) -> str:
    """Lowercase, punctuation-stripped token for set/dict operations."""
    return word_str.lower().translate(_PUNCT_STRIP).strip()


def _is_eos(word_str: str) -> bool:
    """True if this word token ends a sentence (faster-whisper attaches punctuation)."""
    return bool(word_str) and word_str[-1:] in _EOS_CHARS


def _is_sentence_start_filler(word_str: str, token: str) -> bool:
    if token not in SENTENCE_START_FILLERS:
        return False
    if token in AMBIGUOUS_SENTENCE_START_FILLERS:
        return word_str.rstrip().endswith(",")
    return True


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _has_meaning_contrast(left_tokens: list[str], right_tokens: list[str]) -> bool:
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if bool(left_set & _NEGATION_TOKENS) != bool(right_set & _NEGATION_TOKENS):
        return True
    left_quantities = {
        token
        for token in left_set
        if token in _QUANTITY_TOKENS or any(character.isdigit() for character in token)
    }
    right_quantities = {
        token
        for token in right_set
        if token in _QUANTITY_TOKENS or any(character.isdigit() for character in token)
    }
    if (left_quantities or right_quantities) and left_quantities != right_quantities:
        return True
    for positive, negative in _SEMANTIC_CONTRAST_PAIRS:
        left_positive = bool(left_set & positive)
        left_negative = bool(left_set & negative)
        right_positive = bool(right_set & positive)
        right_negative = bool(right_set & negative)
        if (
            left_positive and right_negative and not left_negative and not right_positive
            or left_negative and right_positive and not left_positive and not right_negative
        ):
            return True
    return False


def _delivery_penalty(words: list[dict], tokens: list[str]) -> float:
    filler_penalty = sum(
        1.0 for token in tokens if token in STRONG_FILLERS or token in SENTENCE_START_FILLERS
    )
    correction_penalty = sum(1.5 for token in tokens if token in _CORRECTION_TOKENS)
    probabilities = [
        float(word["probability"])
        for word in words
        if word.get("probability") is not None
    ]
    confidence_penalty = (
        (1.0 - sum(probabilities) / len(probabilities)) * 2.0
        if probabilities
        else 0.0
    )
    return filler_penalty + correction_penalty + confidence_penalty


# ── Core detection ────────────────────────────────────────────────────────────

def detect_fillers(
    word_segments: list[dict],
    gap_threshold: float = GAP_THRESHOLD_DEFAULT,
) -> list[dict]:
    """
    Single O(n) forward pass that detects filler ranges in word-timestamped segments.

    Parameters
    ----------
    word_segments : list[dict]
        Transcript segments each optionally containing a "words" key with per-word
        dicts: {"word": str, "start": float, "end": float, "probability": float}.
    gap_threshold : float
        Silences longer than this (seconds) are tagged "gap".

    Returns
    -------
    list[dict]
        Removal ranges: [{"start": float, "end": float, "reason": str}, ...].
        Not guaranteed to be sorted — call merge_overlaps(sorted(...)) before use.
    """
    all_words: list[dict] = []
    for seg in word_segments:
        all_words.extend(seg.get("words") or [])

    if not all_words:
        return []

    removals: list[dict] = []

    # Forward-pass state
    prev_end = 0.0
    prev_eos = True  # treat the very start of the recording as a sentence boundary

    # Utterance accumulation (sentence-grouped) for false-start detection
    utterances: list[tuple[float, float, list[str], list[dict]]] = []
    utt_tokens: list[str] = []
    utt_words: list[dict] = []
    utt_start = float(all_words[0]["start"])
    utt_end   = utt_start

    for i, w in enumerate(all_words):
        tok     = _token(w["word"])
        w_start = float(w["start"])
        w_end   = float(w["end"])

        # 1. Gap detection (checked first so emission order is monotone)
        if i > 0 and (w_start - prev_end) > gap_threshold:
            removals.append({
                "start":  round(prev_end, 3),
                "end":    round(w_start,  3),
                "reason": "gap",
            })

        # 2. Strong filler (always flagged regardless of position)
        if tok in STRONG_FILLERS:
            removals.append({
                "start":  round(w_start, 3),
                "end":    round(w_end,   3),
                "reason": "filler:strong",
            })

        # 3. Sentence-start soft filler (only flagged after an EOS word)
        elif prev_eos and _is_sentence_start_filler(w["word"], tok):
            removals.append({
                "start":  round(w_start, 3),
                "end":    round(w_end,   3),
                "reason": "filler:sentence_start",
            })

        # 4. Accumulate tokens for utterance grouping (all words, including fillers)
        if tok:
            utt_tokens.append(tok)
            utt_words.append(w)
            utt_end = w_end

        # 5. Close utterance on EOS punctuation
        if _is_eos(w["word"]) and utt_tokens:
            utterances.append((utt_start, utt_end, utt_tokens, utt_words))
            utt_tokens = []
            utt_words = []
            nxt_start  = float(all_words[i + 1]["start"]) if i + 1 < len(all_words) else w_end
            utt_start  = nxt_start
            utt_end    = nxt_start

        prev_end = w_end
        prev_eos = _is_eos(w["word"])

    # Flush trailing utterance (no terminal EOS punctuation)
    if utt_tokens:
        utterances.append((utt_start, utt_end, utt_tokens, utt_words))

    # 6. False-start detection: O(u) pass over consecutive utterance pairs
    for i in range(len(utterances) - 1):
        u1_start, u1_end, u1_toks, u1_words = utterances[i]
        u2_start, u2_end, u2_toks, u2_words = utterances[i + 1]

        if len(u1_toks) < _MIN_UTT_TOKENS or len(u2_toks) < _MIN_UTT_TOKENS:
            continue

        u1_set = set(u1_toks)
        u2_set = set(u2_toks)

        if _has_meaning_contrast(u1_toks, u2_toks):
            continue

        if (
            _jaccard(u1_set, u2_set) >= JACCARD_THRESHOLD
            or _jaccard(_bigrams(u1_toks), _bigrams(u2_toks)) >= BIGRAM_THRESHOLD
        ):
            remove_start, remove_end = u1_start, u1_end
            if _delivery_penalty(u2_words, u2_toks) > _delivery_penalty(u1_words, u1_toks):
                remove_start, remove_end = u2_start, u2_end
            removals.append({
                "start":  round(remove_start, 3),
                "end":    round(remove_end,   3),
                "reason": "false_start",
            })

    return removals


# ── Merge overlapping removal ranges ─────────────────────────────────────────

def merge_overlaps(removals: list[dict]) -> list[dict]:
    """
    O(m) merge of sorted removal ranges into non-overlapping spans.

    Precondition: removals is sorted by "start".
    """
    if not removals:
        return []
    merged = [dict(removals[0])]
    for r in removals[1:]:
        cur = merged[-1]
        if r["start"] <= cur["end"]:
            cur["end"] = max(cur["end"], r["end"])
        else:
            merged.append(dict(r))
    return merged


# ── Apply removals to transcript segments ─────────────────────────────────────

def apply_removals_to_segments(
    transcript_segments: list[dict],
    removals: list[dict],
) -> list[dict]:
    """
    O(s log r) segment filter using bisect on removal end-times.

    For each transcript segment, binary-searches the removal list to find
    the first range whose end > seg.start, then linearly scans forward to
    accumulate total overlap. Drops any segment where filler overlap covers
    >= OVERLAP_RATIO of its duration.

    Parameters
    ----------
    transcript_segments : list[dict]
        Segments with at minimum "start", "end", "text" keys.
        "words" key is stripped from output (not needed downstream).
    removals : list[dict]
        Sorted, non-overlapping removal ranges from merge_overlaps().

    Returns
    -------
    list[dict]
        Filtered segments with {"start", "end", "text"} keys.
    """
    if not removals:
        return [
            {k: v for k, v in seg.items() if k != "words"}
            for seg in transcript_segments
            if float(seg["end"]) - float(seg["start"]) > 0
        ]

    # Build sorted end-time index once — O(r)
    removal_ends = [r["end"] for r in removals]

    kept: list[dict] = []
    for seg in transcript_segments:
        seg_start = float(seg["start"])
        seg_end   = float(seg["end"])
        duration  = seg_end - seg_start
        if duration <= 0:
            continue

        # Jump past removals that end before this segment starts — O(log r)
        idx = bisect.bisect_right(removal_ends, seg_start)

        overlap = 0.0
        j = idx
        while j < len(removals) and removals[j]["start"] < seg_end:
            r = removals[j]
            o = min(r["end"], seg_end) - max(r["start"], seg_start)
            if o > 0:
                overlap += o
            j += 1

        if overlap / duration >= OVERLAP_RATIO:
            continue

        words = seg.get("words") or []
        if words:
            clean_words: list[list[dict]] = []
            current_run: list[dict] = []
            previous_word_end: float | None = None
            for word in words:
                w_start = float(word["start"])
                w_end = float(word["end"])
                removal_between_words = (
                    previous_word_end is not None
                    and any(
                        r["start"] >= previous_word_end and r["end"] <= w_start
                        for r in removals[idx:j]
                    )
                )
                if removal_between_words and current_run:
                    clean_words.append(current_run)
                    current_run = []

                overlaps_removal = any(
                    min(r["end"], w_end) - max(r["start"], w_start) > 0
                    for r in removals[idx:j]
                )
                if overlaps_removal:
                    if current_run:
                        clean_words.append(current_run)
                        current_run = []
                else:
                    current_run.append(word)
                previous_word_end = w_end
            if current_run:
                clean_words.append(current_run)

            for run in clean_words:
                start = round(float(run[0]["start"]), 3)
                end = round(float(run[-1]["end"]), 3)
                if end <= start:
                    continue
                clean_seg = {k: v for k, v in seg.items() if k not in {"words", "text", "start", "end"}}
                clean_seg.update({
                    "start": start,
                    "end": end,
                    "text": " ".join(w["word"].strip() for w in run if w.get("word", "").strip()),
                })
                kept.append(clean_seg)
        else:
            kept.append({k: v for k, v in seg.items() if k != "words"})

    return kept
