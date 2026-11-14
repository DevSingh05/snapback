"""Forensics over many rental ads: the investigator view (Arlequin AI Track 1).

One renter's check answers one ad; an investigator needs the ring behind the ads. Everything in
this package runs on SYNTHETIC data only (`fixtures/forensics/`, made by `generate.py`). No
CoStar, Matterport or Vexcel data, no real address, no real phone number ever enters it.

Pipeline: `extract` (the existing claim and rule code) -> `embed` (concept-folded TF-IDF) ->
`graph` (ad, photo-set, phone and phrasing links) -> `rings` (communities, timelines, evidence)
-> `evaluate` (precision and recall against the seeded ground truth, and a keyword baseline).
`investigator` answers questions from the graph only, and cites ad ids and spans.
"""

SYNTHETIC_LABEL = "SYNTHETIC DATA"
