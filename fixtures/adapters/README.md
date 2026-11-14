# Adapter fixtures

`costar-kit/` mirrors the layout of the CoStar hackathon kit (`data/*.jsonl`) with three invented
records, so the CoStar adapter runs the same parser in fixture and live mode. Every value is
synthetic and team-made; ids start with `fx-`. Field names follow the adapter's best reading of
the kit and are checked against the real kit with
`uv run python -m snapback.adapters.costar_jsonl --coverage` (counts only).
