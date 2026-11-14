"""Local OCR for a renter's screenshot. Nothing leaves the machine.

The engine is RapidOCR on ONNX Runtime (Apache-2.0, models bundled in the wheel), installed
with the `intake` extra. It is imported on first use, so the rest of intake works without it.

Small text is where the engine drops the spaces between words, which would hide a word from
the rules. Screenshots are therefore enlarged before reading.
"""

import io
from functools import cache

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000
TARGET_WIDTH = 1800
MAX_SCALE = 3.0


class OcrUnavailable(RuntimeError):
    """No local OCR engine is installed."""


@cache
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise OcrUnavailable("local OCR needs the intake extra: uv sync --extra intake") from error
    return RapidOCR()


def read_image(image: bytes) -> str:
    """The text in an image, one line per line of text, top to bottom. Empty if none."""
    engine = _engine()
    import numpy as np
    from PIL import Image

    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("image is too large to read")
    picture = Image.open(io.BytesIO(image))
    if picture.width * picture.height > MAX_PIXELS:
        raise ValueError("image has too many pixels to read")
    picture = picture.convert("RGB")

    scale = min(MAX_SCALE, TARGET_WIDTH / picture.width)
    if scale > 1.2:
        size = (round(picture.width * scale), round(picture.height * scale))
        picture = picture.resize(size, Image.Resampling.LANCZOS)

    result, _ = engine(np.asarray(picture))
    return "\n".join(text for _, text, _ in result or [])
