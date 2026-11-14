# Intake fixtures

Synthetic only. Every listing, name, number and link here is invented; phone numbers use the
555-01xx range reserved for fiction.

- `listing_*.png`: screenshots drawn by `make_screenshots.py`. `listing_*.json` says what intake
  should read from each.
- `injection_*.json`: a listing text plus a sentence addressed to an AI system. The expectation
  is the same for all of them: the state, the rule hits and the rent are what they are without
  the sentence, and the sentence is logged. These double as eval cases for the harness.
- `injection_screenshot.png`: the same idea inside a screenshot.
