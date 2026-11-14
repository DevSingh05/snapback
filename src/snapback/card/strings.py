"""Every word a renter reads on a card, and every reason a verdict gives.

Code refers to these by key and never writes prose of its own, so a language model cannot put
words on a card and a reviewer can read the product's whole wording in this one file.

Conventions (tests/test_card_rows.py enforces them):

- No entry contains "safe", "verified" or "scam". About a person we say what was or was not
  shown, never what they are.
- Tone is never carried by colour alone. A red-flag line ends with "Red flag.", a `not_shown`
  line starts with "NOT SHOWN." and a `not_checked` line starts with "Not checked".
- A rule that fires is worded under `rule.<rule_id>`. A rule id with no entry of its own falls
  back to `rule_category.<category>`, so a new rule can never put raw text on a card.
"""

DEFAULT_LANG = "en"

EN: dict[str, str] = {
    # --- line labels -----------------------------------------------------------------------
    "label.real": "Real",
    "label.here_now": "Here now",
    "label.allowed": "Allowed to rent it",
    "label.payment_ask": "Payment ask",
    "label.data_ask": "Data ask",
    "label.pressure": "Pressure",
    "label.rent_vs_record": "Rent vs record",
    "label.seen_before": "Seen before",
    # --- PLACE: were the photos taken here? ------------------------------------------------
    "place.located_plan": (
        "Taken in this building, in the {floor_plan} floor plan ({located} of {total} photos)."
    ),
    "place.located": "Taken in this building ({located} of {total} photos).",
    "place.elsewhere": "Taken in a different building ({elsewhere} of {total} photos). Red flag.",
    "place.not_located": "NOT SHOWN. These photos could not be placed in this building's 3D scan.",
    "place.not_indexed": "Not checked (we have no 3D scan of this building).",
    "place.no_photos": "Not checked (no listing photos were sent).",
    "place.seen_before_dated": "A listing photo also appeared in another check on {date}.",
    "place.seen_before": "A listing photo also appeared in another check.",
    # --- PERSON: is someone there now, and may they rent it? -------------------------------
    "here_now.proven_plan": (
        "Someone with access to a {floor_plan} unit here sent these just now "
        "({matched} of {total} spots, code read, {time})."
    ),
    "here_now.proven": (
        "Someone with access to a unit here sent these just now "
        "({matched} of {total} spots, code read, {time})."
    ),
    "here_now.proven_bare": "Someone with access to a unit here proved it just now.",
    "here_now.waiting": "No reply yet. An honest landlord may need time.",
    "here_now.retry": "The reply photo could not be accepted. Ask for a new photo at a new spot.",
    "here_now.not_requested": "Not checked (no one has been asked to prove they are inside yet).",
    "here_now.forged_copy": "The reply is a copy of listing photo {n}. Red flag.",
    "here_now.forged_copy_unknown": "The reply is a copy of one of the listing photos. Red flag.",
    "here_now.forged": "The reply was not a fresh photo taken in the unit. Red flag.",
    "here_now.seen_before_dated": "A reply photo also appeared in another check on {date}.",
    "here_now.seen_before": "A reply photo also appeared in another check.",
    "allowed.not_shown": "NOT SHOWN. Being inside does not mean they may rent it.",
    "allowed.matches": "The company they named matches the manager on record for this building.",
    "allowed.mismatch": (
        "The name they gave does not match the manager on record for this building. Red flag."
    ),
    # --- PRICE: what are they asking for, and does the rent fit? ---------------------------
    "payment.none": "No risky payment ask found in the text you sent.",
    "rule.payment.zelle_before_viewing": "Zelle before a viewing. Red flag.",
    "rule_category.payment_method": (
        "A payment that cannot be taken back, asked for before a viewing. Red flag."
    ),
    "rule_category.fee_ask": "A fee to a person before a viewing. Red flag.",
    "rule_category.data_ask": "Personal or bank details asked for before a viewing. Red flag.",
    "rule_category.pressure": "Pressure to decide fast. Red flag.",
    "rule_category.link": "A payment or lease link sent by the poster. Red flag.",
    "rent.not_checked": "Not checked (our data has no rent for this building).",
    "rent.within_range": "In line with the rents on record for this building.",
    "rent.below_range": "Below the rents on record for this building. Ask why; discounts happen.",
    # --- what no card ever checks, and the two lines under every card ----------------------
    "not_checked.id": "ID",
    "not_checked.lease": "lease",
    "not_checked.ownership": "ownership",
    "footer.two_rules": (
        "Two rules: never pay before a signed lease and a viewing; "
        "never pay by Zelle, wire or gift card."
    ),
    "footer.only_trust": (
        "Only trust a SNAPBACK result you asked for yourself. "
        "SNAPBACK never texts first or asks for money."
    ),
    # --- reasons a verdict gives (Verdict.reasons, Evidence.forgery_reason) ----------------
    "reason.forged": "The proof-of-presence reply was not a fresh photo taken in the unit.",
    "reason.forged_copy": "The reply is a copy of listing photo {n}.",
    "reason.forged_copy_unknown": "The reply is a copy of one of the listing photos.",
    "reason.photo_elsewhere": "At least one listing photo was taken in a different property.",
    "reason.authority_mismatch": "The poster does not match the contact on the property record.",
    "reason.price_flag": "The rent is far below comparable units.",
    "reason.payment_flag": "Payment was requested before any viewing.",
    "reason.not_indexed": (
        "This property has no 3D twin in our index, so the photos could not be checked."
    ),
    "reason.not_located": "The photos could not be located in this property's 3D twin.",
    "reason.located": "The photos were located in this property.",
    "reason.authority_matches": "The poster matches the contact on the property record.",
    "reason.authority_unknown": "We could not confirm who is allowed to rent this unit.",
    "reason.presence_proven": "A fresh photo proved someone was inside the unit.",
    "reason.presence_proven_not_authority": (
        "A fresh photo proved someone was inside the unit, which is not authority."
    ),
    "reason.presence_missing": "Nobody has proved they are inside the unit yet.",
}

TABLES: dict[str, dict[str, str]] = {DEFAULT_LANG: EN}


def _table(lang: str) -> dict[str, str]:
    return TABLES.get(lang, TABLES[DEFAULT_LANG])


def has(key: str, lang: str = DEFAULT_LANG) -> bool:
    return key in _table(lang)


def text(key: str, lang: str = DEFAULT_LANG, **values: object) -> str:
    """The wording for `key`, with `{placeholders}` filled in. A missing key is a bug: KeyError."""
    return _table(lang)[key].format(**values)
