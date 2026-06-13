"""
xml_export.py

Exports Claude's kept segments as a Final Cut Pro 7 XML (XMEML) timeline
that Adobe Premiere Pro can import as a new sequence with all cuts pre-applied.

Three key fixes applied over raw OTIO output:

1. pathurl fix — OTIO writes a bare file path; Premiere requires a proper
   file:// URI (file:///Users/... on Mac, file:///D:/... on Windows).
   Without this Premiere shows "Media Offline" and there is no video or audio.

2. Format injection — OTIO writes an empty <format/> in the sequence-level
   <video> block. We replace that empty element with a properly populated
   <samplecharacteristics> block so Premiere opens the sequence at the
   correct resolution and frame rate.

3. Audio channel fix — detects the real channel count and sample rate from
   the source video and generates matching audio tracks + channel type tags
   (Stereo / Mono) so Premiere can link the media without "Cannot Link Media"
   errors caused by a channel-count mismatch.
"""

import re
import subprocess
from pathlib import Path

import opentimelineio as otio


def _detect_fps(video_path: str) -> float:
    """Read frame rate from video using ffprobe. Falls back to 25.0 on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        raw = result.stdout.strip()
        if "/" in raw:
            num, den = raw.split("/")
            return round(float(num) / float(den), 3)
        return float(raw)
    except Exception:
        return 25.0


def _detect_audio_info(video_path: str) -> tuple[int, int]:
    """
    Read audio channel count and sample rate from video using ffprobe.

    Returns
    -------
    (channels, sample_rate)
        Falls back to (2, 48000) on any failure so exports always succeed.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=channels,sample_rate",
        "-of", "default=noprint_wrappers=1",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        channels = 2
        sample_rate = 48000
        for line in result.stdout.strip().splitlines():
            if line.startswith("channels="):
                channels = int(line.split("=")[1])
            elif line.startswith("sample_rate="):
                sample_rate = int(line.split("=")[1])
        return channels, sample_rate
    except Exception:
        return 2, 48000


def _build_file_audio_xml(channel_count: int) -> str:
    """
    Build the <audio> element for the file-level <media> block.

    Declares the source file's channel count and individual channel labels
    so Premiere can link the media without a channel-count mismatch.
    """
    if channel_count == 1:
        return (
            "<audio>"
            "<channelcount>1</channelcount>"
            "<audiochannel><sourcechannel>1</sourcechannel>"
            "<channellabel>mono</channellabel></audiochannel>"
            "</audio>"
        )
    labels = ["left", "right", "C", "LFE", "Ls", "Rs"]
    ch_xml = "".join(
        f"<audiochannel><sourcechannel>{i}</sourcechannel>"
        f"<channellabel>{labels[i - 1] if i - 1 < len(labels) else f'A{i}'}</channellabel>"
        f"</audiochannel>"
        for i in range(1, channel_count + 1)
    )
    return f"<audio><channelcount>{channel_count}</channelcount>{ch_xml}</audio>"


def _to_file_uri(file_path: str) -> str:
    """
    Convert an absolute file path to a file:// URI that Premiere Pro accepts.

    Mac:     /Users/foo/bar.mp4  →  file:///Users/foo/bar.mp4
    Windows: C:\\Users\\foo\\bar.mp4  →  file:///C:/Users/foo/bar.mp4
    """
    p = Path(file_path).resolve()
    return p.as_uri()


def _fix_media_paths(content: str, abs_path: str) -> str:
    """
    Replace the bare pathurl written by OTIO with a proper file:// URI.
    OTIO uses the value we passed in as the target_url; we need to replace
    it with the URI version in all <pathurl> elements.
    """
    uri = _to_file_uri(abs_path)
    posix = Path(abs_path).resolve().as_posix()
    return content.replace(
        f"<pathurl>{posix}</pathurl>",
        f"<pathurl>{uri}</pathurl>",
    )


def _inject_sequence_settings(
    xml_path: str,
    width: int,
    height: int,
    fps: float,
    abs_video_path: str,
    num_channels: int = 2,
    sample_rate: int = 48000,
) -> None:
    """
    Post-process the OTIO-generated FCP7 XML to:
    1. Replace the bare pathurl with a file:// URI (fixes Media Offline).
    2. Replace the empty <format/> in the sequence-level <video> block with
       proper resolution/fps settings.
    3. Inject correct audio format (real sample rate) into the sequence-level
       <audio> section.
    4. Add <audiochanneltype>Stereo|Mono</audiochanneltype> to each audio track.
    5. Replace OTIO's empty <audio/> in every file-level <media> block with a
       full <channelcount> + <audiochannel> declaration (done last to avoid
       confusing the sequence-level <audio> searches in steps 3/4).
    """
    timebase = str(round(fps))
    ntsc = "TRUE" if abs(fps - round(fps)) > 0.01 else "FALSE"
    channel_type = "Stereo" if num_channels >= 2 else "Mono"

    video_format_xml = (
        f"<format><samplecharacteristics>"
        f"<width>{width}</width>"
        f"<height>{height}</height>"
        f"<anamorphic>FALSE</anamorphic>"
        f"<pixelaspectratio>square</pixelaspectratio>"
        f"<fielddominance>none</fielddominance>"
        f"<rate><timebase>{timebase}</timebase><ntsc>{ntsc}</ntsc></rate>"
        f"</samplecharacteristics></format>"
    )

    audio_format_xml = (
        f"<format><samplecharacteristics>"
        f"<depth>16</depth>"
        f"<samplerate>{sample_rate}</samplerate>"
        f"</samplecharacteristics></format>"
    )

    with open(xml_path, "r", encoding="utf-8") as f:
        content = f.read()

    # ── Fix 1: file:// URI ─────────────────────────────────────────────────
    content = _fix_media_paths(content, abs_video_path)

    # ── Fix 2: sequence-level video format ────────────────────────────────
    media_pos = content.find("<media>")
    if media_pos != -1:
        video_pos = content.find("<video>", media_pos)
        if video_pos != -1:
            track_pos = content.find("<track>", video_pos)
            if track_pos != -1:
                region = content[video_pos + 7 : track_pos]
                region = re.sub(r"<format\s*/>", "", region)
                region = re.sub(r"<format>.*?</format>", "", region, flags=re.DOTALL)
                content = (
                    content[: video_pos + 7]
                    + video_format_xml
                    + region
                    + content[track_pos:]
                )

    # ── Fix 4a: sequence-level audio format block ─────────────────────────
    if media_pos != -1:
        media_pos2 = content.find("<media>")
        audio_pos = content.find("<audio>", media_pos2 if media_pos2 != -1 else 0)
        if audio_pos != -1:
            audio_track_pos = content.find("<track>", audio_pos)
            if audio_track_pos != -1:
                audio_region = content[audio_pos + 7 : audio_track_pos]
                if "<format>" not in audio_region:
                    audio_region = re.sub(r"<format\s*/>", "", audio_region)
                    content = (
                        content[: audio_pos + 7]
                        + audio_format_xml
                        + audio_region
                        + content[audio_track_pos:]
                    )

    # ── Fix 4b: <audiochanneltype> inside each sequence-level audio <track> ─
    media_pos3 = content.find("<media>")
    if media_pos3 != -1:
        audio_start = content.find("<audio>", media_pos3)
        audio_end   = content.find("</audio>", audio_start) if audio_start != -1 else -1
        if audio_start != -1 and audio_end != -1:
            audio_block = content[audio_start : audio_end + 8]

            def _add_channel_type(m):
                tag = m.group(0)  # the literal "<track>" string
                rest = audio_block[m.start():]
                if "<audiochanneltype>" in rest[:80]:
                    return tag  # already annotated — leave it
                return tag + f"<audiochanneltype>{channel_type}</audiochanneltype>"

            new_audio_block = re.sub(r"<track>", _add_channel_type, audio_block)
            content = content[:audio_start] + new_audio_block + content[audio_end + 8:]

    # ── Fix 5: file-level <audio/> → channel declaration ──────────────────
    # Done last so the <audio> string it introduces doesn't confuse the
    # sequence-level <audio> searches in Fixes 3/4a/4b above.
    # OTIO writes <audio/> inside each <file><media> block; Premiere reads
    # this to verify channel count before linking the media — an empty element
    # defaults to 1ch and causes "Cannot Link Media" for stereo sources.
    content = content.replace("<audio/>", _build_file_audio_xml(num_channels))

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(content)


def export_premiere_xml(
    input_video_path: str,
    segments: list[dict],
    output_xml_path: str,
    width: int = 1920,
    height: int = 1080,
    target_fps: int | None = None,
) -> None:
    """
    Write a Premiere Pro-importable FCP7 XML timeline to output_xml_path.

    Parameters
    ----------
    input_video_path : str
        Absolute path to the original video file.
    segments : list[dict]
        Kept segments: [{"start": float, "end": float, "reason": str}, ...]
    output_xml_path : str
        Destination path for the .xml file.
    width : int
        Sequence width in pixels. Use 1080 for 9:16 vertical (default: 1920).
    height : int
        Sequence height in pixels. Use 1920 for 9:16 vertical (default: 1080).
    target_fps : int | None
        Override the auto-detected frame rate (e.g. 30). None = auto-detect.
    """
    detected_fps = _detect_fps(input_video_path)
    fps = float(target_fps) if target_fps is not None else detected_fps
    num_channels, sample_rate = _detect_audio_info(input_video_path)

    print(f"  Detected frame rate  : {detected_fps:.3f} fps  |  Sequence fps: {fps:.0f}")
    print(f"  Sequence resolution  : {width}x{height}")
    print(f"  Audio                : {num_channels}ch @ {sample_rate} Hz"
          f"  ({'Stereo' if num_channels >= 2 else 'Mono'})")

    timeline = otio.schema.Timeline(name="AutoEdit — Rough Cut")

    video_track = otio.schema.Track(name="Video 1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(video_track)

    # FCP7 XML expects one sequence audio track per source channel.
    audio_tracks = []
    for channel_index in range(max(1, num_channels)):
        audio_track = otio.schema.Track(
            name=f"Audio {channel_index + 1}",
            kind=otio.schema.TrackKind.Audio,
        )
        timeline.tracks.append(audio_track)
        audio_tracks.append(audio_track)

    abs_path = str(Path(input_video_path).resolve())
    abs_posix = Path(abs_path).as_posix()

    max_end_sec = max((seg["end"] for seg in segments), default=0.0)
    available_range = otio.opentime.TimeRange(
        start_time=otio.opentime.RationalTime(0, fps),
        duration=otio.opentime.RationalTime(round((max_end_sec + 1.0) * fps), fps),
    )
    media_ref = otio.schema.ExternalReference(
        target_url=abs_posix,
        available_range=available_range,
    )

    for seg in segments:
        start_frame = round(seg["start"] * fps)
        end_frame   = round(seg["end"] * fps)
        duration_frames = end_frame - start_frame
        if duration_frames <= 0:
            continue

        source_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(start_frame, fps),
            duration=otio.opentime.RationalTime(duration_frames, fps),
        )
        label = (seg.get("reason") or f"{seg['start']:.1f}s-{seg['end']:.1f}s")[:50]

        video_track.append(otio.schema.Clip(
            name=label,
            media_reference=media_ref,
            source_range=source_range,
        ))
        for audio_track in audio_tracks:
            audio_track.append(otio.schema.Clip(
                name=label,
                media_reference=media_ref,
                source_range=source_range,
            ))

    output_path = Path(output_xml_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(timeline, str(output_path), adapter_name="fcp_xml")

    # Post-process: fix pathurl, inject resolution + real audio format/channels
    _inject_sequence_settings(
        str(output_path),
        width=width,
        height=height,
        fps=fps,
        abs_video_path=abs_path,
        num_channels=num_channels,
        sample_rate=sample_rate,
    )

    print(f"  Premiere XML saved to: {output_path}")
