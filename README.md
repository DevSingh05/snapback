# SNAPBACK

**Check any rental before you pay.**

A renter sends SNAPBACK a rental ad: a link, a screenshot or the ad's text and photos. SNAPBACK
reads the home's own record, checks what the ad claims against it, and answers with a card that
says one of four things: **Hold off for now**, **Don't pay**, **Checks passed** or **Could not
place these photos**. Every line on the card says where its facts came from, and code, not a
language model, picks the verdict.

## The problem

Rental scammers rarely fake the photos. They copy a real home's real listing, put their own
contact details on it, and ask for a deposit or first month's rent before anyone has seen the
place.

- **A renter, on Reddit:** "Common scam: they say they are outta town, so they cant see you in
  person to show the property, but there's a code to access the unit." (r/AskSF)
- **Listing agents, through the Houston Association of Realtors:** scammers are "hijacking
  property listings from HAR.com, including the photos, and listing them on craigslist", and
  stealing lockbox keys "so they can lease out homes that are for sale." (HARConnect, "Summer of
  Scam")
- **A sourced case:** in Scottsdale, a renter found a home for rent on Realtor.com. It "was
  actually for sale by the company Opendoor". The listing came down after a TV station called,
  and then "it has since been reposted for rent." (AZFamily, Jan 16 2026)
- **The scale:** the FTC counts about 65,000 rental scam reports from January 2020 to June 2025,
  with a median loss of $1,000. It notes that "many would-be renters report discovering that the
  scammer copied an ad for a property that was really for sale." (FTC Data Spotlight, Dec 2025)

So the photos usually pass. What is fake is the person and whether the home is for rent at all.
That is what SNAPBACK checks.

## How it works

Two steps, in this order:

1. **The twin identifies the home.** The ad's photos are matched against the home's 3D scan
   (Matterport) to say which building and which floor plan they were taken in.
2. **The record gives the verdict.** The home's own record (CoStar property and Homes.com
   listing data) is compared with what the ad says: who is renting it, whether it is for rent,
   the unit and the price.

Then the code in `src/snapback/verdict.py` turns the evidence into one verdict, with reasons in
the order a renter asks them: who and availability first, then presence, place and price.

### The checks

| Check                    | What it can prove                                                                                                                                                                                      | What it cannot prove                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| **Place: photo in scan** | A photo was taken in this building's floor plan, or in a different property.                                                                                                                           | Who holds the keys today. A scan covers a floor plan, not a unit number.                |
| **For sale**             | The home is listed for sale on Homes.com. Homes for sale are sometimes also offered for lease, so the card says to confirm with the listing brokerage. "Recently rented" is shown as information only. | That the owner would not rent it. Lease status is not public, so we never claim it.     |
| **Unit on record**       | The record lists no unit with the number or bedroom count the ad gives.                                                                                                                                | That a unit missing from the record does not exist.                                     |
| **Contact on record**    | Whether the poster's phone is the leasing office's on record (compared as keyed hashes), and whether a link imitates the building's site.                                                              | That a different number is a scammer's. Agents and locators often use their own number. |
| **Allowed to rent it**   | Whether the name the poster gives matches the manager on record.                                                                                                                                       | Authority. A match is a supporting line, never a pass on its own.                       |
| **Rent vs record**       | How far the asking rent is from the building's own rent band for that size.                                                                                                                            | That a low rent is a scam. Discounts happen; the card says "Ask why".                   |
| **Payment ask**          | That the text asks for Zelle, wire, gift cards, a fee, personal data or money under pressure.                                                                                                          | Intent.                                                                                 |
| **Here now**             | A reply photo from the poster is a copy of one of the ad's own photos (photo memory), or carries the code we asked for (local OCR).                                                                    | That the poster stood at the spot. That needs the locator on the reply (in progress).   |
| **Aerial view**          | A Vexcel aerial tile of the claimed building, beside the building the photo was placed in.                                                                                                             | Anything by itself. It is a picture for the renter, not a check that changes the card.  |

The proof-of-presence challenge is the renter's choice. SNAPBACK draws a spot in the home and a
fresh code, shows the renter the message, and sends nothing until the renter approves it.
SNAPBACK never texts the poster first and never asks anyone for money.

## What the card says

| Card                                           | When                                                                                                                                                                                                                  |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Don't pay. Something here doesn't match.**   | Only on proof: a listing photo was taken in a different property, or the poster's reply is a copy of one of the ad's own photos. The proof is the only reason given.                                                  |
| **Hold off for now**                           | The home is listed for sale (this comes first, even when no photo could be placed); or any red flag (price, payment, fee, data ask, pressure, lookalike link, unit); or the contact or presence is not confirmed yet. |
| **Could not place these photos**               | No photo landed in the claimed building: there is no scan, the scan is not indexed yet, or the photos did not match.                                                                                                  |
| **Checks passed. Still follow the two rules.** | The photos landed in this building, the poster proved they are there, the contact matches the record, and nothing is flagged.                                                                                         |

Each row reads Matches, Doesn't match, Not confirmed, Warning or Not checked. Every card ends with
the two rules: "never pay before a signed lease and a viewing; never pay by Zelle, wire or gift
card." Things that are not proof never set Don't pay: a for-sale listing, a name or phone that is
not the one on record, an unreadable code, or a model's recapture score. We never call a named
person a scammer.

Cards come in English and Spanish, as a web page and a PNG, with a verify link and QR code that
open the same card at `/c/<id>`.

## Architecture

```
renter: link, screenshot, text, photos (web upload; iMessage sidecar)
  -> POST /cases                       limits, upload caps, case registered to its renter
  -> intake                            local OCR, listing fields, prompt-injection guard
  -> agent                             picks the next check from options code wrote;
                                       the renter approves any message before it is sent
  -> modules                           CoStar record, Homes.com for-sale lookup, rules
                                       (price, unit, contact, payment), twin locate,
                                       photo memory, challenge and reply
  -> verdict.decide()                  code sets the state and the reasons
  -> card                              strings (en, es), PNG, verify link and QR
  -> web                               result page, live trace, twin view, aerial view, replay
```

| Path                                  | What it is                                                                              | Lane |
| ------------------------------------- | --------------------------------------------------------------------------------------- | ---- |
| `src/snapback/contracts.py`           | Shared data shapes every lane reads and writes                                          | XO   |
| `src/snapback/verdict.py`             | Evidence in, verdict out. Pure code, no model                                           | A    |
| `src/snapback/agent/`                 | Case runner, code policy or deepagents graph, the join of live modules, reply checks    | A    |
| `src/snapback/agent/intake/`          | Screenshot OCR (local), listing fields, injection guard                                 | A    |
| `src/snapback/agent/rules/`           | Price, unit, payment and contact rules                                                  | A    |
| `src/snapback/api/`                   | FastAPI service: cases, card, card PNG, trace stream (SSE), aerial, reply, eval results | A    |
| `src/snapback/card/`                  | Locked card strings (en, es) and the PNG card                                           | A    |
| `src/snapback/vision/locate/`         | Retrieval index over scan faces, geometric verification, pose                           | V    |
| `src/snapback/vision/memory/`         | Photo memory: pHash, dHash and embedding lookup, hashes only                            | V    |
| `src/snapback/vision/embed.py`        | DINOv2 embedder (and a small numpy embedder for CI)                                     | V    |
| `src/snapback/eval/`                  | Locate gate script                                                                      | V    |
| `src/snapback/adapters/matterport.py` | Matterport skybox fetch                                                                 | V    |
| `src/snapback/adapters/`              | CoStar JSONL, Homes.com residential listings, Vexcel tiles; live and fixture            | D    |
| `src/snapback/challenge/`             | Two-step proof-of-presence challenge: spots, codes, OCR                                 | D    |
| `src/snapback/redteam/`               | Scripted attack generator                                                               | D    |
| `src/snapback/safety/`                | Daily limits, delete a case or a renter, purge                                          | D    |
| `apps/web/`                           | Vite, React and TypeScript web app                                                      | T    |
| `apps/sidecar/`                       | iMessage intake handler (Photon client not connected yet)                               | D    |
| `fixtures/`                           | Synthetic, team-made data only, including the demo cases                                | all  |
| `tests/`                              | Python tests (web and sidecar tests live in their apps)                                 | all  |

Web routes: `/` upload, `/case/<id>` the renter's result, `/case/<id>/trace` the live trace,
`/case/<id>/twin` where the photos landed, `/c/<id>` the public verify page, `/replay/<slug>` a
step-by-step replay. Lanes: A agent and backend (Dev), T front end (Vidyut), V vision and ML
(Jeffrey), D data and iMessage (Rishit). Details in [docs/ROLES.md](docs/ROLES.md).

## Data and privacy

The full account is in [DATA_USE.md](DATA_USE.md). In short:

- **No sponsor data in git.** Scans, records, indexes and caches live in `data/`, which is
  git-ignored. `make hygiene` fails if anything there is tracked. No real addresses in code,
  fixtures, tests or docs.
- **Sponsor data stays on our machines.** Records and images never go to an outside model. With
  `SNAPBACK_AGENT=deepagents`, a model sees only the renter's own text and yes/no facts we derive.
- **Photos are kept as hashes, never pixels,** in the photo memory, with a 7-day limit.
- **Phones are compared as keyed hashes.** No digits are stored.
- **Owners are named only as companies.** A person is never named.
- **Delete and purge.** `uv run python -m snapback.safety delete-case <case_id>` and
  `delete-renter <renter_id>` remove a renter's cases and their photo memory rows. `make purge`
  deletes everything under `data/`.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Node 22 or newer.

```bash
uv sync --locked --extra agent --extra intake   # python, plus the agent and local OCR
npm install                                     # web app and sidecar
cp .env.example .env                            # fixture mode needs no keys
make api                                        # API on http://localhost:8000
make web                                        # web app on http://localhost:5173 (calls the API via /api)
```

Add `--extra vision` to the `uv sync` line for the locator (torch, kornia, faiss, OpenCV).

**Fixture or live.** `SNAPBACK_DATA_SOURCE=fixture` (the default) runs on synthetic, team-made
data and needs no keys. `SNAPBACK_DATA_SOURCE=live` reads the CoStar kit from `data/` and the
sponsor APIs with your own keys in `.env`. Every card and screen says LIVE or FIXTURE.

**Demo cases.** Three staged cases in `fixtures/demo/` run end to end. Each card made from them
says "Staged example" first in its footer.

```bash
uv run python -m snapback.agent.demo   # prints all three cards
DEMO_CASE=a make api                   # every new check runs on case a (a, b or c)
```

| Case | The staged poster                                                       | The card                                             |
| ---- | ----------------------------------------------------------------------- | ---------------------------------------------------- |
| `a`  | Real building, wrong unit, low rent, lookalike link, copied reply photo | Don't pay: the reply is a copy of listing photo 2    |
| `b`  | The same ad, with one photo taken in a different building               | Don't pay: a photo was taken in a different property |
| `c`  | A house listed for sale, posted as a rental, with no scan               | Hold off: listed for sale, not for rent              |

In live mode `DEMO_CASE` supplies only the listing text; see
[fixtures/demo/README.md](fixtures/demo/README.md).

**Checks.** `make check` runs everything CI runs: the hygiene guard, ruff, ESLint, Prettier,
TypeScript, pytest, and the web and sidecar tests.

### The CoStar kit (live mode)

1. Open the kit portal at https://beta-app.matterport.com/2026-princeton-hackathon and accept the
   Terms. Each person accepts for themselves.
2. Get your own sponsor keys from the CoStar Discord (`/costar-keys` in `#costar-group`) and put
   them in `.env` only. The names are in `.env.example`.
3. Unzip the kit under `data/`, for example `data/raw/costar/costar-hackathon-kit/`.
4. Run `python3 scripts/probe_kit.py`. It prints field names and counts only, never record values.

## Evaluation

What is measured:

- **The results route.** `GET /eval/results.csv` serves one CSV of aggregate numbers (condition,
  metric, k, n, rate, interval, frozen date) and nothing else. Its first line says FIXTURE or
  LIVE, and the Lab panel on the card page shows that label. Today the only results file in the
  repo is the synthetic sample `fixtures/contracts/results_sample.csv`, labelled FIXTURE.
- **The locate gate.** `uv run python -m snapback.eval.locate_gate --index data/index/<name> --n 20`
  counts how many held-out views of a building are placed in it, with pose, and how many views of
  another building are placed elsewhere. The views are renders of the indexed scans at
  viewpoints the index never stored, not phone photos, and every line it prints says so. A rerun
  with the merged thresholds is pending, so we quote no number here yet.
- **Tests.** The verdict rules, card strings, demo cases, API routes, adapters, challenge, photo
  memory and safety code are covered by tests that run in CI on fixtures.

What is not measured yet: accuracy on real phone photos of these homes, the locator on house
scans, accuracy on real scam ads, and the deepagents path with a live model. No number goes in the
demo or this README before the harness measures it, with n shown.

## Limits

- **Live cases do not place photos yet.** The locator works on indexed scans and in fixture
  cases, but a live case reads "Not checked" for the photos until it is wired in. So today a live
  card can say Hold off or Could not place these photos, and not Don't pay or Checks passed.
- **A scan shows a floor plan, not a unit.** Apartment scans are model units. A match says "this
  building, this floor plan", never a unit number.
- **The data covers Houston and Los Angeles.** That is what the CoStar kit holds.
- **A code on a reply photo is not proof.** The local reader can miss handwriting, so a wrong or
  missing code asks again and then holds. It never says Don't pay.
- **Lease status is not public.** "Recently rented" is information, never a flag.
- **iMessage intake is a tested handler,** not a running bridge: the Photon client is not
  connected yet.
- **The replay on main is fictional** and labelled so. Sourced replays of reported cases are not
  in the repo yet.

### In progress

These are being built and are not on `main`:

- Placing photos on live cases: the locator wired into live checks (#141).
- A license line: whether a poster who claims to be an agent holds an active Texas license (#134, #137).
- Owner of record: the owner as a company name, and the rule that owner publishes (#140, #130).
- "Report this copy": an evidence pack a listing agent can send to the platform (#126).
- The app restyle (#122).

## Team and credits

Built by Vidyut ([@vs-githjk](https://github.com/vs-githjk)), Dev
([@DevSingh05](https://github.com/DevSingh05)), Jeffrey
([@jeffrey-g05](https://github.com/jeffrey-g05)) and Rishit
([@RishitRai](https://github.com/RishitRai)).

Data from the CoStar kit (CoStar property records, Homes.com listings, Matterport scans and
Vexcel aerial imagery), used under its terms. Models and libraries: DINOv2 (Meta, Apache 2.0),
DISK and LightGlue through kornia (Apache 2.0), RapidOCR on ONNX Runtime, and deepagents.

Agents working in this repo: read [AGENTS.md](AGENTS.md) first.
