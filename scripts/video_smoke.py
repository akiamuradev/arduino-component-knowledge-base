"""Real local FFmpeg smoke for H.264/AAC rendition and WebP poster."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import SecretStr

from arduino_component_kb.config import Settings
from arduino_component_kb.media.videos import SubprocessCommandRunner, VideoProcessor


async def smoke() -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
        auth_throttle_pepper=SecretStr("x" * 32),
        redis_url="redis://127.0.0.1:6379/15",
        minio_endpoint="127.0.0.1:9000",
        minio_access_key=SecretStr("test-access"),
        minio_secret_key=SecretStr("test-secret-placeholder"),
        minio_secure=False,
        ffmpeg_path=os.environ.get("ACKB_FFMPEG_PATH", "ffmpeg"),
        ffprobe_path=os.environ.get("ACKB_FFPROBE_PATH", "ffprobe"),
        ffprobe_timeout_seconds=30,
        ffmpeg_timeout_seconds=120,
    )
    runner = SubprocessCommandRunner()
    with TemporaryDirectory(prefix="ackb-video-smoke-") as directory:
        root = Path(directory)
        original = root / "original.mp4"
        rendition = root / "rendition.mp4"
        poster = root / "poster.webp"
        generated = await runner.run(
            settings.ffmpeg_path,
            (
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=24",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "2",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-y",
                str(original),
            ),
            120,
        )
        if generated.returncode != 0:
            raise RuntimeError("FFmpeg smoke fixture generation failed")
        processed = await VideoProcessor(settings, runner).transcode(
            original, rendition, poster, "video/mp4"
        )
        assert processed.rendition.video_codec == "h264"
        assert processed.rendition.audio_codec == "aac"
        assert processed.rendition.width <= 1280
        assert processed.rendition.height <= 720
        assert processed.rendition.frame_rate is not None
        assert processed.rendition.frame_rate <= 30
        assert processed.poster.mime == "image/webp"
        assert processed.poster.size_bytes > 0


def main() -> int:
    asyncio.run(smoke())
    print("Real FFmpeg video smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
