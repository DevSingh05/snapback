"""Every word a renter reads on a card, and every reason a verdict gives.

Code refers to these by key and never writes prose of its own, so a language model cannot put
words on a card and a reviewer can read the product's whole wording in this one file.

Conventions (tests/test_card_rows.py enforces them):

- No entry contains "safe", "verified" or "scam". About a person we say what was or was not
  shown, never what they are.
- Tone is never carried by colour alone. A red-flag line ends with "Red flag.", a `not_shown`
  line starts with "NOT SHOWN." or "Not confirmed." and a `not_checked` line starts with
  "Not checked".
- A rule that fires is worded under `rule.<rule_id>`. A rule id with no entry of its own falls
  back to `rule_category.<category>`, so a new rule can never put raw text on a card.
"""

DEFAULT_LANG = "en"

EN: dict[str, str] = {
    # --- line labels -----------------------------------------------------------------------
    "label.real": "Real",
    "label.matched_home": "Home in the photos",
    "place.matched_office": (
        "Not checked. The home in these photos is listed by its office on CoStar's record: "
        "{office}. We can't tell you if it is offered, or at this price."
    ),
    "label.here_now": "Here now",
    "label.allowed": "Allowed to rent it",
    "label.payment_ask": "Payment ask",
    "label.data_ask": "Data ask",
    "label.pressure": "Pressure",
    "label.rent_vs_record": "Rent vs record",
    "label.seen_before": "Seen before",
    "label.for_sale": "For sale",
    "label.recently_rented": "Rental history",
    "label.contact": "Contact on record",
    "label.office": "Office confirmation",
    "label.link": "Link",
    "label.license": "License",
    "label.owner": "Owner of record",
    "label.owner_rule": "Owner's rule",
    "label.unit": "Unit on record",
    # --- PLACE: were the photos taken here? ------------------------------------------------
    "place.located_plan": (
        "Taken in this building, in the {floor_plan} floor plan ({located} of {total} photos)."
    ),
    "place.located": "Taken in this building ({located} of {total} photos).",
    # A house is a home, not a building.
    "place.located_home": "Taken in this home ({located} of {total} photos).",
    "place.elsewhere": "Taken in a different building ({elsewhere} of {total} photos). Red flag.",
    "place.not_located": "NOT SHOWN. These photos could not be placed in this building's 3D scan.",
    "place.not_indexed": "Not checked (we have no 3D scan of this building).",
    "place.not_indexed_yet": "Not checked (this building's scan is not indexed yet).",
    "place.no_photos": "Not checked (no listing photos were sent).",
    "place.seen_before_dated": "A listing photo also appeared in another check on {date}.",
    "place.seen_before": "A listing photo also appeared in another check.",
    # For sale is a red flag, never proof: it holds a case and cannot set DON'T PAY by itself.
    # A warning, never a red flag, and never "not for rent" (red team H5, Sat 03:25). We do
    # not know whether a home is leased; the record says it is for sale, and so do we. The
    # line is what the record says ({record}, one of the four below) and then who to ask.
    "place.for_sale_record": "Listed for sale on {site} by {brokerage} since {date}.",
    "place.for_sale_record_no_date": "Listed for sale on {site} by {brokerage}.",
    "place.for_sale_record_no_brokerage": "Listed for sale on {site} since {date}.",
    "place.for_sale_record_bare": "Listed for sale on {site}.",
    "place.for_sale": (
        "{record} Homes for sale are sometimes also offered for lease, so confirm with that "
        "brokerage before you pay."
    ),
    "place.for_sale_ask_listing": (
        "{record} Homes for sale are sometimes also offered for lease, so confirm with the "
        "listing brokerage before you pay."
    ),
    # The ad's phone is the office's on record: the brokerage itself is offering the home.
    # Information only; it holds nothing (ruling, Sat 03:36).
    "place.for_sale_office": (
        "Not confirmed. {record} The contact in this listing is the office on record, so ask "
        "them whether it is also offered for lease."
    ),
    # Lease status is something we do not know and never claim (ruling, Sat 01:20). This is
    # an information line: it carries no flag and holds no case by itself.
    "place.recently_rented": (
        "Not confirmed. The record shows it was rented recently. "
        "Ask the manager on record if it's still available."
    ),
    "place.recently_rented_dated": (
        "Not confirmed. The record shows it was rented on {date}. "
        "Ask the manager on record if it's still available."
    ),
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
    # A reply came, could not be accepted, and nothing more will be asked (A14).
    "here_now.no_retry_left": (
        "We could not confirm they are there. Call the office on record yourself."
    ),
    # A14: a reply came. What it showed, and what nothing has checked yet.
    "here_now.code_only": (
        "Not confirmed. The reply shows the code we asked for, but nothing has checked "
        "that it was taken at the spot."
    ),
    "here_now.code_missing": (
        "The reply did not show the code we asked for. Ask for a new photo at a new spot."
    ),
    "here_now.not_requested": "Not checked (no one has been asked to prove they are inside yet).",
    "here_now.forged_copy": "The reply is a copy of listing photo {n}. Red flag.",
    "here_now.forged_copy_unknown": "The reply is a copy of one of the listing photos. Red flag.",
    "here_now.forged": "The reply was not a fresh photo taken in the unit. Red flag.",
    "here_now.seen_before_dated": "A reply photo also appeared in another check on {date}.",
    "here_now.seen_before": "A reply photo also appeared in another check.",
    "allowed.not_shown": "NOT SHOWN. Being inside does not mean they may rent it.",
    # A match never lifts this line: anyone can type a company's public name.
    "allowed.call_manager": (
        "Not confirmed. Call {manager} on a number you look up yourself before you pay."
    ),
    "allowed.call_manager_unnamed": (
        "Not confirmed. Call the manager on record on a number you look up yourself before you pay."
    ),
    # A name that is not the one on record is never a red flag by itself (ruling, Sat 01:20):
    # the manager, the leasing office and a listing brokerage may all market a home.
    "allowed.call_office": "Not confirmed. Call the office on record yourself.",
    # Contact on record. The phone number itself and the record's web address are never shown.
    # A match is a supporting line only. It never counts as matching the record by itself.
    "contact.phone_match": (
        "The phone matches the leasing office on record. Call it yourself to confirm."
    ),
    # H1: the name matches the record and there was no phone to compare with the office's.
    "contact.phone_unchecked": (
        "Not checked (no phone number in the listing could be compared with the leasing "
        "office on record)."
    ),
    # A15: a home for sale with no property record. Whatever the ad says, there is no phone
    # on record for the brokerage to compare it with.
    "contact.no_brokerage_phone": "Not checked (we hold no phone for the listing brokerage).",
    # Not a red flag (ruling, Sat 02:10, #121): agents and locators often post with their own
    # number. The line is Not confirmed, and it says who to call.
    "contact.phone_mismatch": (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own, so check it with the office."
    ),
    "contact.phone_mismatch_unnamed": (
        "Not confirmed. This number is not the leasing office's on record. "
        "Agents often use their own. Call the office on record yourself to confirm."
    ),
    # Vidyut, Sat 07:35: an active licence checked by number, sponsored by the brokerage on
    # record. Information, not a confirmation: the number is still not the office's.
    "contact.licensed_sponsor": (
        "Not the office's number. The license number given is active, under the name in the "
        "ad, and sponsored by {brokerage}, the brokerage on record. A license number can be "
        "copied from a real listing, so call {brokerage} on a number you look up yourself to "
        "confirm this agent."
    ),
    "contact.lookalike_link": (
        "A link in the listing imitates this building's website but is not it. Red flag."
    ),
    "contact.office_confirmed": (
        "Confirmed by the office: someone at {domain}, the website CoStar has on record for "
        "this office, said this ad is theirs."
    ),
    # Vidyut, Sat 11:06: the office said yes but the phone in the ad is not the office's, so the
    # card still reads Hold off. Said plainly, right under the confirmation.
    "contact.office_still_hold": (
        "Still hold off: the phone in the ad is not the office's number on record. Call the "
        "office on a number you look up yourself before you pay."
    ),
    "contact.office_declined": (
        "Not confirmed. Someone at {domain}, the website CoStar has on record for this "
        "office, said the office does not recognise this ad."
    ),
    "reason.office_declined": (
        "The office at {domain}, the website CoStar has on record, did not recognise this ad."
    ),
    "office.call_yourself": (
        "No website for this office is on record, so it cannot be confirmed here. Call the "
        "office on a number you look up yourself."
    ),
    "license.licensed": "Licensed in Texas.",
    "license.licensed_sponsored": (
        "An active Texas license exists under the name in the ad, sponsored by {broker}."
    ),
    # D10 (#128): NOT_FOUND only from a license number the ad itself gives. A name never gives it.
    "license.not_found": (
        "The license number in the ad is not an active Texas license. "
        "Look it up yourself at trec.texas.gov."
    ),
    "license.not_checked_claimed": (
        "Says they're licensed. Ask for their Texas license number and look it up at "
        "trec.texas.gov."
    ),
    # A24 stretch: the number was typed by the renter, so these say "the number you gave" and
    # a dead number is "Not confirmed" (typo risk), never "Doesn't match" (ruling, Sat 07:14).
    "license.not_found_given": (
        "The license number you gave is not an active Texas license. Check it was typed "
        "right, then look it up yourself at trec.texas.gov."
    ),
    "license.not_checked_given": (
        "Says they're licensed. The number you gave did not confirm it. Look it up yourself "
        "at trec.texas.gov."
    ),
    "owner.company_not_poster": "Not confirmed. Owner of record: {company}, not the poster.",
    "owner.company": "Not confirmed. Owner of record: {company}.",
    "owner.company_unnamed_not_poster": (
        "Not confirmed. Owner of record: a company owner, not the poster."
    ),
    "owner.company_unnamed": "Not confirmed. Owner of record: a company owner.",
    "owner.company_matches": "The company they named is the owner of record: {company}.",
    "owner.person_matches": "The owner of record is a private owner, and the name given matches.",
    "owner.person_mismatch": (
        "Not confirmed. The owner of record is a private owner, and the name given doesn't "
        "match. Owners can rent through family or a trust; check with the owner of record or "
        "the county records yourself."
    ),
    "owner.person_no_claim": (
        "Not checked (a private owner is on record, and the poster does not say they are the "
        "owner)."
    ),
    "owner.person_no_name": (
        "Not checked (a private owner is on record, and the poster gave no name to compare)."
    ),
    # The owner's own published rule, quoted, with where it is from and the day we read it.
    "owner.rule": '{company} says: "{rule}" ({source}, read {date}).',
    "owner.rule_beside_payment": (
        '{company}, the owner of record, says: "{rule}" ({source}, read {date}).'
    ),
    # --- PRICE: what are they asking for, and does the rent fit? ---------------------------
    "payment.none": "No risky payment ask found in the text you sent.",
    # The ad asks you to pay rent or a deposit before move-in. Honest listings do too, so it is
    # never a red flag; the line just must not read "Matches" (conductor, Sat 10:03).
    "payment.before_move_in": (
        "The ad asks you to pay rent or a deposit before move-in. "
        "We could not confirm who it would go to."
    ),
    "payment.before_move_in_not_owner": (
        "The ad asks you to pay rent or a deposit before move-in, "
        "and the owner of record is not the poster."
    ),
    # One entry per red-flag rule in agent/rules/table.py, keyed by its rule id.
    "rule.payment.zelle_before_viewing": "Zelle before a viewing. Red flag.",
    "rule.payment.wire_before_viewing": "Wire transfer before a viewing. Red flag.",
    "rule.payment.p2p_app_before_viewing": "Payment by app before a viewing. Red flag.",
    "rule.payment.gift_card": "Gift cards as payment. Red flag.",
    "rule.payment.crypto": "Crypto as payment. Red flag.",
    "rule.payment.overpayment_refund": (
        "More money than is owed, with the difference to be sent back. Red flag."
    ),
    "rule.fee.holding_deposit_before_viewing": (
        "A deposit or holding fee before a viewing. Red flag."
    ),
    "rule.fee.application_fee_before_viewing": (
        "An application fee sent to a person before a viewing. Red flag."
    ),
    "rule.data.ssn_before_viewing": "Social Security number before a viewing. Red flag.",
    "rule.data.bank_login": "Bank login details. Red flag.",
    "rule.data.id_before_viewing": "A photo of your ID before a viewing. Red flag.",
    "rule.pressure.cannot_show": "They say they cannot show the unit in person. Red flag.",
    "rule.link.payment_link": "A payment link sent by the poster. Red flag.",
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
    # "NN% under this building's lowest N bed": the comparison with the listing's own size.
    "rent.below_floor_plan": (
        "{percent}% under this building's lowest {plan} on record. Ask why; discounts happen."
    ),
    "rent.plan.studio": "studio",
    "rent.plan.beds": "{beds} bed",
    "rent.per_bed": "Not checked (priced per bed here, so the rent was not compared).",
    "unit.not_on_record": (
        "The record for this building lists no unit with that number. Ask the manager on record."
    ),
    "unit.beds_mismatch": (
        "The bedroom count in the listing does not match the record for this building. "
        "Ask the manager on record."
    ),
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
    # --- the "Report this copy" pack (A20, #126) --------------------------------------------
    # For a listing agent whose listing was copied. Facts and where to click. No line here is
    # about a person, and like every string in this table none uses the word the card bans:
    # Facebook's own menu label for the reason is described, not quoted.
    "report.pair.elsewhere": "Listing photo {n} was taken in a different property.",
    "report.platform.facebook": "Facebook Marketplace",
    "report.platform.zillow": "Zillow",
    "report.platform.craigslist": "Craigslist",
    "report.steps.facebook.1": "Open the copied listing on Facebook Marketplace.",
    "report.steps.facebook.2": (
        'Open the menu (three dots) and choose "Report listing". Pick the reason for a fake '
        "or misleading listing."
    ),
    "report.steps.facebook.3": "Paste the lines from this page where it asks for details.",
    "report.steps.zillow.1": "Open the copied listing on Zillow.",
    "report.steps.zillow.2": (
        'Choose "Report listing", then "Listing seems to be fraudulent or illegal".'
    ),
    "report.steps.zillow.3": "Paste the lines from this page where it asks for details.",
    "report.steps.craigslist.1": "Open the copied post on Craigslist.",
    "report.steps.craigslist.2": 'Use the "prohibited" flag at the top of the post.',
    "report.steps.craigslist.3": (
        "For a fuller report, use the Craigslist contact form and paste the lines from this page."
    ),
    # On every card made from a staged demo case (fixtures/demo), first in the footer.
    "footer.staged": (
        "Staged example. The SNAPBACK team wrote this listing to show the checks. "
        "It is not a real poster."
    ),
    # On a card made from a replay demo case (fixtures/demo/replay-*), instead of footer.staged.
    "footer.replay": (
        "Replay of a reported case ({source}, {date}). "
        "The listing and house are re-created; no real names."
    ),
    # --- the challenge message the renter relays, and the agent's own trace lines ----------
    "challenge.text": (
        "Before you pay, ask them to send a photo of {spot} with the code {code} written on paper."
    ),
    "trace.checks.twin": "The building is in our data area and has a 3D twin.",
    "trace.checks.no_twin": "We have no 3D scan of this building, so only the text can be checked.",
    "trace.checks.short_term": (
        "This is a short-term stay listing, which this check does not cover."
    ),
    "trace.checks.commercial": "This is a commercial listing, which this check does not cover.",
    "trace.tool.locate": "Placing {count} listing photos in the twin.",
    "trace.floor_plan.best": "{alias}: {best} inliers vs {next}.",
    "trace.floor_plan.only": "Only one floor plan is in the running.",
    "trace.floor_plan.unranked": "No photo was placed, so the first floor plan on record is used.",
    "trace.spot.draw": "Random draw from the top {count}.",
    "trace.spot.draw_skipped_one": (
        "Random draw from the top {count}; {skipped} skipped because it overlaps a listing photo."
    ),
    "trace.spot.draw_skipped_many": (
        "Random draw from the top {count}; {skipped} spots skipped because they overlap "
        "listing photos."
    ),
    "trace.hitl.waiting": (
        "Waiting for the renter to approve the message. Nothing is sent until then."
    ),
    "trace.hitl.send": "The renter approved the challenge text.",
    "trace.reply.waiting": (
        "The message is with the renter to pass on. Waiting for the poster's reply photo."
    ),
    "trace.tool.reply": "Checked the reply photo for the code and against the listing photos.",
    "trace.hitl.edit": "The renter edited the challenge text and approved it.",
    "trace.hitl.cancel": "The renter chose not to send a challenge.",
    # --- the evidence-driven plan (A24): which check runs next -------------------------------
    "plan.pick.record": "The home's own record gives the rent band and who is on record. Read it.",
    # With a listing active, who is on record is the brokerage step's finding (A15).
    "plan.pick.record_rent": "The home's own record gives the rent band. Read it.",
    "plan.pick.brokerage": "The home is listed for sale right now. Check the listing office.",
    "plan.pick.license": "The ad names a license. Look it up with the state.",
    "plan.pick.owner": "An owner is on public record. Compare it with who is posting.",
    "plan.pick.claims": (
        "The ad makes claims the record can answer. Compare what the ad says with CoStar's "
        "record of the home."
    ),
    "plan.pick.ask": (
        "The ad says they're licensed but gives no number. Ask the renter for the license number."
    ),
    "plan.ask.question": (
        "The ad says they're a licensed agent but gives no license number. Can you ask them "
        "for it, or paste it here?"
    ),
    "plan.ask.looked_up": "Looked up the license number you gave with the state.",
    "plan.ask.no_number": "No license number came back. The license stays not checked.",
    "plan.ask.not_looked_up": (
        "Could not look up the license number you gave. The license stays not checked."
    ),
    "plan.skip.ask_off": "asking the renter is not available",
    "plan.skip.ask_none": "the ad does not claim a license without giving its number",
    "plan.pick.report": "Every check that could run has run. Gather what they found for a report.",
    "plan.skip.record": "no property record to read",
    "plan.skip.brokerage": "the home is not listed for sale right now",
    "plan.skip.license_off": "license lookup not available",
    "plan.skip.license_none": "the ad names no license to look up",
    "plan.skip.owner_off": "owner lookup not available",
    "plan.skip.owner_none": "no owner on record to read",
    "plan.skip.claims_off": "ad claims are not compared here",
    "plan.skip.claims_none": "nothing in the ad that the record answers",
    "plan.skipped": "Skipped {option}: {reason}.",
    "plan.only_option": "Only one option was open.",
    "trace.retry.accept_both": "Both spots matched with the code read and no recapture flag.",
    "trace.retry.accept": (
        "{matched} of {total} spots matched with the code read and no recapture flag."
    ),
    "trace.retry.forged": "The reply failed the check, so there is nothing to retry.",
    "trace.retry.again": "The reply could not be accepted, so we ask again at a new spot.",
    "trace.retry.late": "The reply came too late to count, so we ask once more at a new spot.",
    "trace.reply.late": (
        "The reply came after the time limit. It was compared with the listing photos and "
        "not counted."
    ),
    "trace.retry.code_only": (
        "The reply shows the code. Whether it was taken at the spot cannot be checked yet, "
        "so it stays not confirmed."
    ),
    "trace.retry.stop": (
        "The reply could not be accepted and no retry is left, so the result stays on hold."
    ),
    "trace.error.bad_pick": (
        "The model answered with something that was not on the list, so the default was used."
    ),
    "trace.error.model_failed": "The model could not be used, so the default was used.",
    "trace.agent.todos": "The agent wrote its plan: {count} steps, {done} done.",
    "trace.agent.delegate": (
        "Handed the {name} checks to a sub-agent that sees only its own tools and "
        "writes its findings to a note."
    ),
    "trace.agent.note": "Note written: {path} ({chars} characters).",
    "trace.agent.returned": "The {name} sub-agent finished and handed back its findings.",
    "trace.unsure.inliers": "{photo} fell short: {n} matched points, the bar is {bar}.",
    "trace.unsure.ratio": "{photo} fell short: too few of its points agreed, the bar is {bar}.",
    "trace.unsure.spread": "{photo} fell short: its matched points cover too little of the photo.",
    "trace.unsure.ambiguity": (
        "Another building matched far more strongly, so {photo} was not placed."
    ),
    "trace.place.searched": "{photo}: searched {option} ({seconds} s). {result}",
    "place.option.focus_scan": "one scan more closely",
    "place.option.wider_index": "more buildings",
    "place.option.deeper_claimed": "more views of this home",
    "place.result.placed": "Placed.",
    "place.result.not_placed": "Still could not place it.",
    "place.result.elsewhere": "It matched a different building.",
    "place.result.skipped": "Skipped.",
    "trace.intake.injection": (
        "The listing has text written for an AI system. It was ignored, and the checks go on."
    ),
    "trace.intake.truncated": (
        "The text you sent was very long. Only the first 20,000 characters were read. "
        "The rest was not checked."
    ),
    # --- reasons a verdict gives (Verdict.reasons, Evidence.forgery_reason) ----------------
    "reason.forged": "The proof-of-presence reply was not a fresh photo taken in the unit.",
    "reason.forged_copy": "The reply is a copy of listing photo {n}.",
    "reason.forged_copy_unknown": "The reply is a copy of one of the listing photos.",
    "reason.photo_elsewhere": "At least one listing photo was taken in a different property.",
    "reason.price_flag": "The rent is far below comparable units.",
    "reason.payment_flag": "Payment was requested before any viewing.",
    "reason.rule_flag": "Something in the text you sent is a red flag.",
    "reason.for_sale": (
        "This home is listed for sale. Confirm with the listing brokerage that it is also "
        "offered for lease."
    ),
    "reason.phone_not_confirmed": (
        "The contact in the listing was not shown to be the leasing office on record."
    ),
    "reason.phone_not_confirmed_brokerage": (
        "We hold no phone for the listing brokerage, so the contact in the listing could not "
        "be compared."
    ),
    "reason.phone_flag": "The phone in the listing is not the leasing office on record.",
    "reason.lookalike_link": "A link in the listing imitates the building's website.",
    "reason.license_not_found": "The license number in the ad is not an active Texas license.",
    "reason.license_not_found_given": "The license number you gave is not an active Texas license.",
    "reason.owner_not_poster": (
        "The poster says they are the owner, and the owner of record is someone else."
    ),
    "reason.unit_flag": "The unit in the listing does not fit the record for this building.",
    "reason.not_indexed": (
        "This property has no 3D twin in our index, so the photos could not be checked."
    ),
    "reason.not_located": "The photos could not be located in this property's 3D twin.",
    "reason.located": "The photos were located in this property.",
    "reason.authority_matches": ("The ad names the manager on record. Anyone can type that name."),
    "reason.authority_matches_brokerage": (
        "The ad names the listing brokerage on record. Anyone can type that name."
    ),
    # Vidyut, Sat 09:38: someone at the office's own website domain on CoStar's record opened
    # a one-time link. Only the domain is named, never an address or a person.
    "reason.office_confirmed": (
        "Confirmed through {domain}, the website CoStar has on record for this office; "
        "the photos are of this home."
    ),
    "reason.authority_unknown": "We could not confirm who is allowed to rent this unit.",
    "reason.presence_proven": "A fresh photo proved someone was inside the unit.",
    "reason.presence_proven_not_authority": (
        "A fresh photo proved someone was inside the unit, which is not authority."
    ),
    "reason.presence_missing": "Nobody has proved they are inside the unit yet.",
    # --- the card's own words: row titles, tone and state labels, the header -------------
    "row.place": "PLACE",
    "row.person": "PERSON",
    "row.price": "PRICE",
    # LOCKED wording (decisions Fri 22:40, XO review of #59). Five row states: Matches,
    # Doesn't match, Not confirmed, Warning, Not checked. Three headlines. Do not reword.
    # A row state is chosen by `tone_word`: by the line's tone, and for two tones by its row.
    "tone.ok": "Matches",
    "tone.hold": "Warning",
    "tone.hold.person": "Not confirmed",  # no reply yet is not a warning about anyone
    "tone.red_flag": "Doesn't match",
    "tone.red_flag.price": "Warning",  # a risky ask is a warning, not a mismatch
    "tone.not_shown": "Not confirmed",
    "tone.not_checked": "Not checked",
    "state.hold": "Hold off for now",
    # A HOLD with nothing against it: every line matches and only the presence step is left.
    # Same state, different words, so an honest ad does not read like a scam (#10, Sat 19:0x).
    "state.hold_clean": (
        "Everything we checked matches the record. "
        "One step left before you pay: ask them to prove they're inside."
    ),
    "state.dont_pay": "Don't pay. Something here doesn't match.",
    "state.unverified": "Could not place these photos",
    "state.verified": "Checks passed. Still follow the two rules.",
    "card.case": "Case {case_id}",
    "card.checked": "Checked {time}",
    "card.expires": "Expires {time}",
    "card.not_checked": "Not checked by SNAPBACK: {items}",
    "card.verify": "Check this card yourself:",
    "card.source.fixture": "FIXTURE",
    "card.source.live": "LIVE",
}

# Spanish, for Houston. Same keys and the same blanks as EN; tests hold it to both.
# Banned here: estafa, seguro, verificado. A red-flag line ends "Señal de alerta.", a
# not-shown line starts "NO DEMOSTRADO." or "Sin confirmar.", a not-checked line starts
# "No comprobado".
ES: dict[str, str] = {
    "label.real": "Real",
    "label.matched_home": "Vivienda de las fotos",
    "place.matched_office": (
        "No comprobado. La vivienda de estas fotos figura con esta oficina en el registro de "
        "CoStar: {office}. No podemos decirle si se ofrece, ni a este precio."
    ),
    "label.here_now": "Aquí ahora",
    "label.allowed": "Con permiso para alquilarlo",
    "label.payment_ask": "Pago que piden",
    "label.data_ask": "Datos que piden",
    "label.pressure": "Presión",
    "label.rent_vs_record": "Renta frente al registro",
    "label.seen_before": "Visto antes",
    "label.for_sale": "En venta",
    "label.recently_rented": "Historial de alquiler",
    "label.contact": "Contacto en el registro",
    "label.office": "Confirmación de la oficina",
    "label.link": "Enlace",
    "label.license": "Licencia",
    "label.owner": "Propietario registrado",
    "label.owner_rule": "Regla del propietario",
    "label.unit": "Unidad en el registro",
    "place.located_plan": (
        "Tomadas en este edificio, en el plano de {floor_plan} ({located} de {total} fotos)."
    ),
    "place.located": "Tomadas en este edificio ({located} de {total} fotos).",
    "place.located_home": "Tomadas en esta vivienda ({located} de {total} fotos).",
    "place.elsewhere": "Tomadas en otro edificio ({elsewhere} de {total} fotos). Señal de alerta.",
    "place.not_located": (
        "NO DEMOSTRADO. Estas fotos no se pudieron ubicar en el escaneo 3D de este edificio."
    ),
    "place.not_indexed": "No comprobado (no tenemos un escaneo 3D de este edificio).",
    "place.not_indexed_yet": (
        "No comprobado (el escaneo de este edificio todavía no está indexado)."
    ),
    "place.no_photos": "No comprobado (no se enviaron fotos del anuncio).",
    "place.seen_before_dated": "Una foto del anuncio también apareció en otra revisión el {date}.",
    "place.seen_before": "Una foto del anuncio también apareció en otra revisión.",
    "place.for_sale_record": "En venta en {site} por {brokerage} desde el {date}.",
    "place.for_sale_record_no_date": "En venta en {site} por {brokerage}.",
    "place.for_sale_record_no_brokerage": "En venta en {site} desde el {date}.",
    "place.for_sale_record_bare": "En venta en {site}.",
    "place.for_sale": (
        "{record} Las viviendas en venta a veces también se ofrecen en alquiler, así que "
        "confírmelo con esa agencia antes de pagar."
    ),
    "place.for_sale_ask_listing": (
        "{record} Las viviendas en venta a veces también se ofrecen en alquiler, así que "
        "confírmelo con la agencia que la anuncia antes de pagar."
    ),
    "place.for_sale_office": (
        "Sin confirmar. {record} El contacto de este anuncio es la oficina que figura en el "
        "registro, así que pregúnteles si también se ofrece en alquiler."
    ),
    "place.recently_rented": (
        "Sin confirmar. El registro muestra que se alquiló hace poco. "
        "Pregunte al administrador que figura en el registro si sigue disponible."
    ),
    "place.recently_rented_dated": (
        "Sin confirmar. El registro muestra que se alquiló el {date}. "
        "Pregunte al administrador que figura en el registro si sigue disponible."
    ),
    "here_now.proven_plan": (
        "Alguien con acceso a una unidad de {floor_plan} aquí las envió ahora mismo "
        "({matched} de {total} puntos, código leído, {time})."
    ),
    "here_now.proven": (
        "Alguien con acceso a una unidad aquí las envió ahora mismo ({matched} de {total} "
        "puntos, código leído, {time})."
    ),
    "here_now.proven_bare": "Alguien con acceso a una unidad aquí lo demostró ahora mismo.",
    "here_now.waiting": "Aún sin respuesta. Un arrendador honesto puede necesitar tiempo.",
    "here_now.retry": "No se pudo aceptar la foto de respuesta. Pida una foto nueva en otro punto.",
    "here_now.no_retry_left": (
        "No pudimos confirmar que están allí. Llame usted mismo a la oficina que figura en "
        "el registro."
    ),
    "here_now.code_only": (
        "Sin confirmar. La respuesta muestra el código que pedimos, pero nada ha comprobado "
        "que se tomó en el punto indicado."
    ),
    "here_now.code_missing": (
        "La respuesta no mostró el código que pedimos. Pida una foto nueva en otro punto."
    ),
    "here_now.not_requested": (
        "No comprobado (aún no se ha pedido a nadie que demuestre que está dentro)."
    ),
    "here_now.forged_copy": (
        "La respuesta es una copia de la foto {n} del anuncio. Señal de alerta."
    ),
    "here_now.forged_copy_unknown": (
        "La respuesta es una copia de una de las fotos del anuncio. Señal de alerta."
    ),
    "here_now.forged": "La respuesta no era una foto nueva tomada en la unidad. Señal de alerta.",
    "here_now.seen_before_dated": (
        "Una foto de respuesta también apareció en otra revisión el {date}."
    ),
    "here_now.seen_before": "Una foto de respuesta también apareció en otra revisión.",
    "allowed.not_shown": "NO DEMOSTRADO. Estar dentro no significa que pueda alquilarlo.",
    "allowed.call_manager": (
        "Sin confirmar. Llame a {manager} a un número que usted mismo busque antes de pagar."
    ),
    "allowed.call_manager_unnamed": (
        "Sin confirmar. Llame al administrador que figura en el registro, a un número que "
        "usted mismo busque, antes de pagar."
    ),
    "allowed.call_office": (
        "Sin confirmar. Llame usted mismo a la oficina que figura en el registro."
    ),
    "contact.phone_match": (
        "El teléfono coincide con el de la oficina de alquiler que figura en el registro. "
        "Llame usted mismo para confirmarlo."
    ),
    "contact.phone_unchecked": (
        "No comprobado (ningún teléfono del anuncio se pudo comparar con el de la oficina de "
        "alquiler que figura en el registro)."
    ),
    "contact.no_brokerage_phone": (
        "No comprobado (no tenemos un teléfono de la agencia que anuncia la vivienda)."
    ),
    "contact.phone_mismatch": (
        "Sin confirmar. Este número no es el de la oficina de alquiler que figura en el "
        "registro. Los agentes suelen usar el suyo, así que confírmelo con la oficina."
    ),
    "contact.phone_mismatch_unnamed": (
        "Sin confirmar. Este número no es el de la oficina de alquiler que figura en el "
        "registro. Los agentes suelen usar el suyo. Llame usted mismo a la oficina que figura "
        "en el registro para confirmarlo."
    ),
    "contact.licensed_sponsor": (
        "No es el número de la oficina. El número de licencia que se dio está activo, a nombre "
        "de quien firma el anuncio, y patrocinado por {brokerage}, la agencia que figura en el "
        "registro. Un número de licencia se puede copiar de un anuncio real, así que llame a "
        "{brokerage} a un número que usted mismo busque para confirmar a este agente."
    ),
    "contact.lookalike_link": (
        "Un enlace del anuncio imita el sitio web de este edificio, pero no lo es. Señal de alerta."
    ),
    "contact.office_confirmed": (
        "Confirmado por la oficina: alguien en {domain}, el sitio web que CoStar tiene "
        "registrado para esta oficina, dijo que este anuncio es suyo."
    ),
    "contact.office_still_hold": (
        "Aún en espera: el teléfono del anuncio no es el número de la oficina en el registro. "
        "Llame a la oficina a un número que usted mismo busque antes de pagar."
    ),
    "contact.office_declined": (
        "No confirmado. Alguien en {domain}, el sitio web que CoStar tiene registrado para "
        "esta oficina, dijo que la oficina no reconoce este anuncio."
    ),
    "reason.office_declined": (
        "La oficina en {domain}, el sitio web que CoStar tiene registrado, no reconoció este "
        "anuncio."
    ),
    "office.call_yourself": (
        "No hay un sitio web registrado para esta oficina, así que no se puede confirmar aquí. "
        "Llame a la oficina a un número que usted mismo busque."
    ),
    "license.licensed": "Con licencia en Texas.",
    "license.licensed_sponsored": (
        "Existe una licencia activa de Texas a nombre de quien firma el anuncio, patrocinada "
        "por {broker}."
    ),
    "license.not_found": (
        "El número de licencia del anuncio no es una licencia activa de Texas. "
        "Búsquelo usted mismo en trec.texas.gov."
    ),
    "license.not_checked_claimed": (
        "Dice tener licencia. Pídale su número de licencia de Texas y búsquelo en trec.texas.gov."
    ),
    "license.not_found_given": (
        "El número de licencia que usted dio no es una licencia activa de Texas. Revise que "
        "esté bien escrito y búsquelo usted mismo en trec.texas.gov."
    ),
    "license.not_checked_given": (
        "Dice tener licencia. El número que usted dio no lo confirmó. Búsquelo usted mismo "
        "en trec.texas.gov."
    ),
    "owner.company_not_poster": (
        "Sin confirmar. Propietario registrado: {company}, no quien publica."
    ),
    "owner.company": "Sin confirmar. Propietario registrado: {company}.",
    "owner.company_unnamed_not_poster": (
        "Sin confirmar. Propietario registrado: una empresa, no quien publica."
    ),
    "owner.company_unnamed": "Sin confirmar. Propietario registrado: una empresa.",
    "owner.company_matches": "La empresa que nombró es la propietaria registrada: {company}.",
    "owner.person_matches": (
        "El propietario registrado es un particular, y el nombre dado coincide."
    ),
    "owner.person_mismatch": (
        "Sin confirmar. El propietario registrado es un particular, y el nombre dado no "
        "coincide. Los propietarios pueden alquilar a través de familiares o de un "
        "fideicomiso; consulte usted mismo con el propietario registrado o en los registros "
        "del condado."
    ),
    "owner.person_no_claim": (
        "No comprobado (hay un propietario particular registrado, y quien publica no dice "
        "ser el propietario)."
    ),
    "owner.person_no_name": (
        "No comprobado (hay un propietario particular registrado, y quien publica no dio un "
        "nombre para comparar)."
    ),
    "owner.rule": '{company} dice: "{rule}" ({source}, leído el {date}).',
    "owner.rule_beside_payment": (
        '{company}, el propietario registrado, dice: "{rule}" ({source}, leído el {date}).'
    ),
    "payment.none": "No se encontró ningún pedido de pago riesgoso en el texto que envió.",
    "payment.before_move_in": (
        "El anuncio pide renta o depósito antes de la mudanza. No pudimos confirmar a quién iría."
    ),
    "payment.before_move_in_not_owner": (
        "El anuncio pide renta o depósito antes de la mudanza, "
        "y el propietario registrado no es quien publica."
    ),
    "rule.payment.zelle_before_viewing": "Zelle antes de una visita. Señal de alerta.",
    "rule.payment.wire_before_viewing": (
        "Transferencia bancaria antes de una visita. Señal de alerta."
    ),
    "rule.payment.p2p_app_before_viewing": (
        "Pago por aplicación antes de una visita. Señal de alerta."
    ),
    "rule.payment.gift_card": "Tarjetas de regalo como pago. Señal de alerta.",
    "rule.payment.crypto": "Criptomonedas como pago. Señal de alerta.",
    "rule.payment.overpayment_refund": (
        "Más dinero del que se debe, con la diferencia por devolver. Señal de alerta."
    ),
    "rule.fee.holding_deposit_before_viewing": (
        "Un depósito o cargo de reserva antes de una visita. Señal de alerta."
    ),
    "rule.fee.application_fee_before_viewing": (
        "Un cargo de solicitud enviado a una persona antes de una visita. Señal de alerta."
    ),
    "rule.data.ssn_before_viewing": (
        "Número de SSN (Social Security) antes de una visita. Señal de alerta."
    ),
    "rule.data.bank_login": "Datos de acceso al banco. Señal de alerta.",
    "rule.data.id_before_viewing": (
        "Una foto de su identificación antes de una visita. Señal de alerta."
    ),
    "rule.pressure.cannot_show": (
        "Dicen que no pueden mostrar la unidad en persona. Señal de alerta."
    ),
    "rule.link.payment_link": (
        "Un enlace de pago enviado por quien publicó el anuncio. Señal de alerta."
    ),
    "rule_category.payment_method": (
        "Un pago que no se puede recuperar, pedido antes de una visita. Señal de alerta."
    ),
    "rule_category.fee_ask": "Un cargo a una persona antes de una visita. Señal de alerta.",
    "rule_category.data_ask": (
        "Datos personales o bancarios pedidos antes de una visita. Señal de alerta."
    ),
    "rule_category.pressure": "Presión para decidir rápido. Señal de alerta.",
    "rule_category.link": (
        "Un enlace de pago o de contrato enviado por quien publicó el anuncio. Señal de alerta."
    ),
    "rent.not_checked": "No comprobado (nuestros datos no tienen la renta de este edificio).",
    "rent.within_range": "Acorde con las rentas que figuran en el registro de este edificio.",
    "rent.below_range": (
        "Por debajo de las rentas que figuran en el registro de este edificio. Pregunte por "
        "qué; hay descuentos."
    ),
    "rent.below_floor_plan": (
        "{percent}% por debajo de la renta más baja que figura en el registro de este edificio "
        "para {plan}. Pregunte por qué; hay descuentos."
    ),
    "rent.plan.studio": "un estudio",
    "rent.plan.beds": "{beds} hab.",
    "rent.per_bed": "No comprobado (aquí se cobra por cama, así que la renta no se comparó).",
    "unit.not_on_record": (
        "El registro de este edificio no tiene ninguna unidad con ese número. "
        "Pregunte al administrador que figura en el registro."
    ),
    "unit.beds_mismatch": (
        "El número de habitaciones del anuncio no coincide con el registro de este edificio. "
        "Pregunte al administrador que figura en el registro."
    ),
    "not_checked.id": "identificación",
    "not_checked.lease": "contrato",
    "not_checked.ownership": "propiedad",
    "footer.two_rules": (
        "Dos reglas: nunca pague antes de firmar el contrato y visitar la unidad; nunca pague"
        " por Zelle, transferencia o tarjeta de regalo."
    ),
    "footer.only_trust": (
        "Confíe solo en un resultado de SNAPBACK que usted mismo pidió. SNAPBACK nunca "
        "escribe primero ni pide dinero."
    ),
    # The platforms' menus are quoted as they appear in English.
    "report.pair.elsewhere": "La foto {n} del anuncio se tomó en otra propiedad.",
    "report.platform.facebook": "Facebook Marketplace",
    "report.platform.zillow": "Zillow",
    "report.platform.craigslist": "Craigslist",
    "report.steps.facebook.1": "Abra el anuncio copiado en Facebook Marketplace.",
    "report.steps.facebook.2": (
        'Abra el menú (tres puntos) y elija "Report listing". Elija el motivo para un '
        "anuncio falso o engañoso."
    ),
    "report.steps.facebook.3": "Pegue las líneas de esta página donde le pidan detalles.",
    "report.steps.zillow.1": "Abra el anuncio copiado en Zillow.",
    "report.steps.zillow.2": (
        'Elija "Report listing" y luego "Listing seems to be fraudulent or illegal".'
    ),
    "report.steps.zillow.3": "Pegue las líneas de esta página donde le pidan detalles.",
    "report.steps.craigslist.1": "Abra la publicación copiada en Craigslist.",
    "report.steps.craigslist.2": ('Use la marca "prohibited" que está arriba en la publicación.'),
    "report.steps.craigslist.3": (
        "Para un informe más completo, use el formulario de contacto de Craigslist y pegue "
        "las líneas de esta página."
    ),
    "footer.staged": (
        "Ejemplo preparado. El equipo de SNAPBACK escribió este anuncio para mostrar las "
        "revisiones. No es un anunciante real."
    ),
    "footer.replay": (
        "Repetición de un caso denunciado ({source}, {date}). "
        "El anuncio y la casa están recreados; no hay nombres reales."
    ),
    "challenge.text": (
        "Antes de pagar, pídales que envíen una foto de {spot} con el código {code} escrito "
        "en papel."
    ),
    "trace.checks.twin": "El edificio está en nuestra zona de datos y tiene un gemelo 3D.",
    "trace.checks.no_twin": (
        "No tenemos un escaneo 3D de este edificio, así que solo se puede revisar el texto."
    ),
    "trace.checks.short_term": "Este es un anuncio de estancia corta, que esta revisión no cubre.",
    "trace.checks.commercial": "Este es un anuncio comercial, que esta revisión no cubre.",
    "trace.tool.locate": "Ubicando {count} fotos del anuncio en el gemelo.",
    "trace.floor_plan.best": "{alias}: {best} coincidencias frente a {next}.",
    "trace.floor_plan.only": "Solo hay un plano posible.",
    "trace.floor_plan.unranked": (
        "No se ubicó ninguna foto, así que se usa el primer plano del registro."
    ),
    "trace.spot.draw": "Sorteo al azar entre los {count} mejores.",
    "trace.spot.draw_skipped_one": (
        "Sorteo al azar entre los {count} mejores; se omitió {skipped} porque coincide con "
        "una foto del anuncio."
    ),
    "trace.spot.draw_skipped_many": (
        "Sorteo al azar entre los {count} mejores; se omitieron {skipped} puntos porque "
        "coinciden con fotos del anuncio."
    ),
    "trace.hitl.waiting": (
        "Esperando a que el inquilino apruebe el mensaje. No se envía nada hasta entonces."
    ),
    "trace.hitl.send": "El inquilino aprobó el texto del reto.",
    "trace.reply.waiting": (
        "El mensaje está con el inquilino para que lo pase. Esperando la foto de respuesta "
        "del anunciante."
    ),
    "trace.tool.reply": (
        "Se revisó la foto de respuesta: el código y su parecido con las fotos del anuncio."
    ),
    "trace.hitl.edit": "El inquilino editó el texto del reto y lo aprobó.",
    "trace.hitl.cancel": "El inquilino decidió no enviar un reto.",
    "plan.pick.record": (
        "El registro propio de la vivienda da el rango de renta y quién figura. Leerlo."
    ),
    "plan.pick.record_rent": "El registro propio de la vivienda da el rango de renta. Leerlo.",
    "plan.pick.brokerage": "La vivienda está en venta ahora. Revisar la oficina que la anuncia.",
    "plan.pick.license": "El anuncio menciona una licencia. Buscarla en el estado.",
    "plan.pick.owner": "Hay un propietario en el registro público. Compararlo con quien publica.",
    "plan.pick.claims": (
        "El anuncio afirma cosas que el registro puede responder. Comparar lo que dice el "
        "anuncio con el registro de CoStar de la casa."
    ),
    "plan.pick.ask": (
        "El anuncio dice que tienen licencia pero no da el número. Pedirle el número al inquilino."
    ),
    "plan.ask.question": (
        "El anuncio dice que es agente con licencia pero no da el número de licencia. "
        "¿Puede pedírselo, o pegarlo aquí?"
    ),
    "plan.ask.looked_up": "Se buscó en el estado el número de licencia que usted dio.",
    "plan.ask.no_number": "No llegó ningún número de licencia. La licencia sigue sin comprobarse.",
    "plan.ask.not_looked_up": (
        "No se pudo buscar el número de licencia que usted dio. La licencia sigue sin comprobarse."
    ),
    "plan.skip.ask_off": "preguntar al inquilino no está disponible",
    "plan.skip.ask_none": "el anuncio no dice tener licencia sin dar su número",
    "plan.pick.report": (
        "Se hicieron todas las comprobaciones posibles. Reunir lo encontrado para un informe."
    ),
    "plan.skip.record": "no hay registro de la propiedad que leer",
    "plan.skip.brokerage": "la vivienda no está en venta ahora",
    "plan.skip.license_off": "la búsqueda de licencias no está disponible",
    "plan.skip.license_none": "el anuncio no menciona ninguna licencia que buscar",
    "plan.skip.owner_off": "la búsqueda de propietarios no está disponible",
    "plan.skip.owner_none": "no hay propietario en el registro que leer",
    "plan.skip.claims_off": "aquí no se comparan las afirmaciones del anuncio",
    "plan.skip.claims_none": "nada en el anuncio que el registro responda",
    "plan.skipped": "Omitido {option}: {reason}.",
    "plan.only_option": "Solo había una opción abierta.",
    "trace.retry.accept_both": (
        "Los dos puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.accept": (
        "{matched} de {total} puntos coincidieron, con el código leído y sin aviso de recaptura."
    ),
    "trace.retry.forged": "La respuesta no pasó la revisión, así que no hay nada que reintentar.",
    "trace.retry.code_only": (
        "La respuesta muestra el código. Todavía no se puede comprobar si se tomó en el punto "
        "indicado, así que queda sin confirmar."
    ),
    "trace.retry.again": "No se pudo aceptar la respuesta, así que pedimos otra en un punto nuevo.",
    "trace.retry.late": (
        "La respuesta llegó demasiado tarde para contar, así que pedimos una más en un punto nuevo."
    ),
    "trace.reply.late": (
        "La respuesta llegó después del límite de tiempo. Se comparó con las fotos del "
        "anuncio y no se contó."
    ),
    "trace.retry.stop": (
        "No se pudo aceptar la respuesta y no quedan reintentos, así que el resultado queda "
        "en espera."
    ),
    "trace.error.bad_pick": (
        "El modelo respondió con algo que no estaba en la lista, así que se usó la opción por"
        " defecto."
    ),
    "trace.error.model_failed": "No se pudo usar el modelo, así que se usó la opción por defecto.",
    "trace.agent.todos": "El agente escribió su plan: {count} pasos, {done} hechos.",
    "trace.agent.delegate": (
        "Pasó las comprobaciones de {name} a un subagente que solo ve sus propias "
        "herramientas y escribe lo que encuentra en una nota."
    ),
    "trace.agent.note": "Nota escrita: {path} ({chars} caracteres).",
    "trace.agent.returned": "El subagente de {name} terminó y devolvió lo que encontró.",
    "trace.unsure.inliers": "{photo} no llegó: {n} puntos coincidentes, el mínimo es {bar}.",
    "trace.unsure.ratio": "{photo} no llegó: pocos puntos coincidieron, el mínimo es {bar}.",
    "trace.unsure.spread": "{photo} no llegó: sus puntos cubren muy poco de la foto.",
    "trace.unsure.ambiguity": ("Otro edificio coincidió mucho más, así que {photo} no se ubicó."),
    "trace.place.searched": "{photo}: búsqueda de {option} ({seconds} s). {result}",
    "place.option.focus_scan": "un escaneo más de cerca",
    "place.option.wider_index": "más edificios",
    "place.option.deeper_claimed": "más vistas de este hogar",
    "place.result.placed": "Ubicada.",
    "place.result.not_placed": "Aún no se pudo ubicar.",
    "place.result.elsewhere": "Coincidió con otro edificio.",
    "place.result.skipped": "Omitida.",
    "trace.intake.injection": (
        "El anuncio tiene texto escrito para un sistema de IA. Se ignoró y las revisiones "
        "continúan."
    ),
    "trace.intake.truncated": (
        "El texto que enviaste era muy largo. Solo se leyeron los primeros 20,000 caracteres. "
        "El resto no se revisó."
    ),
    "reason.forged": (
        "La respuesta a la prueba de presencia no era una foto nueva tomada en la unidad."
    ),
    "reason.forged_copy": "La respuesta es una copia de la foto {n} del anuncio.",
    "reason.forged_copy_unknown": "La respuesta es una copia de una de las fotos del anuncio.",
    "reason.photo_elsewhere": "Al menos una foto del anuncio se tomó en otra propiedad.",
    "reason.price_flag": "La renta está muy por debajo de unidades comparables.",
    "reason.payment_flag": "Se pidió un pago antes de cualquier visita.",
    "reason.rule_flag": "Algo en el texto que envió es una señal de alerta.",
    "reason.for_sale": (
        "Esta vivienda está en venta. Confirme con la agencia que la anuncia que también se "
        "ofrece en alquiler."
    ),
    "reason.phone_not_confirmed": (
        "No se demostró que el contacto del anuncio sea la oficina de alquiler que figura en "
        "el registro."
    ),
    "reason.phone_not_confirmed_brokerage": (
        "No tenemos un teléfono de la agencia que anuncia la vivienda, así que no se pudo "
        "comparar el contacto del anuncio."
    ),
    "reason.phone_flag": (
        "El teléfono del anuncio no es el de la oficina de alquiler que figura en el registro."
    ),
    "reason.lookalike_link": "Un enlace del anuncio imita el sitio web del edificio.",
    "reason.license_not_found": (
        "El número de licencia del anuncio no es una licencia activa de Texas."
    ),
    "reason.license_not_found_given": (
        "El número de licencia que usted dio no es una licencia activa de Texas."
    ),
    "reason.owner_not_poster": (
        "Quien publica dice ser el propietario, y el propietario registrado es otro."
    ),
    "reason.unit_flag": "La unidad del anuncio no encaja con el registro de este edificio.",
    "reason.not_indexed": (
        "Esta propiedad no tiene un gemelo 3D en nuestro índice, así que no se pudieron "
        "revisar las fotos."
    ),
    "reason.not_located": "Las fotos no se pudieron ubicar en el gemelo 3D de esta propiedad.",
    "reason.located": "Las fotos se ubicaron en esta propiedad.",
    "reason.authority_matches": (
        "El anuncio nombra al administrador del registro. Cualquiera puede escribir ese nombre."
    ),
    "reason.authority_matches_brokerage": (
        "El anuncio nombra a la agencia que figura en el registro. Cualquiera puede escribir "
        "ese nombre."
    ),
    "reason.office_confirmed": (
        "Confirmado a través de {domain}, el sitio web que CoStar tiene registrado para esta "
        "oficina; las fotos son de este hogar."
    ),
    "reason.authority_unknown": "No pudimos confirmar quién puede alquilar esta unidad.",
    "reason.presence_proven": "Una foto nueva demostró que alguien estaba dentro de la unidad.",
    "reason.presence_proven_not_authority": (
        "Una foto nueva demostró que alguien estaba dentro de la unidad, lo cual no es "
        "autorización."
    ),
    "reason.presence_missing": "Nadie ha demostrado todavía que está dentro de la unidad.",
    "row.place": "LUGAR",
    "row.person": "PERSONA",
    "row.price": "PRECIO",
    # The locked English wording, in Spanish. Same keys, same rule for choosing a row state.
    "tone.ok": "Coincide",
    "tone.hold": "Advertencia",
    "tone.hold.person": "Sin confirmar",
    "tone.red_flag": "No coincide",
    "tone.red_flag.price": "Advertencia",
    "tone.not_shown": "Sin confirmar",
    "tone.not_checked": "No comprobado",
    "state.hold": "Espere por ahora",
    "state.hold_clean": (
        "Todo lo que revisamos coincide con el registro. "
        "Falta un paso antes de pagar: pídales que demuestren que están dentro."
    ),
    "state.dont_pay": "No pague. Algo aquí no coincide.",
    "state.unverified": "No se pudieron ubicar estas fotos",
    "state.verified": "Las revisiones pasaron. Siga igual las dos reglas.",
    "card.case": "Caso {case_id}",
    "card.checked": "Revisado {time}",
    "card.expires": "Vence {time}",
    "card.not_checked": "SNAPBACK no revisó: {items}",
    "card.verify": "Compruebe esta tarjeta usted mismo:",
    "card.source.fixture": "DATOS DE PRUEBA",
    "card.source.live": "EN VIVO",
}

# --- ad vs record: what the ad says and what CoStar's record shows (information only) ---------
# These lines hold no case and set no state. Each says what the ad claims, then what the record
# shows, "as of CoStar's last research". A line that doubts the ad starts "Not confirmed."
# (Spanish: "Sin confirmar."); a line that agrees with it says so plainly and is the only one.
EN.update(
    {
        "row.claims": "WHAT THE AD CLAIMS",
        "label.ad_claim": "Ad vs record",
        "label.ad_pretext": "Ad's explanation",
        "label.aerial": "Aerial photo",
        "claimword.floor_wood": "hardwood floors",
        "claimword.floor_carpet": "carpet",
        "claimword.floor_tile": "tile floors",
        "claimword.floor_laminate": "laminate floors",
        "claimword.washer_dryer": "a washer and dryer",
        "claimword.pool": "a pool",
        "claimword.garage": "a garage or parking",
        "claimword.yard": "a yard",
        "claimword.pets": "pets are allowed",
        "claimword.beds": "{ad_value} bedrooms",
        "claimword.beds_studio": "a studio",
        "claimword.baths": "{ad_value} bathrooms",
        "claimword.sqft": "{ad_value} square feet",
        "claimword.new_management": "new management",
        "claimword.new_ownership": "new ownership",
        "claimword.just_sold": "the home just sold",
        "claimword.owner_away": "the owner is away",
        "claimword.cant_show": "the home can't be shown",
        "kind.wood": "hardwood",
        "kind.carpet": "carpet",
        "kind.tile": "tile",
        "kind.laminate": "laminate or vinyl",
        "kind.hookup": "washer and dryer hookups",
        "kind.machine": "a washer and dryer",
        "kind.room": "a laundry room",
        "list.and": " and ",
        "claims.floor_photos": (
            "Not confirmed. The ad says {claim}. CoStar's photos of this home are labelled "
            "{record} (as of CoStar's last research)."
        ),
        "claims.floor_listing": (
            "Not confirmed. The ad says {claim}. CoStar's listing features for this home name "
            "{record} floors (as of CoStar's last research)."
        ),
        "claims.floor_match": (
            "The ad says {claim}. CoStar's record of this home also names {record} floors "
            "(as of CoStar's last research)."
        ),
        "claims.wd_listing": (
            "Not confirmed. The ad says {claim}. CoStar's listing features for this home list "
            "{record}, not a washer or dryer (as of CoStar's last research)."
        ),
        "claims.wd_match": (
            "The ad says {claim}. CoStar's listing features for this home list one "
            "(as of CoStar's last research)."
        ),
        "claims.pool_none": (
            "Not confirmed. The ad says {claim}. CoStar's record of this home does not list or "
            "show a pool (as of CoStar's last research)."
        ),
        "claims.pool_match": (
            "The ad says {claim}. CoStar's record of this home shows one "
            "(as of CoStar's last research)."
        ),
        "claims.parking_none": (
            "Not confirmed. The ad says {claim}. CoStar's record shows no parking spaces for "
            "this home (as of CoStar's last research)."
        ),
        "claims.parking_match": (
            "The ad says {claim}. CoStar's record of this home shows parking spaces "
            "(as of CoStar's last research)."
        ),
        "claims.parking_ratio_match": (
            "The ad says {claim}. CoStar's record of this building shows parking, about "
            "{record_value} spaces per unit (as of CoStar's last research)."
        ),
        "claims.aerial_date": (
            "Not checked. An aerial photo of this property from {ad_value} (Vexcel) is on file; "
            "nothing is read from it."
        ),
        "claims.yard_match": (
            "The ad says {claim}. CoStar's record of this home shows one "
            "(as of CoStar's last research)."
        ),
        "claims.pets_no": (
            "Not confirmed. The ad says {claim}. CoStar's record of this home says pets are not "
            "allowed (as of CoStar's last research)."
        ),
        "claims.pets_match": (
            "The ad says {claim}. CoStar's record of this home agrees (as of CoStar's last "
            "research)."
        ),
        "claims.beds_differ": (
            "Not confirmed. The ad says {claim}. CoStar's record of this home shows "
            "{record_value} (as of CoStar's last research)."
        ),
        "claims.beds_match": (
            "The ad says {claim}. CoStar's record of this home agrees (as of CoStar's last "
            "research)."
        ),
        "claims.baths_differ": (
            "Not confirmed. The ad says {claim}. CoStar's record of this home shows "
            "{record_value} (as of CoStar's last research)."
        ),
        "claims.baths_match": (
            "The ad says {claim}. CoStar's record of this home agrees (as of CoStar's last "
            "research)."
        ),
        "claims.sqft_differ": (
            "Not confirmed. The ad says {claim}. CoStar's record of this home shows "
            "{record_value} square feet (as of CoStar's last research)."
        ),
        "claims.sqft_match": (
            "The ad says {claim}. CoStar's record of this home agrees (as of CoStar's last "
            "research)."
        ),
        "claims.manager_same": (
            "Not confirmed. The ad says {claim}. CoStar's record shows the same property "
            "manager since {year} (as of CoStar's last research)."
        ),
        "claims.manager_new": (
            "The ad says {claim}. CoStar's record shows a property manager starting in {year} "
            "(as of CoStar's last research)."
        ),
        "claims.sale_none": (
            "Not confirmed. The ad says {claim}. CoStar's record shows no sale in the last 12 "
            "months (as of CoStar's last research)."
        ),
        "claims.sale_older": (
            "Not confirmed. The ad says {claim}. CoStar's record shows the last sale in {year}, "
            "not in the last 12 months (as of CoStar's last research)."
        ),
        "claims.sale_recent": (
            "The ad says {claim}. CoStar's record shows a sale in {year} "
            "(as of CoStar's last research)."
        ),
        "claims.office_listed": (
            "Not confirmed. The ad says {claim}. CoStar's record lists a leasing office for "
            "this property (as of CoStar's last research). Ask the office to show the home."
        ),
    }
)
ES.update(
    {
        "row.claims": "LO QUE DICE EL ANUNCIO",
        "label.ad_claim": "Anuncio frente al registro",
        "label.ad_pretext": "Explicación del anuncio",
        "label.aerial": "Foto aérea",
        "claimword.floor_wood": "pisos de madera",
        "claimword.floor_carpet": "alfombra",
        "claimword.floor_tile": "pisos de azulejo",
        "claimword.floor_laminate": "pisos laminados",
        "claimword.washer_dryer": "lavadora y secadora",
        "claimword.pool": "piscina",
        "claimword.garage": "cochera o estacionamiento",
        "claimword.yard": "patio o jardín",
        "claimword.pets": "se aceptan mascotas",
        "claimword.beds": "{ad_value} recámaras",
        "claimword.beds_studio": "un estudio",
        "claimword.baths": "{ad_value} baños",
        "claimword.sqft": "{ad_value} pies cuadrados",
        "claimword.new_management": "nueva administración",
        "claimword.new_ownership": "nuevos dueños",
        "claimword.just_sold": "la casa se acaba de vender",
        "claimword.owner_away": "el dueño está fuera",
        "claimword.cant_show": "no se puede mostrar la casa",
        "kind.wood": "madera",
        "kind.carpet": "alfombra",
        "kind.tile": "azulejo",
        "kind.laminate": "laminado o vinilo",
        "kind.hookup": "conexiones para lavadora y secadora",
        "kind.machine": "lavadora y secadora",
        "kind.room": "un cuarto de lavandería",
        "list.and": " y ",
        "claims.floor_photos": (
            "Sin confirmar. El anuncio dice {claim}. Las fotos de esta casa en CoStar están "
            "etiquetadas como {record} (según la última investigación de CoStar)."
        ),
        "claims.floor_listing": (
            "Sin confirmar. El anuncio dice {claim}. Las características del anuncio de esta "
            "casa en CoStar indican pisos de {record} (según la última investigación de CoStar)."
        ),
        "claims.floor_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa también indica pisos "
            "de {record} (según la última investigación de CoStar)."
        ),
        "claims.wd_listing": (
            "Sin confirmar. El anuncio dice {claim}. Las características del anuncio de esta "
            "casa en CoStar indican {record}, no una lavadora ni una secadora (según la última "
            "investigación de CoStar)."
        ),
        "claims.wd_match": (
            "El anuncio dice {claim}. Las características del anuncio de esta casa en CoStar "
            "indican que hay (según la última investigación de CoStar)."
        ),
        "claims.pool_none": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar de esta casa no indica "
            "ni muestra una piscina (según la última investigación de CoStar)."
        ),
        "claims.pool_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa muestra una "
            "(según la última investigación de CoStar)."
        ),
        "claims.parking_none": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar no muestra lugares "
            "de estacionamiento para esta casa (según la última investigación de CoStar)."
        ),
        "claims.parking_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa muestra lugares de "
            "estacionamiento (según la última investigación de CoStar)."
        ),
        "claims.parking_ratio_match": (
            "El anuncio dice {claim}. El registro de CoStar de este edificio muestra "
            "estacionamiento, unos {record_value} lugares por unidad (según la última "
            "investigación de CoStar)."
        ),
        "claims.aerial_date": (
            "No comprobado. Hay una foto aérea de esta propiedad del {ad_value} (Vexcel) en el "
            "archivo; no se lee nada de ella."
        ),
        "claims.yard_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa muestra uno "
            "(según la última investigación de CoStar)."
        ),
        "claims.pets_no": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar de esta casa dice que "
            "no se permiten mascotas (según la última investigación de CoStar)."
        ),
        "claims.pets_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa coincide "
            "(según la última investigación de CoStar)."
        ),
        "claims.beds_differ": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar de esta casa muestra "
            "{record_value} (según la última investigación de CoStar)."
        ),
        "claims.beds_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa coincide "
            "(según la última investigación de CoStar)."
        ),
        "claims.baths_differ": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar de esta casa muestra "
            "{record_value} (según la última investigación de CoStar)."
        ),
        "claims.baths_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa coincide "
            "(según la última investigación de CoStar)."
        ),
        "claims.sqft_differ": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar de esta casa muestra "
            "{record_value} pies cuadrados (según la última investigación de CoStar)."
        ),
        "claims.sqft_match": (
            "El anuncio dice {claim}. El registro de CoStar de esta casa coincide "
            "(según la última investigación de CoStar)."
        ),
        "claims.manager_same": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar muestra al mismo "
            "administrador desde {year} (según la última investigación de CoStar)."
        ),
        "claims.manager_new": (
            "El anuncio dice {claim}. El registro de CoStar muestra un administrador que empezó "
            "en {year} (según la última investigación de CoStar)."
        ),
        "claims.sale_none": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar no muestra ninguna "
            "venta en los últimos 12 meses (según la última investigación de CoStar)."
        ),
        "claims.sale_older": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar muestra la última "
            "venta en {year}, no en los últimos 12 meses (según la última investigación de "
            "CoStar)."
        ),
        "claims.sale_recent": (
            "El anuncio dice {claim}. El registro de CoStar muestra una venta en {year} "
            "(según la última investigación de CoStar)."
        ),
        "claims.office_listed": (
            "Sin confirmar. El anuncio dice {claim}. El registro de CoStar muestra una oficina "
            "de arrendamiento para esta propiedad (según la última investigación de CoStar). "
            "Pida a la oficina que le muestre la casa."
        ),
    }
)

EN.update(
    {
        "real.as_of": "as of CoStar's last research",
        "real.plan_studio": "studio",
        "real.plan_beds": "{beds}-bed",
        "real.plan_unnamed": "matching floor plan",
        "real.ad_rent": "The ad asks {ad_rent} a month.",
        "real.ad_no_rent": "The ad's rent could not be read.",
        "real.ad_irreversible": (
            "It asks for a payment that cannot be taken back, before a viewing."
        ),
        "real.range": "{low} to {high}",
        "real.record_one": (
            "Its Apartments.com listing on CoStar's record says {band} a month for a {plan}."
        ),
        "real.record_many": (
            "Its Apartments.com listing on CoStar's record says {band} a month across "
            "{n} matching floor plans."
        ),
        "real.record_hidden": (
            "CoStar's record has this building's Apartments.com listing; its rent figures "
            "are not shown here."
        ),
        "real.record_no_rent": "CoStar's record has no rent for a matching floor plan.",
        "real.record_no_plan": (
            "CoStar's record has this building, with no whole-unit floor plan that matches the ad."
        ),
        "real.managed_by": "Managed by {company}.",
        "real.website": "Its own website: {host}.",
        "real.provenance_scan": (
            "{n} of {m} of the ad's photos are in CoStar's own scan of this building."
        ),
        "real.provenance_elsewhere": (
            "{n} of {m} of the ad's photos are in CoStar's scan of a different building "
            "than the one the ad names."
        ),
        "real.provenance_none": (
            "None of the ad's {m} photos could be placed in CoStar's scan of this building."
        ),
        "real.phone_office": "The ad's number is the office's on record.",
        "real.phone_not_office": "The ad's number is not the office's on record.",
        "real.cta": "See the real listing",
        "real.no_record": "CoStar has no record of the building this ad names.",
        "copy.subject": "An ad using photos of your building was checked",
        "copy.to_company": "To the leasing office at {company},",
        "copy.to_office": "To the leasing office,",
        "copy.photos_claimed": (
            "SNAPBACK checked an ad today. {n} of its {m} photos sit in CoStar's own 3D scan "
            "of your building."
        ),
        "copy.photos_matched": (
            "SNAPBACK checked an ad today. {n} of its {m} photos sit in CoStar's own 3D scan "
            "of your building, though the ad names a different one."
        ),
        "copy.phone_not_office": "The number in the ad is not the office's number on record.",
        "copy.rent_under": "Its asked rent is {percent}% under your listed plan.",
        "copy.ask": (
            "This may be a copy of your listing, or an agent you work with. Please confirm "
            "whether you posted it."
        ),
        "copy.report_line": "If you did not, the {report} for this check shows where to report it.",
        "copy.report_name": "evidence pack",
        "copy.draft_only": "This is a draft. Nothing has been sent.",
        "handoff.listing": "Its listing on Apartments.com",
        "handoff.site": "The building's own site",
        "summary.price_gap": "The rent is {percent}% under this building's {plan} listing.",
        "summary.price_gap_any": "The rent is {percent}% under this building's listings.",
    }
)

ES.update(
    {
        "real.as_of": "según la última investigación de CoStar",
        "real.plan_studio": "estudio",
        "real.plan_beds": "de {beds} dormitorios",
        "real.plan_unnamed": "plano que coincide",
        "real.ad_rent": "El anuncio pide {ad_rent} al mes.",
        "real.ad_no_rent": "No se pudo leer el alquiler del anuncio.",
        "real.ad_irreversible": (
            "Pide un pago que no se puede recuperar, antes de cualquier visita."
        ),
        "real.range": "{low} a {high}",
        "real.record_one": (
            "Su anuncio en Apartments.com, en el registro de CoStar, dice {band} al mes "
            "por un plano {plan}."
        ),
        "real.record_many": (
            "Su anuncio en Apartments.com, en el registro de CoStar, dice {band} al mes "
            "en {n} planos que coinciden."
        ),
        "real.record_hidden": (
            "El registro de CoStar tiene el anuncio de este edificio en Apartments.com; "
            "aquí no se muestran sus cifras de alquiler."
        ),
        "real.record_no_rent": (
            "El registro de CoStar no tiene alquiler para un plano que coincida."
        ),
        "real.record_no_plan": (
            "El registro de CoStar tiene este edificio, sin un plano de unidad completa que "
            "coincida con el anuncio."
        ),
        "real.managed_by": "Administrado por {company}.",
        "real.website": "Su sitio web: {host}.",
        "real.provenance_scan": (
            "{n} de {m} fotos del anuncio están en el escaneo propio de CoStar de este edificio."
        ),
        "real.provenance_elsewhere": (
            "{n} de {m} fotos del anuncio están en el escaneo de CoStar de un edificio "
            "distinto al que nombra el anuncio."
        ),
        "real.provenance_none": (
            "Ninguna de las {m} fotos del anuncio se pudo ubicar en el escaneo de CoStar "
            "de este edificio."
        ),
        "real.phone_office": "El número del anuncio es el de la oficina en el registro.",
        "real.phone_not_office": "El número del anuncio no es el de la oficina en el registro.",
        "real.cta": "Ver el anuncio real",
        "real.no_record": "CoStar no tiene registro del edificio que nombra este anuncio.",
        "copy.subject": "Se revisó un anuncio que usa fotos de su edificio",
        "copy.to_company": "A la oficina de arrendamiento de {company}:",
        "copy.to_office": "A la oficina de arrendamiento:",
        "copy.photos_claimed": (
            "SNAPBACK revisó hoy un anuncio. {n} de sus {m} fotos están en el escaneo 3D "
            "propio de CoStar de su edificio."
        ),
        "copy.photos_matched": (
            "SNAPBACK revisó hoy un anuncio. {n} de sus {m} fotos están en el escaneo 3D "
            "propio de CoStar de su edificio, aunque el anuncio nombra otro."
        ),
        "copy.phone_not_office": "El número del anuncio no es el de la oficina en el registro.",
        "copy.rent_under": "La renta que pide está {percent}% por debajo de su plano publicado.",
        "copy.ask": (
            "Puede ser una copia de su anuncio, o de un agente con quien trabajan. Confirme "
            "si lo publicaron."
        ),
        "copy.report_line": "Si no fue así, el {report} de esta revisión muestra dónde reportarlo.",
        "copy.report_name": "paquete de evidencia",
        "copy.draft_only": "Este es un borrador. No se ha enviado nada.",
        "handoff.listing": "Su anuncio en Apartments.com",
        "handoff.site": "El sitio del propio edificio",
        "summary.price_gap": (
            "La renta está {percent}% por debajo de lo que el edificio anuncia para {plan}."
        ),
        "summary.price_gap_any": (
            "La renta está {percent}% por debajo de los anuncios de este edificio."
        ),
    }
)

TABLES: dict[str, dict[str, str]] = {DEFAULT_LANG: EN, "es": ES}


def _table(lang: str) -> dict[str, str]:
    return TABLES.get(lang, TABLES[DEFAULT_LANG])


def has(key: str, lang: str = DEFAULT_LANG) -> bool:
    return key in _table(lang)


def text(key: str, lang: str = DEFAULT_LANG, **values: object) -> str:
    """The wording for `key`, with `{placeholders}` filled in. A missing key is a bug: KeyError."""
    return _table(lang)[key].format(**values)


def tone_word(tone: str, row: str, lang: str = DEFAULT_LANG) -> str:
    """The locked word shown beside a card line: its row state.

    One word per tone, except where the row changes what the tone means. A red flag on the
    PRICE row is a risky ask ("Warning"); on PLACE or PERSON it is something that contradicts
    the listing ("Doesn't match"). A hold on the PERSON row is someone not heard from yet
    ("Not confirmed"); elsewhere it is something to ask about ("Warning"). `tone` and `row`
    are the values of `CardTone` and `CardRowKind`.
    """
    by_row = f"tone.{tone}.{row}"
    return text(by_row if has(by_row, lang) else f"tone.{tone}", lang)
