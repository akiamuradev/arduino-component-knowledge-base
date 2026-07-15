"""FFprobe parsing, FFmpeg command, container, limit, and timeout tests."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import MediaValidationError
from arduino_component_kb.media.models import MediaJob
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.videos import (
    CommandResult,
    MediaToolError,
    SubprocessCommandRunner,
    VideoProcessor,
    validate_video_magic,
)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        ffprobe_path="ffprobe-test",
        ffmpeg_path="ffmpeg-test",
    )


def write_mp4(path: Path, trailing: bytes = b"") -> None:
    ftyp = (16).to_bytes(4, "big") + b"ftyp" + b"isom\x00\x00\x00\x00"
    mdat = (8).to_bytes(4, "big") + b"mdat"
    path.write_bytes(ftyp + mdat + trailing)


def probe_document(
    *,
    codec: str = "h264",
    audio: str | None = "aac",
    width: int = 1280,
    height: int = 720,
    frame_rate: str = "30000/1001",
    duration: str = "12.5",
) -> bytes:
    streams: list[dict[str, object]] = [
        {
            "codec_type": "video",
            "codec_name": codec,
            "width": width,
            "height": height,
            "avg_frame_rate": frame_rate,
        }
    ]
    if audio is not None:
        streams.append({"codec_type": "audio", "codec_name": audio})
    return json.dumps(
        {
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": duration},
            "streams": streams,
        }
    ).encode()


class FakeRunner:
    def __init__(self, probes: list[bytes]) -> None:
        self.probes = probes
        self.calls: list[tuple[str, tuple[str, ...], float]] = []

    async def run(
        self, executable: str, arguments: tuple[str, ...], timeout: float
    ) -> CommandResult:
        self.calls.append((executable, arguments, timeout))
        if executable == "ffprobe-test":
            return CommandResult(0, self.probes.pop(0), b"")
        destination = Path(arguments[-1])
        if destination.suffix == ".mp4":
            write_mp4(destination)
        else:
            Image.new("RGB", (640, 360), (20, 100, 180)).save(destination, "WEBP")
        return CommandResult(0, b"", b"")


def test_iso_container_rejects_trailing_payload(tmp_path: Path) -> None:
    clean = tmp_path / "clean.mp4"
    write_mp4(clean)
    validate_video_magic(clean, "video/mp4")
    tainted = tmp_path / "tainted.mp4"
    write_mp4(tainted, b"payload")
    with pytest.raises(MediaValidationError) as captured:
        validate_video_magic(tainted, "video/mp4")
    assert captured.value.code == "video_container_trailing_or_truncated"


async def test_probe_rejects_video_over_frame_rate_limit(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    write_mp4(source)
    processor = VideoProcessor(settings(), FakeRunner([probe_document(frame_rate="31/1")]))
    with pytest.raises(MediaValidationError) as captured:
        await processor.probe(source, "video/mp4")
    assert captured.value.code == "video_limits_exceeded"


async def test_transcode_requests_h264_aac_and_creates_validated_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    rendition = tmp_path / "rendition.mp4"
    poster = tmp_path / "poster.webp"
    write_mp4(source)
    runner = FakeRunner(
        [
            probe_document(codec="hevc", audio="opus", width=1920, height=1080),
            probe_document(codec="h264", audio="aac", width=1280, height=720),
        ]
    )
    processed = await VideoProcessor(settings(), runner).transcode(
        source, rendition, poster, "video/mp4"
    )

    ffmpeg_calls = [
        arguments for executable, arguments, _ in runner.calls if executable == "ffmpeg-test"
    ]
    rendition_arguments = ffmpeg_calls[0]
    assert ("-c:v", "libx264") == (
        rendition_arguments[rendition_arguments.index("-c:v")],
        rendition_arguments[rendition_arguments.index("-c:v") + 1],
    )
    assert "aac" in rendition_arguments
    assert "-map_metadata" in rendition_arguments
    assert processed.rendition.video_codec == "h264"
    assert processed.rendition.audio_codec == "aac"
    assert processed.rendition.width == 1280
    assert processed.poster.mime == "image/webp"
    assert len(processed.original_sha256) == 64
    assert len(processed.poster.sha256) == 64


async def test_subprocess_runner_enforces_timeout_without_shell() -> None:
    runner = SubprocessCommandRunner()
    with pytest.raises(MediaToolError, match="timed out"):
        await runner.run(sys.executable, ("-c", "import time; time.sleep(2)"), 0.01)


async def test_durable_progress_never_moves_backwards() -> None:
    now = datetime.now(UTC)
    job = MediaJob(
        id=uuid4(),
        asset_id=uuid4(),
        status="running",
        attempts=1,
        phase="uploading",
        progress_percent=90,
        created_at=now,
        updated_at=now,
    )
    repository = MediaRepository(Mock(spec=AsyncSession))
    await repository.update_job_progress(job, phase="probing", progress_percent=10, now=now)
    assert job.phase == "probing"
    assert job.progress_percent == 90
