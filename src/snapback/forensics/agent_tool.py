"""Optional: the investigator as a deepagents tool.

Needs the `agent` extra (`uv sync --extra agent`) and an ANTHROPIC_API_KEY in the environment;
nothing else in the package imports this module, and `investigator.ask` works without it. The
model gets ONE tool, `ask_graph`, which returns the fixture-mode answer as JSON (answer, evidence
pointers). The model writes the reply from that JSON; `ask_with_model` then runs the same check
as the fixture path: the reply must cite at least one ad id the tool returned, and any ad id it
names must exist. If not, the fixture answer is shown instead. The model never sees raw ads.

Not exercised in CI: it needs a key and spends tokens. The fixture mode is what the tests cover.
"""

import json
import re
from typing import Any

from snapback.forensics.investigator import Answer, ask, verify_answer
from snapback.forensics.pipeline import Analysis, default_analysis

SYSTEM_PROMPT = """\
You are an investigator's assistant over a corpus of SYNTHETIC rental ads. You have one tool,
`ask_graph`, that answers a question from the evidence graph and returns the answer with the
ad ids, sentences and photo ids behind it. Answer ONLY from what the tool returns. Cite ad ids
as "ad N". If the tool says there is no evidence, say so and stop. Never guess, never name a
person, never add facts."""


def ask_graph_json(question: str, analysis: Analysis | None = None) -> str:
    analysis = analysis or default_analysis()
    return ask(analysis, question).model_dump_json()


def build_agent(model: str = "claude-opus-5-5") -> Any:
    from deepagents import create_deep_agent  # imported late: the extra may be absent
    from langchain_core.tools import tool

    @tool
    def ask_graph(question: str) -> str:
        """Answer a question about the synthetic ad corpus from the evidence graph."""
        return ask_graph_json(question)

    return create_deep_agent(model=model, tools=[ask_graph], system_prompt=SYSTEM_PROMPT)


def accept_model_reply(analysis: Analysis, base: Answer, reply: str) -> Answer:
    """Keep the model's wording only if it stays inside the evidence the tool returned."""
    cited = {int(n) for n in re.findall(r"\bads?\s+#?(\d+)", reply, re.IGNORECASE)}
    allowed = {e.ad_id for e in base.evidence}
    if not verify_answer(analysis, base):
        return base
    if base.grounded and (not cited or not cited <= allowed):
        return base
    if not base.grounded and cited:
        return base
    return base.model_copy(update={"answer": reply.strip(), "mode": "model"})


def ask_with_model(question: str, analysis: Analysis | None = None) -> Answer:
    analysis = analysis or default_analysis()
    base = ask(analysis, question)
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    reply = result["messages"][-1].content
    if isinstance(reply, list):
        reply = " ".join(part.get("text", "") for part in reply if isinstance(part, dict))
    return accept_model_reply(analysis, base, str(reply))


def tool_schema() -> dict[str, Any]:
    """The tool contract, for docs and tests."""
    return json.loads(json.dumps({"name": "ask_graph", "args": {"question": "string"}}))
