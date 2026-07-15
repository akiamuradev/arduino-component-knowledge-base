"""Strict image validation, safe re-encoding, and perceptual hashing."""

from __future__ import annotations

import hashlib
import math
import statistics
import warnings
from collections.abc import Sequence
from io import BytesIO
from typing import cast

from PIL import Image, ImageOps, UnidentifiedImageError

from arduino_component_kb.media.domain import (
    ALLOWED_IMAGE_MIMES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIDE,
    VARIANT_WIDTHS,
    MediaValidationError,
    ProcessedImage,
    VariantData,
)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


def detect_magic(data: bytes) -> str:
    """Detect an allowlisted container and reject bytes after its logical end."""
    if data.startswith(b"\xff\xd8\xff"):
        _validate_jpeg_end(data)
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        _validate_png_end(data)
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        declared_length = int.from_bytes(data[4:8], "little") + 8
        if declared_length != len(data):
            raise MediaValidationError("image_container_trailing_or_truncated")
        return "image/webp"
    raise MediaValidationError("image_magic_not_allowed")


def _validate_jpeg_end(data: bytes) -> None:
    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            raise MediaValidationError("image_container_trailing_or_truncated")
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise MediaValidationError("image_container_trailing_or_truncated")
        marker = data[offset]
        offset += 1
        if marker == 0xD9:
            if offset != len(data):
                raise MediaValidationError("image_container_trailing_or_truncated")
            return
        if marker == 0x00 or marker == 0xD8:
            raise MediaValidationError("image_container_trailing_or_truncated")
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            raise MediaValidationError("image_container_trailing_or_truncated")
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            raise MediaValidationError("image_container_trailing_or_truncated")
        offset += segment_length
        if marker != 0xDA:
            continue
        while offset < len(data):
            marker_start = data.find(b"\xff", offset)
            if marker_start < 0 or marker_start + 1 >= len(data):
                raise MediaValidationError("image_container_trailing_or_truncated")
            marker = data[marker_start + 1]
            if marker == 0x00 or marker == 0xFF or 0xD0 <= marker <= 0xD7:
                offset = marker_start + 2
                continue
            offset = marker_start
            break
    raise MediaValidationError("image_container_trailing_or_truncated")


def _validate_png_end(data: bytes) -> None:
    offset = 8
    found_end = False
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise MediaValidationError("image_container_trailing_or_truncated")
        chunk_type = data[offset + 4 : offset + 8]
        offset = chunk_end
        if chunk_type == b"IEND":
            found_end = length == 0 and offset == len(data)
            break
    if not found_end:
        raise MediaValidationError("image_container_trailing_or_truncated")


def process_image(data: bytes, declared_mime: str) -> ProcessedImage:
    """Validate an original and create metadata-free bounded WebP variants."""
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise MediaValidationError("image_size_not_allowed")
    if declared_mime not in ALLOWED_IMAGE_MIMES:
        raise MediaValidationError("image_declared_mime_not_allowed")
    detected_mime = detect_magic(data)
    if detected_mime != declared_mime:
        raise MediaValidationError("image_mime_mismatch")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                image_format = probe.format
                if getattr(probe, "n_frames", 1) != 1:
                    raise MediaValidationError("animated_image_not_allowed")
                _validate_dimensions(*probe.size)
                probe.verify()
            with Image.open(BytesIO(data)) as decoded:
                normalized = ImageOps.exif_transpose(decoded)
                normalized.load()
                _validate_dimensions(*normalized.size)
                safe_image = normalized.convert("RGBA" if "A" in normalized.getbands() else "RGB")
    except MediaValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise MediaValidationError("image_dimensions_not_allowed") from None
    except (OSError, UnidentifiedImageError, ValueError):
        raise MediaValidationError("image_decode_failed") from None

    if _FORMAT_MIME.get(image_format or "") != detected_mime:
        raise MediaValidationError("image_format_mismatch")
    variants = tuple(_variant(safe_image, width) for width in VARIANT_WIDTHS)
    return ProcessedImage(
        detected_mime=detected_mime,
        width=safe_image.width,
        height=safe_image.height,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        phash=perceptual_hash(safe_image),
        variants=variants,
    )


def _validate_dimensions(width: int, height: int) -> None:
    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_SIDE
        or height > MAX_IMAGE_SIDE
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise MediaValidationError("image_dimensions_not_allowed")


def _variant(image: Image.Image, target_width: int) -> VariantData:
    width = min(target_width, image.width)
    height = max(1, round(image.height * width / image.width))
    resized = (
        image.resize((width, height), Image.Resampling.LANCZOS)
        if image.size != (width, height)
        else image.copy()
    )
    output = BytesIO()
    resized.save(output, format="WEBP", quality=85, method=6, exif=b"")
    data = output.getvalue()
    return VariantData(
        name=f"{target_width}w",
        data=data,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def perceptual_hash(image: Image.Image) -> str:
    """Compute a conventional 64-bit pHash without a heavy numeric dependency."""
    pixels = list(
        cast(
            Sequence[int],
            image.convert("L").resize((32, 32), Image.Resampling.LANCZOS).get_flattened_data(),
        )
    )
    cosine = [
        [math.cos((2 * index + 1) * frequency * math.pi / 64) for index in range(32)]
        for frequency in range(8)
    ]
    coefficients: list[float] = []
    for vertical in range(8):
        for horizontal in range(8):
            value = 0.0
            for y in range(32):
                row_factor = cosine[vertical][y]
                for x in range(32):
                    value += pixels[y * 32 + x] * cosine[horizontal][x] * row_factor
            coefficients.append(value)
    median = statistics.median(coefficients[1:])
    bits = 0
    for coefficient in coefficients:
        bits = (bits << 1) | int(coefficient > median)
    return f"{bits:016x}"
