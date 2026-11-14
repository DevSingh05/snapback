"""The investigator: answers questions about the case from the link graph, and only from it.

Every answer is built from graph lookups and carries its evidence: ad ids, the matched sentence
(verbatim from the ad), photo ids, numbers, dates. A question the graph cannot answer gets the
plain reply that there is no evidence, with no evidence attached, and `grounded` false. Nothing
here calls a model; `agent_tool.py` offers the same functions to a deepagents agent, and
`verify_answer` is the check a model-written answer must pass before it is shown.
"""

import re

from pydantic import BaseModel, Field

from snapback.forensics.pipeline import Analysis
from snapback.forensics.rings import Evidence, Ring

NO_EVIDENCE = "I have no evidence in the graph for that."
EXAMPLES = [
    "Which ads share photos with ad {ad}?",
    "Which ring is ad {ad} in?",
    "When did ring {ring} start?",
    "What numbers does ring {ring} use?",
    "How does ring {ring} ask for money?",
    "Where were the photos in ad {ad} copied from?",
    "List the rings.",
]

_AD = re.compile(r"\b(?:ad|listing|posting)\s*#?\s*(\d{1,5})\b", re.IGNORECASE)
_RING = re.compile(r"\bring\s+([A-Za-z])\b", re.IGNORECASE)


class Answer(BaseModel):
    question: str
    answer: str
    grounded: bool  # true only when at least one evidence pointer backs it
    intent: str
    evidence: list[Evidence] = Field(default_factory=list)
    mode: str = "fixture"  # fixture: no model was involved
    synthetic: bool = True


def _ids(question: str) -> tuple[int | None, str | None]:
    ad = _AD.search(question)
    ring = _RING.search(question)
    return (int(ad.group(1)) if ad else None, ring.group(1).upper() if ring else None)


def _none(question: str, intent: str, why: str = NO_EVIDENCE) -> Answer:
    return Answer(question=question, answer=why, grounded=False, intent=intent)


def _ad_line(analysis: Analysis, ad_id: int) -> str:
    ad = analysis.graph.ads[ad_id]
    return f"ad {ad_id} ({ad.posted_at}, {ad.phone})"


def shared_photos(analysis: Analysis, question: str, ad_id: int) -> Answer:
    graph = analysis.graph
    if ad_id not in graph.ads:
        return _none(question, "shared_photos", f"There is no ad {ad_id} in this corpus.")
    others: dict[int, list[str]] = {}
    for node, ads in graph.photo_ads().items():
        if ad_id in ads:
            for other in ads:
                if other != ad_id:
                    others.setdefault(other, []).append(node)
    if not others:
        return Answer(
            question=question,
            answer=f"No other ad shares a photo-set with ad {ad_id}.",
            grounded=True,
            intent="shared_photos",
            evidence=[Evidence(ad_id=ad_id, photo_ids=sorted(graph.ads[ad_id].photos))],
        )
    evidence = [Evidence(ad_id=ad_id, photo_ids=sorted(graph.ads[ad_id].photos))]
    for other, nodes in sorted(others.items()):
        ids = [p for n in nodes for p in graph.ad_photos[other][n]]
        evidence.append(Evidence(ad_id=other, photo_ids=sorted(ids)))
    text = "; ".join(
        f"{_ad_line(analysis, o)} on {len(n)} photo-set(s)" for o, n in sorted(others.items())
    )
    return Answer(
        question=question,
        answer=f"{len(others)} ad(s) share photos with ad {ad_id}: {text}.",
        grounded=True,
        intent="shared_photos",
        evidence=evidence,
    )


def ring_of_ad(analysis: Analysis, question: str, ad_id: int) -> Answer:
    if ad_id not in analysis.graph.ads:
        return _none(question, "ring_of_ad", f"There is no ad {ad_id} in this corpus.")
    ad = analysis.graph.ads[ad_id]
    ring = analysis.ring_of(ad_id)
    spans = [
        Evidence(
            ad_id=ad_id, span=link.sentence, rule_id=None if link.why == "concept" else link.why
        )
        for link in analysis.graph.phrase_links.get(ad_id, [])
    ]
    if ring is None:
        return Answer(
            question=question,
            answer=(
                f"Ad {ad_id} is in no ring. Its number {ad.phone} appears on "
                f"{len(analysis.graph.phone_ads[ad.phone])} ad(s) and it asks for no money first."
                if not spans
                else f"Ad {ad_id} asks for money first but links to no ring of four or more ads."
            ),
            grounded=True,
            intent="ring_of_ad",
            evidence=spans or [Evidence(ad_id=ad_id, phone=ad.phone)],
        )
    return Answer(
        question=question,
        answer=(
            f"Ad {ad_id} is in {ring.label} ({len(ring.ad_ids)} ads, {len(ring.phones)} numbers)."
        ),
        grounded=True,
        intent="ring_of_ad",
        evidence=spans or [Evidence(ad_id=ad_id, phone=ad.phone)],
    )


def ring_start(analysis: Analysis, question: str, ring: Ring, end: bool = False) -> Answer:
    first = ring.timeline[0]
    last = max(ring.ad_ids, key=lambda a: (analysis.graph.ads[a].posted_at, a))
    ad_id = last if end else first.ad_id
    when = ring.last_seen if end else ring.first_seen
    verb = "last posted" if end else "started"
    return Answer(
        question=question,
        answer=(
            f"{ring.label} {verb} on {when}, with {_ad_line(analysis, ad_id)}; "
            f"it ran {ring.first_seen} to {ring.last_seen}."
        ),
        grounded=True,
        intent="ring_end" if end else "ring_start",
        evidence=[Evidence(ad_id=ad_id, phone=analysis.graph.ads[ad_id].phone)],
    )


def ring_size(analysis: Analysis, question: str, ring: Ring) -> Answer:
    return Answer(
        question=question,
        answer=f"{ring.label} has {len(ring.ad_ids)} ads: {', '.join(map(str, ring.ad_ids))}.",
        grounded=True,
        intent="ring_size",
        evidence=[Evidence(ad_id=a) for a in ring.ad_ids],
    )


def ring_phones(analysis: Analysis, question: str, ring: Ring) -> Answer:
    graph = analysis.graph
    evidence = []
    parts = []
    for phone in ring.phones:
        ids = [a for a in graph.phone_ads[phone] if a in ring.ad_ids]
        parts.append(f"{phone} (ads {', '.join(map(str, ids))})")
        evidence += [Evidence(ad_id=a, phone=phone) for a in ids]
    return Answer(
        question=question,
        answer=f"{ring.label} used {len(ring.phones)} numbers: " + "; ".join(parts) + ".",
        grounded=True,
        intent="ring_phones",
        evidence=evidence,
    )


def ring_wording(analysis: Analysis, question: str, ring: Ring) -> Answer:
    evidence = [e for f in ring.findings if f.kind == "shared_phrasing" for e in f.evidence]
    if not evidence:
        return _none(question, "ring_wording")
    seen: dict[str, int] = {}
    for e in evidence:
        seen.setdefault(e.span or "", e.ad_id)
    examples = " | ".join(f'"{s}" (ad {a})' for s, a in list(seen.items())[:4])
    return Answer(
        question=question,
        answer=(
            f"{ring.label} asks for money before the keys in {len(seen)} wordings, e.g. {examples}."
        ),
        grounded=True,
        intent="ring_wording",
        evidence=evidence[:30],
    )


def copied_from(analysis: Analysis, question: str, ad_id: int) -> Answer:
    if ad_id not in analysis.graph.ads:
        return _none(question, "copied_from", f"There is no ad {ad_id} in this corpus.")
    ring = analysis.ring_of(ad_id)
    note = None
    if ring:
        for f in ring.findings:
            if f.kind == "copied_listing":
                note = next((e for e in f.evidence if e.ad_id == ad_id and e.note), None)
    if note is None:
        return Answer(
            question=question,
            answer=f"Ad {ad_id}'s photos were not found in any older ad under a different number.",
            grounded=True,
            intent="copied_from",
            evidence=[Evidence(ad_id=ad_id, photo_ids=sorted(analysis.graph.ads[ad_id].photos))],
        )
    src = int(re.search(r"ad (\d+)", note.note or "").group(1))  # type: ignore[union-attr]
    src_ev = Evidence(
        ad_id=src,
        photo_ids=sorted(
            p
            for n in analysis.graph.shared_photo_nodes(ad_id, src)
            for p in analysis.graph.ad_photos[src][n]
        ),
    )
    return Answer(
        question=question,
        answer=(
            f"Ad {ad_id} reuses photos first posted in {_ad_line(analysis, src)}, "
            f"under a different number ({analysis.graph.ads[ad_id].phone})."
        ),
        grounded=True,
        intent="copied_from",
        evidence=[note, src_ev],
    )


def list_rings(analysis: Analysis, question: str) -> Answer:
    if not analysis.rings:
        return _none(question, "list_rings")
    parts = [
        f"{r.label}: {len(r.ad_ids)} ads, {len(r.phones)} numbers, {r.first_seen} to {r.last_seen}"
        for r in analysis.rings
    ]
    return Answer(
        question=question,
        answer="; ".join(parts) + ".",
        grounded=True,
        intent="list_rings",
        evidence=[Evidence(ad_id=r.ad_ids[0]) for r in analysis.rings],
    )


def same_phone(analysis: Analysis, question: str, ad_id: int) -> Answer:
    graph = analysis.graph
    if ad_id not in graph.ads:
        return _none(question, "same_phone", f"There is no ad {ad_id} in this corpus.")
    phone = graph.ads[ad_id].phone
    ids = sorted(graph.phone_ads[phone])
    return Answer(
        question=question,
        answer=f"Ad {ad_id} uses {phone}; that number appears on ads {', '.join(map(str, ids))}.",
        grounded=True,
        intent="same_phone",
        evidence=[Evidence(ad_id=a, phone=phone) for a in ids],
    )


def ask(analysis: Analysis, question: str) -> Answer:
    q = question.strip()
    low = q.lower()
    ad_id, ring_letter = _ids(q)
    ring = analysis.ring(ring_letter) if ring_letter else None
    if re.search(r"\b(list|all|which|what|show)\b.*\brings\b", low) and ring_letter is None:
        return list_rings(analysis, q)
    if ad_id is not None:
        if re.search(r"photo|picture|image", low) and re.search(
            r"cop(y|ied)|from|source|stole", low
        ):
            return copied_from(analysis, q, ad_id)
        if re.search(r"photo|picture|image", low):
            return shared_photos(analysis, q, ad_id)
        if re.search(r"phone|number|call", low):
            return same_phone(analysis, q, ad_id)
        if re.search(r"\bring\b|part of|member|belong|scam|operator", low):
            return ring_of_ad(analysis, q, ad_id)
    if ring_letter is not None:
        if ring is None:
            return _none(q, "ring", f"There is no ring {ring_letter} in the graph.")
        if re.search(r"\b(start|began|begin|first|origin)", low):
            return ring_start(analysis, q, ring)
        if re.search(r"\b(end|last|stop|latest|finish)", low):
            return ring_start(analysis, q, ring, end=True)
        if re.search(r"phone|number", low):
            return ring_phones(analysis, q, ring)
        if re.search(r"word|phras|ask|money|pay|say", low):
            return ring_wording(analysis, q, ring)
        if re.search(r"how many|size|which ads|members|ads", low):
            return ring_size(analysis, q, ring)
    return _none(q, "unknown")


def verify_answer(analysis: Analysis, answer: Answer) -> bool:
    """A shown answer must cite real evidence: every ad id exists, every span is a sentence of
    that ad, every photo id is one of its photos, every number is its number. An ungrounded
    answer must carry no evidence at all."""
    graph = analysis.graph
    if not answer.grounded:
        return not answer.evidence
    if not answer.evidence:
        return False
    for e in answer.evidence:
        ad = graph.ads.get(e.ad_id)
        if ad is None:
            return False
        if e.span is not None and e.span not in ad.text:
            return False
        if any(p not in ad.photos for p in e.photo_ids):
            return False
        if e.phone is not None and e.phone != ad.phone:
            return False
    return True
