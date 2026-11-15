"""Public data sources for the homes CoStar does not cover (HUD, Census, RDAP; HCAD is an adapter).

Every source here is free, keyless and public. Each answers one narrow question, names itself on
the card, and reads "not checked" when it cannot answer. None of them can set a verdict alone:
`snapback.verdict.decide` is still the only place a state is chosen.
"""
