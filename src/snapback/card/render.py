"""Draw a `Card` as a PNG, for iMessage.

The picture carries what the card carries and nothing else: the state, the case id and expiry,
the three rows, what was not checked, the two rules, and the verify link with its QR code.
Every word on it is either on the `Card` already or comes from `card/strings.py` in the card's
language.

Tone is never colour alone. Each line gets a drawn icon and its tone in words, and the line's
own text says it again.

Fonts: Pillow's built-in font has no accented letters, so a Spanish card drawn with it would
show boxes. The renderer therefore looks for a system font that covers them (set
`SNAPBACK_CARD_FONT` to choose one). If it finds none it still never draws a box: a letter the
font lacks is drawn without its accent.
"""

import io
import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cache

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_M

from snapback.card import strings
from snapback.contracts import Card, CardTone, DataSource, VerdictState

WIDTH = 1080
# Raise this whenever the drawing changes. It is part of each picture's cache key and ETag,
# so a picture drawn by an older renderer is never served or kept as "unchanged".
RENDER_VERSION = "2"
MARGIN = 56
CONTENT = WIDTH - 2 * MARGIN
ICON = 48
TEXT_LEFT = MARGIN + ICON + 24
CANVAS_HEIGHT = 6000
QR_MODULE = 10
QR_QUIET = 4

INK = (17, 24, 39)
MUTED = (88, 99, 115)
RULE = (214, 219, 226)
PAPER = (255, 255, 255)

TONE_COLOUR = {
    CardTone.OK: (15, 118, 110),
    CardTone.HOLD: (180, 83, 9),
    CardTone.RED_FLAG: (185, 28, 28),
    CardTone.NOT_SHOWN: (71, 85, 105),
    CardTone.NOT_CHECKED: (100, 116, 139),
}
STATE_COLOUR = {
    VerdictState.VERIFIED: (15, 118, 110),
    VerdictState.HOLD: (180, 83, 9),
    VerdictState.DONT_PAY: (185, 28, 28),
    VerdictState.UNVERIFIED: (29, 78, 216),
}

Pen = ImageDraw.ImageDraw
Colour = tuple[int, int, int]


@dataclass(frozen=True)
class RenderedCard:
    png: bytes
    width: int
    height: int
    qr_box: tuple[int, int, int] | None  # left, top and side of the QR modules, in pixels


FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
)
# What a card in English or Spanish needs beyond plain ASCII.
REQUIRED_GLYPHS = "áéíóúñüÁÉÍÓÚÑ¿¡·"


def _lacks(font: ImageFont.FreeTypeFont, char: str) -> bool:
    """True if `font` has no glyph for `char` (it would draw its "missing" box)."""
    return bytes(font.getmask(char)) == bytes(font.getmask("\uffff"))


@cache
def font_path() -> str | None:
    """The font file cards are drawn with, or None for Pillow's built-in font."""
    chosen = os.environ.get("SNAPBACK_CARD_FONT")
    for path in (chosen, *FONT_CANDIDATES):
        if not path or not os.path.exists(path):
            continue
        try:
            font = ImageFont.truetype(path, 30)
        except OSError:
            continue
        if not any(_lacks(font, char) for char in REQUIRED_GLYPHS):
            return path
    return None


@cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    path = font_path()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


@cache
def _drawable_char(char: str) -> str:
    if char.isascii() or not _lacks(_font(30), char):
        return char
    plain = unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode()
    return plain  # "ñ" becomes "n"; a sign with no plain form, like "¿", is dropped


def drawable(text: str) -> str:
    """`text` as the active font can draw it: accents are dropped only where it lacks them."""
    return "".join(_drawable_char(char) for char in text)


def wrap(pen: Pen, text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Break `text` into lines no wider than `max_width`. A word that is too long is split."""
    lines: list[str] = []
    current = ""
    for word in drawable(text).split():
        candidate = f"{current} {word}".strip()
        if pen.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = ""
        while pen.textlength(word, font=font) > max_width:
            cut = len(word)
            while cut > 1 and pen.textlength(word[:cut], font=font) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def qr_matrix(url: str) -> list[list[bool]]:
    """The QR code for `url` as rows of modules, without the quiet zone."""
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=1, border=0)
    code.add_data(url)
    code.make(fit=True)
    return [[bool(module) for module in row] for row in code.get_matrix()]


# --- icons: one per tone, drawn so the tone reads without colour -------------------------------


def _ring(pen: Pen, x: int, y: int, colour: Colour) -> None:
    pen.ellipse((x, y, x + ICON, y + ICON), outline=colour, width=4)


def _icon_ok(pen: Pen, x: int, y: int, colour: Colour) -> None:
    _ring(pen, x, y, colour)
    points = [(x + 13, y + 25), (x + 21, y + 33), (x + 36, y + 16)]
    pen.line(points, fill=colour, width=5, joint="curve")


def _icon_hold(pen: Pen, x: int, y: int, colour: Colour) -> None:
    _ring(pen, x, y, colour)
    pen.rectangle((x + 16, y + 14, x + 21, y + 34), fill=colour)
    pen.rectangle((x + 27, y + 14, x + 32, y + 34), fill=colour)


def _icon_red_flag(pen: Pen, x: int, y: int, colour: Colour) -> None:
    pen.polygon([(x + 24, y + 2), (x + 47, y + 45), (x + 1, y + 45)], outline=colour, width=4)
    pen.rectangle((x + 22, y + 17, x + 26, y + 31), fill=colour)
    pen.ellipse((x + 21, y + 35, x + 27, y + 41), fill=colour)


def _icon_not_shown(pen: Pen, x: int, y: int, colour: Colour) -> None:
    _ring(pen, x, y, colour)
    pen.text((x + ICON / 2, y + ICON / 2), "?", fill=colour, font=_font(32), anchor="mm")


def _icon_not_checked(pen: Pen, x: int, y: int, colour: Colour) -> None:
    for start in range(0, 360, 45):
        pen.arc((x, y, x + ICON, y + ICON), start, start + 26, fill=colour, width=4)
    pen.rectangle((x + 14, y + 22, x + 34, y + 26), fill=colour)


ICONS: dict[CardTone, Callable[[Pen, int, int, Colour], None]] = {
    CardTone.OK: _icon_ok,
    CardTone.HOLD: _icon_hold,
    CardTone.RED_FLAG: _icon_red_flag,
    CardTone.NOT_SHOWN: _icon_not_shown,
    CardTone.NOT_CHECKED: _icon_not_checked,
}


# --- the card ----------------------------------------------------------------------------------


def _paragraph(
    pen: Pen, text: str, size: int, colour: Colour, x: int, y: int, width: float, gap: int = 10
) -> int:
    """Draw wrapped text and return the y just below it."""
    font = _font(size)
    for line in wrap(pen, text, font, width):
        pen.text((x, y), line, fill=colour, font=font)
        y += size + gap
    return y


def _draw_qr(pen: Pen, url: str, left: int, top: int) -> tuple[int, int, int]:
    matrix = qr_matrix(url)
    origin_x = left + QR_QUIET * QR_MODULE
    origin_y = top + QR_QUIET * QR_MODULE
    for row_index, row in enumerate(matrix):
        for column, dark in enumerate(row):
            if dark:
                x = origin_x + column * QR_MODULE
                y = origin_y + row_index * QR_MODULE
                pen.rectangle((x, y, x + QR_MODULE - 1, y + QR_MODULE - 1), fill=(0, 0, 0))
    return origin_x, origin_y, len(matrix) * QR_MODULE


def _stamp(moment: datetime) -> str:
    """A time with the zone it is in, so a card read in another city is not misread."""
    zone = moment.tzname()
    return moment.strftime("%Y-%m-%d %H:%M") + (f" {zone}" if zone else "")


def render_card(card: Card) -> RenderedCard:
    lang = card.lang

    def say(key: str, **values: object) -> str:
        return strings.text(key, lang, **values)

    canvas = Image.new("RGB", (WIDTH, CANVAS_HEIGHT), PAPER)
    pen = ImageDraw.Draw(canvas)
    y = MARGIN

    # Header: the name, and whether this is live or fixture data.
    pen.text((MARGIN, y), "SNAPBACK", fill=INK, font=_font(44))
    source_key = "card.source.live" if card.source is DataSource.LIVE else "card.source.fixture"
    source = drawable(say(source_key))
    chip_width = pen.textlength(source, font=_font(24)) + 32
    chip = (WIDTH - MARGIN - chip_width, y + 4, WIDTH - MARGIN, y + 44)
    pen.rounded_rectangle(chip, radius=20, outline=INK, width=3)
    pen.text((chip[0] + 16, y + 11), source, fill=INK, font=_font(24))
    y += 76

    # The state, in words on a solid band.
    state_colour = STATE_COLOUR[card.state]
    state_lines = wrap(pen, say(f"state.{card.state.value}"), _font(50), CONTENT - 64)
    band_height = 40 + len(state_lines) * 62
    pen.rounded_rectangle(
        (MARGIN, y, WIDTH - MARGIN, y + band_height), radius=24, fill=state_colour
    )
    text_y = y + 22
    for text in state_lines:
        pen.text((MARGIN + 32, text_y), text, fill=PAPER, font=_font(50))
        text_y += 62
    y += band_height + 24

    # Case id and how long the card stands.
    meta = "   ·   ".join(
        [
            say("card.case", case_id=card.case_id),
            say("card.checked", time=_stamp(card.checked_at)),
            say("card.expires", time=_stamp(card.expires_at.astimezone(card.checked_at.tzinfo))),
        ]
    )
    y = _paragraph(pen, meta, 26, MUTED, MARGIN, y, CONTENT) + 14

    # The three rows.
    for row in card.rows:
        pen.line((MARGIN, y, WIDTH - MARGIN, y), fill=RULE, width=2)
        y += 22
        pen.text((MARGIN, y), drawable(say(f"row.{row.kind.value}")), fill=MUTED, font=_font(26))
        y += 46
        for item in row.lines:
            colour = TONE_COLOUR[item.tone]
            ICONS[item.tone](pen, MARGIN, y, colour)
            label = drawable(item.label)
            pen.text((TEXT_LEFT, y - 2), label, fill=INK, font=_font(34))
            tone_x = TEXT_LEFT + pen.textlength(label, font=_font(34)) + 20
            word = strings.tone_word(item.tone.value, row.kind.value, lang)
            tone_word = drawable(word.upper())
            pen.text((tone_x, y + 8), tone_word, fill=colour, font=_font(22))
            y = _paragraph(pen, item.text, 28, INK, TEXT_LEFT, y + 46, WIDTH - MARGIN - TEXT_LEFT)
            y += 20
        y += 4

    # What no card checks, and the two rules.
    pen.line((MARGIN, y, WIDTH - MARGIN, y), fill=RULE, width=2)
    y += 24
    not_checked = say("card.not_checked", items=", ".join(card.not_checked))
    y = _paragraph(pen, not_checked, 28, INK, MARGIN, y, CONTENT) + 14
    for footer in card.footer:
        y = _paragraph(pen, footer, 24, MUTED, MARGIN, y, CONTENT, gap=8) + 10

    # The verify link and its QR code.
    qr_box = None
    if card.verify_url:
        y += 10
        pen.line((MARGIN, y, WIDTH - MARGIN, y), fill=RULE, width=2)
        y += 24
        qr_box = _draw_qr(pen, card.verify_url, MARGIN, y)
        side = qr_box[2] + 2 * QR_QUIET * QR_MODULE
        text_x = MARGIN + side + 28
        text_y = _paragraph(
            pen, say("card.verify"), 28, INK, text_x, y + 36, WIDTH - MARGIN - text_x
        )
        _paragraph(pen, card.verify_url, 26, MUTED, text_x, text_y + 6, WIDTH - MARGIN - text_x)
        y += side

    height = y + MARGIN
    picture = canvas.crop((0, 0, WIDTH, height))
    out = io.BytesIO()
    picture.save(out, format="PNG", optimize=True)
    return RenderedCard(png=out.getvalue(), width=WIDTH, height=height, qr_box=qr_box)


def render_card_png(card: Card) -> bytes:
    """The card as PNG bytes."""
    return render_card(card).png
