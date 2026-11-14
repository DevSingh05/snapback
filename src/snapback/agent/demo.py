"""The staged demo cases (A9, issue #73): three listings that each run end to end to a card.

In the demo the poster is staged (the listing text is ours) and the records are real, read
from the sponsor kit at run time. What is in `fixtures/demo/` is the staged listing plus a
synthetic stand-in for everything else, so the same three cases run with no kit and nothing
of the sponsor's is in git.

    a  everything about the poster is off, and the reply is a copy of a listing photo
    b  the same listing, with one photo taken in another building
    c  a house that is for sale, posted as a rental

`DEMO_CASE=a` (or b, c) makes the API use that case's stand-ins for every new check.
`uv run python -m snapback.agent.demo` prints all three cards.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from snapback.agent.intake import Listing, read_listing
from snapback.agent.modules import FixtureModules
from snapback.agent.runner import PolicyChooser, run_case
from snapback.agent.session import CaseSession
from snapback.agent.trace import Trace
from snapback.card import strings
from snapback.contracts import Card, DataSource, ForSaleMatch, Verdict
from snapback.replays import replay_for_case, replay_note
from snapback.verdict import build_card

DEMO_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "demo"


@dataclass(frozen=True)
class DemoCase:
    case_id: str  # "a", "b" or "c"
    title: str
    listing_text: str  # the staged poster's message, as a renter would paste it
    folder: Path
    for_sale: ForSaleMatch | None


def demo_case_ids() -> list[str]:
    return sorted(path.parent.name for path in DEMO_DIR.glob("*/case.json"))


def load_demo_case(case_id: str) -> DemoCase:
    known = demo_case_ids()
    if case_id not in known:
        raise LookupError(f"No demo case {case_id!r}. The cases are: {', '.join(known)}.")
    folder = DEMO_DIR / case_id
    about = json.loads((folder / "case.json").read_text())
    for_sale = ForSaleMatch.model_validate(about["for_sale"]) if about.get("for_sale") else None
    return DemoCase(
        case_id=case_id,
        title=about["title"],
        listing_text=(folder / "listing.txt").read_text(),
        folder=folder,
        for_sale=for_sale,
    )


def demo_modules(case: DemoCase, listing: Listing) -> FixtureModules:
    """The case's stand-ins for the twin, the record and the challenge.

    What the listing itself says (its asks, its rent, its unit, its contacts) is read by the
    same code as any other listing, and replaces nothing here.
    """
    return FixtureModules(
        evidence_file="module_evidence.json",
        fixtures_dir=case.folder,
        record_file="property_record.json",
        listing_scope=listing.scope,
        rules=listing.rule_hits,
        listed_rent=listing.listed_rent,
        contacts=listing.contacts,
        unit=listing.unit,
        beds=listing.beds,
        for_sale=case.for_sale,
    )


def staged(card: Card, demo_case_id: str | None = None) -> Card:
    """The same card, saying first in its footer that it is a staged example. A replay of a
    reported case says instead what it replays: the source and its date."""
    replay = replay_for_case(demo_case_id) if demo_case_id else None
    note = (replay and replay_note(replay, card.lang)) or strings.text("footer.staged", card.lang)
    return card.model_copy(update={"footer": [note, *card.footer]})


def run_demo_case(
    case_id: str, *, lang: str = strings.DEFAULT_LANG, checked_at: datetime | None = None
) -> tuple[Verdict, Card]:
    """Run one staged case from its listing to its card, approving the challenge as drafted."""
    case = load_demo_case(case_id)
    listing = read_listing(case.listing_text)
    full_id = f"fx-demo-{case_id}"
    session = CaseSession(full_id, demo_modules(case, listing), Trace(full_id, DataSource.FIXTURE))
    verdict = run_case(session, PolicyChooser(), lambda draft: "send")
    assert verdict is not None  # an approver was given, so the run cannot pause
    return verdict, staged(build_card(session.evidence, checked_at=checked_at, lang=lang), case_id)


def main() -> None:
    for case_id in demo_case_ids():
        case = load_demo_case(case_id)
        verdict, card = run_demo_case(case_id)
        print(f"\n({case_id}) {case.title}  [FIXTURE, staged example]")
        print(f"    {verdict.state.value.upper()}: {' '.join(verdict.reasons)}")
        for row in card.rows:
            for line in row.lines:
                print(f"    {row.kind.value.upper():6} {line.label}: {line.text}")


if __name__ == "__main__":
    main()
