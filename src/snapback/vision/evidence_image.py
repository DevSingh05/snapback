"""J1 (#10): the evidence image. The ad photo on the left, the scan view it matched on the right,
the matched points joined across the two, and one caption line written by code.

Rendered on the fly from bytes the case holds in memory; nothing here reads or writes a file.
The caption carries only counts, the placement in words and LIVE or FIXTURE: never an id, an
address, a name or a phone number.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from snapback.contracts import DataSource, EvidencePoints, LocateStatus

WIDTH, HEIGHT = 1600, 680
BAR = 70  # caption bar height
GAP = 16
PANEL_W = (WIDTH - 3 * GAP) // 2
PANEL_H = HEIGHT - BAR - 2 * GAP
BG = (246, 245, 242)
INK = (29, 29, 27)
DOT = (31, 95, 174)
LINE = (31, 95, 174, 150)

_WORDS = {
    "en": {
        LocateStatus.LOCATED_IN_CLAIMED: "Taken in this building",
        LocateStatus.LOCATED_ELSEWHERE: "Taken in a different building",
        "flipped": "matched when flipped left to right",
        "points": "{n} matched points",
    },
    "es": {
        LocateStatus.LOCATED_IN_CLAIMED: "Tomada en este edificio",
        LocateStatus.LOCATED_ELSEWHERE: "Tomada en otro edificio",
        "flipped": "coincide al invertirla de izquierda a derecha",
        "points": "{n} puntos coincidentes",
    },
}
PLACED = (LocateStatus.LOCATED_IN_CLAIMED, LocateStatus.LOCATED_ELSEWHERE)


def caption(
    alias: str,
    status: LocateStatus,
    matched: int | None,
    flipped: bool | None,
    source: DataSource,
    lang: str = "en",
) -> str:
    """The one line under the image, from code: "P1 · Taken in this building · 312 matched
    points · LIVE". Only placed photos have an image."""
    if status not in PLACED:
        raise ValueError("only a placed photo has an evidence image")
    words = _WORDS.get(lang, _WORDS["en"])
    where = words[status]
    if flipped:
        where = f"{where} ({words['flipped']})"
    parts = [alias, where]
    if matched:
        parts.append(words["points"].format(n=matched))
    parts.append(source.value.upper())
    return " · ".join(parts)


def _fit(image: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    """The image scaled to fit a panel, and its top-left offset inside the panel."""
    image = image.convert("RGB")
    scale = min(PANEL_W / image.width, PANEL_H / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    fitted = image.resize(size, Image.Resampling.LANCZOS)
    return fitted, ((PANEL_W - size[0]) // 2, (PANEL_H - size[1]) // 2)


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(
    ad_photo: bytes,
    scan_view: bytes,
    points: EvidencePoints | None,
    line: str,
) -> bytes:
    """The evidence image as PNG bytes: ad photo left, scan view right, matched pairs joined."""
    with Image.open(io.BytesIO(ad_photo)) as a, Image.open(io.BytesIO(scan_view)) as b:
        left, (lx, ly) = _fit(a)
        right, (rx, ry) = _fit(b)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), BG)
    ox_left, ox_right, oy = GAP, 2 * GAP + PANEL_W, GAP
    canvas.paste(left, (ox_left + lx, oy + ly))
    canvas.paste(right, (ox_right + rx, oy + ry))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x, y, u, v in points.sampled if points else []:
        p = (ox_left + lx + x * left.width, oy + ly + y * left.height)
        q = (ox_right + rx + u * right.width, oy + ry + v * right.height)
        draw.line([p, q], fill=LINE, width=2)
        for cx, cy in (p, q):
            draw.ellipse(
                [cx - 6, cy - 6, cx + 6, cy + 6], fill=DOT + (255,), outline=(255, 255, 255, 255)
            )
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")

    text = ImageDraw.Draw(canvas)
    font = _font(28)
    bar_top = HEIGHT - BAR
    text.rectangle([0, bar_top, WIDTH, HEIGHT], fill=(255, 255, 255))
    text.text((GAP, bar_top + (BAR - 30) // 2), line, fill=INK, font=font)

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()
