"""The staged case for the A24 stretch: the agent asks the renter for a license number.

A house for sale is posted by someone who says they are a licensed agent and gives no number.
A name never gives "Doesn't match" (D10), so the license line can only say "ask for it". The
agent does that: it asks the renter, the renter answers with the number the poster sent, and
only the license lookup runs again. Synthetic throughout: `fx-` ids, 555-010-01xx phones, a
fixture stand-in for the state's list (`fixtures/demo-ask/case.json`, `trec_numbers`).

    uv run python -m snapback.agent.demo_ask            # the card before and after the answer
    uv run python -m snapback.agent.demo_ask 5550100    # answer with another number
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from snapback.agent.demo import staged
from snapback.agent.intake import read_listing
from snapback.agent.modules import FixtureModules
from snapback.agent.runner import PolicyChooser, run_case
from snapback.agent.session import CaseSession
from snapback.agent.trace import Trace
from snapback.card import strings
from snapback.contracts import Card, DataSource, ForSaleMatch, LicenseResult, TraceEvent, Verdict
from snapback.verdict import build_card

ASK_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "demo-ask"
CASE_ID = "fx-demo-ask"


@dataclass(frozen=True)
class AskDemo:
    question: str  # what the renter was asked, a code string
    before: Card  # the card while the case waits for the answer
    after: Card
    verdict: Verdict
    trace: list[TraceEvent]


def ask_modules() -> FixtureModules:
    about = json.loads((ASK_DIR / "case.json").read_text())
    listing = read_listing((ASK_DIR / "listing.txt").read_text())
    return FixtureModules(
        evidence_file="module_evidence.json",
        fixtures_dir=ASK_DIR,
        listing_scope=listing.scope,
        rules=listing.rule_hits,
        listed_rent=listing.listed_rent,
        contacts=listing.contacts,
        unit=listing.unit,
        beds=listing.beds,
        for_sale=ForSaleMatch.model_validate(about["for_sale"]),
        license=LicenseResult.model_validate(about["license"]),
        trec_numbers={
            number: LicenseResult.model_validate(found)
            for number, found in about["trec_numbers"].items()
        },
    )


def staged_answer() -> str:
    return json.loads((ASK_DIR / "case.json").read_text())["renter_answer"]


def run_ask_demo(answer: str | None = None, *, lang: str = strings.DEFAULT_LANG) -> AskDemo:
    """Run the case to the question, then answer it (the staged answer unless one is given)."""
    session = CaseSession(CASE_ID, ask_modules(), Trace(CASE_ID, DataSource.FIXTURE), lang=lang)
    approve = lambda draft: "send"  # noqa: E731
    assert run_case(session, PolicyChooser(), approve) is None and session.waiting_for_answer
    question = session.question or ""
    before = staged(build_card(session.evidence, lang=lang))
    session.answer(staged_answer() if answer is None else answer)
    verdict = run_case(session, PolicyChooser(), approve)
    assert verdict is not None
    return AskDemo(
        question,
        before,
        staged(build_card(session.evidence, lang=lang)),
        verdict,
        list(session.trace.events),
    )


def _print(title: str, card: Card) -> None:
    print(f"\n{title}")
    for row in card.rows:
        for line in row.lines:
            if line.label in {"License", "Real"}:
                print(f"    {row.kind.value.upper():6} {line.label}: {line.text}")


def main() -> None:
    demo = run_ask_demo(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"Question for the renter: {demo.question}")
    _print("Card before the answer:", demo.before)
    _print(f"Card after the answer ({demo.verdict.state.value.upper()}):", demo.after)
    print("\nTrace:")
    for event in demo.trace:
        by = f" [{event.chosen_by}]" if event.chosen_by else ""
        print(f"    {event.kind.value:7}{by} {event.reason}")


if __name__ == "__main__":
    main()
