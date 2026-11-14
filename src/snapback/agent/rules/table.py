"""The rules, as data.

Each rule is a stable id, a category, whether it is a red flag, and the phrasings that count as
the ask. `apply.py` reads this table; nothing here runs. The wording a renter sees for a rule
lives in `snapback.card.strings` under `rule.<rule_id>`, never here.

How to read a rule:

- `patterns`: regular expressions, matched without regard to case against one sentence of the
  renter's own text. Any one of them is enough. Every quantifier needs an upper bound
  (`{0,40}`, never `*` or `+`): the text is written by the person being checked, and an
  unbounded pattern lets them stall the check. A test refuses a pattern without one.
- `excused_after_viewing`: the ask is ordinary once the renter has toured the unit or signed the
  lease, so a sentence that puts it after one of those does not fire. Rules without this fire
  whenever they match: nobody legitimate takes gift cards at any stage.
- `excused_when_refused`: a clause in which the writer says they never ask for or accept the
  thing ("we never ask for payment by Zelle"), or warns the renter off it ("never pay by
  Zelle"), is a warning, not an ask. The refusal has to come before the thing, in its clause.
- `excused_as_rent_terms`: a clause that describes how tenants pay rent ("tenants can pay rent
  by Venmo or Zelle") and asks for nothing now is not an ask either.
- `excused_after_approval`: a fee or a holding deposit that is due "after approval" or "once
  approved" is the ordinary order of things: the application came first. It does not fire.
- `excused_through_portal`: a fee paid "through our portal", "on our website" or "online" is
  where an application fee is ordinarily paid. It does not fire.
  Neither of these two excuses a sentence that names money that cannot be taken back (Zelle,
  a wire, a gift card, cash, "to me") or that wants it today.
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
    excused_after_approval: bool = False
    excused_through_portal: bool = False
    needs_link: bool = False


# Pieces of the "money before move-in" rule. A deposit that is "no deposit" or "without
# deposit" is not money asked for, and "not required" is not an ask.
# A deposit that is refused is not asked for: "no deposit", "no pet deposit", "zero deposit".
_A_DEPOSIT = (
    r"(?<!no )(?<!no security )(?<!no pet )(?<!no holding )(?<! or pet )"
    r"(?<!without )(?<!zero )\bdeposit\b"
)
_MONEY = (
    r"(?:" + _A_DEPOSIT + r"|\bfirst month(?:'s)?\b|\bmonth'?s rent\b"
    r"|\$\d[\d,]{0,12})"
)
_NOT = r"(?<!not )(?<!n't )(?<!never )(?<!dont )"
_DOLLARS = r"\$[1-9][\d,]{0,12}"  # "$0 deposit" asks for nothing
_BEFORE_MOVE_IN = r"\b(?:before|prior to|ahead of)\b[^.!?]{0,15}\bmov(?:e|ing)[- ]?in\b"

# Names a scammer borrows to make the money look safe. A site that says it never holds money
# is a warning, not the scam, so the words between the name and the "hold" may not refuse it.
_PLATFORMS = (
    r"(?:apartments\.?com|apartment finder|airbnb|vrbo|homeaway|zillow|trulia|redfin|"
    r"realtor\.?com|zumper|homes\.?com|craigslist|facebook|marketplace)"
)
# "We", "our" or "us" between the name and the verb means the office does it, not the site.
_NOT_REFUSED = (
    r"(?:(?!\bnever\b|\bnot\b|n't\b|\bno\b|\bcannot\b|\bwe\b|\bour\b|\bus\b|\bi\b|\bmy\b)"
    r"[^.!?])"
)
_HOLDS = r"(?:hold|holds|holding|insure|insures|secure|secures|safeguard|safeguards|keep|keeps)"
_RENTERS_MONEY = (
    r"your (?:money|deposit|payment|funds|rent|first month(?:'s)?(?: rent)?|security deposit)"
)
# A domain written out, other than the free report site, the three bureaus and Credit Karma.
_ANY_SITE = (
    r"(?<![\w.-])(?!(?:https?://)?(?:www\.)?(?:annualcreditreport|experian|equifax|transunion|creditkarma)\.com)"
    r"(?:https?://|www\.|[a-z0-9-]{1,40}\.(?:com|net|org|co|io|us|info|biz|app|site|online|"
    r"xyz|link|club|top|example))"
)
_SEND = r"\b(?:send|text|email|e-mail|forward|upload|attach|share|snap|screenshot)\b"
_PAYSTUB = r"\b(?:pay ?stubs?|pay slips?|paycheck stubs?)\b"
_SSN = r"\b(?:ssn|social security)\b"

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
            r"(?:\b(?:fee|payment|money)|\$\d[\d,]{0,12})\b[^.!?]{0,30}\b(?:to|will) "
            r"(?:hold|secure|reserve)\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_after_approval=True,
        excused_through_portal=True,
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
        excused_after_approval=True,
        excused_through_portal=True,
    ),
    Rule(
        # Rent or a deposit asked for before move-in. Honest listings say this too, so it is
        # never a red flag and can hold nothing. It only stops the card saying "Matches"
        # about the payment ask, and puts the owner's own rule beside it when the owner
        # publishes one (conductor, Sat 10:03).
        rule_id="fee.money_before_move_in",
        category=RuleCategory.FEE_ASK,
        red_flag=False,
        patterns=(
            # "the deposit is due before move-in"
            _MONEY
            + r"[^.!?$]{0,40}"  # no "$" in the gap: a run of "$1," cannot stall the match
            + _NOT
            + r"\b(?:due|required|needed|payable|paid|pay|send|collected|owed)\b"
            + r"[^.!?]{0,25}"
            + _BEFORE_MOVE_IN,
            # "you pay the deposit before moving in"
            _NOT
            + r"\b(?:pay|send|need|needs|require|requires|collect|owe)\b[^.!?]{0,40}"
            + _MONEY
            + r"[^.!?]{0,25}"
            + _BEFORE_MOVE_IN,
            # "before move-in we need the deposit"
            _BEFORE_MOVE_IN
            + r"[^.!?]{0,40}"
            + _NOT
            + r"\b(?:pay|send|need|require|due|owe)[a-z]{0,3}\b[^.!?]{0,40}"
            + _MONEY,
            # "you need first month and deposit to move in"
            _NOT
            + r"\b(?:need|needs|needed|require[sd]?|pay|send|bring|due)\b[^.!?]{0,40}"
            + _MONEY
            + r"[^.!?]{0,40}\bto move in\b",
            # "to move in you need $2,200"
            r"\bto move in\b[^.!?]{0,30}"
            + _NOT
            + r"\b(?:need|pay|send|require|bring)[a-z]{0,3}\b[^.!?]{0,40}"
            + _MONEY,
            r"\bmove[- ]?in (?:cost|costs|total|amount|funds|money)\b",
            # A deposit is paid before move-in by its nature, so naming one is the ask:
            # "the deposit is $1,100", "$1,100 deposit", "deposit required",
            # "deposit is one month's rent".
            _A_DEPOSIT + r"[^.!?$]{0,20}" + _DOLLARS,
            _DOLLARS + r"(?:(?! no | without | zero )[^.!?$]){0,15}\bdeposit\b",
            _A_DEPOSIT + r"[^.!?]{0,15}" + _NOT + r"\b(?:due|required|needed|payable)\b",
            _A_DEPOSIT + r"[^.!?]{0,15}\b(?:one|two|1|2|a|first|last) month",
            # The first month asked for ahead of time, and "first and last".
            r"\bfirst month(?:'s)?(?: rent)?\b[^.!?]{0,20}"
            r"\b(?:up ?front|in advance|at signing)\b",
            r"\bfirst and last month'?s?\b(?: rent)?",  # not "first and last name"
        ),
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
    Rule(
        # The FTC warns that scammers ask for a screenshot of a credit score (FTC, Dec 2025).
        # A credit check run by the landlord after an application is ordinary.
        rule_id="data.credit_score_screenshot",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(
            r"\b(?:screen ?shots?|photos?|pictures?|pics?|copy|copies|scan|image)s? of (?:your|ur|"
            r"the) (?:credit score|credit report|credit karma|credit)\b",
            r"\b(?:send|text|email|forward|share|upload)\b[^.!?]{0,40}\bscreen ?shots?\b"
            r"[^.!?]{0,30}\bcredit\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_after_approval=True,
        excused_through_portal=True,
    ),
    Rule(
        # Pay stubs sent to a person together with an SSN, or to "me", before a viewing.
        # Landlords do collect pay stubs, but with the application, not by text.
        rule_id="data.paystub_before_viewing",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(
            _SEND + r"[^.!?]{0,40}" + _PAYSTUB + r"[^.!?]{0,60}(?:" + _SSN + r"|\b(?:me|my)\b)",
            _SSN + r"[^.!?]{0,60}" + _PAYSTUB,
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_after_approval=True,
        excused_through_portal=True,
    ),
    Rule(
        # UW International Student Services warns students about requests for SEVIS or
        # I-20 papers by a stranger who has not shown the room.
        rule_id="data.sevis_before_viewing",
        category=RuleCategory.DATA_ASK,
        red_flag=True,
        patterns=(
            _SEND + r"[^.!?]{0,40}\b(?:sevis|i[- ]?20|ds[- ]?2019)\b",
            r"\b(?:need|require|requires|required|want|must have)\b[^.!?]{0,30}"
            r"\b(?:your|a copy of)\b[^.!?]{0,20}\b(?:sevis|i[- ]?20|ds[- ]?2019)\b"
            r"[^.!?]{0,30}\b(?:reserve|hold|secure|save|book|before)\b",
        ),
        excused_after_viewing=True,
        excused_when_refused=True,
        excused_after_approval=True,
        excused_through_portal=True,
    ),
    # --- pressure --------------------------------------------------------------------------
    Rule(
        # "I am abroad, I cannot show it, I will mail the keys": the story that removes the viewing.
        rule_id="pressure.cannot_show",
        category=RuleCategory.PRESSURE,
        red_flag=True,
        # Being unable to show a home is ordinary: "I can't show it until Saturday", "we
        # can't meet in person, but we offer a live video tour", "I'm out of town this week,
        # but you can tour with the lockbox code" (red team H8, Sat 03:25). What is not
        # ordinary is a poster who is abroad, or keys that come by mail.
        patterns=(
            r"\b(?:i am|i'm|i will be|we are|we're|currently|i work|i live|i moved|relocated)\b"
            r"[^.!?]{0,30}\b(?:out of (?:the )?country|abroad|overseas|deployed|"
            r"on a mission)\b",
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
    # --- impersonation: a trusted name or a stranger said to hold the money ---------------
    Rule(
        # CoStar's own scam page lists "Claim of affiliation with us. Scammers may impersonate
        # Apartments.com or Apartment Finder to make it seem like we participate in the lease
        # transaction or transfer of funds." Filed under pressure: the claim is a way of
        # making the ask feel safe.
        rule_id="impersonation.platform_holds_money",
        category=RuleCategory.PRESSURE,
        red_flag=True,
        patterns=(
            "^"
            + _NOT_REFUSED
            + r"{0,80}?"
            + _PLATFORMS
            + _NOT_REFUSED
            + r"{0,40}\b"
            + _HOLDS
            + r"\b"
            + _NOT_REFUSED
            + r"{0,40}"
            r"\b(?:money|deposit|payment|funds|rent)\b",
            _PLATFORMS + r"\s{1,3}(?:payment|payments|escrow|billing|booking|rental|deposit) "
            r"(?:team|department|agent|agents|service|protection|desk|processor)\b",
            _PLATFORMS + _NOT_REFUSED + r"{0,30}\bescrow\b",
        ),
        excused_when_refused=True,
        excused_as_rent_terms=True,
    ),
    Rule(
        # An "escrow agent" or "the platform" that is said to hold the renter's deposit.
        # A rental deposit goes to the owner's office; sales have escrow, rentals do not.
        rule_id="impersonation.escrow_agent",
        category=RuleCategory.PRESSURE,
        red_flag=True,
        patterns=(
            r"\b(?:escrow|third[- ]party)\s{1,3}(?:agent|agents|company|service|officer)"
            r"\b[^.!?]{0,40}\b" + _HOLDS + r"\b[^.!?]{0,30}\b" + _RENTERS_MONEY,
            r"\b(?:send|pay|wire|transfer|give|deposit)\b[^.!?]{0,40}\bto (?:the |our |an? |your )?"
            r"(?:escrow|third[- ]party)\s{1,3}(?:agent|company|service|account)\b",
            r"\bthe (?:platform|website|site|rental company|rental service|booking site)\b"
            r"[^.!?]{0,15}\b" + _HOLDS + r"\b[^.!?]{0,20}\b" + _RENTERS_MONEY,
            # CoStar's example 3: "they will hold and insure your money until you check".
            r"\b(?:hold and insure|insure and hold)\b[^.!?]{0,15}\b" + _RENTERS_MONEY,
            r"\b" + _RENTERS_MONEY + r"\b[^.!?]{0,30}\b(?:held|kept|insured|secured|protected)"
            r"\b[^.!?]{0,30}\b(?:escrow\s{1,3}(?:agent|company|service)|third[- ]party|"
            r"the platform)\b",
        ),
        excused_when_refused=True,
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
    Rule(
        # "Run your credit at <site>": a credit-check link that enrols the renter in a paid
        # membership (FTC, Dec 2025). Honest listings say where the landlord runs the check,
        # not where the renter should run their own.
        rule_id="link.affiliate_credit_check",
        category=RuleCategory.LINK,
        red_flag=True,
        patterns=(
            r"\b(?:run|check|pull|get|see|view|do)\b[^.!?]{0,20}\b(?:your|ur|a) (?:own |free )?"
            r"credit\b[^.!?]{0,30}\b(?:at|on|through|via|with|using|from|here)\b[^.!?]{0,15}"
            + _ANY_SITE,
        ),
        excused_when_refused=True,
        excused_after_approval=True,
        excused_through_portal=True,
    ),
)
