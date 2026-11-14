# SNAPBACK: Devpost draft

> Draft for the HackPrinceton Fall 2026 Devpost page. Every number carries its n and whether it
> is LIVE (the CoStar kit) or FIXTURE (synthetic, team-made). Lines marked **TODO** need a fact
> from a teammate before submitting. Sources: the README, the PRs on `main` and the team board.

## Tagline

**Trust the home, not the ad.** Paste a rental ad you found online. SNAPBACK checks it against
the home's own record before you pay anyone.

## Inspiration

In February 2025, a renter near Houston found a house on Craigslist. The poster said he was the
landlord and gave her a door code. She paid $2,200 for rent and a deposit and moved in. Two days
later the real owner, a rental company, told her the poster did not own the house
([ABC13, Feb 15 2025](https://abc13.com/post/conroe-woman-loses-2200-fears-homelessness-renting-home-landlord-did-not-own-property/15907951/)).

She did nothing careless. The photos were of a real house, and she even got inside. The FTC
counted nearly 65,000 rental-scam reports from January 2020 to June 2025, and about half began
with a fake ad on Facebook
([FTC Data Spotlight, Dec 2025](https://www.ftc.gov/news-events/data-visualizations/data-spotlight/2025/12/rental-scams-hit-home-65-million-reported-losses)).

These scams work because real photos pass. The person and the offer are what's fake, and the
home's own record can show that. So we built a renter's agent that checks the ad against the
record before money moves.

## What it does

You paste the ad: a link, its text, or screenshots. You can also text it to SNAPBACK on iMessage.
SNAPBACK runs a set of checks, each reading one source and writing one sourced line on a card:

- **Photos taken in this home:** the ad's photos are matched against the building's Matterport 3D
  scan. "Taken in this building (3 of 3 photos)" or "Taken in a different building. Red flag."
- **For sale, posted as a rental:** the Homes.com listings in the CoStar kit.
- **Owner of record:** the county owner roll for Houston houses. "Owner of record: Invitation
  Homes, not the poster", quoted with that owner's own published rule on where it takes
  applications.
- **Agent license:** Texas Real Estate Commission public data.
- **Contact, unit and rent against the record:** the CoStar property record's leasing office
  phone, website, units and asking rents.
- **Payment, data and pressure asks in the ad's own text:** "Zelle before a viewing. Red flag."
- **Here now:** a proof-of-presence challenge. The poster sends a fresh photo of a spot in the
  home, and a copy of a listing photo is caught.
- **Aerial view:** Vexcel imagery of the claimed building.

The card gives one of four verdicts: **Hold off for now**, **Don't pay. Something here doesn't
match.**, **Could not place these photos** or **Checks passed. Still follow the two rules.**
"Don't pay" needs proof, and SNAPBACK never calls a named person a scammer.

Then it helps you find a real place. It shows researched places from CoStar's Houston listings
that fit your budget, on a 3D city map, with "Walk it first" tours from the scans and a tour
request drafted to the leasing office on record. You send it yourself: SNAPBACK never pays, books
or sends anything for you.

## How we built it

- **Backend:** Python 3.12 and FastAPI. The case runner, intake, rules, search and API are in
  `src/snapback/`.
- **Code sets every verdict.** `verdict.decide()` is the only place a verdict is chosen. A model
  may pick the order of checks (deepagents planner, opt in) and write explanations, and every
  step on the live trace says who picked it. No model ever sees or sets a verdict.
- **Photo locating:** DINOv2 retrieval over views rendered from the Matterport scans, then DISK and
  LightGlue matching (kornia) with RANSAC verification and a spatial-spread check.
- **Data adapters:** the CoStar kit (property records, Homes.com listings), Matterport scans,
  Vexcel aerial imagery, Harris County owner records and TREC license data. The kit stays in a
  git-ignored folder, and nothing from it goes to an outside model.
- **Intake:** local OCR (RapidOCR on ONNX Runtime) for screenshots, listing-field extraction and
  a prompt-injection guard.
- **Front end:** Vite, React and TypeScript, with a MapLibre 3D city map, an isometric 3D house
  and a walkthrough tour. Every screen says LIVE or FIXTURE.
- **iMessage:** a Node sidecar on Photon's Spectrum SDK. A renter texts the ad and gets the card
  back as text plus a link. Only allowlisted threads are answered, and thread ids are kept as
  keyed hashes.
- **Forensics:** a ring finder for investigators (Arlequin track), using concept-folded TF-IDF, a
  link graph of ads, photos, numbers and wordings, and Louvain communities. Every finding carries
  its evidence.
- **Process:** four people, each running coding agents in their own lane (agent and backend,
  front end, vision, data and iMessage). Each lane opened PRs against shared contracts, with
  review, failing-test-first fixes and CI on every change (hygiene guard, ruff, ESLint, Prettier,
  TypeScript, pytest, web and sidecar tests, and an eval gate).

## Results (with n, LIVE or FIXTURE)

- **Locate gate, on renders of our scans (not phone photos):** of n = 20 claimed-building views and
  10 other-building views, from unseen directions, 20 of 20 were placed in the right building with
  0 false placements (held-out seed, #28).
- **Photo accuracy on real listing photos, LIVE (A8, #72; CoStar OK'd sharing totals):** of
  n = 78 photos (48 from the indexed homes, 30 decoys from other homes), 43 of 48 were placed in
  the right home, 0 were placed in a wrong one, and 5 could not be placed. Right room was not
  measured. **TODO:** confirm the decoy outcome (30 not placed?) with Dev before submitting.
- **Forensics, SYNTHETIC/FIXTURE corpus:** on n = 301 ads with 4 seeded rings (57 ring ads), it
  recovered 4 of 4 rings, found 57 of 57 ring ads and flagged 0 of 244 honest ads. A keyword
  baseline recovered 0 of 4 rings. On 10 held-out seeds (about 300 ads each) it averaged ring
  precision 0.88 and recall 0.93. The corpus and the method were built together, so this shows
  the method works on rings shaped like these. It is not an accuracy claim for real listings.
- **Replays of reported cases, FIXTURE:** two staged replays (the move-in paid to a poster who
  didn't own the house, and a Zelle deposit for a house never for rent) both stop at Hold off,
  before the payment.

## Challenges we ran into

- **Not overclaiming.** Real photos of a real home pass any photo check, so the product has to
  separate "the photos are real" from "this person may rent it". We kept "Don't pay" for proof
  only. We quoted no accuracy number until we had measured it on real listing photos, and we
  still label each number with its n and with renders or photos.
- **Privacy in public records.** The county owner roll names people. After several review rounds
  on name classifiers, we changed what the card shows instead. A private owner is "a private
  owner", and a company is named only when it matches one we already know. Each privacy gate is
  tested on its own by turning it off.
- **Sponsor data rules.** No kit data in git, in a log or in an outside model, with a hygiene guard
  in CI to hold the line.
- **Real-world plumbing:** door codes that pass a presence check, iMessage photos that arrive as
  grouped messages, Windows tooling quirks, and a reconnecting event stream that must never text
  the same alert twice.

## Accomplishments we're proud of

- One rule held from start to finish: code sets the verdict, and every line on the card says
  where its fact came from.
- A real iMessage round trip from a phone: text an ad and get the card back in the thread.
- The news case we started from replays end to end and stops at **Hold off** before the $2,200
  goes out. The card shows the owner of record and that owner's own rule.

## What we learned

- The strongest signal is often not the photo but the record behind it: who owns the home, who
  manages it, and whether it is for sale.
- Saying "not checked" honestly builds more trust than a confident guess.

## What's next

- **University partnerships for international students.** They rent from abroad, sight unseen,
  and often to a deadline. Pre-arrival housing guides could carry "check any listing before you
  send a deposit".
- **Platforms:** run the check when a listing is posted on Facebook Marketplace, Zillow or
  Craigslist. Today it works on any listing a renter can paste or forward.
- **Voice:** send a voice memo in iMessage and get the answer back as text plus a voice reply.
- **More cities, more languages** (English and Spanish today), and measured accuracy on real ad
  photos at scale.

## Built with

Python, FastAPI, pydantic, uv, PyTorch, DINOv2, kornia (DISK, LightGlue), FAISS, OpenCV,
RapidOCR, ONNX Runtime, deepagents, TypeScript, React, Vite, MapLibre,
Node.js, Photon Spectrum (iMessage), Matterport, Vexcel, CoStar and Homes.com data, GitHub
Actions.

## Tracks

- **CoStar:** checks every ad against CoStar's own property records, the Homes.com listings, the
  Matterport scans and the Vexcel aerial imagery, then turns that data into a safer search. The
  kit never leaves the machine or goes to a model.
- **Amazon Practical AI:** **TODO (Dev):** name the Amazon service we used and what it does in
  SNAPBACK. Nothing in the repo uses an Amazon service yet, so we can't claim this track until
  something does.
- **Photon (+ Best Voice Agent):** the iMessage sidecar is live on Photon's Spectrum SDK: text an
  ad and get the card back. Watch alerts text a linked Finder search at most 3 times a day, and
  "stop" ends them. Voice memos in and spoken replies out are in progress (**TODO:** update when
  the voice PR lands).
- **Arlequin:** the investigator view finds rental-scam rings across many ads, with evidence for
  every link, on a SYNTHETIC/FIXTURE corpus (numbers above).
- **GoDaddy domain:** **TODO:** the domain Vidyut picks (snapback.rent or trustthehome) once
  registered.

## Team

Vidyut ([@vs-githjk](https://github.com/vs-githjk)), Dev
([@DevSingh05](https://github.com/DevSingh05)), Jeffrey
([@jeffrey-g05](https://github.com/jeffrey-g05)) and Rishit
([@RishitRai](https://github.com/RishitRai)).
