# Data use

What SNAPBACK reads, where it goes, what it keeps and for how long. This file describes the code
as merged, not plans; a PR that changes any row below updates this file in the same PR.
Owner: lane D. Last checked against `main` on Fri Nov 13 2026.

## What we read

| Data                                          | From                                                                | Read by                                                      | Leaves this machine?                                                                                    |
| --------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| CoStar property and listing records           | the CoStar hackathon kit (JSONL), unzipped under `data/raw/costar/` | `adapters/costar_jsonl.py`                                   | No. Never sent to any outside model.                                                                    |
| Matterport twins (panoramas)                  | Matterport Model API, sponsor keys                                  | lane V (`adapters/matterport.py`, `vision/`)                 | No. Matching runs on our machines.                                                                      |
| Vexcel aerial tile                            | Vexcel API, sponsor key                                             | `adapters/vexcel.py` (D2, not merged yet)                    | No.                                                                                                     |
| Renter's listing link and text                | the renter (web upload; iMessage is D4, not merged yet)             | `api/`, `agent/rules/`                                       | Text only, to Claude, and only when `SNAPBACK_AGENT=deepagents` (default is the code policy, no model). |
| Renter's photos (screenshots, listing photos) | the renter                                                          | `api/uploads.py`                                             | No. Held in memory for the check.                                                                       |
| Reply photos from the poster                  | the poster, passed on by the renter                                 | `challenge/` (local OCR), lane V (locate, recapture, memory) | No. OCR runs locally.                                                                                   |

Rules that hold for every row (AGENTS.md): sponsor images and records never go to an outside
model API; Claude sees only the renter's own text and yes/no facts we derive; owner names are
companies only, never a person.

## What we keep, and for how long

Everything kept lives under `data/` (git-ignored, never committed; `make check` fails if a file
there is tracked).

| What                                                    | Where                                         | How long                                                             |
| ------------------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------- |
| CoStar kit                                              | `data/raw/costar/`                            | Until `make purge`, no later than Sun Nov 15 16:00 (sponsor terms).  |
| Matterport and Vexcel caches                            | under `data/`                                 | At most 7 days, and purged by Sun Nov 15 16:00.                      |
| Photo memory (hashes, never pixels)                     | `data/memory/photo_memory.sqlite` (V5)        | 7-day TTL; cleared per case on "delete"; purged by Sun Nov 15 16:00. |
| Daily check counts, and which renter started which case | `data/safety.sqlite`                          | Ids and counts only, no content. Until purge.                        |
| Case photos                                             | `data/cases/<case_id>/` if a lane writes them | Until the renter says "delete", or purge.                            |
| Red-team attacks (team-made photos only)                | `data/redteam/`                               | Until purge.                                                         |

## Limits and deletion

- **3 checks per renter per day** (`SNAPBACK_DAILY_LIMIT`). `safety.check_limit(renter_id)`;
  counts persist across restarts. Asking does not use up a check; only a check that started does.
- **"delete" one case**: `uv run python -m snapback.safety delete-case <case_id>` removes the case
  folder `data/cases/<case_id>/` with its photos, the case's rows in the photo memory (through
  V5's `PhotoMemory.delete_case`, which keys rows by a hashed case id), and every row with that
  `case_id` in any other SQLite store under `data/`. Deleted rows are overwritten
  (`secure_delete`). Daily counts are kept, since they hold no content and deleting them would
  reset the limit.
- **"delete" all of a renter's cases**: `delete-renter <renter_id>`. Every case is registered with
  the renter who started it when it is created (A11), so this finds and deletes each of them as
  above. The owner is the iMessage sidecar's renter id (`imsg-` plus a keyed hash of the thread,
  never a phone number), or `browser:<client cookie>` for a check started on the web. A case that
  cannot be registered is not started, so no check exists that its renter could not delete.
  One limit: a running API keeps a case it has already loaded in memory, so a deleted case can
  still be read from that process until it restarts (or until the API evicts it on delete).
- **`make purge`** (`uv run python -m snapback.safety purge`): deletes everything under `data/`.
  It refuses any folder not named `data`, and a relative `SNAPBACK_DATA_DIR` is taken from the
  repo root, so it works from any directory. A missing folder is an error, not "0 removed". Run it
  after judging and before Sun Nov 15 16:00.

## Never

- Sponsor data, caches or screenshots of them in git, issues, PRs, the README or Devpost.
- Real addresses in code, fixtures, tests or docs.
- A person's name as owner of record; we show "matches owner of record: yes / no".
- SNAPBACK texting first or asking anyone for money.
