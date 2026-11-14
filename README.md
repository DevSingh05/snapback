# SNAPBACK

**The photos are real. The person isn't.**

Rental scammers copy a real listing, swap in their own contact details and collect a deposit
before any viewing. SNAPBACK checks a listing against the building's 3D scan and its property
record, and answers three separate questions before a renter pays:

1. **Is the place real?** Each listing photo is located inside the building's 3D twin.
2. **Is it really like this?** The photo is compared with the scan from the same viewpoint.
3. **Is the person real?** The poster is checked against the contact on the property record, and
   asked for a fresh photo that only someone inside the unit could take.

Built at HackPrinceton Fall '26 for the CoStar "Inside and Out: AI for the Built World" track.

> **Status: skeleton.** Tooling, shared contracts, the verdict rules and a health-check slice
> exist. Nothing else is built yet. Scope and assignments live in the repo's issues, starting
> with the pinned issue labelled `start-here`.

## Quick start

Needs [uv](https://docs.astral.sh/uv/) and Node 22 or newer.

```bash
make setup        # install python and node dependencies
cp .env.example .env
make check        # hygiene + lint + tests: everything CI runs
make api          # API on http://localhost:8000
make web          # web app on http://localhost:5173
```

Heavy dependencies are opt-in, so the base install stays fast:

```bash
uv sync --extra vision   # torch, kornia, faiss, opencv
uv sync --extra agent    # deepagents, langchain-anthropic
uv sync --extra intake   # local OCR for screenshots (RapidOCR on ONNX Runtime)
```

## Get the CoStar kit

The team accepted the CoStar hackathon Terms as written (Fri 21:48). Each person accepts for
themselves and gets their own key.

1. Open the kit portal: https://beta-app.matterport.com/2026-princeton-hackathon and accept the Terms.
2. Get your own sponsor keys from the CoStar track Discord (`/costar-keys` in `#costar-group`) and
   put them in `.env` only (names in `.env.example`).
3. Unzip the kit under `data/` (git-ignored), for example `data/raw/costar/costar-hackathon-kit/`.
4. Run `python3 scripts/probe_kit.py`. It prints field names and counts only, never record values,
   so its output is safe to paste into the data gate issue.

## Layout

| Path                                  | What it is                                          | Lane |
| ------------------------------------- | --------------------------------------------------- | ---- |
| `src/snapback/contracts.py`           | Shared data shapes every lane reads and writes      | XO   |
| `fixtures/contracts/`                 | One synthetic fixture per contract                  | XO   |
| `src/snapback/verdict.py`             | Evidence in, verdict out. Pure code, no model       | A    |
| `src/snapback/agent/`                 | Agent (5 choices), rules tables, intake             | A    |
| `src/snapback/api/`                   | FastAPI service and SSE trace stream                | A    |
| `src/snapback/card/`                  | Card strings (en, es), PNG card, verify link and QR | A    |
| `apps/web/`                           | Vite + React + TypeScript app: S1, S2, S3           | T    |
| `src/snapback/vision/`                | locate, recapture, memory                           | V    |
| `src/snapback/eval/`                  | Eval harness that produces every number we quote    | V    |
| `src/snapback/adapters/matterport.py` | Matterport skybox fetch                             | V    |
| `src/snapback/adapters/`              | CoStar and Vexcel adapters, live and fixture        | D    |
| `src/snapback/challenge/`             | Proof-of-presence challenge                         | D    |
| `src/snapback/redteam/`               | Scripted attack generator                           | D    |
| `src/snapback/safety/`                | Limits, delete, purge                               | D    |
| `apps/sidecar/`                       | Photon iMessage bridge                              | D    |
| `fixtures/`                           | Synthetic, team-made test data only                 | all  |
| `tests/`                              | Python tests                                        | all  |

Lanes: A agent and backend (Dev), T front end (Vidyut), V vision and ML (Jeffrey), D data and
iMessage (Rishit). Details in [docs/ROLES.md](docs/ROLES.md).

## Rules that are not negotiable

- **No sponsor data in git.** Scans, panoramas, records, indexes and caches live in `data/`
  (git-ignored). `make hygiene` enforces this. The repo is public at submission.
- **No secrets in git.** Keys go in `.env`.
- **Code sets the verdict.** A language model may explain it, never decide it.
- **Every screen and number says LIVE or FIXTURE**, and no number is quoted before it is measured.
- **We never call a named person a scammer.** The strongest wording is "Don't pay · could not verify".

Agents working in this repo: read [AGENTS.md](AGENTS.md) first.
