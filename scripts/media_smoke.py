"""Dependency-isolated smoke test for the image safety pipeline."""

from __future__ import annotations

from io import BytesIO

from PIL import Image

from arduino_component_kb.media.images import detect_magic, process_image


def main() -> int:
    source = BytesIO()
    Image.new("RGB", (640, 360), (20, 100, 180)).save(source, "PNG")
    processed = process_image(source.getvalue(), "image/png")
    assert len(processed.sha256) == 64
    assert len(processed.phash) == 16
    assert [variant.name for variant in processed.variants] == ["320w", "800w", "1600w"]
    assert all(detect_magic(variant.data) == "image/webp" for variant in processed.variants)
    assert max(variant.width for variant in processed.variants) == 640
    print("Media image pipeline smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
