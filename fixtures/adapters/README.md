# Adapter fixtures

`costar-kit/` holds small invented versions of the CoStar kit files the adapters read
(`commercial-property.jsonl`, `apartment-listing.jsonl`, `residential-listings.jsonl`,
`enums.json`; the real kit keeps them under `data/`), so the adapters run the same parser in
fixture and live mode. Every value is synthetic and team-made: ids start with `fx-`, streets are
invented (Fixture Lane, Sample Street), phone numbers use the reserved 555-01xx range.

Field names follow the adapters' best reading of the kit and are checked against the real kit
with `uv run python -m snapback.adapters.costar_jsonl --coverage` (counts only).
