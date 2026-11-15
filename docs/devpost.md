# SNAPBACK: Devpost draft

> Draft for the HackPrinceton Fall 2026 Devpost page. Every number carries its n and whether it
> is LIVE (the CoStar kit) or FIXTURE (synthetic, team-made). Sources: the README, the PRs on
> `main` and the team board. Features not yet on `main` are listed under "In progress" only.
> Quotes are word for word from the sources named beside them.

## Tagline

**Trust the home, not the ad.**

"I text SNAPBACK a rental ad before I pay and get a report: is this the real listing, and who do I
call?"

How it works:

1. Send the ad (iMessage, or paste it in the box).
2. We check it against CoStar's record of the building (and its 3D scan where one exists).
3. You get a report: the verdict in plain words, the ad beside the real listing, what to do next,
   and safer homes on Apartments.com.

One prong: the scam check before you pay. Everything else lives inside the report.

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
- **It is common.** The FTC (Dec 22 2025) counted nearly 65,000 rental-scam reports since 2020,
  about $65 million lost, with a median loss of $1,000. About half of reports in the 12 months to
  June 2025 began with a fake Facebook ad.
- **It is costly.** The FBI's Boston office (Aug 11 2026) reported that 12,368 people lost
  $275,110,419 to real estate scams in 2025 (all real estate scams, not only rentals).

SNAPBACK meets the renter where the copy is: they paste it, upload it or text it, and the home's
own record answers before any money moves. CoStar could ship this beside its listings.

## Who it serves

1. **The renter about to pay.** Our two stories: Sascha, and a student moving from India to
   Houston who must sign before she lands.
2. **The leasing office whose listing is copied.** We draft a "your listing is being copied" note
   for the office on record. It is never sent automatically.
3. **CoStar and Apartments.com.** Check before you pay, and the renter is handed back to the real
   listing.
4. **The public.** A report the renter can file. Free for renters.

The live moment of our pitch is the iMessage round trip: text the ad, get the report in the same
thread.

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
- **Photo placement, LIVE (A8, #72; CoStar OK'd sharing totals):** "Measured on 78 real listing
  photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it." The
  right room is not measured, and we don't claim it.
- **Live tamper test, LIVE (a real listing and tampered copies of it; nothing posted
  anywhere).** Counts are Dev's run on real photos, then Jeffrey's on scan renders:
  - Phone number changed: caught 6 of 6 and 2 of 2.
  - "Send the deposit by Zelle before the tour": caught 6 of 6 and 2 of 2.
  - Lookalike website link: caught 6 of 6 and 2 of 2.
  - Rent cut 40%: flagged 2 of 2. Rent cut 30%: not flagged, by design. We flag only rents far
    below the building's lowest rent, so honest discounts pass.
  - Cropped photos still match (14 of 18; 4 of 4). Mirrored photos mostly stop matching (4 of 18
    placed) and were never placed in a wrong home.
- **Batch run, FIXTURE (composed ads, n per type, re-measured after the new rules):** cloned
  phone 9 of 9 held; another building's photos 6 of 6 "Don't pay"; price cut 9 of 9 held; a
  for-sale home listed as a rental 3 of 3 held; clean ads 6 of 6 cleared; clean messages 43 of 43
  cleared; messages with money asks 41 of 47 caught. Overall 117 of 123.
- **CoStar record coverage, LIVE kit (counts):** 3,339 records; 2,139 have the building's
  website; 1,747 have floor-plan rents; 708 have an availability page. The locate index on the
  demo machine holds 21 scans.
- **Speed, LIVE:** text-only checks take about 1 s; checks with photos take about 19 to 26 s.
- **Forensics, SYNTHETIC/FIXTURE corpus:** on n = 301 ads with 4 seeded rings (57 ring ads), it
  recovered 4 of 4 rings, found 57 of 57 ring ads and flagged 0 of 244 honest ads. A keyword
  baseline recovered 0 of 4 rings. On 10 held-out seeds (about 300 ads each) it averaged ring
  precision 0.88 and recall 0.93. The corpus and the method were built together, so this shows
  the method works on rings shaped like these. It is not an accuracy claim for real listings.
- **Replays of reported cases, FIXTURE:** two staged replays (the move-in paid to a poster who
  didn't own the house, and a Zelle deposit for a house never for rent) both stop at Hold off,
  before the payment.

## Limitations

- **Not every home has a 3D scan.** The rules, phone and link checks run on any ad. Rent, office,
  manager and website need CoStar's record, and photo placement needs a scan. Where we lack one,
  the report says "not checked", never a guess.
- **This weekend: the Houston area,** from CoStar's event kit.
- **Mirrored photos can defeat the photo match.** The other checks still run.
- **An honest ad reads "Hold off" until the poster proves they're inside** (one tap). We never call
  a home safe without proof.

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

- **The report page** that shows the real listing beside the ad, with its hand-off link to
  Apartments.com (#265). The real-listing API behind it is on `main` (#250).
- **Adaptive memory in iMessage:** it learns the renter's language, budget and beds, and "show
  me safer homes" uses them (#264).
- The **Stories** page (#265).

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

Main track: **Business and Enterprise.** Sponsor tracks: **CoStar**, **Amazon Best Practical
AI**, **LangChain deepagents**, **Arlequin Track 1** and **Photon** (+ Best Voice Agent). Each
section answers that sponsor's own criteria.

### Business and Enterprise

- **Who pays today:** the renter, with a median loss of $1,000 (FTC, Dec 22 2025), and the
  listing businesses whose real listings are copied to bait them.
- **Who it serves:** the renter about to pay, the leasing office whose listing is copied, CoStar
  and Apartments.com (the renter is handed back to the real listing), and the public. Free for
  renters.
- **How it fits a business:** every check reads a record the business already keeps (the
  property record, its office, its website, its floor-plan rents, its 3D scan). CoStar could ship
  this beside its listings.

### CoStar

- **Uses the record, not guesses:** each ad is checked against CoStar's own record of the
  building. In the event kit: 3,339 records; 2,139 with the building's website; 1,747 with
  floor-plan rents; 708 with an availability page (LIVE kit, counts).
- **Measured on CoStar's own data (LIVE):** "Measured on 78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it." In the live tamper test, a changed phone,
  "send the deposit by Zelle before the tour" and a lookalike website link were each caught 6 of
  6 (real photos) and 2 of 2 (scan renders).
- **Sends renters back to CoStar:** the report ends with the real listing on Apartments.com.
- **Respects the data:** the kit stays on the machine and is deleted after Sun Nov 15 16:00.
  Only derived yes/no facts reach a model, never kit rows, photos, addresses or prices.

### Amazon Best Practical AI

- **Creativity:** the renter checks an ad by texting it, in the same thread where the scam
  arrives, and the answer is a report built from the home's own record.
- **Usefulness:** it answers the one question that matters before money moves, "is this the real
  listing, and who do I call?". Batch run (FIXTURE): 117 of 123 ads and messages handled as
  expected, including 43 of 43 clean messages cleared.
- **Technical work:** code sets every verdict; a model only picks the order of checks and writes
  explanations, through deepagents. Photo placement uses DINOv2 retrieval and DISK + LightGlue
  matching over Matterport scans (LIVE): "Measured on 78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it."
- **UX:** one text in, one short report out: the verdict, "Before you pay:" with the top two
  reasons, one next step and the full report. Text-only checks take about 1 s, and checks with
  photos about 19 to 26 s (LIVE).
- **Adaptive:**
  - Follow-ups ("why?", "who do I call?", "is it safe?") answer from the renter's own case, without
    a new check.
  - The Finder learns preferences by consent (#238).
  - In iMessage, adaptive memory learns the renter's language, budget and beds, and "show me safer
    homes" uses them. This is in review (#264), so it's listed under In progress.
- **AWS:** nothing in the repo uses AWS yet. This is what we'd run on it: the API on a container
  service, the photo index on a GPU instance, and the per-renter memory in a managed key-value
  store.

### LangChain deepagents

- **A planner, not a verdict:** the main agent plans with `write_todos` and hands each check family
  to its own sub-agent. Each sub-agent gets one read-only tool, a narrow prompt and permission to
  write one file.
- **Findings as files:** sub-agents leave notes in the deepagents file system under /case/<id>/.
  The main agent reads them and writes the explanation and tour questions.
- **Bounded choices:** the model gets four tools and can only pick from options code wrote.
  Sending the challenge is gated by the harness's human-in-the-loop interrupt.
- **The Finder crew (#238) and the place and walk sub-agents with a retry budget (#222)** run on
  the same harness.
- **Safe by construction:** whatever the model does, the driver finishes the case with the code
  policy, and the verdict is still `decide()` on the evidence. No note is read by `decide()`.

### Arlequin Track 1

- **One renter's check answers one ad; an investigator needs the ring behind many.** The
  investigator view links ads by reworded text, shared photos, numbers and wordings, finds
  communities, and builds each ring's timeline. Every finding carries its evidence.
- **Measured, SYNTHETIC/FIXTURE:** on n = 301 ads with 4 seeded rings (57 ring ads): 4 of 4 rings
  recovered, 57 of 57 ring ads found, 0 of 244 honest ads flagged. A keyword baseline recovered 0
  of 4. On 10 held-out seeds (about 300 ads each): ring precision 0.88, recall 0.93. The corpus
  and method were built together, so this is not an accuracy claim for real listings.

### Photon (+ Best Voice Agent)

- **Built on Photon:** the sidecar runs on Photon's Spectrum SDK (`spectrum-ts`) and is live on
  iMessage. A real round trip from a phone works.
- **The messaging is essential:** renters don't download an app in the middle of a scam. They
  forward the message, and SNAPBACK answers in the same thread.
- **In the thread:**
  - a "checking" reply, then a short report and the card picture (#255);
  - "why?", "what should I do?", "who do I call?" and "is it safe?" answered from the same case;
  - watch alerts at most 3 a day, with "stop" to end them (#232).
- **Voice:** a voice memo is written down by our speech-to-text and checked like a typed ad. The
  answer comes back as text plus a voice memo, sent as a native voice bubble (#245).
- **Safe by design:** only allowlisted threads, never texts first, no case token and no phone
  digits in any reply.

## Team

Vidyut ([@vs-githjk](https://github.com/vs-githjk)), Dev
([@DevSingh05](https://github.com/DevSingh05)), Jeffrey
([@jeffrey-g05](https://github.com/jeffrey-g05)) and Rishit
([@RishitRai](https://github.com/RishitRai)).
