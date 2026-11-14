"""The PNG card for iMessage, and the Spanish string table."""

import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from snapback.card import render, strings
from snapback.card.render import (
    ICONS,
    REQUIRED_GLYPHS,
    WIDTH,
    drawable,
    qr_matrix,
    render_card,
    render_card_png,
    wrap,
)
from snapback.contracts import Card, CardRowKind, CardTone, ModuleEvidence, VerdictState
from snapback.verdict import build_card

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "contracts"
CHECKED_AT = datetime.fromisoformat("2026-11-13T21:42:00-05:00")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
BANNED_ES = ("estafa", "seguro", "verificado")


def hold_card() -> Card:
    return Card.model_validate_json((FIXTURES / "card_hold.json").read_text())


def evidence(name: str = "module_evidence_hold.json", **top_level) -> ModuleEvidence:
    data = json.loads((FIXTURES / name).read_text())
    return ModuleEvidence.model_validate(data | top_level)


def card_in(lang: str, name: str = "module_evidence_hold.json", **top_level) -> Card:
    return build_card(
        evidence(name, **top_level),
        checked_at=CHECKED_AT,
        verify_base_url="http://localhost:5173",
        lang=lang,
    )


def open_png(png: bytes) -> Image.Image:
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    return Image.open(io.BytesIO(png)).convert("RGB")


def read_qr_modules(
    image: Image.Image, box: tuple[int, int, int], modules: int
) -> list[list[bool]]:
    """Sample the centre of every QR module inside `box` (left, top, size)."""
    left, top, size = box
    step = size / modules
    return [
        [
            sum(image.getpixel((round(left + (col + 0.5) * step), round(top + (row + 0.5) * step))))
            < 384
            for col in range(modules)
        ]
        for row in range(modules)
    ]


# --- the tests named in the task -----------------------------------------------------------


def test_render_hold_fixture_png_size_and_qr_decodes():
    card = hold_card()
    rendered = render_card(card)
    image = open_png(rendered.png)

    assert image.width == WIDTH == 1080
    assert 700 <= image.height <= 2400
    assert len(rendered.png) < 400_000  # small enough to send in a message

    # The QR on the card is the QR for the verify link, module for module.
    expected = qr_matrix(card.verify_url)
    assert read_qr_modules(image, rendered.qr_box, len(expected)) == expected

    # And a real decoder reads the link back out of the picture, where one is installed
    # (OpenCV comes with the intake extra, which CI installs).
    try:
        import cv2
        import numpy as np
    except ImportError:
        return
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.asarray(image))
    assert decoded == card.verify_url == "http://localhost:5173/c/7Q2M"


def test_es_table_has_every_en_key():
    en, es = strings.TABLES["en"], strings.TABLES["es"]
    assert set(es) == set(en)
    for key in en:
        assert es[key].strip(), key
        # The same blanks to fill in, so a Spanish line can never drop a fact.
        assert set(PLACEHOLDER.findall(es[key])) == set(PLACEHOLDER.findall(en[key])), key


def test_no_banned_words_es():
    for key, text in strings.TABLES["es"].items():
        for banned in BANNED_ES:
            assert banned not in text.lower(), f"es:{key} contains {banned!r}"


# --- the picture ---------------------------------------------------------------------------


def test_png_bytes_and_layout_agree():
    card = hold_card()
    assert render_card_png(card) == render_card(card).png


def test_rendering_is_deterministic():
    assert render_card_png(hold_card()) == render_card_png(hold_card())


def test_every_tone_has_an_icon_and_a_word_in_both_languages():
    # Tone is never colour alone: each one has its own drawn icon and its own words.
    assert set(ICONS) == set(CardTone)
    for lang in ("en", "es"):
        words = [strings.text(f"tone.{tone.value}", lang) for tone in CardTone]
        assert len(set(words)) == len(CardTone)


LOCKED_ROW_STATES = {"Matches", "Doesn't match", "Not confirmed", "Warning", "Not checked"}
LOCKED_HEADLINES = {
    VerdictState.HOLD: "Hold off for now",
    VerdictState.DONT_PAY: "Don't pay. Something here doesn't match.",
    VerdictState.VERIFIED: "Checks passed. Still follow the two rules.",
}
BEFORE_THE_LOCK = ("Held up", "On hold", "Not shown", "Checks held up", "could not verify")


def test_row_states_and_headlines_use_the_locked_wording():
    # Decisions Fri 22:40, XO review of #59. These words are not to be reworded.
    for state, words in LOCKED_HEADLINES.items():
        assert strings.text(f"state.{state.value}") == words
    said = {strings.tone_word(tone.value, row.value) for tone in CardTone for row in CardRowKind}
    assert said == LOCKED_ROW_STATES
    for key, words in strings.TABLES["en"].items():
        if key.startswith(("tone.", "state.")):
            assert not any(old in words for old in BEFORE_THE_LOCK), key
            assert words != "Red flag" and words != "Hold", key


@pytest.mark.parametrize(
    ("tone", "row", "word"),
    [
        (CardTone.OK, CardRowKind.PLACE, "Matches"),
        (CardTone.OK, CardRowKind.PRICE, "Matches"),
        (CardTone.NOT_SHOWN, CardRowKind.PERSON, "Not confirmed"),
        (CardTone.NOT_CHECKED, CardRowKind.PRICE, "Not checked"),
        # A red flag that contradicts the listing, against one that is a risky ask.
        (CardTone.RED_FLAG, CardRowKind.PLACE, "Doesn't match"),
        (CardTone.RED_FLAG, CardRowKind.PERSON, "Doesn't match"),
        (CardTone.RED_FLAG, CardRowKind.PRICE, "Warning"),
        # No reply yet is nobody's fault: it is not confirmed, and it is not a warning.
        (CardTone.HOLD, CardRowKind.PERSON, "Not confirmed"),
        (CardTone.HOLD, CardRowKind.PRICE, "Warning"),
        (CardTone.HOLD, CardRowKind.PLACE, "Warning"),
    ],
)
def test_the_row_state_follows_the_tone_and_for_two_tones_the_row(tone, row, word):
    assert strings.tone_word(tone.value, row.value) == word


def test_spanish_has_a_row_state_for_everything_english_does():
    for tone in CardTone:
        for row in CardRowKind:
            english = strings.tone_word(tone.value, row.value, "en")
            spanish = strings.tone_word(tone.value, row.value, "es")
            assert spanish and spanish != english
    same_in_english = {(t, r) for t in CardTone for r in CardRowKind}
    for first in same_in_english:
        for second in same_in_english:
            if strings.tone_word(first[0].value, first[1].value) == strings.tone_word(
                second[0].value, second[1].value
            ):
                assert strings.tone_word(first[0].value, first[1].value, "es") == (
                    strings.tone_word(second[0].value, second[1].value, "es")
                )


def test_waiting_for_a_reply_is_never_labelled_a_mismatch_or_a_warning():
    raw = json.loads((FIXTURES / "module_evidence_hold.json").read_text())
    waiting = evidence(challenge=raw["challenge"] | {"presence": "waiting"})
    card = build_card(waiting, checked_at=CHECKED_AT)
    person = next(row for row in card.rows if row.kind is CardRowKind.PERSON)
    here_now = person.lines[0]
    assert here_now.tone is CardTone.HOLD
    assert strings.tone_word(here_now.tone.value, person.kind.value) == "Not confirmed"


def test_the_card_time_names_its_zone():
    from snapback.card.render import _stamp

    assert _stamp(CHECKED_AT) == "2026-11-13 21:42 UTC-05:00"
    houston = CHECKED_AT.astimezone(ZoneInfo("America/Chicago"))
    assert _stamp(houston) == "2026-11-13 20:42 CST"


def test_every_state_has_words_in_both_languages():
    for lang in ("en", "es"):
        for state in VerdictState:
            assert strings.text(f"state.{state.value}", lang)


def test_a_card_without_a_verify_link_has_no_qr():
    card = hold_card().model_copy(update={"verify_url": None})
    rendered = render_card(card)
    assert rendered.qr_box is None
    assert open_png(rendered.png).height < open_png(render_card_png(hold_card())).height


def test_a_longer_card_is_a_taller_picture():
    short = open_png(render_card_png(card_in("en", rules=[])))
    long_rules = [
        {"rule_id": rule_id, "category": category, "red_flag": True}
        for rule_id, category in [
            ("payment.zelle_before_viewing", "payment_method"),
            ("payment.gift_card", "payment_method"),
            ("fee.holding_deposit_before_viewing", "fee_ask"),
            ("data.ssn_before_viewing", "data_ask"),
            ("pressure.cannot_show", "pressure"),
        ]
    ]
    tall = open_png(render_card_png(card_in("en", rules=long_rules)))
    assert tall.height > short.height
    assert tall.width == short.width == WIDTH


def test_text_is_wrapped_to_the_width_it_is_given():
    from PIL import ImageDraw, ImageFont

    font = ImageFont.load_default(size=30)
    pen = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    text = "Someone with access to a 2 bed / 2 bath unit here sent these just now " * 3
    lines = wrap(pen, text, font, 600)
    assert len(lines) > 3
    assert all(pen.textlength(line, font=font) <= 600 for line in lines)
    assert " ".join(lines) == " ".join(text.split())


@pytest.mark.parametrize("name", ["module_evidence_hold.json", "module_evidence_forged.json"])
@pytest.mark.parametrize("lang", ["en", "es"])
def test_cards_for_both_fixtures_render_in_both_languages(name, lang):
    image = open_png(render_card_png(card_in(lang, name)))
    assert image.width == WIDTH


# --- Spanish -------------------------------------------------------------------------------


def test_a_spanish_card_is_in_spanish_and_has_the_same_shape():
    en, es = card_in("en"), card_in("es")
    assert es.lang == "es"
    assert es.state is en.state
    assert [(r.kind, [line.tone for line in r.lines]) for r in es.rows] == [
        (r.kind, [line.tone for line in r.lines]) for r in en.rows
    ]
    assert es.rows[0].lines[0].text == (
        "Tomadas en este edificio, en el plano de 2 bed / 2 bath (3 de 3 fotos)."
    )
    assert es.rows[2].lines[0].text == "Zelle antes de una visita. Señal de alerta."
    assert render_card_png(es) != render_card_png(en)


@pytest.mark.parametrize(
    "top_level",
    [
        {},
        {"challenge": None, "recapture": [], "memory": []},
        {"authority": {"status": "matches_record", "manager_on_record": "Fixture Living LLC"}},
        {"authority": {"status": "mismatch"}},
        {"locate": None},
        {"price": {"status": "below_range", "listed_rent": 900}},
    ],
)
def test_spanish_lines_carry_their_tone_in_words_too(top_level):
    for row in card_in("es", **top_level).rows:
        for line in row.lines:
            if line.tone is CardTone.RED_FLAG:
                assert line.text.endswith("Señal de alerta."), line.text
            else:
                assert "señal de alerta" not in line.text.lower(), line.text
            if line.tone is CardTone.NOT_SHOWN:
                assert line.text.startswith(("NO DEMOSTRADO.", "Sin confirmar.")), line.text
            if line.tone is CardTone.NOT_CHECKED:
                assert line.text.startswith("No comprobado"), line.text


def test_no_letter_is_ever_drawn_as_a_missing_glyph_box():
    # Whatever font is in use, what gets drawn is something that font has.
    font = render._font(30)
    for text in ("Aquí ahora", "Señal de alerta", "¿Qué?", "identificación", REQUIRED_GLYPHS):
        assert not any(render._lacks(font, char) for char in drawable(text) if not char.isspace())


def test_without_a_font_that_has_accents_they_are_dropped_not_boxed(monkeypatch):
    for cached in (render.font_path, render._font, render._drawable_char):
        cached.cache_clear()
    monkeypatch.setattr(render, "FONT_CANDIDATES", ())
    monkeypatch.delenv("SNAPBACK_CARD_FONT", raising=False)
    try:
        assert render.font_path() is None  # Pillow's built-in font, which has no accents
        assert drawable("Señal de alerta") == "Senal de alerta"
        assert drawable("Aquí ahora") == "Aqui ahora"
        assert drawable("¿Qué?") == "Que?"
        assert drawable("Zelle before a viewing.") == "Zelle before a viewing."
        open_png(render_card_png(card_in("es")))  # still renders
    finally:
        for cached in (render.font_path, render._font, render._drawable_char):
            cached.cache_clear()


def test_an_unknown_language_falls_back_to_english():
    assert card_in("fr").rows == card_in("en").rows
