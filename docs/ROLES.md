# Lanes

Four lanes, one person each. The lane names and paths below match `README.md` and
`.github/CODEOWNERS`; those two files win if anything here disagrees. Letters A, T, V and D are
the lane names used in the build plan.

| Lane          | Person (CODEOWNERS)    | Paths                                                                                   |
| ------------- | ---------------------- | --------------------------------------------------------------------------------------- |
| A. integrator | Vidyut (@vs-githjk)    | `src/snapback/contracts.py`, `verdict.py`, `settings.py`, `api/`, `agent/`, `AGENTS.md` |
| V. vision     | Dev (@DevSingh05)      | `src/snapback/vision/`, `src/snapback/eval/`                                            |
| T. web        | Jeffrey (@jeffrey-g05) | `apps/web/`                                                                             |
| D. data       | Rishit (@RishitRai)    | `src/snapback/adapters/`, `apps/sidecar/`                                               |

Shared: `fixtures/` (synthetic, team-made only) and `tests/`. A change to `contracts.py` or
`verdict.py` needs the integrator lane's approval (AGENTS.md).

## A. Integrator: agent, verdict, API

- `verdict.py`: evidence in, card rows out (PLACE / PERSON / PRICE). Pure code. Tests cover every
  row case and grep the string table for "safe", "verified" and "scam".
- Rules tables (payment method, pressure language, fee and data asks, links) with fires and
  does-not-fire fixtures. Suggested home: `src/snapback/agent/rules/`.
- `agent/`: deepagents orchestrator on fixtures first; the trace streams to the web app over SSE.
  Claude sees the renter's own text and derived facts only.
- Intake: screenshot to local OCR to listing schema, with prompt-injection fixtures.
- `api/`: case create and get, SSE trace stream.

## V. Vision: locate, recapture, memory, eval

- Skybox index and retrieval on one building, then verify and pose, with `thresholds.toml`. Index
  files stay in `data/` (git-ignored).
- Recapture classifier: data protocol, team capture session, v0 by Sat 02:00 (150 genuine, 150
  attacks, team-made only).
- Fingerprint memory (pHash, dHash, embeddings; no pixels kept).
- `eval/`: case bank, held-out splits, the harness that produces every number we quote, and the CI
  gate once it exists.
- Suggested homes: `src/snapback/vision/{locate,recapture,memory}`.

## T. Web: twin, card, trace

- S3 card page from fixture JSON (3 rows, evidence table, case id, expiry), LIVE / FIXTURE chip.
- S2 twin: Matterport Showcase SDK on localhost with one demo model, fly to a fixture pose.
- Agent trace panel over SSE, S1 upload page, Vexcel tile with a neutral fact, Lab panel from the
  eval results.

## D. Data: adapters, intake sidecar, challenge, data use

- Run `python3 scripts/probe_kit.py` for the 22:15 data gate; paste its output (counts only) on the
  kit issue.
- `adapters/`: CoStar JSONL and Matterport adapters, fixture and live behind
  `SNAPBACK_DATA_SOURCE`, local cache only, a purge command.
- `apps/sidecar/`: Photon round trip (receive a photo, reply with a fixture card).
- Challenge flow: code, OCR compare, timers, spot draw from the vision lane's ranking. Suggested
  home: `src/snapback/challenge/` (add it to CODEOWNERS when created).
- `DATA_USE.md`: what we read, where it goes, what we keep. True at every merge.

## Cross-lane contracts first

The evidence shapes that vision and data hand to `verdict.py`, and the SSE trace event shape, live
in `src/snapback/contracts.py` with fixtures in `fixtures/`, so every lane can start without the
others.
