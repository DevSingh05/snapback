"""E5: the trace bridge. Every todo, hand-off and file on the rail comes from one event in the
agent's stream, and an event is never made up. A stub model drives a real deepagents run."""

from snapback.agent import graph
from snapback.contracts import TraceKind
from test_agent_subagents import CHECK_AGENTS, demo_session, run_with_crew

BRIDGED = (TraceKind.TODO, TraceKind.AGENT, TraceKind.FILE)


def run_and_record(session):
    """Run the case, keeping every stream chunk the watcher was shown."""
    chunks: list[dict] = []
    real = graph.RunWatch.update

    def spy(self, chunk):
        chunks.append(chunk)
        return real(self, chunk)

    graph.RunWatch.update = spy
    try:
        run_with_crew(session)
    finally:
        graph.RunWatch.update = real
    return chunks


def calls_in(chunks, name):
    out = []
    for chunk in chunks:
        for update in chunk.values():
            for part in update if isinstance(update, list) else [update]:
                if not isinstance(part, dict):
                    continue
                for message in part.get("messages") or []:
                    out += [
                        c for c in getattr(message, "tool_calls", None) or [] if c["name"] == name
                    ]
    return out


def files_in(chunks):
    seen = set()
    for chunk in chunks:
        for update in chunk.values():
            for part in update if isinstance(update, list) else [update]:
                if isinstance(part, dict) and isinstance(part.get("files"), dict):
                    seen |= set(part["files"])
    return seen


def test_every_rail_item_maps_to_one_stream_event_and_back():
    session = demo_session("a")
    chunks = run_and_record(session)
    events = [e for e in session.trace.events if e.kind in BRIDGED]

    todos = [e for e in events if e.kind is TraceKind.TODO]
    assert len(todos) == len(calls_in(chunks, "write_todos")) == 1

    started = [e.pick for e in events if e.kind is TraceKind.AGENT and "done" not in e.pick]
    returned = [e.pick for e in events if e.kind is TraceKind.AGENT and "done" in e.pick]
    asked = [f"sub-agent: {c['args']['subagent_type']}" for c in calls_in(chunks, "task")]
    assert started == asked and len(returned) == len(asked) == len(CHECK_AGENTS)

    written = {e.pick.removeprefix("file: ") for e in events if e.kind is TraceKind.FILE}
    assert written and written <= files_in(chunks)  # no file on the rail the stream did not carry


def test_no_bridged_event_without_a_tool_call_in_the_stream():
    session = demo_session("b")
    chunks = run_and_record(session)
    bridged = [e for e in session.trace.events if e.kind in BRIDGED]
    budget = (
        len(calls_in(chunks, "write_todos"))
        + 2 * len(calls_in(chunks, "task"))
        + len(files_in(chunks))
    )
    assert 0 < len(bridged) <= budget


def test_a_run_with_no_model_puts_nothing_on_the_rail():
    from snapback.agent import PolicyChooser, run_case

    session = demo_session("a")
    run_case(session, PolicyChooser(), lambda draft: "send")
    assert not [e for e in session.trace.events if e.kind in BRIDGED]
