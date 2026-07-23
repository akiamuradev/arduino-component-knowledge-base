"""Media domain types and typed failures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_SIDE = 10_000
MAX_VIDEO_BYTES = 256 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 600.0
MAX_VIDEO_WIDTH = 1920
MAX_VIDEO_HEIGHT = 1080
MAX_VIDEO_FRAME_RATE = 30.0
MAX_COMPONENT_IMAGES = 12
MAX_COMPONENT_VIDEOS = 2
MAX_COMPONENT_ORIGINAL_BYTES = 600 * 1024 * 1024
VARIANT_WIDTHS = (320, 800, 1600)
ALLOWED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_VIDEO_MIMES = frozenset({"video/mp4", "video/quicktime", "video/webm"})


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    REJECTED = "rejected"


class MediaJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MediaError(Exception):
    """Base class for typed media failures."""


class MediaValidationError(MediaError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class MediaNotFoundError(MediaError):
    """Asset does not exist or is not visible to the actor."""


class MediaStateConflictError(MediaError):
    """Asset is not in the required state."""


class MediaRevisionConflictError(MediaError):
    """Attached component optimistic revision is stale."""


class MediaQuotaError(MediaError):
    """Per-user pending upload quota is exhausted."""

    def __init__(self, code: str = "media_pending_quota_exceeded") -> None:
        super().__init__(code)
        self.code = code


class RetryableJobError(MediaError):
    """Ask Dramatiq to redeliver after the durable backoff delay."""

    def __init__(self, delay_ms: int) -> None:
        super().__init__("retryable media job failure")
        self.delay_ms = delay_ms


@dataclass(frozen=True, slots=True)
class UploadReservation:
    asset_id: UUID
    bucket: str
    object_key: str
    declared_mime: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ComponentMediaUsage:
    images: int
    videos: int
    original_bytes: int


@dataclass(frozen=True, slots=True)
class ComponentMediaVariant:
    name: str
    mime: str
    width: int
    height: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ComponentMedia:
    asset_id: UUID
    kind: MediaKind
    purpose: str
    alt_text: str
    caption: str | None
    display_order: int
    is_primary: bool
    status: MediaStatus
    width: int | None
    height: int | None
    variants: tuple[ComponentMediaVariant, ...] = ()


@dataclass(frozen=True, slots=True)
class ComponentImageMutation:
    asset_id: UUID
    purpose: str
    alt_text: str
    caption: str | None


@dataclass(frozen=True, slots=True)
class VariantData:
    name: str
    data: bytes
    width: int
    height: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    detected_mime: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    phash: str
    variants: tuple[VariantData, ...]
