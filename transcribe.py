"""
transcribe.py

Extracts audio from the input video and transcribes it with Sarvam AI for
supported Indian languages or local faster-whisper as a fallback. Returns a
list of timed segments with start, end, text, and word timestamps when
available.
"""

import os
# Force CPU-only mode before ctranslate2/faster-whisper loads.
# Without this, ctranslate2 probes for CUDA at import time on Windows and
# crashes with "cublas64_12.dll not found" on machines without CUDA 12.
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SARVAM_PREFERRED_LANGUAGES = {
    "mr-IN", "hi-IN", "en-IN",
    "bn-IN", "gu-IN", "kn-IN", "ml-IN", "pa-IN", "ta-IN", "te-IN",
}

SARVAM_MODEL = "saaras:v3"
SARVAM_MODE = "verbatim"
SARVAM_SEGMENT_GAP_SECONDS = 0.5
SARVAM_MAX_SEGMENT_SECONDS = 12.0
_SENTENCE_ENDINGS = frozenset(".?!।")


def _check_ffmpeg() -> None:
    """Raise a clear error if ffmpeg is not found on PATH."""
    if shutil.which("ffmpeg") is None:
        print("\n[ERROR] FFmpeg was not found on your system PATH.")
        print("  Windows: Download from https://github.com/BtbN/FFmpeg-Builds/releases")
        print("           Then add the 'bin' folder to your system PATH.")
        print("  Mac:     Run:  brew install ffmpeg")
        print("  After installing, open a NEW terminal window and try again.\n")
        sys.exit(1)


def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Use ffmpeg to extract a mono 16kHz WAV from the video — ideal for Whisper."""
    cmd = [
        "ffmpeg",
        "-y",                  # overwrite output if it exists
        "-i", str(video_path),
        "-ac", "1",            # mono channel
        "-ar", "16000",        # 16kHz sample rate (Whisper's preferred rate)
        "-vn",                 # no video stream
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n[ERROR] FFmpeg failed to extract audio from: {video_path}")
        print(f"  FFmpeg error: {result.stderr[-500:]}")
        sys.exit(1)


def _sarvam_language(language: str | None) -> str:
    if not language:
        return "unknown"
    short_map = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}
    return short_map.get(language, language)


def _whisper_language(language: str | None) -> str | None:
    if not language or language == "unknown":
        return None
    return language.split("-", 1)[0].lower()


def _should_prefer_sarvam(language: str | None) -> bool:
    normalized = _sarvam_language(language)
    return normalized in SARVAM_PREFERRED_LANGUAGES and bool(os.getenv("SARVAM_API_KEY"))


def _segment_timestamped_words(word_dicts: list[dict]) -> list[dict]:
    segments = []
    current = []

    def flush() -> None:
        if not current:
            return
        segments.append({
            "start": current[0]["start"],
            "end": current[-1]["end"],
            "text": " ".join(word["word"].strip() for word in current if word["word"].strip()),
            "words": list(current),
        })
        current.clear()

    for word in word_dicts:
        if current:
            gap = word["start"] - current[-1]["end"]
            proposed_duration = word["end"] - current[0]["start"]
            if gap > SARVAM_SEGMENT_GAP_SECONDS or proposed_duration > SARVAM_MAX_SEGMENT_SECONDS:
                flush()

        current.append(word)
        if word["word"].rstrip()[-1:] in _SENTENCE_ENDINGS:
            flush()

    flush()
    return segments


def _normalize_sarvam_response(data: dict) -> list[dict]:
    timestamps = data.get("timestamps") or {}
    words = timestamps.get("words") or []
    starts = timestamps.get("start_time_seconds") or []
    ends = timestamps.get("end_time_seconds") or []
    if words and starts and ends and len(words) == len(starts) == len(ends):
        word_dicts = []
        previous_start = None
        previous_end = None
        for word, start, end in zip(words, starts, ends):
            word_text = str(word).strip()
            try:
                start_seconds = float(start)
                end_seconds = float(end)
            except (TypeError, ValueError):
                continue
            if (
                not word_text
                or not math.isfinite(start_seconds)
                or not math.isfinite(end_seconds)
                or start_seconds < 0.0
                or end_seconds <= start_seconds
            ):
                continue
            if (
                previous_start is not None
                and (
                    start_seconds < previous_start
                    or end_seconds < previous_end
                )
            ):
                continue
            word_dicts.append({
                "word": word_text,
                "start": round(start_seconds, 3),
                "end": round(end_seconds, 3),
            })
            previous_start = start_seconds
            previous_end = end_seconds
        return _segment_timestamped_words(word_dicts)

    diarized_entries = ((data.get("diarized_transcript") or {}).get("entries") or [])
    if diarized_entries:
        segments = []
        for entry in diarized_entries:
            start = float(entry.get("start_time_seconds", 0.0))
            end = float(entry.get("end_time_seconds", start))
            text = (entry.get("transcript") or "").strip()
            if end > start and text:
                segments.append({
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "speaker_id": entry.get("speaker_id"),
                })
        if segments:
            return segments

    transcript = (data.get("transcript") or "").strip()
    if transcript:
        return [{"start": 0.0, "end": 0.0, "text": transcript}]

    return []


def _transcribe_with_sarvam(audio_path: Path, language: str | None, logs_path: Path) -> list[dict]:
    try:
        from sarvamai import SarvamAI
    except ImportError as exc:
        raise RuntimeError("sarvamai package is not installed") from exc

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set")

    client = SarvamAI(api_subscription_key=api_key)
    job = client.speech_to_text_job.create_job(
        model=SARVAM_MODEL,
        mode=SARVAM_MODE,
        language_code=_sarvam_language(language),
        with_diarization=False,
        with_timestamps=True,
    )
    job.upload_files(file_paths=[str(audio_path)])
    job.start()
    job.wait_until_complete()
    with tempfile.TemporaryDirectory(prefix="sarvam_", dir=logs_path) as output_dir:
        job.download_outputs(output_dir=output_dir)
        result_files = sorted(Path(output_dir).glob("*.json"))
        if not result_files:
            raise RuntimeError("Sarvam completed without a transcript JSON output")
        data = json.loads(result_files[0].read_text(encoding="utf-8"))

    segments = _normalize_sarvam_response(data)
    if not segments:
        raise RuntimeError("Sarvam transcript JSON did not contain usable timestamped text")
    (logs_path / "sarvam_raw.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return segments


def _transcribe_with_whisper(
    audio_path: Path,
    model_name: str,
    language: str | None,
    initial_prompt: str,
) -> tuple[list[dict], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("\n[ERROR] faster-whisper is not installed.")
        print("  Run:  pip install faster-whisper\n")
        sys.exit(1)

    model = WhisperModel(model_name, device="cpu", compute_type="int8")

    whisper_language = _whisper_language(language)
    lang_display = whisper_language if whisper_language else "auto-detect"
    print(f"  Transcribing... (language: {lang_display})")
    segments_generator, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language=whisper_language,
        vad_filter=True,
        word_timestamps=True,
        initial_prompt=initial_prompt,
        condition_on_previous_text=True,
    )

    segments: list[dict] = []
    for seg in segments_generator:
        seg_dict: dict = {
            "start": round(float(seg.start), 3),
            "end":   round(float(seg.end),   3),
            "text":  seg.text.strip(),
        }
        try:
            if seg.words:
                seg_dict["words"] = [
                    {
                        "word":        w.word,
                        "start":       round(float(w.start),       3),
                        "end":         round(float(w.end),         3),
                        "probability": round(float(w.probability), 4),
                    }
                    for w in seg.words
                ]
        except Exception:
            pass
        segments.append(seg_dict)

    return segments, info.language


def transcribe_video(
    video_path: str,
    model_name: str,
    logs_dir: str = "logs",
    language: str | None = None,
    initial_prompt: str = "A talking-head video. Clear spoken speech.",
) -> list[dict]:
    """
    Transcribe a video file and return a list of timed segments.

    Each segment is a dict:  {"start": float, "end": float, "text": str}

    Parameters
    ----------
    video_path : str
        Path to the input video file.
    model_name : str
        Whisper model size: tiny | base | small | medium | large
    logs_dir : str
        Directory where transcript.json will be saved.
    language : str | None
        BCP-47 language code (e.g. "en"). None = auto-detect (default).
        Passing the language skips Whisper's language-detection step and
        reduces transcription errors for known-language content.
    initial_prompt : str
        Domain hint fed to Whisper to anchor it to the expected speech style.
        Reduces errors on filler words and domain-specific vocabulary.

    Returns
    -------
    list[dict]
        Sorted list of transcript segments with start/end times.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(Path.cwd() / ".env")
        load_dotenv()
    except Exception:
        pass

    _check_ffmpeg()

    video_path = Path(video_path)
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)

    # Extract audio to a temporary WAV file
    audio_path = logs_path / "_audio_temp.wav"
    print(f"  Extracting audio from: {video_path.name}")
    _extract_audio(video_path, audio_path)

    provider = "whisper"
    detected_language = language
    sarvam_fallback_reason = None
    normalized_language = _sarvam_language(language)

    if _should_prefer_sarvam(language):
        print(f"  Using Sarvam AI STT ({SARVAM_MODEL}, {SARVAM_MODE}) for {normalized_language}")
        try:
            segments = _transcribe_with_sarvam(audio_path, normalized_language, logs_path)
            provider = "sarvam"
            detected_language = normalized_language
        except Exception as exc:
            sarvam_fallback_reason = str(exc)
            print(f"  [WARNING] Sarvam transcription failed: {sarvam_fallback_reason}")
            print("  Falling back to local Whisper.")
            print(f"  Loading Whisper model: {model_name}")
            print("  (First run downloads model files - this may take a few minutes)")
            segments, detected_language = _transcribe_with_whisper(
                audio_path, model_name, language, initial_prompt
            )
    else:
        print(f"  Loading Whisper model: {model_name}")
        print("  (First run downloads model files - this may take a few minutes)")
        segments, detected_language = _transcribe_with_whisper(
            audio_path, model_name, language, initial_prompt
        )

    # Clean up temp audio file
    if audio_path.exists():
        audio_path.unlink()

    # Save to logs
    transcript_log = logs_path / "transcript.json"
    with open(transcript_log, "w", encoding="utf-8") as f:
        payload = {
            "provider": provider,
            "model": SARVAM_MODEL if provider == "sarvam" else model_name,
            "language": detected_language,
            "segments": segments,
        }
        if sarvam_fallback_reason:
            payload["sarvam_fallback_reason"] = sarvam_fallback_reason
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"  Transcription complete - {len(segments)} segments found")
    print(f"  Saved transcript to: {transcript_log}")
    return segments
