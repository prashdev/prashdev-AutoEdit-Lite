import json
from pathlib import Path
import sys
import types

import transcribe


class FakeWhisperModel:
    calls = []
    transcribe_calls = []

    def __init__(self, model_name, device, compute_type):
        self.calls.append((model_name, device, compute_type))

    def transcribe(self, audio_path, **kwargs):
        self.transcribe_calls.append(kwargs)
        class Info:
            language = "en"

        class Segment:
            start = 0.0
            end = 1.2
            text = "fallback transcript"
            words = []

        return iter([Segment()]), Info()


def test_sarvam_job_explicitly_requests_word_timestamps(monkeypatch, tmp_path):
    create_job_kwargs = {}

    class FakeJob:
        def upload_files(self, file_paths):
            pass

        def start(self):
            pass

        def wait_until_complete(self):
            pass

        def download_outputs(self, output_dir):
            Path(output_dir, "result.json").write_text(
                json.dumps({
                    "timestamps": {
                        "words": ["precise", "cuts"],
                        "start_time_seconds": [0.0, 0.5],
                        "end_time_seconds": [0.4, 0.9],
                    },
                }),
                encoding="utf-8",
            )

    class FakeSpeechToTextJob:
        def create_job(self, **kwargs):
            create_job_kwargs.update(kwargs)
            return FakeJob()

    class FakeSarvamAI:
        def __init__(self, api_subscription_key):
            self.speech_to_text_job = FakeSpeechToTextJob()

    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "sarvamai", types.SimpleNamespace(SarvamAI=FakeSarvamAI))

    transcribe._transcribe_with_sarvam(tmp_path / "audio.wav", "mr-IN", tmp_path)

    assert create_job_kwargs["with_timestamps"] is True


def test_sarvam_job_does_not_reuse_stale_downloaded_transcript(monkeypatch, tmp_path):
    stale_dir = tmp_path / "sarvam"
    stale_dir.mkdir()
    (stale_dir / "a_stale.json").write_text(
        json.dumps({"transcript": "stale transcript"}),
        encoding="utf-8",
    )

    class FakeJob:
        def upload_files(self, file_paths):
            pass

        def start(self):
            pass

        def wait_until_complete(self):
            pass

        def download_outputs(self, output_dir):
            Path(output_dir, "result.json").write_text(
                json.dumps({
                    "timestamps": {
                        "words": ["current", "transcript"],
                        "start_time_seconds": [0.0, 0.5],
                        "end_time_seconds": [0.4, 1.0],
                    },
                }),
                encoding="utf-8",
            )

    class FakeSarvamAI:
        def __init__(self, api_subscription_key):
            self.speech_to_text_job = types.SimpleNamespace(create_job=lambda **kwargs: FakeJob())

    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "sarvamai", types.SimpleNamespace(SarvamAI=FakeSarvamAI))

    segments = transcribe._transcribe_with_sarvam(tmp_path / "audio.wav", "mr-IN", tmp_path)

    assert segments[0]["text"] == "current transcript"


def test_prefers_sarvam_for_indian_languages_when_key_is_configured(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setattr(transcribe, "_check_ffmpeg", lambda: None)
    monkeypatch.setattr(transcribe, "_extract_audio", lambda video, audio: audio.write_bytes(b"wav"))
    monkeypatch.setattr(
        transcribe,
        "_transcribe_with_sarvam",
        lambda audio_path, language, logs_path: calls.append((audio_path.name, language))
        or [{"start": 0.1, "end": 1.0, "text": "sarvam transcript"}],
    )

    result = transcribe.transcribe_video(
        video_path=str(tmp_path / "input.mp4"),
        model_name="medium",
        logs_dir=str(tmp_path),
        language="mr-IN",
    )

    assert result == [{"start": 0.1, "end": 1.0, "text": "sarvam transcript"}]
    assert calls == [("_audio_temp.wav", "mr-IN")]


def test_loads_sarvam_key_from_dotenv_before_provider_selection(monkeypatch, tmp_path):
    calls = []
    (tmp_path / ".env").write_text("SARVAM_API_KEY=dotenv-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.setattr(transcribe, "_check_ffmpeg", lambda: None)
    monkeypatch.setattr(transcribe, "_extract_audio", lambda video, audio: audio.write_bytes(b"wav"))
    monkeypatch.setattr(
        transcribe,
        "_transcribe_with_sarvam",
        lambda audio_path, language, logs_path: calls.append(language)
        or [{"start": 0.1, "end": 1.0, "text": "dotenv sarvam transcript"}],
    )

    result = transcribe.transcribe_video(
        video_path=str(tmp_path / "input.mp4"),
        model_name="medium",
        logs_dir=str(tmp_path / "logs"),
        language="mr-IN",
    )

    assert result[0]["text"] == "dotenv sarvam transcript"
    assert calls == ["mr-IN"]


def test_falls_back_to_whisper_when_sarvam_fails(monkeypatch, tmp_path):
    FakeWhisperModel.calls = []
    FakeWhisperModel.transcribe_calls = []
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setattr(transcribe, "_check_ffmpeg", lambda: None)
    monkeypatch.setattr(transcribe, "_extract_audio", lambda video, audio: audio.write_bytes(b"wav"))
    monkeypatch.setattr(
        transcribe,
        "_transcribe_with_sarvam",
        lambda audio_path, language, logs_path: (_ for _ in ()).throw(RuntimeError("api down")),
    )

    import types
    import sys

    fake_module = types.SimpleNamespace(WhisperModel=FakeWhisperModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)

    result = transcribe.transcribe_video(
        video_path=str(tmp_path / "input.mp4"),
        model_name="base",
        logs_dir=str(tmp_path),
        language="hi-IN",
    )

    assert result[0]["text"] == "fallback transcript"
    assert FakeWhisperModel.transcribe_calls[0]["language"] == "hi"
    provider_log = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert provider_log["provider"] == "whisper"
    assert provider_log["sarvam_fallback_reason"] == "api down"


def test_sarvam_response_timestamps_are_normalized_to_word_segments(tmp_path):
    response = {
        "language_code": "hi-IN",
        "timestamps": {
            "words": ["नमस्ते", "दोस्तों"],
            "start_time_seconds": [0.0, 0.6],
            "end_time_seconds": [0.5, 1.1],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert segments == [
        {
            "start": 0.0,
            "end": 1.1,
            "text": "नमस्ते दोस्तों",
            "words": [
                {"word": "नमस्ते", "start": 0.0, "end": 0.5},
                {"word": "दोस्तों", "start": 0.6, "end": 1.1},
            ],
        }
    ]


def test_sarvam_response_discards_blank_timestamp_tokens_before_segmenting():
    response = {
        "timestamps": {
            "words": ["   ", "IVF", "helps"],
            "start_time_seconds": [0.0, 1.0, 1.5],
            "end_time_seconds": [0.8, 1.4, 2.0],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert segments == [
        {
            "start": 1.0,
            "end": 2.0,
            "text": "IVF helps",
            "words": [
                {"word": "IVF", "start": 1.0, "end": 1.4},
                {"word": "helps", "start": 1.5, "end": 2.0},
            ],
        }
    ]


def test_sarvam_response_discards_non_positive_word_timestamp_ranges():
    response = {
        "timestamps": {
            "words": ["IVF", "invalid", "helps"],
            "start_time_seconds": [0.0, 1.2, 1.5],
            "end_time_seconds": [0.5, 1.0, 2.0],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [word["word"] for segment in segments for word in segment["words"]] == [
        "IVF",
        "helps",
    ]
    assert all(word["end"] > word["start"] for segment in segments for word in segment["words"])


def test_sarvam_response_discards_word_with_backward_start_timestamp():
    response = {
        "timestamps": {
            "words": ["IVF", "stale", "helps"],
            "start_time_seconds": [1.0, 0.2, 1.5],
            "end_time_seconds": [1.4, 0.6, 2.0],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [word["word"] for segment in segments for word in segment["words"]] == [
        "IVF",
        "helps",
    ]
    assert segments[0]["start"] == 1.0
    assert segments[0]["end"] == 2.0


def test_sarvam_response_discards_word_with_backward_end_timestamp():
    response = {
        "timestamps": {
            "words": ["IVF", "stale", "helps"],
            "start_time_seconds": [0.0, 0.6, 1.5],
            "end_time_seconds": [1.0, 0.8, 2.0],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [word["word"] for segment in segments for word in segment["words"]] == [
        "IVF",
        "helps",
    ]
    assert all(
        later["start"] >= earlier["start"] and later["end"] >= earlier["end"]
        for segment in segments
        for earlier, later in zip(segment["words"], segment["words"][1:])
    )


def test_sarvam_word_timestamps_split_at_sentence_boundaries():
    response = {
        "timestamps": {
            "words": ["IVF", "helps.", "Patient", "support", "matters."],
            "start_time_seconds": [0.0, 0.4, 1.1, 1.6, 2.1],
            "end_time_seconds": [0.3, 0.9, 1.5, 2.0, 2.7],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [(segment["start"], segment["end"], segment["text"]) for segment in segments] == [
        (0.0, 0.9, "IVF helps."),
        (1.1, 2.7, "Patient support matters."),
    ]
    assert [word["word"] for word in segments[0]["words"]] == ["IVF", "helps."]


def test_sarvam_word_timestamps_split_at_meaningful_pause_without_punctuation():
    response = {
        "timestamps": {
            "words": ["IVF", "helps", "patient", "support"],
            "start_time_seconds": [0.0, 0.4, 2.0, 2.5],
            "end_time_seconds": [0.3, 0.9, 2.4, 3.0],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [segment["text"] for segment in segments] == ["IVF helps", "patient support"]


def test_sarvam_word_timestamps_split_at_short_form_pause_threshold():
    response = {
        "timestamps": {
            "words": ["IVF", "helps", "patient", "support"],
            "start_time_seconds": [0.0, 0.4, 1.5, 2.0],
            "end_time_seconds": [0.3, 0.9, 1.9, 2.5],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [segment["text"] for segment in segments] == ["IVF helps", "patient support"]


def test_sarvam_word_timestamps_keep_exact_half_second_pause_contiguous():
    response = {
        "timestamps": {
            "words": ["IVF", "helps", "patients"],
            "start_time_seconds": [0.0, 0.4, 1.4],
            "end_time_seconds": [0.3, 0.9, 1.9],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert [segment["text"] for segment in segments] == ["IVF helps patients"]


def test_sarvam_word_timestamps_cap_long_unpunctuated_segments():
    words = [f"word{i}" for i in range(30)]
    starts = [i * 0.5 for i in range(30)]
    ends = [start + 0.4 for start in starts]
    response = {
        "timestamps": {
            "words": words,
            "start_time_seconds": starts,
            "end_time_seconds": ends,
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert len(segments) == 2
    assert all(segment["end"] - segment["start"] <= 12.0 for segment in segments)
    assert [word["word"] for segment in segments for word in segment["words"]] == words


def test_sarvam_response_prefers_word_timestamps_over_coarse_diarized_entries():
    response = {
        "diarized_transcript": {
            "entries": [{
                "start_time_seconds": 0.0,
                "end_time_seconds": 2.0,
                "transcript": "coarse transcript",
                "speaker_id": "speaker-1",
            }]
        },
        "timestamps": {
            "words": ["precise", "transcript"],
            "start_time_seconds": [0.2, 1.1],
            "end_time_seconds": [0.8, 1.8],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert segments[0]["start"] == 0.2
    assert segments[0]["end"] == 1.8
    assert segments[0]["text"] == "precise transcript"
    assert segments[0]["words"][0]["start"] == 0.2


def test_sarvam_response_does_not_fabricate_word_confidence():
    response = {
        "timestamps": {
            "words": ["precise", "transcript"],
            "start_time_seconds": [0.2, 1.1],
            "end_time_seconds": [0.8, 1.8],
        },
    }

    segments = transcribe._normalize_sarvam_response(response)

    assert all(word.get("probability") is None for word in segments[0]["words"])
