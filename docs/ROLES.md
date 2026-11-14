# Lanes

Final split (Vidyut, Fri Nov 13 21:53). Paths match `.github/CODEOWNERS`, which wins if anything
here disagrees. Each lane has one epic issue (label `epic`) with its ordered task issues.

| Lane                         | Person (GitHub)              | Paths                                                                                                               |
| ---------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| A. Agent and backend         | Dev (@DevSingh05)            | `verdict.py`, `settings.py`, `api/`, `agent/` (incl. `agent/rules/`, `agent/intake/`), `card/`                      |
| T. Front end                 | Vidyut + Claude (@vs-githjk) | `apps/web/`                                                                                                         |
| V. Vision and ML             | Jeffrey (@jeffrey-g05)       | `vision/locate/`, `vision/recapture/`, `vision/memory/`, `eval/`, `adapters/matterport.py`                          |
| D. Data, iMessage, challenge | Rishit (@RishitRai)          | `adapters/` (CoStar, Vexcel), `apps/sidecar/` (Photon iMessage), `challenge/`, `redteam/`, `safety/`, `DATA_USE.md` |
| Contracts, repo rules, docs  | Vidyut + Claude + XO         | `contracts.py`, `fixtures/contracts/`, `AGENTS.md`, `CLAUDE.md`, `.github/`, `docs/`                                |

All Python paths are under `src/snapback/`. Shared by everyone: `fixtures/` (synthetic, team-made
only) and `tests/`.

## The 12 committed modules (feature freeze Sun 02:00)

| #   | Module          | Lane | What ships                                                                                   |
| --- | --------------- | ---- | -------------------------------------------------------------------------------------------- |
| 1   | adapters        | D, V | CoStar JSONL, Vexcel tile (D); Matterport skybox fetch (V); fixture and live behind one flag |
| 2   | locate          | V    | DINOv2 retrieval, LightGlue verify, pose, `thresholds.toml`, walkthrough-video index         |
| 3   | challenge       | D    | spot draw from V's ranking, 4-char code, local OCR compare, 10 min then 90 s timers          |
| 4   | recapture       | V    | screen, print and paste detector: v0, then retrain v1 and v2                                 |
| 5   | memory          | V    | pHash + dHash store (SQLite, 7-day TTL) plus embedding lookup                                |
| 6   | verdict + rules | A    | `decide()`, rules tables, price row incl. refund-the-difference                              |
| 7   | agent           | A    | deepagents, the 5 visible choices, HITL, FastAPI + SSE trace, intake                         |
| 8   | photon          | D    | iMessage in and out, renter-thread allowlist, card text plus link                            |
| 9   | web             | T    | S1 upload; S2 twin + trace + aerial tile; S3 card + verify + Lab panel                       |
| 10  | card            | A    | PNG card, verify link + QR, Spanish strings                                                  |
| 11  | redteam         | D, V | scripted attack generator (D); locate calibration, recapture retrain v1 and v2 (V)           |
| 12  | safety          | D    | per-renter limits, delete command, `make purge`, `DATA_USE.md`                               |
| +   | eval harness    | V    | case bank, held-out H0, `make eval`, CI gate, `results.csv` for the Lab panel                |

Ordered stretch after freeze-ready core (label `stretch`, P2): 13 tactic classifier (A),
14 scam-ring graph (V), 15 listing-time platform screen S5 (T), 16 feedback loop with
anti-poisoning (A).

## Cross-lane contracts

Every module's output shape is in `src/snapback/contracts.py` (`LocateResult`, `ChallengeResult`,
`RecaptureResult`, `MemoryResult`, `RuleHit`, `PriceResult`, `AuthorityResult`, bundled as
`ModuleEvidence`; `Card` for every renderer; `TraceEvent` for the SSE trace). Fixtures for each are
in `fixtures/contracts/` and `tests/test_contracts.py` proves they parse. Build against the
fixture first; never wait on another lane. Adding an optional field is fine in your PR; renaming or
removing one needs an issue tagged `contracts` first.
