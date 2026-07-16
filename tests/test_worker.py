"""Worker actor discovery and broker registration tests."""

from pytest import MonkeyPatch


def test_all_actors_share_one_redis_broker(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ACKB_DATABASE_URL", "postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb"
    )
    monkeypatch.setenv("ACKB_ENVIRONMENT", "test")
    from arduino_component_kb.broker import broker
    from arduino_component_kb.worker import (
        process_import,
        process_media_image,
        process_media_video,
    )

    assert process_import.broker is broker
    assert process_media_image.broker is broker
    assert process_media_video.broker is broker
    queue_names = {
        process_import.queue_name,
        process_media_image.queue_name,
        process_media_video.queue_name,
    }
    assert queue_names == {
        "imports",
        "images",
        "videos",
    }
