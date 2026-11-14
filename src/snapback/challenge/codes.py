"""Fresh 4-character codes the poster writes on paper and holds up at the spot."""

import random
import re
import secrets

# No 0/O, 1/I/L, 5/S or 8/B: handwriting and OCR mix those up.
CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY234679"
CODE_LENGTH = 4

_NOT_ALNUM = re.compile(r"[^A-Z0-9]")


def new_code(rng: random.Random | None = None) -> str:
    """A fresh code. Pass a seeded `rng` only in tests; production uses `secrets`."""
    pick = rng.choice if rng is not None else secrets.choice
    return "".join(pick(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def compare(code: str, ocr_text: str) -> tuple[bool, bool]:
    """(code was read, other text was on the paper). Case, spaces and punctuation are ignored."""
    seen = _NOT_ALNUM.sub("", ocr_text.upper())
    if code not in seen:
        return False, bool(seen)
    return True, bool(seen.replace(code, "", 1))
