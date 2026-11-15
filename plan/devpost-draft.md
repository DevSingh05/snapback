# SNAPBACK: Devpost draft (the eight fields)

> For the conductor's review before anything is pasted into Devpost. Built from `docs/devpost.md`
> on `main` (already reviewed, every number sourced) and from the PRs merged since. Every number
> carries its n and LIVE (the CoStar event kit), FIXTURE (team-made) or SYNTHETIC.
>
> **Rules applied:**
>
> - CoStar record figures are off: no rents, and no kit record counts.
> - No AWS claim.
> - No named person is called a scammer.
> - Nothing is said about whether any listing site detects scams.
>
> **Open PRs are not claimed:** #272 (mirrored photos), #283 (evidence image) and #302 (public
> data). Each moves into the text only once it merges. #296 (the strict 60% bar) is merged as
> `63f3122`.
>
> **Vexcel** is listed only as data we were given. No verdict line uses it until the labelled set
> merges.
>
> `plan/money-case.md` is not on any branch I can read, so its numbers aren't in this draft. Point
> me at it and I'll fold them in.

**Tagline:** Rental tour prep, with scam safety built in. Trust the home, not the ad.

## Inspiration

In February 2025, a renter near Houston found a house on Craigslist. The poster said they were the
landlord and gave the renter a door code. The renter paid $2,200 for rent and a deposit and moved
in. Two days later the real owner, a rental company, told them the poster did not own the house
(ABC13 Houston, Feb 15 2025).

They did nothing careless. The photos were of a real house, and they even got inside.

This is common:

- **Rental scams:** the FTC counted nearly 65,000 rental-scam reports since 2020 and about $65
  million lost, with a median loss of $1,000. About half of the reports in the 12 months to June
  2025 began with a fake Facebook ad (FTC, Dec 22 2025).
- **Real estate scams overall:** in 2025, 12,368 people lost $275,110,419 (FBI Boston, Aug 11
  2026). That covers all real estate scams, not only rentals.

These scams work because real photos pass. The person and the offer are what's fake, and the
home's own record can show that. So we built what a renter needs to prepare for a tour, and put
a check against the home's record inside it, before any money moves.

## What it does

**SNAPBACK is rental tour prep with scam safety built in.** Find a place, see it on the map, walk
it in 3D before you go, and check the ad before any money moves.

**Tour prep:**

- **Listings finder:** researched places from CoStar's Houston listings that fit your budget.
- **Map:** the places on a 3D city map.
- **3D walk:** "Walk it first" tours from the building's Matterport scan.
- **Tour request:** drafted to the leasing office on record. You send it yourself.

**Scam safety, built in.** Text SNAPBACK an ad before you pay and get a report: is this the real
listing, and who do I call? You send the ad on iMessage, or paste it in the one box on the web: a
link, its text or screenshots. A team of checks runs. Each reads one source and writes one sourced
line on the card:

- **Photos taken in this home:** the ad's photos are matched against the building's Matterport 3D
  scan. "Taken in this building (3 of 3 photos)", or "Taken in a different building. Red flag."
- **Contact and unit against the record:** CoStar's record of the building has the leasing
  office, its website and its units.
- **For sale, posted as a rental:** the Homes.com listings in the CoStar kit.
- **Owner of record:** the county owner roll for Houston houses, shown with that owner's own
  published rule on where it takes applications.
- **Public records:** the Texas Comptroller's company check, HUD's manager record and Houston
  address points. Each is a neutral information line that names its source.
- **The ad's own words:** asks for money, papers or haste. "Zelle before a viewing. Red flag."
- **Here now:** the poster is asked for a fresh photo of a spot in the home, and a copy of a
  listing photo is caught.

The card gives one of four verdicts:

- Hold off for now
- Don't pay. Something here doesn't match.
- Could not place these photos
- Checks passed. Still follow the two rules.

Code sets the verdict. "Don't pay" needs proof, and SNAPBACK never calls a named person a scammer.

**In iMessage, it's a conversation, not a form:**

- Photos get an instant "Got 3 photos. Checking where they were taken, about 20 seconds." Then
  comes a short report: the verdict, the top two reasons, one next step and the full report.
- "Why?", "Who do I call?", "Is it safe?" and "How did you check?" are answered from the same
  case. "How did you check?" gives one line per agent. None of them starts a new check.
- It remembers the renter's language, budget and beds for 30 days. "Show me safer homes" uses
  them, and "forget me" deletes them.
- When a listing is being copied, it offers to draft a note to the real leasing office. The note
  is marked "Draft, not sent. You send it."
- **A voice memo in gets a spoken reply out** of 15 seconds or less: the verdict, the top reason
  and who to call. It never speaks a phone number, a rent or a link.

**On the web:**

- The report shows the ad beside the real listing and a hand-off link to it.
- The Proof Room lets you watch the check team work: a Planner, Rules, Record, Phone and office,
  Owner and licence, Photo and Web, with the Decider (code) as the only one that sets the verdict.

SNAPBACK never pays, books or sends anything for you.

**What a realtor said:**

> "if he can add in additional safety features for preventing further scams and financial scams, I
> think this would be a very good app to have in the marketplace."
>
> Ashwin Veeravalli, Realtor, The Agency, Los Gatos CA

## How we built it

- **Backend:** Python 3.12 and FastAPI. Intake, the rules, the case runner and the API are in
  `src/snapback/`.
- **Code sets every verdict.** `verdict.decide()` is the only place a verdict is chosen, and no
  model ever sees or sets one.
- **LangChain deepagents runs on every case,** in the background. A planner writes todos and hands
  each check family to its own sub-agent. Each sub-agent has one read-only tool and writes its
  findings as notes in the agent file system. The answer never waits on the agent, and a hard
  time limit stops it.
- **Photo placement:** DINOv2 retrieval over views rendered from the Matterport scans, then DISK
  and LightGlue matching (kornia), RANSAC verification and a spatial-spread check.
- **Data:**
  - The CoStar kit (property records, Homes.com listings) and Matterport scans. We were also given
    Vexcel aerial imagery, which is shown as a picture and not yet used in a verdict.
  - Harris County owner records, TREC licence data, the Texas Comptroller, HUD and City of
    Houston.
  - The kit stays in a git-ignored folder. Only derived yes/no facts reach a model, never kit
    rows, photos, addresses or prices.
- **Intake:** local OCR (RapidOCR on ONNX Runtime) for screenshots, listing-field extraction and a
  prompt-injection guard.
- **iMessage:** a Node sidecar on Photon 2.0 (the Spectrum SDK).
  - Only allowlisted conversations are answered, and their ids are kept as keyed hashes.
  - It never texts first.
  - Voice uses ElevenLabs speech-to-text and text-to-speech through our API, sent as a native
    voice bubble.
- **Front end:** Vite, React and TypeScript, with a MapLibre 3D city map, an isometric house, a
  walkthrough tour and the check team's crew view. Every screen says LIVE or FIXTURE.
- **MCP server:** SNAPBACK as tools for any agent.
- **Forensics (Arlequin):** a ring finder that links ads by reworded text, shared photos, numbers
  and wordings, with Louvain communities. Every finding carries its evidence.
- **Process:** four people, each running coding agents in their own lane.
  - Every change went through a PR against shared contracts, with failing-test-first fixes and
    review.
  - CI ran on every change: a hygiene guard, ruff, ESLint, Prettier, TypeScript, pytest, the web
    and sidecar tests, and an eval gate.

## Challenges we ran into

- **Not overclaiming.** Real photos of a real home pass any photo check, so the product has to
  separate "the photos are real" from "this person may rent it". We kept "Don't pay" for proof
  only. We quoted no accuracy number until we'd measured it, and we label each number with its n,
  and with renders or photos.
- **Privacy in public records.** The county owner roll names people. We changed what the card
  shows: a private owner is "a private owner", and a company is named only when it matches one we
  already know. Each privacy gate is tested on its own by turning it off.
- **Sponsor data rules.** No kit data in git or in a log, and only derived yes/no facts reach a
  model. A hygiene guard in CI holds the line.
- **Messaging is messy.** iMessage photos arrive as grouped messages. Voice memos come in Apple's
  CAF format and have to be converted. A spoken reply must never read out a phone number. And a
  reconnecting event stream must never text the same alert twice.

## Accomplishments that we're proud of

- **One rule held from start to finish:** code sets the verdict, and every line on the card says
  where its fact came from.
- **Photo placement on real listing photos, LIVE** (CoStar OK'd sharing the totals): "Measured on
  78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys
  fooled it." Re-measured on the final matcher with the same counts (n=48 photos, n=30 decoys).
  The right room is not measured, and we don't claim it.
- **A live tamper test** (LIVE; a real listing and tampered copies of it, nothing posted anywhere):
  - a changed phone number, caught 6 of 6 on real photos and 2 of 2 on scan renders;
  - "send the deposit by Zelle before the tour", caught 6 of 6 and 2 of 2;
  - a lookalike website link, caught 6 of 6 and 2 of 2.
- **Batch run** (FIXTURE, composed ads): 117 of 123 handled as expected, including 43 of 43 clean
  messages left alone.
- **The news case we started from** replays end to end and stops at Hold off before the $2,200
  goes out (FIXTURE replay).
- **Speed** (LIVE): text-only checks take about 1 s, and checks with photos about 19 to 26 s.
  - The spoken iMessage reply is 11.8 to 12.5 s long, and making it takes 1.31 to 1.55 s
    (ElevenLabs, n=3, on the demo laptop).
- **Forensics** (SYNTHETIC, n = 301 ads with 4 seeded rings):
  - 4 of 4 rings recovered and 0 of 244 honest ads flagged; a keyword baseline found 0 of 4.
  - On 10 held-out seeds, ring precision was 0.88 and recall 0.93.
  - The corpus and the method were built together, so this is not an accuracy claim for real
    listings.

## What we learned

- The strongest signal is often not the photo but the record behind it: who owns the home, who
  manages it, and whether it is for sale.
- Saying "not checked" honestly builds more trust than a confident guess.
- Renters won't download an app in the middle of a scam. The check has to live where the ad
  arrives: a text thread.

## What's next

- **Edited and AI-made photos.** One AI-edited photo was caught as inconsistent with the real scan
  (n=1). A stricter bar now runs, but at n=1 it needs measuring before we claim more.
- **University partnerships for international students,** who rent from abroad, sight unseen and
  to a deadline. Pre-arrival housing guides could carry "check any listing before you send a
  deposit".
- **Platforms:** CoStar could ship this beside its listings, and other platforms could run the
  check when an ad is posted.
- **Reach:** more cities and languages (English and Spanish today), and accuracy measured on real
  ad photos at scale.

## Built with

Python, FastAPI, pydantic, uv, PyTorch, DINOv2, kornia (DISK, LightGlue), FAISS, OpenCV, RapidOCR,
ONNX Runtime, LangChain deepagents, TypeScript, React, Vite, MapLibre, Node.js, Photon 2.0
(Spectrum SDK, iMessage), ElevenLabs, Matterport, CoStar and Homes.com data, Vexcel aerial
imagery (provided), GitHub Actions.

## Tracks

> **For the reviewer, not for Devpost:**
>
> - One section per track. Numbers come only from merged PRs, each with n and LIVE, FIXTURE or
>   SYNTHETIC.
> - **The A8 photo line is current.** Dev re-measured it on main `f3d17f0`, after #296's strict
>   bar (M1, #8), and got the same counts: 43 of 48, 0 of 48 wrong, 0 of 30 decoys.
> - **Not on `main` yet, so not claimed:**
>   - the deep agent's per-ad plan, re-planning and next-step draft;
>   - the Arlequin ring case file, case study and reworded-ads test;
>   - photo auto-fade;
>   - `/under-the-hood`;
>   - the loose-match warning (#297) and the evidence image (#283).
>     Each goes in once it merges.

### CoStar · Inside and Out

**What we built on CoStar's data:** every ad is checked against CoStar's own record of the
building: its leasing office, its website, its units and its Matterport scan. The report then
sends the renter back to the real listing.

- **Photos placed in CoStar's 3D scans** (LIVE, re-measured on the final matcher; CoStar OK'd
  sharing totals): of n=48 real listing photos, 43 were placed in the right home and 0 in a wrong
  one. Of n=30 decoys, 0 were placed in the claimed building.
- **Live tamper test (LIVE; a real listing and tampered copies of it, nothing posted):**
  - a changed phone number, a "Zelle before the tour" ask and a lookalike website link;
  - each was caught 6 of 6 on real photos and 2 of 2 on scan renders.
- **Respects the data:** record figures (rents) are off by default. Only derived yes/no facts
  reach a model, and the kit is deleted after Sun Nov 15 16:00.

**Where to see it:**

- the report at `/case/<id>`: the ad beside the real listing, with "See the real listing" (#250,
  #299);
- the photos placed in the 3D scan at `/case/<id>/twin`;
- the draft note to the real leasing office, in the report and in iMessage (#250, #276).

### LangChain · deepagents

**What we built on deepagents:**

- A deep agent runs on every case, in the background (#273).
- It plans with todos and hands each check family to its own sub-agent. Each sub-agent has one
  read-only tool and writes its findings as notes in the agent file system.
- It never sets the verdict. It has none of the choice tools, so it can't move a case, and
  `decide()` in code sets every verdict.

**Measured (FIXTURE backend, real model runs, #273):**

- the case answer returns in 0.03 to 0.09 s, without waiting for the agent (n=6);
- the agent's first step: median 2.35 s (2.14 to 6.02, n=5);
- the agent done: median 22.9 s (21.8 to 25.7, n=5), with no fallbacks.

**Where to see it:**

- the check team working beside the 3D scan at `/case/<id>/twin`, also at
  `/proof-room?case=<id>`;
- the step-by-step trace at `/case/<id>/trace`;
- "How did you check?" in iMessage, which answers with one line per agent (#275).

### Arlequin · AI forensics

**What we built:** an investigator view that finds the ring behind many ads. It links ads by
reworded text, shared photos, numbers and wordings, finds communities, and gives every finding
its evidence.

**Measured (SYNTHETIC; the corpus and method were built together, so this is not an accuracy
claim for real listings):**

- **300-ad corpus** (n = 301, 4 seeded rings): 4 of 4 rings recovered, 57 of 57 ring ads found
  and 0 of 244 honest ads flagged. A keyword baseline recovered 0 of 4. On 10 held-out seeds, ring
  precision was 0.88 and recall 0.93.
- **90-day stream** (n = 1 seed, 3,039 ads, 10 rings, #268): ad recall 0.927 and 0 of 2,684
  honest ads flagged, against a keyword baseline's recall of 0.014. Honest limit: it merges
  separate rings into larger groups, so 0 of 10 rings were recovered at the 0.7 overlap bar.
  Splitting them is next.

**Where to see it:** `/investigate`.

### Photon · Build a Messaging Agent (+ Best Voice Agent)

**What we built on Photon 2.0:** SNAPBACK lives in iMessage through the Spectrum SDK.

- **The thread:**
  - Forward an ad, as text, a screenshot or photos. An instant line says what's happening, then
    the short report arrives with a picture of the card.
  - "Why?", "Who do I call?", "Is it safe?" and "How did you check?" are answered from the same
    case, without a new check.
  - It remembers the renter's language, budget and beds for 30 days ("forget me" deletes them).
  - It drafts a note to the real leasing office, which is never sent automatically.
- **Voice:** a voice memo in gets a native voice bubble out. The spoken reply is 15 s or less:
  the verdict, the top reason and who to call, and never a phone number, a rent or a link.
- **Safety:** only allowlisted conversations are answered, it never texts first, and every reply
  goes to its own thread only.

**Measured:**

- **Server-side reply time** (FIXTURE; the demo laptop, not counting Photon delivery):
  - a text ad: p50 14 ms, p90 15 ms (n=10, all 10 ok);
  - a screenshot read by local OCR: p50 862 ms, p90 890 ms (n=10, all 10 ok);
  - "why?": p50 2 ms (n=20).
- **Spoken reply** (ElevenLabs, n=3, on the demo laptop): 11.8 to 12.5 s long, made in 1.31 to
  1.55 s.

**Where to see it:** text the SNAPBACK line from the team phone at our table. Merged in #204,
#232, #245, #255, #264, #275, #276 and #281.

### Amazon · Best Practical AI

These answer the packet's five focus areas.

- **Agentic behavior:** a planner agent with a sub-agent per check runs on every case, and code
  sets the verdict (see LangChain above).
- **Real-world impact:**
  - The FTC counted nearly 65,000 rental-scam reports since 2020, with a median loss of $1,000.
  - Batch run (FIXTURE, composed ads): 117 of 123 ads and messages handled as expected,
    including 43 of 43 clean messages left alone.
- **Adaptive intelligence:**
  - Follow-up questions are answered from the renter's own case.
  - iMessage remembers language, budget and beds (#264), and "show me safer homes" uses them.
- **User-friendly design:** one box on the web, or one text in iMessage. The short report gives
  the verdict, the top two reasons and one next step. Text-only checks take about 1 s, and checks
  with photos about 19 to 26 s (LIVE).
- **Creative innovation:** the renter checks an ad in the same thread where the scam arrives, and
  the answer is built from the home's own record and 3D scan.

**Where to see it:** the home page box and the report at `/case/<id>`.

### Best Overall · Business and Enterprise

- **Who pays today:** the renter, with a median loss of $1,000 (FTC, Dec 22 2025), and the
  listing businesses whose listings are copied to bait them.
- **Covers the homes CoStar doesn't (#302):** free public sources fill the gaps.
  - **Sources:** HUD's typical rent by ZIP and bedroom count (3,238 Texas ZIP rows), the Census
    address check, the county owner of record and the website's domain age.
  - Each source names itself on the card. The rent cutoff for HUD isn't measured yet (0 Texas
    ads in our eval bank), so we don't claim its accuracy.
- **What a realtor said:** see the quote under "What it does" (Ashwin Veeravalli, Realtor, The
  Agency, Los Gatos CA).
- **Public ratings:** `/reviews` shows ratings from a public form, with n on every number (#306).
- **Where to see it:**
  - tour prep on the home page and `/map`;
  - the reported cases replayed at `/replay`;
  - renters' stories at `/stories`;
  - ratings at `/reviews`.
