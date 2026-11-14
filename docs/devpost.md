# SNAPBACK: Devpost draft

> Draft for the HackPrinceton Fall 2026 Devpost page. Every number carries its n and whether it
> is LIVE (the CoStar kit) or FIXTURE (synthetic, team-made). Sources: the README, the PRs on
> `main` and the team board. Features not yet on `main` are listed under "In progress" only.
> Quotes are word for word from the sources named beside them.

## Tagline

**Trust the home, not the ad.** Paste a rental ad you found online. SNAPBACK checks it against
the home's own record before you pay anyone.

CoStar protects the listings on its own sites; SNAPBACK protects the renter from the ad that
copies one, wherever it shows up, and sends them back to the real listing on Apartments.com.

## Scam prevention first

Many rental scams happen on the copy: a real home's photos, reposted somewhere else, with a
stranger's phone number and a request for money.

- **The renter is the one holding the copy.** CoStar's own scam page warns renters that "Scammers
  may impersonate Apartments.com or Apartment Finder to make it seem like we participate in the
  lease transaction or transfer of funds", and that "we do not participate in any rental
  transactions and cannot refund your money if you are scammed" (apartmenthomeliving.com, "Avoid
  scams and fraud", © 2026 CoStar Group). A listing site can't see ads posted elsewhere; the
  renter is the one holding the copy.
- **It is common.** The FTC (Dec 22 2025) counted nearly 65,000 rental-scam reports and about
  $65 million lost. About half of people reporting in the 12 months ending June 2025 said it
  began with a fake Facebook ad.
- **It is costly.** The FBI's Boston office (Aug 11 2026) reported that 12,368 people lost
  $275,110,419 to real estate scams in 2025 (all real estate scams, not only rentals).

SNAPBACK meets the renter where the copy is: they paste it, upload it or text it, and the home's
own record answers before any money moves. CoStar could ship this beside its listings.

## Inspiration

In February 2025, a renter near Houston found a house on Craigslist. The poster said he was the
landlord and gave her a door code. She paid $2,200 for rent and a deposit and moved in. Two days
later the real owner, a rental company, told her the poster did not own the house (ABC13 Houston,
Feb 15 2025).

She did nothing careless. The photos were of a real house, and she even got inside.

These scams work because real photos pass. The person and the offer are what's fake, and the
home's own record can show that. So we built a renter's agent that checks the ad against the
record before money moves.

## What it does

You paste the ad: a link, its text, or screenshots. You can also text it to SNAPBACK on iMessage.
SNAPBACK runs a set of checks, each reading one source and writing one sourced line on a card:

- **Photos taken in this home:** the ad's photos are matched against the building's Matterport 3D
  scan. "Taken in this building (3 of 3 photos)" or "Taken in a different building. Red flag."
- **For sale, posted as a rental:** the Homes.com listings in the CoStar kit.
- **Owner of record:** the county owner roll for Houston houses. "Owner of record: a large rental
  company, not the poster", quoted with that owner's own published rule on where it takes
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
  git-ignored folder. Only derived yes/no facts reach a model, never kit rows, photos, addresses
  or prices, as CoStar allowed for the event.
- **Intake:** local OCR (RapidOCR on ONNX Runtime) for screenshots, listing-field extraction and
  a prompt-injection guard.
- **Front end:** Vite, React and TypeScript, with a MapLibre 3D city map, an isometric 3D house
  and a walkthrough tour. Every screen says LIVE or FIXTURE.
- **The one box:** the home page is a single box. Type, talk, paste or drop an ad; code routes it
  and answers inline (#243).
- **MCP server:** SNAPBACK as tools for any agent, over local stdio: six tools, and the tour
  request stays a draft (#241).
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

- **Locate gate, LIVE scans, renders (not photos):** of n = 20 claimed-building views and
  10 other-building views, from unseen directions, 20 of 20 were placed in the right building with
  0 false placements (held-out seed, #28).
- **Photo accuracy on real listing photos, LIVE (A8, #72; CoStar OK'd sharing totals):** of
  n = 78 photos (48 from the indexed homes, 30 decoys), 43 of 48 were placed in the right home,
  0 were placed in a wrong one, and 5 could not be placed; 0 of 30 decoys fooled it. Right room
  was not measured.
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
- **Sponsor data rules.** No kit data in git or in a log, and only derived yes/no facts to a
  model, with a hygiene guard in CI to hold the line.
- **Real-world plumbing:** door codes that pass a presence check, iMessage photos that arrive as
  grouped messages, Windows tooling quirks, and a reconnecting event stream that must never text
  the same alert twice.

## Accomplishments we're proud of

- One rule held from start to finish: code sets the verdict, and every line on the card says
  where its fact came from.
- A real iMessage round trip from a phone: text an ad and get the card back in the thread.
- The news case we started from replays end to end and stops at **Hold off** before the $2,200
  goes out. The card shows that a large rental company, not the poster, is the owner of record,
  with that company's own rule.

## What we learned

- The strongest signal is often not the photo but the record behind it: who owns the home, who
  manages it, and whether it is for sale.
- Saying "not checked" honestly builds more trust than a confident guess.

## In progress

Built, not yet on `main`, so not claimed above:

- **The real listing:** a panel that shows the home's real listing, a hand-off link back to it on
  Apartments.com, and an alert when an ad looks copied from it (#250).
- **New rules,** and a **batch run** over many ads at once.
- The **Stories** page.
- **Voice in iMessage:** merged in the sidecar (#245); the live round trip from a phone is next.

## What's next

- **University partnerships for international students.** They rent from abroad, sight unseen,
  and often to a deadline. Pre-arrival housing guides could carry "check any listing before you
  send a deposit".
- **Platforms:** CoStar could ship this beside its listings, and other platforms could run the
  check when an ad is posted. Today it works on any listing a renter can paste or forward.
- **More cities, more languages** (English and Spanish today), and measured accuracy on real ad
  photos at scale.

## Data and terms

Data used during HackPrinceton under the sponsor's terms and deleted after Sun Nov 15 16:00; the
public build shows FIXTURE data.

## Built with

Python, FastAPI, pydantic, uv, PyTorch, DINOv2, kornia (DISK, LightGlue), FAISS, OpenCV,
RapidOCR, ONNX Runtime, deepagents, TypeScript, React, Vite, MapLibre,
Node.js, Photon Spectrum (iMessage), Matterport, Vexcel, CoStar and Homes.com data, GitHub
Actions.

## Tracks

- **CoStar:** checks every ad against CoStar's own property records, the Homes.com listings, the
  Matterport scans and the Vexcel aerial imagery, then turns that data into a safer search. The
  kit stays on the machine. Only derived yes/no facts reach a model, never kit rows, photos,
  addresses or prices, as CoStar allowed for the event.
- **Photon (+ Best Voice Agent):** the iMessage sidecar is live on Photon's Spectrum SDK: text an
  ad and get the card back. Watch alerts text a linked Finder search at most 3 times a day, and
  "stop" ends them. Voice memos in and spoken replies out are built (#245): a memo is written down
  by our speech-to-text and checked like a typed ad, and the answer comes back as text plus a voice
  memo. The live round trip from a phone is next.
- **Arlequin:** the investigator view finds rental-scam rings across many ads, with evidence for
  every link, on a SYNTHETIC/FIXTURE corpus (numbers above).
- **GoDaddy domain:** TBD.

## Team

Vidyut ([@vs-githjk](https://github.com/vs-githjk)), Dev
([@DevSingh05](https://github.com/DevSingh05)), Jeffrey
([@jeffrey-g05](https://github.com/jeffrey-g05)) and Rishit
([@RishitRai](https://github.com/RishitRai)).
