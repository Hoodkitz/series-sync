"""Thin, safe wrappers around ffmpeg/ffprobe.

All calls use argument lists (never a shell) and only ever receive paths that the
storage layer produced, so user input cannot reach the command line as options.
"""
from __future__ import annotations

import asyncio
import json
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


class MediaError(RuntimeError):
    """ffmpeg/ffprobe failed or the media is unusable."""


async def _run(*args: str, timeout: float = 3600) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError(f"{args[0]} timed out after {timeout}s")
    if proc.returncode != 0:
        tail = err.decode(errors="replace").strip().splitlines()[-3:]
        raise MediaError(f"{args[0]} failed: {' | '.join(tail)}")
    return out


# Containers we accept. Playlist/script demuxers (hls, concat, ffconcat, image2 sequences, tty, ...) can make ffmpeg
# open other local files or network URLs named *inside* an uploaded file, so they are rejected outright.
SAFE_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm", "avi", "wav", "mp3", "flac", "ogg"}


def _inp(path: str | Path) -> list[str]:
    """Input arguments for a file: local files only, no protocol other than 'file' may ever be opened."""
    return ["-protocol_whitelist", "file", "-i", str(path)]


async def probe(path: str | Path) -> dict:
    out = await _run(FFPROBE, "-v", "error", "-protocol_whitelist", "file", "-print_format", "json", "-show_format",
                     "-show_streams", "--", str(path), timeout=120)
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:  # pragma: no cover - ffprobe always emits JSON with -print_format json
        raise MediaError(f"ffprobe returned invalid JSON: {e}")


async def media_info(path: str | Path) -> dict:
    """Duration and stream presence of a media file."""
    data = await probe(path)
    fmt = data.get("format", {})
    names = set((fmt.get("format_name") or "").split(","))
    if not names or not names <= SAFE_FORMATS:
        raise MediaError(f"unsupported container format: {fmt.get('format_name')}")
    streams = data.get("streams", [])
    try:
        duration = float(fmt.get("duration") or 0.0)
    except ValueError:
        duration = 0.0
    if duration <= 0:
        raise MediaError("media has no measurable duration")
    return {
        "duration": duration,
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


async def extract_audio_for_asr(src: str | Path, dst: str | Path, max_seconds: float) -> Path:
    """Mono 16 kHz speech-optimised MP3 (small enough for hosted ASR upload limits).

    ``-t`` caps the work actually done, independent of the duration the container claims."""
    await _run(FFMPEG, "-nostdin", "-y", *_inp(src), "-t", f"{max_seconds:.3f}", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
               "-f", "mp3", str(dst))
    return Path(dst)


async def cut_audio(src: str | Path, dst: str | Path, start: float, duration: float) -> Path:
    await _run(FFMPEG, "-nostdin", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", *_inp(src),
               "-ac", "1", "-ar", "16000", "-b:a", "48k", "-f", "mp3", str(dst))
    return Path(dst)


async def to_wav(src: str | Path, dst: str | Path) -> Path:
    """Decode anything to mono 16-bit PCM WAV at SAMPLE_RATE."""
    await _run(FFMPEG, "-nostdin", "-y", *_inp(src), "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16",
               "-f", "wav", str(dst))
    return Path(dst)


def _atempo_chain(factor: float) -> str:
    # atempo accepts 0.5..2.0 per instance; chain for anything outside.
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append(f"atempo={factor:.4f}")
    return ",".join(parts)


async def change_tempo(src: str | Path, dst: str | Path, factor: float) -> Path:
    """Speed speech up (factor > 1) or down without changing pitch."""
    await _run(FFMPEG, "-nostdin", "-y", *_inp(src), "-filter:a", _atempo_chain(factor), "-ac", "1",
               "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", "-f", "wav", str(dst))
    return Path(dst)


def wav_duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav(path: str | Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != SAMPLE_RATE:
            raise MediaError(f"unexpected WAV format in {path}")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def assemble_track(placements: list[tuple[str | Path, float]], total_seconds: float, dst: str | Path) -> Path:
    """Place mono WAV clips at absolute start times on a silent track (overlaps are summed and clipped)."""
    total = int(round(total_seconds * SAMPLE_RATE))
    track = np.zeros(total, dtype=np.int32)
    for path, start in placements:
        clip = read_wav(path).astype(np.int32)
        offset = max(0, int(round(start * SAMPLE_RATE)))
        if offset >= total:
            continue
        end = min(total, offset + len(clip))
        track[offset:end] += clip[: end - offset]
    np.clip(track, -32768, 32767, out=track)
    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(track.astype(np.int16).tobytes())
    return Path(dst)


async def mux_dub(video: str | Path, dub_track: str | Path, dst: str | Path, *, background_volume: float,
                  target_language: str, source_language: str, keep_original_track: bool = True) -> Path:
    """Write the final MP4: video copied, dubbed mix as default audio, original audio as optional 2nd track.

    The dub mix is the synthesised speech plus the original soundtrack at ``background_volume`` so music and
    effects stay audible. Loudness is normalised to broadcast level (EBU R128, -16 LUFS for streaming).
    """
    info = await media_info(video)
    args = [FFMPEG, "-nostdin", "-y", *_inp(video), *_inp(dub_track)]
    if info["has_audio"] and background_volume > 0:
        fc = (f"[0:a]volume={background_volume:.3f}[bg];"
              f"[1:a][bg]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[dub]")
    else:
        fc = "[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[dub]"
    args += ["-filter_complex", fc, "-map", "0:v:0", "-map", "[dub]"]
    if info["has_audio"] and keep_original_track:
        args += ["-map", "0:a:0"]
    args += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-metadata:s:a:0", f"language={_iso639_2(target_language)}", "-disposition:a:0", "default"]
    if info["has_audio"] and keep_original_track:
        args += ["-metadata:s:a:1", f"language={_iso639_2(source_language)}", "-disposition:a:1", "0"]
    # EU AI Act Art. 50: synthetic audio must be machine-readably marked as AI-generated.
    args += ["-metadata", "comment=AI-generated dubbing (Series Sync)", "-metadata:s:a:0",
             "handler_name=AI-generated dub", "-shortest", "-movflags", "+faststart", str(dst)]
    await _run(*args)
    return Path(dst)


async def mean_volume_db(path: str | Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        FFMPEG, "-nostdin", *_inp(path), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    for line in err.decode(errors="replace").splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    raise MediaError("could not measure volume")


async def synth_tone(dst: str | Path, seconds: float, freq: int = 440) -> Path:
    """Test helper / fake TTS: a quiet sine tone."""
    await _run(FFMPEG, "-nostdin", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds:.3f}",
               "-af", "volume=0.3", "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", "-f", "wav", str(dst))
    return Path(dst)


async def synth_test_video(dst: str | Path, seconds: float = 6.0) -> Path:
    """Test helper: small video with a tone soundtrack."""
    await _run(FFMPEG, "-nostdin", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=25:duration={seconds}",
               "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-c:v", "libx264", "-preset",
               "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dst))
    return Path(dst)


_ISO = {"de": "ger", "en": "eng", "fr": "fre", "es": "spa", "it": "ita", "pt": "por", "nl": "dut", "pl": "pol",
        "tr": "tur", "ru": "rus", "ja": "jpn", "ko": "kor", "zh": "chi"}


def _iso639_2(lang: str) -> str:
    return _ISO.get(lang.lower()[:2], "und")
