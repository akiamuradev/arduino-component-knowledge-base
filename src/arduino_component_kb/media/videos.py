"""Bounded ffprobe/FFmpeg adapter for local video processing."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol, cast

from PIL import Image, UnidentifiedImageError

from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import (
    ALLOWED_VIDEO_MIMES,
    MAX_VIDEO_BYTES,
    MAX_VIDEO_DURATION_SECONDS,
    MAX_VIDEO_FRAME_RATE,
    MAX_VIDEO_HEIGHT,
    MAX_VIDEO_WIDTH,
    MediaValidationError,
)
from arduino_component_kb.media.images import detect_magic

MAX_TOOL_OUTPUT_BYTES = 1024 * 1024


class MediaToolError(RuntimeError):
    """FFmpeg execution failed without exposing untrusted stderr."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class CommandRunner(Protocol):
    async def run(
        self, executable: str, arguments: tuple[str, ...], timeout: float
    ) -> CommandResult:
        """Run one tool without a command shell."""


class SubprocessCommandRunner:
    async def run(
        self, executable: str, arguments: tuple[str, ...], timeout: float
    ) -> CommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *arguments,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise MediaToolError("media tool is unavailable") from error
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise MediaToolError("media tool timed out") from error
        if len(stdout) > MAX_TOOL_OUTPUT_BYTES or len(stderr) > MAX_TOOL_OUTPUT_BYTES:
            raise MediaToolError("media tool output exceeded limit")
        return CommandResult(process.returncode or 0, stdout, stderr)


@dataclass(frozen=True, slots=True)
class VideoProbe:
    detected_mime: str
    width: int
    height: int
    duration_ms: int
    video_codec: str
    audio_codec: str | None
    frame_rate: float


@dataclass(frozen=True, slots=True)
class VideoArtifact:
    path: Path
    mime: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    duration_ms: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    frame_rate: float | None = None


@dataclass(frozen=True, slots=True)
class ProcessedVideo:
    original: VideoProbe
    original_size_bytes: int
    original_sha256: str
    rendition: VideoArtifact
    poster: VideoArtifact


def validate_video_magic(path: Path, declared_mime: str) -> None:
    if declared_mime not in ALLOWED_VIDEO_MIMES:
        raise MediaValidationError("video_declared_mime_not_allowed")
    size = path.stat().st_size
    if not 0 < size <= MAX_VIDEO_BYTES:
        raise MediaValidationError("video_size_not_allowed")
    with path.open("rb") as source:
        header = source.read(12)
    if declared_mime == "video/webm":
        if not header.startswith(b"\x1aE\xdf\xa3"):
            raise MediaValidationError("video_magic_not_allowed")
        return
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise MediaValidationError("video_magic_not_allowed")
    _validate_iso_boxes(path, size)


def _validate_iso_boxes(path: Path, file_size: int) -> None:
    offset = 0
    with path.open("rb") as source:
        while offset < file_size:
            source.seek(offset)
            header = source.read(16)
            if len(header) < 8:
                raise MediaValidationError("video_container_trailing_or_truncated")
            box_size = int.from_bytes(header[:4], "big")
            header_size = 8
            if box_size == 1:
                if len(header) < 16:
                    raise MediaValidationError("video_container_trailing_or_truncated")
                box_size = int.from_bytes(header[8:16], "big")
                header_size = 16
            elif box_size == 0:
                box_size = file_size - offset
            if box_size < header_size or offset + box_size > file_size:
                raise MediaValidationError("video_container_trailing_or_truncated")
            offset += box_size
    if offset != file_size:
        raise MediaValidationError("video_container_trailing_or_truncated")


class VideoProcessor:
    def __init__(self, settings: Settings, runner: CommandRunner | None = None) -> None:
        self.settings = settings
        self.runner = runner or SubprocessCommandRunner()

    async def probe(self, path: Path, declared_mime: str) -> VideoProbe:
        validate_video_magic(path, declared_mime)
        arguments = (
            "-v",
            "error",
            "-show_entries",
            "format=format_name,duration:format_tags=major_brand:"
            "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration",
            "-of",
            "json",
            str(path),
        )
        result = await self.runner.run(
            self.settings.ffprobe_path, arguments, self.settings.ffprobe_timeout_seconds
        )
        if result.returncode != 0:
            raise MediaValidationError("video_probe_failed")
        try:
            document = cast(dict[str, object], json.loads(result.stdout))
            return _parse_probe(document, declared_mime)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise MediaValidationError("video_probe_invalid") from None

    async def transcode(
        self, original: Path, rendition: Path, poster: Path, declared_mime: str
    ) -> ProcessedVideo:
        original_probe = await self.probe(original, declared_mime)
        await self._run_ffmpeg(
            (
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(original),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-sn",
                "-dn",
                "-vf",
                "scale='min(1280,iw)':'min(720,ih)':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-threads",
                str(self.settings.ffmpeg_threads),
                "-movflags",
                "+faststart",
                "-y",
                str(rendition),
            )
        )
        midpoint = min(5.0, original_probe.duration_ms / 2000)
        await self._run_ffmpeg(
            (
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-ss",
                f"{midpoint:.3f}",
                "-i",
                str(original),
                "-frames:v",
                "1",
                "-map_metadata",
                "-1",
                "-vf",
                "scale='min(1280,iw)':'min(720,ih)':"
                "force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-threads",
                str(self.settings.ffmpeg_threads),
                "-y",
                str(poster),
            )
        )
        rendition_probe = await self.probe(rendition, "video/mp4")
        if rendition_probe.video_codec != "h264" or rendition_probe.audio_codec not in {
            None,
            "aac",
        }:
            raise MediaValidationError("video_rendition_codec_invalid")
        if rendition_probe.width > 1280 or rendition_probe.height > 720:
            raise MediaValidationError("video_rendition_dimensions_invalid")
        if not 0 < rendition.stat().st_size <= MAX_VIDEO_BYTES:
            raise MediaValidationError("video_rendition_size_invalid")
        poster_data = poster.read_bytes()
        poster_width, poster_height = _validate_poster(poster_data)
        return ProcessedVideo(
            original=original_probe,
            original_size_bytes=original.stat().st_size,
            original_sha256=_sha256_file(original),
            rendition=VideoArtifact(
                path=rendition,
                mime="video/mp4",
                width=rendition_probe.width,
                height=rendition_probe.height,
                size_bytes=rendition.stat().st_size,
                sha256=_sha256_file(rendition),
                duration_ms=rendition_probe.duration_ms,
                video_codec=rendition_probe.video_codec,
                audio_codec=rendition_probe.audio_codec,
                frame_rate=rendition_probe.frame_rate,
            ),
            poster=VideoArtifact(
                path=poster,
                mime="image/webp",
                width=poster_width,
                height=poster_height,
                size_bytes=len(poster_data),
                sha256=hashlib.sha256(poster_data).hexdigest(),
            ),
        )

    async def _run_ffmpeg(self, arguments: tuple[str, ...]) -> None:
        result = await self.runner.run(
            self.settings.ffmpeg_path, arguments, self.settings.ffmpeg_timeout_seconds
        )
        if result.returncode != 0:
            raise MediaToolError("ffmpeg failed")


def _parse_probe(document: dict[str, object], declared_mime: str) -> VideoProbe:
    raw_streams = document["streams"]
    raw_format = document["format"]
    if not isinstance(raw_streams, list) or not isinstance(raw_format, dict):
        raise TypeError
    streams = [
        cast(dict[str, object], stream) for stream in raw_streams if isinstance(stream, dict)
    ]
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(streams) != len(video_streams) + len(audio_streams):
        raise MediaValidationError("video_stream_type_not_allowed")
    if len(video_streams) != 1 or len(audio_streams) > 1:
        raise MediaValidationError("video_stream_count_not_allowed")
    video = video_streams[0]
    width = int(cast(str | int, video["width"]))
    height = int(cast(str | int, video["height"]))
    frame_rate = _fraction(str(video.get("avg_frame_rate") or video.get("r_frame_rate")))
    duration_value = raw_format.get("duration") or video.get("duration")
    if not isinstance(duration_value, (str, int, float)):
        raise TypeError
    duration = float(duration_value)
    if (
        width <= 0
        or height <= 0
        or width > MAX_VIDEO_WIDTH
        or height > MAX_VIDEO_HEIGHT
        or frame_rate <= 0
        or frame_rate > MAX_VIDEO_FRAME_RATE + 0.001
        or duration <= 0
        or duration > MAX_VIDEO_DURATION_SECONDS + 0.001
    ):
        raise MediaValidationError("video_limits_exceeded")
    format_name = str(raw_format.get("format_name", ""))
    detected_mime = _detected_mime(format_name, raw_format)
    if detected_mime != declared_mime:
        raise MediaValidationError("video_mime_mismatch")
    audio_codec = str(audio_streams[0]["codec_name"]) if audio_streams else None
    return VideoProbe(
        detected_mime=detected_mime,
        width=width,
        height=height,
        duration_ms=round(duration * 1000),
        video_codec=str(video["codec_name"]),
        audio_codec=audio_codec,
        frame_rate=frame_rate,
    )


def _detected_mime(format_name: str, raw_format: dict[object, object]) -> str:
    if "webm" in format_name:
        return "video/webm"
    if "mov" in format_name or "mp4" in format_name:
        tags = raw_format.get("tags")
        if isinstance(tags, dict) and str(tags.get("major_brand", "")).strip() == "qt":
            return "video/quicktime"
        return "video/mp4"
    raise MediaValidationError("video_container_not_allowed")


def _fraction(value: str) -> float:
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return float(value)
    divisor = float(denominator)
    if divisor == 0:
        raise ValueError
    return float(numerator) / divisor


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_poster(data: bytes) -> tuple[int, int]:
    if not 0 < len(data) <= 8 * 1024 * 1024 or detect_magic(data) != "image/webp":
        raise MediaValidationError("video_poster_invalid")
    try:
        with Image.open(BytesIO(data)) as poster:
            if getattr(poster, "n_frames", 1) != 1:
                raise MediaValidationError("video_poster_invalid")
            poster.load()
            if (
                poster.width <= 0
                or poster.height <= 0
                or poster.width > 1280
                or poster.height > 720
            ):
                raise MediaValidationError("video_poster_invalid")
            if poster.getexif():
                raise MediaValidationError("video_poster_invalid")
            return poster.size
    except MediaValidationError:
        raise
    except (OSError, UnidentifiedImageError, ValueError):
        raise MediaValidationError("video_poster_invalid") from None
