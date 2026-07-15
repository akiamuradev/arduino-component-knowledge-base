"""Image container validation, re-encoding, and hashing tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from arduino_component_kb.media.domain import MAX_IMAGE_BYTES, MediaValidationError
from arduino_component_kb.media.images import detect_magic, process_image


def image_bytes(
    image_format: str = "PNG", *, width: int = 640, height: int = 320, animated: bool = False
) -> bytes:
    output = BytesIO()
    first = Image.new("RGB", (width, height), (18, 91, 173))
    if animated:
        second = Image.new("RGB", (width, height), (173, 91, 18))
        first.save(output, image_format, save_all=True, append_images=[second], duration=100)
    else:
        first.save(output, image_format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "mime"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_magic_detection_accepts_only_supported_containers(image_format: str, mime: str) -> None:
    assert detect_magic(image_bytes(image_format)) == mime


def test_processing_creates_bounded_metadata_free_webp_variants_and_hashes() -> None:
    original = image_bytes(width=640, height=320)
    result = process_image(original, "image/png")

    assert result.detected_mime == "image/png"
    assert (result.width, result.height) == (640, 320)
    assert len(result.sha256) == 64
    assert len(result.phash) == 16
    assert [variant.name for variant in result.variants] == ["320w", "800w", "1600w"]
    assert [(variant.width, variant.height) for variant in result.variants] == [
        (320, 160),
        (640, 320),
        (640, 320),
    ]
    for variant in result.variants:
        assert detect_magic(variant.data) == "image/webp"
        assert len(variant.sha256) == 64
        with Image.open(BytesIO(variant.data)) as decoded:
            assert decoded.getexif() == {}


@pytest.mark.parametrize(
    ("data", "declared_mime", "code"),
    [
        (image_bytes() + b"payload", "image/png", "image_container_trailing_or_truncated"),
        (
            image_bytes("JPEG") + b"payload\xff\xd9",
            "image/jpeg",
            "image_container_trailing_or_truncated",
        ),
        (image_bytes(), "image/jpeg", "image_mime_mismatch"),
        (b"GIF89a", "image/png", "image_magic_not_allowed"),
    ],
)
def test_processing_rejects_untrusted_container_cases(
    data: bytes, declared_mime: str, code: str
) -> None:
    with pytest.raises(MediaValidationError) as captured:
        process_image(data, declared_mime)
    assert captured.value.code == code


def test_processing_rejects_an_oversized_upload_before_decode() -> None:
    with pytest.raises(MediaValidationError) as captured:
        process_image(b"x" * (MAX_IMAGE_BYTES + 1), "image/png")
    assert captured.value.code == "image_size_not_allowed"


def test_processing_rejects_animated_webp() -> None:
    with pytest.raises(MediaValidationError) as captured:
        process_image(image_bytes("WEBP", animated=True), "image/webp")
    assert captured.value.code == "animated_image_not_allowed"


def test_hashes_are_deterministic() -> None:
    original = image_bytes()
    first = process_image(original, "image/png")
    second = process_image(original, "image/png")
    assert first.sha256 == second.sha256
    assert first.phash == second.phash
