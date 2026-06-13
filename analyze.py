"""
analyze.py

Sends the transcript to Claude and gets back a structured list of segments
to keep. Handles retries, validation, chunking for long videos, and logging.
"""

import json
import math
import os
import sys
import time
from pathlib import Path

# ── Model configuration ────────────────────────────────────────────────────
MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096

# Approximate token budget for the transcript portion of the prompt.
# claude-opus-4-7 has a 200k context window but we keep chunks modest
# to ensure response quality stays high.
MAX_TRANSCRIPT_TOKENS = 15_000
CHARS_PER_TOKEN = 4            # rough approximation
CHUNK_DURATION_SECONDS = 600   # 10-minute windows when chunking
MAX_SEGMENT_DURATION = 120.0   # seconds
MIN_SEGMENT_DURATION = 0.5     # seconds


def _load_prompt_template(prompts_dir: str = "prompts") -> str:
    template_path = Path(prompts_dir) / "editor_prompt.txt"
    if not template_path.exists():
        print(f"\n[ERROR] Prompt file not found: {template_path}")
        print("  Make sure the 'prompts/editor_prompt.txt' file exists.\n")
        sys.exit(1)
    return template_path.read_text(encoding="utf-8")


def _format_transcript(segments: list[dict]) -> str:
    """Convert segment list into a readable transcript string for Claude."""
    lines = []
    for seg in segments:
        start = _fmt_time(seg["start"])
        end = _fmt_time(seg["end"])
        lines.append(f"[{start} - {end}] {seg['text']}")
    return "\n".join(lines)


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.s (e.g. 02:34.7)."""
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:04.1f}"


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _build_editor_prompt(
    segments: list[dict],
    quality_mode: str,
    prompt_template: str,
    target_duration: int = 90,
    aspect_ratio: str = "16:9",
    platform: str = "general",
) -> tuple[str, str]:
    transcript_str = _format_transcript(segments)

    from accuracy_outputs import format_editorial_scores, score_transcript_segments
    editorial_scores = format_editorial_scores(score_transcript_segments(segments))

    platform_label = _PLATFORM_LABELS.get(platform, "General")
    platform_context = _PLATFORM_CONTEXT.get(platform, _PLATFORM_CONTEXT["general"])
    min_duration = max(10, round(target_duration * 0.85))
    max_duration = round(target_duration * 1.1)

    prompt = prompt_template.replace("{quality_mode}", quality_mode.upper() + " MODE")
    prompt = prompt.replace("{transcript}", transcript_str)
    prompt = prompt.replace("{editorial_scores}", editorial_scores)
    prompt = prompt.replace("{target_duration}", str(target_duration))
    prompt = prompt.replace("{min_duration}", str(min_duration))
    prompt = prompt.replace("{max_duration}", str(max_duration))
    prompt = prompt.replace("{aspect_ratio}", aspect_ratio)
    prompt = prompt.replace("{platform_label}", platform_label)
    prompt = prompt.replace("{platform_context}", platform_context)
    return prompt, transcript_str


def _call_claude(
    client,
    prompt: str,
    extra_prefix: str = "",
) -> str:
    """Send a single request to Claude and return the raw text response."""
    full_prompt = extra_prefix + prompt if extra_prefix else prompt
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return message.content[0].text


def _call_claude_with_cache(
    client,
    full_prompt: str,
    transcript_str: str,
    extra_prefix: str = "",
) -> str:
    """
    Send prompt with cache_control on the static instruction portion.

    The static instruction template (everything before the transcript) is marked
    ephemeral so Anthropic caches it across calls in the same session. Subsequent
    chunks of the same video are billed at ~10% for the template portion.

    Falls back to _call_claude() if the transcript can't be located in the prompt.
    """
    try:
        split_idx = full_prompt.index(transcript_str)
        static_part = (extra_prefix + full_prompt[:split_idx]).strip()
        dynamic_part = full_prompt[split_idx:]
    except ValueError:
        return _call_claude(client, full_prompt, extra_prefix)

    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_part},
        ]}],
    )
    return message.content[0].text


def _parse_and_validate_json(
    raw: str,
    video_duration: float,
    chunk_start_offset: float = 0.0,
) -> list[dict]:
    """
    Parse Claude's JSON response and validate every segment.

    Returns only segments that pass all validation rules.
    Applies chunk_start_offset to convert chunk-relative timestamps to
    absolute timestamps when processing long-video chunks.
    """
    # Strip any accidental markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    data = json.loads(cleaned)   # raises json.JSONDecodeError on bad JSON

    raw_segments = data.get("segments_to_keep", [])
    validated: list[dict] = []
    prev_end = -1.0

    for seg in raw_segments:
        start = float(seg["start"]) + chunk_start_offset
        end = float(seg["end"]) + chunk_start_offset
        reason = seg.get("reason", "")

        # Rule: finite, non-negative source timestamps
        if not math.isfinite(start) or not math.isfinite(end) or start < 0.0:
            continue

        # Rule: start < end
        if start >= end:
            continue

        # Rule: minimum duration
        if (end - start) < MIN_SEGMENT_DURATION:
            continue

        # Rule: maximum duration
        if (end - start) > MAX_SEGMENT_DURATION:
            end = start + MAX_SEGMENT_DURATION

        # Rule: within video duration
        if start >= video_duration:
            continue
        end = min(end, video_duration)

        # Rule: chronological, no overlap
        if start < prev_end:
            start = prev_end
        if start >= end:
            continue
        if (end - start) < MIN_SEGMENT_DURATION:
            continue

        importance = int(seg.get("importance", 3))
        importance = max(1, min(5, importance))   # clamp to [1, 5]
        validated.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "reason": reason,
            "importance": importance,
        })
        prev_end = end

    return validated


def _snap_to_word_boundaries(
    kept_segments: list[dict],
    transcript_segments: list[dict],
) -> list[dict]:
    """Adjust selected cuts to the nearest enclosing word timestamps."""
    words: list[dict] = []
    for seg in transcript_segments:
        words.extend(seg.get("words") or [])
    if not words:
        return [dict(seg, cut_boundary_source=seg.get("cut_boundary_source", "segment_timestamps")) for seg in kept_segments]

    snapped: list[dict] = []
    prev_end = 0.0
    for seg in kept_segments:
        start = float(seg["start"])
        end = float(seg["end"])
        overlapping = [
            word for word in words
            if float(word["end"]) > start and float(word["start"]) < end
        ]
        adjusted = dict(seg)
        if overlapping:
            adjusted["start"] = round(max(prev_end, float(overlapping[0]["start"])), 3)
            adjusted["end"] = round(float(overlapping[-1]["end"]), 3)
            adjusted["cut_boundary_source"] = "word_timestamps"
        else:
            continue
        if adjusted["end"] > adjusted["start"]:
            snapped.append(adjusted)
            prev_end = adjusted["end"]

    return snapped


def _merge_contiguous_segments(segments: list[dict], tolerance: float = 0.001) -> list[dict]:
    """Merge selected ranges only when no meaningful source-time gap remains."""
    merged: list[dict] = []
    for segment in sorted(segments, key=lambda item: float(item["start"])):
        current = dict(segment)
        if not merged or float(current["start"]) - float(merged[-1]["end"]) > tolerance:
            merged.append(current)
            continue

        previous = merged[-1]
        previous["end"] = round(max(float(previous["end"]), float(current["end"])), 3)
        previous["importance"] = max(
            int(previous.get("importance", 3)),
            int(current.get("importance", 3)),
        )
        reasons = [
            reason
            for reason in (previous.get("reason", ""), current.get("reason", ""))
            if reason
        ]
        previous["reason"] = "; ".join(dict.fromkeys(reasons))
    return merged


def _enforce_duration_budget(
    segments: list[dict],
    target_duration: int = 90,
    transcript_segments: list[dict] | None = None,
) -> list[dict]:
    min_duration = target_duration * 0.85
    max_duration = round(target_duration * 1.1)
    total = sum(s["end"] - s["start"] for s in segments)
    if total <= max_duration or not segments:
        return segments

    trimmed = list(segments)
    while trimmed and total > max_duration:
        removal_order = sorted(
            trimmed,
            key=lambda s: (s.get("importance", 3), -(s["end"] - s["start"])),
        )
        minimum_preserving = [
            segment
            for segment in removal_order
            if total - (segment["end"] - segment["start"]) >= min_duration
        ]
        if transcript_segments:
            current_orphans = _orphaned_context_indexes(trimmed, transcript_segments)
            safe_removals = [
                segment
                for segment in removal_order
                if not (
                    _orphaned_context_indexes(
                        [kept for kept in trimmed if kept is not segment],
                        transcript_segments,
                    )
                    - current_orphans
                )
            ]
            viable = [
                segment for segment in minimum_preserving
                if segment in safe_removals
            ]
        else:
            viable = minimum_preserving
        if not viable:
            break
        removed = viable[0]
        trimmed.remove(removed)
        total -= (removed["end"] - removed["start"])
    trimmed.sort(key=lambda s: s["start"])
    return trimmed


def _overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _passes_editorial_score_gate(scores: dict, quality_mode: str) -> bool:
    """Return False only for clear deterministic keep/remove mistakes."""
    mode = quality_mode.lower()
    repetition_limit = 0.85 if mode == "light" else 0.55
    off_topic_limit = 0.95 if mode == "aggressive" else 0.90

    if scores.get("repetition", 0.0) >= repetition_limit:
        return False
    if scores.get("transcription_confidence", 1.0) < 0.55:
        return False

    clearly_off_topic = (
        scores.get("off_topic_drift", 0.0) >= off_topic_limit
        and scores.get("topic_relevance", 0.0) <= 0.10
        and scores.get("usefulness", 0.0) <= 0.25
        and scores.get("hook_strength", 0.0) <= 0.50
    )
    if clearly_off_topic and mode in {"balanced", "aggressive"}:
        return False

    return True


def _substantive_antecedent_index(
    transcript_index: int,
    scored_segments: list[dict],
    quality_mode: str = "balanced",
) -> int | None:
    """Find the nearest prior transcript row that is viable story context."""
    for prior_index in range(transcript_index - 1, -1, -1):
        if _passes_editorial_score_gate(
            scored_segments[prior_index]["scores"],
            quality_mode,
        ):
            return prior_index
    return None


def _append_refined_run(refined: list[dict], run: dict | None, source: dict) -> None:
    if not run:
        return
    if run["end"] - run["start"] < MIN_SEGMENT_DURATION:
        return
    refined.append({
        "start": round(run["start"], 3),
        "end": round(run["end"], 3),
        "reason": source.get("reason", ""),
        "importance": int(source.get("importance", 3)),
        "refinement_source": "editorial_scores",
    })


def _refine_selected_segments_by_editorial_scores(
    kept_segments: list[dict],
    transcript_segments: list[dict],
    quality_mode: str = "balanced",
) -> list[dict]:
    """
    Remove clearly weak transcript slices from Claude-selected ranges.

    Claude remains the primary editor. This deterministic gate catches two
    high-impact failure modes that are visible from transcript-only signals:
    repeated takes and selected off-topic drift around otherwise useful content.
    """
    if not kept_segments or not transcript_segments:
        return kept_segments

    from accuracy_outputs import score_transcript_segments

    scored_segments = score_transcript_segments(transcript_segments)
    refined: list[dict] = []
    accepted_transcript_indexes: set[int] = set()

    for selected in kept_segments:
        selected_start = float(selected["start"])
        selected_end = float(selected["end"])
        matched_any = False
        current_run: dict | None = None

        for transcript_index, (transcript, scored) in enumerate(zip(transcript_segments, scored_segments)):
            seg_start = float(transcript["start"])
            seg_end = float(transcript["end"])
            overlap = _overlap_seconds(selected_start, selected_end, seg_start, seg_end)
            if overlap <= 0:
                continue

            matched_any = True
            clip_start = max(selected_start, seg_start)
            clip_end = min(selected_end, seg_end)
            scores = scored["scores"]
            antecedent_index = _substantive_antecedent_index(
                transcript_index,
                scored_segments,
                quality_mode,
            )
            has_required_context = (
                scores.get("context_dependency", 0.0) < 0.75
                or antecedent_index in accepted_transcript_indexes
            )
            if not _passes_editorial_score_gate(scores, quality_mode) or not has_required_context:
                _append_refined_run(refined, current_run, selected)
                current_run = None
                continue

            accepted_transcript_indexes.add(transcript_index)
            if current_run and clip_start <= current_run["end"] + 0.001:
                current_run["end"] = max(current_run["end"], clip_end)
            else:
                _append_refined_run(refined, current_run, selected)
                current_run = {"start": clip_start, "end": clip_end}

        _append_refined_run(refined, current_run, selected)
        if not matched_any:
            refined.append(dict(selected))

    return refined


def _duration(segments: list[dict]) -> float:
    return sum(float(seg["end"]) - float(seg["start"]) for seg in segments)


def _overlaps_any(candidate: dict, segments: list[dict]) -> bool:
    start = float(candidate["start"])
    end = float(candidate["end"])
    return any(
        _overlap_seconds(start, end, float(seg["start"]), float(seg["end"])) > 0.001
        for seg in segments
    )


def _orphaned_context_indexes(
    selected_segments: list[dict],
    transcript_segments: list[dict],
) -> set[int]:
    """Return selected context-dependent transcript rows without their antecedent."""
    from accuracy_outputs import score_transcript_segments

    scored = score_transcript_segments(transcript_segments)
    orphans: set[int] = set()
    for index, (transcript, scored_segment) in enumerate(zip(transcript_segments, scored)):
        if not _overlaps_any(transcript, selected_segments):
            continue
        if scored_segment["scores"].get("context_dependency", 0.0) < 0.75:
            continue
        antecedent_index = _substantive_antecedent_index(index, scored)
        if (
            antecedent_index is None
            or not _overlaps_any(transcript_segments[antecedent_index], selected_segments)
        ):
            orphans.add(index)
    return orphans


def _editorial_candidate_score(scores: dict) -> float:
    positive = (
        scores.get("topic_relevance", 0.0) * 0.30
        + scores.get("usefulness", 0.0) * 0.22
        + scores.get("clarity", 0.0) * 0.14
        + scores.get("speaker_confidence", 0.0) * 0.12
        + scores.get("uniqueness", 0.0) * 0.12
        + scores.get("emotional_value", 0.0) * 0.10
    )
    penalties = (
        scores.get("repetition", 0.0) * 0.30
        + scores.get("filler", 0.0) * 0.20
        + scores.get("off_topic_drift", 0.0) * 0.25
    )
    return max(0.0, positive - penalties)


def _fill_duration_with_high_scoring_segments(
    kept_segments: list[dict],
    transcript_segments: list[dict],
    quality_mode: str = "balanced",
    target_duration: int = 90,
) -> list[dict]:
    """Fill an under-length edit with strong missing transcript segments."""
    if not transcript_segments:
        return kept_segments

    min_duration = target_duration * 0.85
    max_duration = target_duration * 1.10
    current_duration = _duration(kept_segments)
    if current_duration >= target_duration:
        return kept_segments

    from accuracy_outputs import infer_main_topic, score_transcript_segments

    candidates: list[dict] = []
    selected_topic_segments = [
        transcript
        for transcript in transcript_segments
        if _overlaps_any(transcript, kept_segments)
    ]
    main_topic = infer_main_topic(selected_topic_segments or transcript_segments)
    scored_transcript = score_transcript_segments(transcript_segments, main_topic=main_topic)
    for transcript_index, (transcript, scored) in enumerate(zip(transcript_segments, scored_transcript)):
        if _overlaps_any(transcript, kept_segments):
            continue
        scores = scored["scores"]
        if not _passes_editorial_score_gate(scores, quality_mode):
            continue
        candidate_score = _editorial_candidate_score(scores)
        if candidate_score < 0.45:
            continue
        duration = float(transcript["end"]) - float(transcript["start"])
        if duration < MIN_SEGMENT_DURATION:
            continue
        candidates.append({
            "start": round(float(transcript["start"]), 3),
            "end": round(float(transcript["end"]), 3),
            "score": candidate_score,
            "transcript_index": transcript_index,
            "context_dependent": scores.get("context_dependency", 0.0) >= 0.75,
            "antecedent_index": _substantive_antecedent_index(
                transcript_index,
                scored_transcript,
                quality_mode,
            ),
        })

    filled = [dict(seg) for seg in kept_segments]
    pending = sorted(candidates, key=lambda item: (-item["score"], item["start"]))
    while pending and current_duration < target_duration:
        deferred: list[dict] = []
        added_any = False
        for candidate in pending:
            transcript_index = candidate["transcript_index"]
            if candidate["context_dependent"] and (
                candidate["antecedent_index"] is None
                or not _overlaps_any(
                    transcript_segments[candidate["antecedent_index"]],
                    filled,
                )
            ):
                deferred.append(candidate)
                continue

            candidate_duration = candidate["end"] - candidate["start"]
            next_duration = current_duration + candidate_duration
            if next_duration > max_duration:
                continue
            if abs(target_duration - next_duration) >= abs(target_duration - current_duration):
                continue
            filled.append({
                "start": candidate["start"],
                "end": candidate["end"],
                "reason": "editorial score fill: relevant missing context",
                "importance": 4 if candidate["score"] >= 0.60 else 3,
                "refinement_source": "editorial_score_fill",
            })
            current_duration = next_duration
            added_any = True
            if current_duration >= target_duration:
                break
        if not added_any:
            break
        pending = deferred

    filled.sort(key=lambda seg: seg["start"])
    return filled


_PLATFORM_CONTEXT = {
    "reels": (
        "Instagram Reels: The first 0–3 seconds are the entire game — open mid-thought or with "
        "the most surprising statement in the whole video. Never open with a greeting. "
        "Pacing must feel snappy; every cut should land on a natural speech beat. "
        "Subtitles are essential (most viewers watch without sound). "
        "End on an emotion, a revelation, or a clear actionable takeaway. Avoid slow build-ups."
    ),
    "tiktok": (
        "TikTok: The first 2 seconds must give the viewer a concrete reason to stay — a bold "
        "claim, a surprising fact, or a question they can't ignore. Re-engage every 10–15 "
        "seconds with a new hook, question, or surprising reveal; viewers who reach the 8-second "
        "mark almost always finish. High energy, direct address. End with a satisfying conclusion "
        "or a cliffhanger that invites re-watches."
    ),
    "shorts": (
        "YouTube Shorts: Viewers skew educational and value clarity over speed. Open with the "
        "core question or problem in the first 3 seconds. Deliver the answer step by step — "
        "every 20 seconds should introduce a new idea or sub-point, not just elaboration of the "
        "previous one. Close with a memorable one-sentence summary. Pacing can be slightly "
        "slower than Reels/TikTok but must still feel faster than long-form YouTube."
    ),
    "general": (
        "General / Premiere edit: Focus on storytelling clarity and pacing. No platform-specific "
        "constraints — prioritise coherence and engagement over speed."
    ),
}

_PLATFORM_LABELS = {
    "reels": "Instagram Reels",
    "tiktok": "TikTok",
    "shorts": "YouTube Shorts",
    "general": "General",
}


def _analyze_chunk(
    client,
    segments: list[dict],
    quality_mode: str,
    video_duration: float,
    prompt_template: str,
    chunk_start_offset: float,
    logs_dir: Path,
    chunk_index: int,
    target_duration: int = 90,
    aspect_ratio: str = "16:9",
    platform: str = "general",
    gap_threshold: float = 0.5,
) -> list[dict]:
    """Run one Claude request for a single transcript chunk. Retries up to 3 times."""
    # Rule-based filler pre-filter: strip obvious fillers before sending to Claude.
    # Only runs when faster-whisper word timestamps are present; skips silently otherwise.
    has_word_data = any("words" in seg and seg["words"] for seg in segments)
    if has_word_data:
        try:
            from filler_detector import detect_fillers, merge_overlaps, apply_removals_to_segments
            raw_removals = detect_fillers(segments, gap_threshold=gap_threshold)
            merged_removals = merge_overlaps(sorted(raw_removals, key=lambda r: r["start"]))
            filtered = apply_removals_to_segments(segments, merged_removals)
            removed = len(segments) - len(filtered)
            if removed:
                print(
                    f"  Rule-based pre-filter: removed {removed} filler segment(s) "
                    f"({len(merged_removals)} filler range(s) detected)"
                )
            segments = filtered
        except Exception as e:
            print(f"  [WARNING] Filler pre-filter failed: {e} - sending full transcript to Claude")

    prompt, transcript_str = _build_editor_prompt(
        segments=segments,
        quality_mode=quality_mode,
        prompt_template=prompt_template,
        target_duration=target_duration,
        aspect_ratio=aspect_ratio,
        platform=platform,
    )

    raw_response = ""
    extra_prefix = ""

    for attempt in range(1, 4):
        try:
            raw_response = _call_claude_with_cache(client, prompt, transcript_str, extra_prefix=extra_prefix)

            # Save raw response for debugging (overwritten each attempt)
            raw_log = logs_dir / f"claude_raw_chunk{chunk_index}.txt"
            raw_log.write_text(raw_response, encoding="utf-8")

            validated = _parse_and_validate_json(raw_response, video_duration, chunk_start_offset)

            # Enforce duration budget — remove lowest-importance segments first
            n_before = len(validated)
            absolute_transcript = [
                {
                    **segment,
                    "start": float(segment["start"]) + chunk_start_offset,
                    "end": float(segment["end"]) + chunk_start_offset,
                }
                for segment in segments
            ]
            validated = _enforce_duration_budget(
                validated,
                target_duration=target_duration,
                transcript_segments=absolute_transcript,
            )
            max_duration = round(target_duration * 1.1)
            total = sum(s["end"] - s["start"] for s in validated)
            if len(validated) < n_before:
                print(
                    f"  [Duration enforcement] Trimmed to {total:.1f}s "
                    f"(removed {n_before - len(validated)} low-importance segment(s), "
                    f"target: {target_duration}s, max: {max_duration}s)"
                )

            # Save clean JSON
            clean_log = logs_dir / f"claude_clean_chunk{chunk_index}.json"
            with open(clean_log, "w", encoding="utf-8") as f:
                json.dump(validated, f, indent=2)

            return validated

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"  [Attempt {attempt}/3] Claude returned invalid JSON: {exc}")
            if attempt < 3:
                extra_prefix = "Your previous response was invalid JSON. Return ONLY valid JSON. "
                time.sleep(1)
            else:
                print("  [WARNING] All 3 attempts failed. No segments kept for this chunk.")
                fail_log = logs_dir / f"claude_raw_chunk{chunk_index}_failed.txt"
                fail_log.write_text(raw_response, encoding="utf-8")
                return []


def analyze_transcript(
    segments: list[dict],
    quality_mode: str,
    video_duration: float,
    target_duration: int = 90,
    aspect_ratio: str = "16:9",
    platform: str = "general",
    logs_dir: str = "logs",
    prompts_dir: str = "prompts",
    gap_threshold: float = 0.5,
) -> list[dict]:
    """
    Send the transcript to Claude and return a validated list of segments to keep.

    Parameters
    ----------
    segments : list[dict]
        Output from transcribe_video(): list of {"start", "end", "text"} dicts.
    quality_mode : str
        "light" | "balanced" | "aggressive"
    video_duration : float
        Total duration of the input video in seconds.
    target_duration : int
        Target length of the final cut in seconds (default: 90).
    aspect_ratio : str
        Output aspect ratio, e.g. "9:16" or "16:9" (default: "16:9").
    platform : str
        Target platform: "reels", "tiktok", "shorts", or "general" (default: "general").
    logs_dir : str
        Directory for saving debug logs.
    prompts_dir : str
        Directory containing editor_prompt.txt.

    Returns
    -------
    list[dict]
        Validated, chronological list of {"start", "end", "reason"} dicts.
    """
    from anthropic import Anthropic
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_key_here":
        print("\n[ERROR] ANTHROPIC_API_KEY is not set.")
        print("  1. Copy .env.example to .env")
        print("  2. Replace 'your_key_here' with your real key from https://console.anthropic.com/")
        print("  3. Save the file and run again.\n")
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    prompt_template = _load_prompt_template(prompts_dir)

    # ── Decide whether to chunk ────────────────────────────────────────────
    full_transcript = _format_transcript(segments)
    estimated_tokens = _estimate_tokens(full_transcript)

    if estimated_tokens > MAX_TRANSCRIPT_TOKENS:
        print(f"  Transcript is large (~{estimated_tokens:,} tokens). Chunking into 10-minute windows.")
        if video_duration > 1800:
            print("  [NOTE] Video is over 30 minutes - processing will take longer and cost a little more.")
        kept_segments = _analyze_in_chunks(
            client, segments, quality_mode, video_duration,
            prompt_template, logs_path,
            target_duration=target_duration, aspect_ratio=aspect_ratio, platform=platform,
            gap_threshold=gap_threshold,
        )
    else:
        print(f"  Transcript size: ~{estimated_tokens:,} tokens - sending in one request.")
        kept_segments = _analyze_chunk(
            client, segments, quality_mode, video_duration,
            prompt_template, chunk_start_offset=0.0,
            logs_dir=logs_path, chunk_index=0,
            target_duration=target_duration, aspect_ratio=aspect_ratio, platform=platform,
            gap_threshold=gap_threshold,
        )

    # Merge the main raw/clean logs from chunk 0 into the standard names
    # so main.py can always reference logs/claude_raw.txt and logs/claude_clean.json
    _merge_logs(logs_path)

    kept_segments = _refine_selected_segments_by_editorial_scores(
        kept_segments=kept_segments,
        transcript_segments=segments,
        quality_mode=quality_mode,
    )
    kept_segments = _fill_duration_with_high_scoring_segments(
        kept_segments=kept_segments,
        transcript_segments=segments,
        quality_mode=quality_mode,
        target_duration=target_duration,
    )
    kept_segments = _snap_to_word_boundaries(kept_segments, segments)
    kept_segments = _enforce_duration_budget(
        kept_segments,
        target_duration=target_duration,
        transcript_segments=segments,
    )
    kept_segments = _merge_contiguous_segments(kept_segments)

    # Save final validated segments
    final_log = logs_path / "final_segments.json"
    with open(final_log, "w", encoding="utf-8") as f:
        json.dump(kept_segments, f, indent=2)
    print(f"  Saved final segments to: {final_log}")

    return kept_segments


def _analyze_in_chunks(
    client,
    segments: list[dict],
    quality_mode: str,
    video_duration: float,
    prompt_template: str,
    logs_path: Path,
    target_duration: int = 90,
    aspect_ratio: str = "16:9",
    platform: str = "general",
    gap_threshold: float = 0.5,
) -> list[dict]:
    """Split segments into 10-minute chunks and process each separately."""
    chunks: list[tuple[float, list[dict]]] = []
    current_chunk: list[dict] = []
    chunk_start = 0.0

    for seg in segments:
        if seg["start"] >= chunk_start + CHUNK_DURATION_SECONDS and current_chunk:
            chunks.append((chunk_start, current_chunk))
            chunk_start = seg["start"]
            current_chunk = []
        current_chunk.append(seg)

    if current_chunk:
        chunks.append((chunk_start, current_chunk))

    print(f"  Split into {len(chunks)} chunk(s) of up to 10 minutes each.")

    all_kept: list[dict] = []
    for i, (chunk_offset, chunk_segs) in enumerate(chunks):
        print(f"  Processing chunk {i + 1}/{len(chunks)} (starting at {_fmt_time(chunk_offset)})...")
        relative_segs = [
            {**s, "start": s["start"] - chunk_offset, "end": s["end"] - chunk_offset}
            for s in chunk_segs
        ]
        kept = _analyze_chunk(
            client, relative_segs, quality_mode, video_duration,
            prompt_template, chunk_start_offset=chunk_offset,
            logs_dir=logs_path, chunk_index=i,
            target_duration=target_duration, aspect_ratio=aspect_ratio, platform=platform,
            gap_threshold=gap_threshold,
        )
        all_kept.extend(kept)

    return all_kept


def _merge_logs(logs_path: Path) -> None:
    """Copy chunk 0 logs to the canonical log filenames."""
    raw_chunk = logs_path / "claude_raw_chunk0.txt"
    clean_chunk = logs_path / "claude_clean_chunk0.json"
    if raw_chunk.exists():
        (logs_path / "claude_raw.txt").write_text(raw_chunk.read_text(encoding="utf-8"), encoding="utf-8")
    if clean_chunk.exists():
        (logs_path / "claude_clean.json").write_text(clean_chunk.read_text(encoding="utf-8"), encoding="utf-8")
