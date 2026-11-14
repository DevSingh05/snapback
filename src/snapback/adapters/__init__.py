"""Adapters for the sponsor data layers (Matterport twins, CoStar records, Vexcel aerial).

Owners: the data + intake lane owns `costar.py` and `vexcel.py`; the vision + eval lane owns
`matterport.py`, because twin access is on its critical path. Empty on purpose; see the lane
issues for scope.

Rule for every adapter: one live backend and one fixture backend behind the single
`SNAPBACK_DATA_SOURCE` switch. Fixture data is synthetic and team-made. Sponsor data is read at
run time into `data/` (git-ignored) and is never committed.
"""
