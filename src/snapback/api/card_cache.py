"""A cache in front of the card picture (A12, issue #103).

Drawing a card takes real work, and `GET /cases/{id}/card.png` needs no secret, so without
this anyone could make the server draw the same picture over and over. Each distinct card is
drawn once and kept. "Distinct" is what the picture shows: a card stamped a few seconds later
within the same minute is the same picture.
"""

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable

from snapback.card import render
from snapback.card.render import render_card_png
from snapback.contracts import Card

DEFAULT_SIZE = 64  # pictures kept; each is about 150 KB


def _draw(card: Card) -> bytes:
    # Looked up at call time, so a test can swap the renderer.
    return render_card_png(card)


class CardPictures:
    def __init__(self, size: int = DEFAULT_SIZE, draw: Callable[[Card], bytes] = _draw) -> None:
        self._size = size
        self._draw = draw
        self._kept: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._kept)

    def etag(self, card: Card) -> str:
        """A short name for what this card's picture shows. Equal cards, equal names."""
        shown = card.model_copy(
            update={
                # The picture prints these to the minute.
                "checked_at": card.checked_at.replace(second=0, microsecond=0),
                "expires_at": card.expires_at.replace(second=0, microsecond=0),
            }
        )
        # The renderer's version is part of the name: a picture drawn by an older renderer
        # is a different picture, even of the same card.
        named = f"{render.RENDER_VERSION}\n{shown.model_dump_json()}"
        return hashlib.sha256(named.encode()).hexdigest()[:32]

    def png(self, card: Card) -> bytes:
        key = self.etag(card)
        with self._lock:
            if key in self._kept:
                self._kept.move_to_end(key)
                return self._kept[key]
        # Drawn outside the lock so one slow picture does not hold up the others. Two
        # requests for the same new card may both draw it; the second result is the same.
        drawn = self._draw(card)
        with self._lock:
            self._kept[key] = drawn
            self._kept.move_to_end(key)
            while len(self._kept) > self._size:
                self._kept.popitem(last=False)
        return drawn
