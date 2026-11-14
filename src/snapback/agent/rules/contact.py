"""Contact on record (A7, issue #67). This first part is the one thing lanes A and D share:
how a phone number is hashed, so that the listing's number can be compared with the leasing
office's without either one being kept.

Lane D calls `phone_hash(number, phone_salt())` when it reads the record and stores the result
in `PropertyRecord.site_phone_hash`. Lane A hashes the numbers in the listing the same way and
compares. The digits never reach evidence, a card, a trace or a log.
"""

import hashlib
import hmac
import secrets

from snapback.contracts import DataSource
from snapback.settings import Settings, get_settings

# Synthetic, for fixtures and tests. A live run uses SNAPBACK_PHONE_SALT, or a salt made for
# this process and kept nowhere.
FIXTURE_PHONE_SALT = "fx-phone-salt"
_PROCESS_SALT = secrets.token_hex(16)


def phone_salt(settings: Settings | None = None) -> str:
    """The salt both lanes hash phones with.

    With no SNAPBACK_PHONE_SALT set, a live run gets a salt that lasts as long as the process,
    so the record must be hashed in the process that runs the check. To keep hashes on disk,
    a human sets SNAPBACK_PHONE_SALT.
    """
    settings = settings or get_settings()
    if settings.snapback_phone_salt is not None:
        return settings.snapback_phone_salt.get_secret_value()
    if settings.snapback_data_source is DataSource.FIXTURE:
        return FIXTURE_PHONE_SALT
    return _PROCESS_SALT


def phone_hash(number: str, salt: str) -> str | None:
    """A keyed hash of a ten-digit phone number, or None if `number` is not one.

    HMAC-SHA256 over the digits (a leading 1 is dropped), so the same number written two ways
    gives one hash, and the hash cannot be turned back into the number without the salt.
    """
    digits = "".join(ch for ch in number[:64] if ch in "0123456789")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return hmac.new(salt.encode(), digits.encode(), hashlib.sha256).hexdigest()
