"""Adapters for the sponsor data layers (Matterport twins, CoStar records, Vexcel aerial).

Owner: data + intake lane. Empty on purpose; see that lane's issue for scope.

Rule for every adapter: one live backend and one fixture backend behind the single
`SNAPBACK_DATA_SOURCE` switch. Fixture data is synthetic and team-made. Sponsor data is read at
run time into `data/` (git-ignored) and is never committed.
"""
