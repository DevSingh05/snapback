"""The rules, as data.

Each rule is a stable id, a category, whether it is a red flag, and the phrasings that count as
the ask. `apply.py` reads this table; nothing here runs. The wording a renter sees for a rule
lives in `snapback.card.strings` under `rule.<rule_id>`, never here.

How to read a rule:

- `patterns`: regular expressions, matched without regard to case against one sentence of the
  renter's own text. Any one of them is enough.
- `excused_after_viewing`: the ask is ordinary once the renter has toured the unit or signed the
  lease, so a sentence that puts it after one of those does not fire. Rules without this fire
  whenever they match: nobody legitimate takes gift cards at any stage.
- `excused_when_refused`: a clause in which the writer says they never ask for or accept the
  thing ("we never ask for payment by Zelle"), or warns the renter off it ("never pay by
  Zelle"), is a warning, not an ask. The refusal has to come before the thing, in its clause.
- `excused_as_rent_terms`: a clause that describes how tenants pay rent ("tenants can pay rent
  by Venmo or Zelle") and asks for nothing now is not an ask either.
- `needs_link`: the sentence must also contain a web link.
- `red_flag`: shown on the card as a red flag. Rules that are not red flags are recorded for the
  agent's trace only, because honest listings use the same words ("won't last").

Every rule here needs at least one firing fixture in `fixtures/rules/cases.json`, and every
red-flag rule needs its own card string. Tests enforce both.
"""

from dataclasses import dataclass

from snapback.contracts import RuleCategory

# Asked rent is "below range" when it is under this share of the lowest rent on record (or of
# the median, when the record has no minimum). Concessions happen, so a modest discount passes.
BELOW_RANGE_RATIO = 0.75


@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: RuleCategory
    red_flag: bool
    patterns: tuple[str, ...]
    excused_after_viewing: bool = False
    excused_when_refused: bool = False
    excused_as_rent_terms: bool = False
    needs_link: bool = False


RULES: tuple[Rule, ...] = (
    # --- payment method: money that cannot be taken back ----------------------------------
    Rule(
        rule_id="payment.zelle_before_viewing",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(r"\bzelle\b",),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_as_rent_terms=True,
    ),
    Rule(
        rule_id="payment.wire_before_viewing",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(
            r"\bwire (?:the|me|it|a|your|\$|transfer|payment|money|deposit|funds)",
            r"\b(?:by|bank) wire\b",
            r"\bwestern union\b",
            r"\bmoneygram\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_as_rent_terms=True,
    ),
    Rule(
        rule_id="payment.p2p_app_before_viewing",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(r"\bcash ?app\b", r"\bvenmo\b", r"\bpaypal\b", r"\bapple cash\b"),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_as_rent_terms=True,
    ),
    Rule(
        rule_id="payment.gift_card",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(
            r"\bgift ?cards?\b",
            r"\b(?:google play|itunes|steam) cards?\b",
            r"\bprepaid (?:debit )?cards?\b",
        ),
        excused_when_refused=True,
    ),
    Rule(
        rule_id="payment.crypto",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(
            r"\bbitcoin\b",
            r"\bbtc\b",
            r"\bcrypto(?:currency)?\b",
            r"\bethereum\b",
            r"\busdt\b",
        ),
        excused_when_refused=True,
    ),
    Rule(
        # The poster asks for more than is owed and promises the difference back, or sends a
        # cheque for more than is owed and wants the difference returned.
        rule_id="payment.overpayment_refund",
        category=RuleCategory.PAYMENT_METHOD,
        red_flag=True,
        patterns=(
            r"\b(?:refund|return|send back|wire back|pay back)\b[^.!?]{0,30}\bthe (?:difference|"
            r"rest|balance|extra|overage)\b",
            r"\b(?:check|cheque|money order)\b[^.!?]{0,40}\bmore than\b",
            r"\boverpa(?:y|id|yment)\b",
        ),
    ),
    # --- fee asks: money to a person before a viewing --------------------------------------
    Rule(
        rule_id="fee.holding_deposit_before_viewing",
        category=RuleCategory.FEE_ASK,
        red_flag=True,
        patterns=(
            r"\bholding (?:fee|deposit)\b",
            r"\b(?:send|pay|wire|transfer|zelle|venmo|cash ?app|mail|forward|put down)\b"
            r"[^.!?]{0,40}\b(?:deposit|first month)\b",
            r"\b(?:deposit|first month(?:'s)?(?: rent)?)\b[^.!?]{0,40}\b(?:to hold|to secure|"
            r"to reserve|up ?front|in advance|right away|today|tonight|now)\b",
            r"(?:\b(?:fee|payment|money)|\$\d[\d,]*)\b[^.!?]{0,30}\b(?:to|will) "
            r"(?:hold|secure|reserve)\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
    ),
    Rule(
        # A listing that merely states an application fee is ordinary. An ask to send one is not.
        rule_id="fee.application_fee_before_viewing",
        category=RuleCategory.FEE_ASK,
        red_flag=True,
        patterns=(
            r"\b(?:send|pay|zelle|venmo|cash ?app|wire|transfer)\b[^.!?]{0,50}\b(?:application|"
            r"processing|background check|credit check|screening) fee\b",
            r"\b(?:application|processing|background check|credit check|screening) fee\b"
            r"[^.!?]{0,50}\b(?:send|zelle|venmo|cash ?app|wire|transfer|to me|to my)\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
    ),
    # --- data asks: details that let someone take money or an identity ---------------------
    Rule(
        rule_id="data.ssn_before_viewing",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(r"\bssn\b", r"\bsocial security\b"),
        excused_after_viewing=True,
        excused_when_refused=True,
    ),
    Rule(
        rule_id="data.bank_login",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(
            r"\b(?:bank|banking)\b[^.!?]{0,30}\b(?:log ?in|password|credentials|username|pin)\b",
            r"\b(?:log ?in|password|credentials)\b[^.!?]{0,30}\b(?:bank|banking)\b",
        ),
        excused_when_refused=True,
    ),
    Rule(
        rule_id="data.id_before_viewing",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(
            r"\b(?:photo|picture|pic|copy|scan|image)s? of (?:your|the) (?:driver'?s? licen[cs]e|"
            r"id|i\.d\.|passport|identification|state id)\b",
            r"\bsend\b[^.!?]{0,30}\b(?:driver'?s? licen[cs]e|passport|photo id|id card)\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
    ),
    # --- pressure --------------------------------------------------------------------------
    Rule(
        # "I am abroad, I cannot show it, I will mail the keys": the story that removes the viewing.
        rule_id="pressure.cannot_show",
        category=RuleCategory.PRESSURE,
        red_flag=True,
        patterns=(
            r"\b(?:i am|i'm|i will be|we are|we're|currently|i work|i live|i moved|relocated)\b"
            r"[^.!?]{0,30}\b(?:out of (?:the )?(?:country|state|town)|abroad|overseas|deployed|"
            r"on a mission)\b",
            r"\b(?:can ?not|can't|cant|unable to|won't be able to|will not be able to|"
            r"not able to)\b"
            r"[^.!?]{0,20}\b(?:show|meet|give (?:you )?a tour)\b",
            r"\b(?:mail|ship|send|courier|fedex|overnight) (?:you )?the keys\b",
            r"\bkeys? (?:will be |by )?(?:mailed|shipped|mail)\b",
        ),
    ),
    Rule(
        rule_id="pressure.urgency",
        category=RuleCategory.PRESSURE,
        red_flag=False,
        patterns=(
            r"\bact (?:now|fast|quick(?:ly)?)\b",
            r"\btoday only\b",
            r"\bfirst to pay\b",
            r"\bfirst come,? first served\b",
            r"\bwon'?t last\b",
            r"\bgoing fast\b",
            r"\bhurry\b",
            r"\bby (?:tonight|end of (?:the )?day)\b",
            r"\bimmediately\b",
            r"\basap\b",
        ),
    ),
    Rule(
        rule_id="pressure.many_interested",
        category=RuleCategory.PRESSURE,
        red_flag=False,
        patterns=(
            r"\b(?:many|several|lots of|a lot of|other|multiple) (?:people|applicants|renters|"
            r"families|tenants)\b[^.!?]{0,30}\b(?:interested|waiting|asking|looking|applied|"
            r"lined up)\b",
            r"\blots of interest\b",
            r"\bhigh demand\b",
        ),
    ),
    # --- links from the poster -------------------------------------------------------------
    Rule(
        rule_id="link.payment_link",
        category=RuleCategory.LINK,
        red_flag=True,
        patterns=(
            r"\b(?:pay|payment|deposit|fee|invoice|checkout)\b",
            r"cash\.app|venmo\.com|paypal\.me",
        ),
        excused_after_viewing=True,
        needs_link=True,
    ),
    Rule(
        rule_id="link.lease_link",
        category=RuleCategory.LINK,
        red_flag=False,
        patterns=(r"\b(?:lease|application|apply|sign|docusign)\b",),
        needs_link=True,
    ),
)
