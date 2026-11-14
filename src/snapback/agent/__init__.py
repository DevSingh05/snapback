"""Agent orchestration: plans a case, runs the checks, pauses for the renter's approval.

Owner: lane A.

- `session.py`: one case as a bounded sequence of choices, with the option set for each.
- `runner.py`: drives a case with a chooser (a model, or the code policy).
- `modules.py`: what the agent calls for evidence, and the fixture-backed stand-in.
- `scope.py`: whether a listing is a rental, a short-term stay or a commercial space.
- `trace.py`: the trace events the web app streams.
- `rules/`: code-owned rules over the renter's own text.
- `graph.py`: the deepagents wiring. It is not imported here, so this package works without the
  `agent` extra installed.
"""

from snapback.agent.modules import ChallengeOutcome, FixtureModules, Modules
from snapback.agent.runner import Approver, Chooser, PolicyChooser, run_case
from snapback.agent.scope import ListingScope, detect_scope
from snapback.agent.session import MAX_RETRIES, CaseSession, ChallengeDraft, Offer, Step
from snapback.agent.trace import Trace, clean_reason

__all__ = [
    "MAX_RETRIES",
    "Approver",
    "CaseSession",
    "ChallengeDraft",
    "ChallengeOutcome",
    "Chooser",
    "FixtureModules",
    "ListingScope",
    "Modules",
    "Offer",
    "PolicyChooser",
    "Step",
    "Trace",
    "clean_reason",
    "detect_scope",
    "run_case",
]
