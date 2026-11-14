# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Sat Nov 14 2026, 01:10. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

## Decisions (locked)

- Fri 20:59 Team is Vidyut, Jeffrey, Rishit, Dev. Product: SNAPBACK. (Vidyut)
- Fri 21:10 Real addresses are OK in the demo video, but stay out of this repo. (Vidyut, from CoStar staff)
- Fri 21:15 Judges watch the presence challenge on team phones; they do not use their own. (Vidyut)
- Fri 21:22 Rentals for the build. Buying (seller impersonation) is the named next market. (Vidyut)
- Fri 21:22 Data gate moved to 22:15; switch to the fallback idea (PRETEXT+) by 22:45 if the data gate fails. (Vidyut)
- Fri 21:22 `main` is controlled by Vidyut + the conductor + the XO. Everyone else works on branches from issues. (Vidyut)
- Fri 21:22 All four download the CoStar kit now; this repo's README has the steps. (Vidyut)
- Fri 21:39 Dev's skeleton (1406815) is the base: layout, tooling, AGENTS.md, CI, hygiene guard. Only the XO merges to main; agents never push to main. (Vidyut + Dev)
- Fri 21:48 CoStar Terms accepted as written (IP assignment to CoStar is fine for a hackathon project). Each person accepts for themselves and runs `/costar-keys` in `#costar-group` for their own key. (Vidyut + Dev; Jeffrey and Rishit accept for themselves)
- Fri 21:48 Scope: 12 committed modules plus the eval harness, then ordered stretch 13 tactic classifier, 14 scam-ring graph, 15 listing-time platform screen (S5), 16 feedback loop with anti-poisoning. See docs/ROLES.md. (Vidyut)
- Fri 21:53 FINAL split: A agent/backend = Dev; T front end = Vidyut + Claude; V vision/ML = Jeffrey; D data + iMessage = Rishit. The XO runs the repo: issues, reviews, merges. (Vidyut)
- Sat 00:35 Plan v3.2 (plan/snapback-v3.2.md, planner summary): one product, three proofs (PLACE, PERSON, PRICE), plus replays of real reported scams (#71, LOCKED 00:35). (Vidyut)
- Sat 00:35 New issues #66-#79: D7 #66, A7 #67, V8 #68, eval route #69, D8 #71, A8 #72, A9 #73, V9 #74, T7-T11 #75-#79. #18, #19, #34 closed as design-only.
- Sat 00:35 Overnight mode 01:30-07:30: humans sleep, agents work their v3.2 queue on their epic issue (#8 #10 #11, plan on #41). (Vidyut)
- Sat 00:35 Token ruling: `GET /eval/results.csv` is public (aggregate only, no case data). (conductor, #69/#70)
- Sat 00:35 Card words are locked; use the locked wording everywhere (CardPage.tsx included, #76). (conductor)
- Sat 00:50 Schedule LOCKED: sleep 01:30-07:30 (agents keep working their queues); feedback round about 10:00 (we go and talk to people), build all day, second feedback round in the evening; demo video made in parallel during the day. **New features stop Sun 01:00**; after that only rest, polish, bug fixes, demo prep. Hard deadline Sun 08:00. (Vidyut, #41)
- Sat 00:38 Ruling: a recapture flag is a model score, not proof: it stays WAITING and asks for a new photo, never FORGED. FORGED only for a wrong or missing code, or a confirmed copy of a listing photo. (conductor, #37)
- Sat 00:40 Ruling: home actively listed for sale = red flag + HOLD, never DON'T PAY. DON'T PAY only on proof (presence FORGED or a photo taken elsewhere). (conductor, #67)
- Sat 00:44 Ruling: eval results are public and read-only (`GET /eval/results.csv`, no token, aggregate only). (conductor, #70)
- Sat 01:03 Ruling: the `unverified` headline is the locked "Could not place these photos" (strings.py), in every surface incl. iMessage (#83). (conductor)
- Sat 01:03 Ruling: Dev does A10 live modules join (CoStar record #80 + D7 lookup #95 into the price, unit and contact rules) BEFORE the A8 harness; then A11 register_case, A12 card.png cache + zone label, A13 end-to-end API test of DEMO_CASE a/b/c. (conductor, #8)
- No "SAFE", "VERIFIED" or "SCAM" state anywhere. Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

Lanes and paths: `.github/CODEOWNERS` and `docs/ROLES.md`. Each lane has an epic issue (label
`epic`: A #8, T #9, V #10, D #11) with ordered task issues; each person's agent starts from `docs/agents/kickoff-<name>.md`.

| Person  | GitHub      | Lane                                 | Now                                                                                                                                                                                                          |
| ------- | ----------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Dev     | DevSingh05  | A. agent and backend                 | A1-A6 merged, eval route #70, contracts #88 #92 merged. Open: #87 A7 rules (in review), #91 A9 demo cases (stacked on #87), #96 A8 harness (not run; needs V2 + kit). Next: A10 live join, then A11-A13 (#8) |
| Vidyut  | vs-githjk   | T. front end (with Claude)           | T7 hero #86, T11 replay #89 merged. Open: #90 T8 card rows, #94 T9 two-building aerial proof (in review); design r6 artifact                                                                                 |
| Jeffrey | jeffrey-g05 | V. vision and ML                     | V1 #63 merged. Open: #61 V5 (264900f), #62 V6 (4c88e6d) in review. Overnight queue (#10): V8 #68 probes, V2 pose #28 (02:00: 5 photos on 1 building), locate JSON, V9 #74                                    |
| Rishit  | RishitRai   | D. data, iMessage, challenge, safety | Claude Pro. D1 #80, D2 #81, D6 #85 merged. Open: D3 #82, D4 #83, D5 #84 (FIX posted), D7 #95 (queued). Blocked: kit download, Vexcel docs (morning)                                                          |

## Data facts (REPORTED until our probe confirms)

- CoStar data is a JSONL file in the kit (`commercial-property.jsonl`, about 3,339 records), not an API.
- Houston research market id 14: about 1,758 records, about 1,314 multifamily, about 1,732 with a Matterport model id.
- Matterport model ids: `attachments[]` entries with `videoExternalReferenceType` 36 or 234; `videoKey` is the model id.
- Apartment scans are model units per floor plan ("2BR, 2BA ..."), not the exact unit. A match claims "this building, this floor plan", never a unit number.
- Matterport Model API: `POST https://api.matterport.com/api/models/graph`, HTTP Basic (token id : secret); six 1024 px skybox faces per sweep.
- Vexcel REST: `https://api.vexcelgroup.com/v2`, header `X-API-KEY`, rate limited (back off on 429).
- No rent, owner or leasing contact field is known yet. Plan for NO until the probe shows one.

## Terms rules

- Sponsor imagery and records never go into git and never go to an outside AI (Claude included) unless CoStar says yes. Matching runs on our machines.
- Claude sees only the renter's own text and yes/no facts we derive.
- Matterport's agreement bans caching API content; we asked CoStar for a weekend exception. Until answered, keep any cache local and purge after judging.
- Owner names: companies only; for a person, show only "matches owner of record: yes / no".
- No real addresses in code, fixtures, tests or docs.

## Gates

- **Fri 22:15 data gate** (issue #5): GO if at least 3 Houston (or LA) multifamily buildings load a Matterport model on our keys (`scripts/probe_kit.py` prints `DATA GATE`).
- **Fri 22:45**: if the data gate failed, switch to PRETEXT+.
- **Sat 02:00 locate and learn gate**: 15 of 20 held-out real photos located; recapture v0 trained (150 genuine, 150 attacks); Photon round trip with a photo; card from a live record.
- **Sat about 10:00 feedback round 1**; evening feedback round 2.
- **Sun 01:00 new features stop** (replaces the old Sun 02:00 freeze); after that polish, bug fixes, demo prep only.
- **Sun 08:00 hard deadline.** Older interim gates (Sat 08:00 recapture v1, Sat 18:00 storyboard, Sat 20:00 recapture v2) still stand as targets.

## Open questions

- Fri 21:15 CoStar q1: may kit data go to Claude? (CoStar, via Discord)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed yet (NOT re-checked at 01:10). main = afdf692 (Sat 01:04).
- Merged 00:34-01:04: #59 A6 card, #70 eval route, #80 D1 CoStar adapter, #81 D2 Vexcel tile, #85 D6 red team, #86 T7 hero, #88 A7 contract stub, #89 T11 replay, #92 Card.for_sale.
- Open PRs at 01:04: #61 #62 (Jeffrey, in review), #82 #83 #84 (Rishit, FIX posted), #87 #91 #96 (Dev, #87 in review), #90 #94 (lane T, in review), #95 (D7, queued).
- Contract fields on main (#88, #92), additive and optional: `PropertyRecord.site_phone_hash` (keyed hash, never digits; both lanes use the same phone hash helper), `website_host` (host only), `floor_plan_rents[]` (name, beds 0=studio, rent_min, rent_max, per_bed), `units[]` (unit, beds, floor_plan); `AuthorityResult.office_phone_match`, `link_domain` (yes/no only); `ForSaleMatch` (status active / recently_rented / none, site, listed_on, changed_on) on `ModuleEvidence.for_sale` and `Card.for_sale`. Pending in #87: `PriceResult.compared_beds`.
- Fri 22:10 data gate GO: 3/3 Houston multifamily Matterport models load on Vidyut's key (issue #5); apartment-listing has min/max rent per floor plan and the management company.
- API: `POST /cases` returns `token` (write; Bearer header only) and `read_token` (trace/status; may go in `?token=`). `/c/:id` card stays public.

## Gotchas

- Env names are Dev's: `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `VEXCEL_API_KEY`, `COSTAR_ZIP_PASSWORD` (`.env.example`). Kit goes in `data/` (git-ignored).
- Null fields are omitted from CoStar records: always use `.get`.
- Enum 0 and missing keys mean unknown, not "no".
- Fixture ids start with `fx-`; never use a real address or a real Matterport model id in a fixture.
- Event packet: the in-person demo is capped at 2 minutes; projects due 08:00 Sun is the safe reading (schedule says 08:30/08:45).
- Quickstart (unchecked on our keys): cube faces at 2k or 4k, a defurnished view of the same panoramas, labelled rooms with dimensions, and a residential folder joined by a home listing id. Probe the residential file too.
- Sponsor Terms: all copies, caches and derivatives deleted when the event period ends (Sun 16:00); no sponsor data in a public demo or repo.
- Branch names: `<lane>/<issue#>-<slug>` with lane `a`, `t`, `v` or `d`. Task PRs say `Closes #n`; epic and inbox issues only `Refs #n`.
- Fri 23:35 Unbounded regex on user text is a DoS: `[\w.+-]+@` took 26 s on 80k chars. Bound every quantifier and cap text length before any pattern runs.
- Fri 23:38 Never put the write secret in a URL (uvicorn logs the query string); use the read-only token for EventSource.
- Fri 23:45 SQLite connections are per thread; FastAPI sync routes run in a threadpool. Open per call or lock.
- Keep PR stacks at most 2 deep; merge `main` into the branch rather than stacking fixes.
- Sat 00:58 New user-facing strings need Spanish too: a test holds the English and Spanish tables to the same keys (#59, #87).
- Sat 01:00 `.github/` is owned by Vidyut and the XO; lane PRs must not touch `ci.yml` (pushing it needs the `workflow` token scope anyway).
- Per-bed rents (`per_bed`) are never compared with a whole-unit rent.
