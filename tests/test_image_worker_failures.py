"""Observable image-worker failure contracts across both storage phases."""

from io import BytesIO
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.models import AuditEvent
from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import RetryableJobError
from arduino_component_kb.media.models import MediaAsset, MediaJob
from arduino_component_kb.media.processor import process_media_job
from arduino_component_kb.media.storage import MediaStorage


@pytest.mark.parametrize("phase", ["download", "upload"])
@pytest.mark.parametrize("terminal", [False, True])
async def test_storage_failure_preserves_retry_and_audit_contract(
    phase: str, terminal: bool
) -> None:
    job = MediaJob(
        id=uuid4(),
        status="queued",
        attempts=3 if terminal else 0,
        max_attempts=4,
        progress_percent=0,
    )
    asset = MediaAsset(
        id=uuid4(),
        owner_user_id=uuid4(),
        status="processing",
        bucket="quarantine",
        object_key="original",
        declared_mime="image/png",
    )
    session = Mock(spec=AsyncSession)
    session.begin.return_value = AsyncMock()
    row = Mock()
    row._tuple.return_value = (job, asset)
    result = Mock()
    result.one_or_none.return_value = row
    session.execute.return_value = result
    database = Mock(dispose=AsyncMock())
    database.sessions.return_value = AsyncMock()
    database.sessions.return_value.__aenter__.return_value = session
    storage = Mock(spec=MediaStorage)
    content = BytesIO()
    Image.new("RGB", (64, 64), "green").save(content, format="PNG")
    storage.download.return_value = content.getvalue()
    failure = OSError("storage unavailable")
    getattr(storage, phase).side_effect = failure
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )

    with patch("arduino_component_kb.media.processor.Database", return_value=database):
        with pytest.raises(OSError if terminal else RetryableJobError) as caught:
            await process_media_job(job.id, settings, storage)

    assert job.attempts == (4 if terminal else 1)
    assert job.status == ("failed" if terminal else "retrying")
    assert job.error_code == ("media_storage_failed" if terminal else "media_storage_transient")
    events = [
        call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], AuditEvent)
    ]
    if terminal:
        assert caught.value is failure
        assert asset.status == "rejected"
        assert asset.failure_code == "media_storage_failed"
        assert job.next_retry_at is None
        assert len(events) == 1
        assert events[0].action == "media.processing_failed"
        assert events[0].object_id == asset.id
    else:
        assert isinstance(caught.value, RetryableJobError)
        assert caught.value.delay_ms == 5000
        assert asset.status == "processing"
        assert job.next_retry_at is not None
        assert events == []
    database.dispose.assert_awaited_once()
