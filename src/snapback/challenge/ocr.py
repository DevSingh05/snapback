"""Local OCR for the code on the paper. Runs on our machine; reply photos never leave it.

Uses RapidOCR (Apache-2.0, ONNX runtime) when installed. It is optional so `make setup` stays
light: `uv add rapidocr-onnxruntime` on the machine that runs live challenges.
"""

from pathlib import Path


class OcrUnavailableError(RuntimeError):
    pass


def read_text(image_path: Path) -> str:
    """Every line of text RapidOCR finds in the image, joined by newlines."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError as err:
        raise OcrUnavailableError(
            "Local OCR is not installed. Run `uv add rapidocr-onnxruntime` (Apache-2.0)."
        ) from err
    result, _ = RapidOCR()(str(image_path))
    return "\n".join(line[1] for line in result or [])
