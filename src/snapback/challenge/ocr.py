"""Local OCR for the code on the paper: the shared intake reader, so one engine and one set of
byte and pixel caps serve both. Reply photos never leave this machine."""

from pathlib import Path

from snapback.agent.intake.ocr import OcrUnavailable, read_image

__all__ = ["OcrUnavailable", "read_text"]


def read_text(image_path: Path) -> str:
    """Every line of text the local OCR engine finds in the image, joined by newlines."""
    return read_image(Path(image_path).read_bytes())
