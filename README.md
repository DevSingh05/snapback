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
```

## Get the CoStar kit

1. Open the kit portal: https://beta-app.matterport.com/2026-princeton-hackathon
2. Get the sponsor keys from the CoStar track Discord (`/costar-keys` in `#costar-group`) and put
   them in `.env` only (names in `.env.example`).
3. Unzip the kit under `data/` (git-ignored), for example `data/raw/costar/costar-hackathon-kit/`.
4. Run `python3 scripts/probe_kit.py`. It prints field names and counts only, never record values,
   so its output is safe to paste into an issue.

**Do not click "I Agree" on the sponsor Terms until Vidyut confirms the team decision** (the Terms
include an IP assignment to CoStar).

## Layout

| Path                        | What it is                                                                       | Lane       |
| --------------------------- | -------------------------------------------------------------------------------- | ---------- |
| `src/snapback/contracts.py` | Shared data shapes every lane reads and writes                                   | integrator |
| `src/snapback/verdict.py`   | Evidence in, verdict out. Pure code, no model                                    | integrator |
| `src/snapback/api/`         | FastAPI service                                                                  | integrator |
| `src/snapback/agent/`       | Agent orchestration                                                              | integrator |
| `src/snapback/vision/`      | Photo index, matching, forgery checks                                            | vision     |
| `src/snapback/eval/`        | Eval harness that produces every number we quote                                 | vision     |
| `src/snapback/adapters/`    | CoStar and Vexcel adapters, live and fixture (`matterport.py` belongs to vision) | data       |
| `apps/sidecar/`             | Intake bridge for inbound renter messages                                        | data       |
| `apps/web/`                 | Vite + React + TypeScript app                                                    | web        |
| `fixtures/`                 | Synthetic, team-made test data only                                              | everyone   |
| `tests/`                    | Python tests                                                                     | everyone   |

## Rules that are not negotiable

- **No sponsor data in git.** Scans, panoramas, records, indexes and caches live in `data/`
  (git-ignored). `make hygiene` enforces this. The repo is public at submission.
- **No secrets in git.** Keys go in `.env`.
- **Code sets the verdict.** A language model may explain it, never decide it.
- **Every screen and number says LIVE or FIXTURE**, and no number is quoted before it is measured.
- **We never call a named person a scammer.** The strongest wording is "Don't pay · could not verify".

Agents working in this repo: read [AGENTS.md](AGENTS.md) first.
