from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

_MAX_IMAGE_DECODE_SIDE = 8_192
_MAX_IMAGE_DECODE_FRAMES = 20
_MAX_IMAGE_DECODE_PIXELS = 20_000_000


@dataclass(frozen=True, slots=True)
class ImageMetadata:
    width: int
    height: int
    frame_count: int


def inspect_image_bytes(payload: bytes, mime_type: str) -> ImageMetadata:
    """Validate the complete image without rewriting the immutable asset bytes."""
    formats = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
    expected = formats.get(mime_type)
    if expected is None:
        raise ValueError("unsupported_image")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload), formats=[expected]) as image:
                image.verify()
            with Image.open(io.BytesIO(payload), formats=[expected]) as image:
                width, height = image.size
                frames = int(getattr(image, "n_frames", 1))
                if (
                    width <= 0
                    or height <= 0
                    or max(width, height) > _MAX_IMAGE_DECODE_SIDE
                    or frames < 1
                    or frames > _MAX_IMAGE_DECODE_FRAMES
                    or width * height * frames > _MAX_IMAGE_DECODE_PIXELS
                ):
                    raise ValueError("image_resource_limit")
                orientation = image.getexif().get(274, 1)
                if orientation not in range(1, 9):
                    raise ValueError("image_orientation_invalid")
                for index in range(frames):
                    image.seek(index)
                    if image.width * image.height > _MAX_IMAGE_DECODE_PIXELS // frames:
                        raise ValueError("image_resource_limit")
                    image.load()
                if orientation in {5, 6, 7, 8}:
                    width, height = height, width
                return ImageMetadata(width=width, height=height, frame_count=frames)
    except (
        OSError,
        EOFError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("image_decode_failed") from exc
