# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Sat Nov 14 2026, 02:07. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

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
- Sat 01:08 Ruling: a poster phone that matches the leasing office on record is a supporting yes/no line only ("call that number yourself"); it never sets authority to MATCHES_RECORD on its own. A phone-only match never verifies. (conductor)
- Sat 01:20 **Realtor reframe (LOCKED):** (1) premise: scammers copy real listings, swap in their own contact, and ask for a deposit before you tour or sign; SNAPBACK checks the listing against the building's own records and tells you who to call (never "pay to view"); (2) PERSON: property manager, leasing office or listing agent/brokerage on record all count; a name mismatch alone is Not confirmed + "call the office on record yourself", never a red flag; (3) never claim lease status; "recently rented" is an informational prompt, no flag; (4) the pitch and demo lead with real sourced cases; (5) second realtor check Sat 10-11:00. (Vidyut, #41)
- Sat 01:28 Overnight: master-planner drafts 2-3 reframe directions, master-council judges (budget about $2.50), conductor decides; result for Vidyut at 07:30. (Vidyut)
- Sat 01:31 Ruling: A9 (#91) stays a staged poster on real records, labelled "Staged example" on screen and in the README; D8 replays land next to it as `fixtures/demo/replay-*`, never replacing it. (conductor, #73)
- Sat 01:31 Ruling: A14 approved, the poster's reply for real (#109): reply route + "waiting for a reply" state, joining D3 challenge and V5 photo memory. A right code that is not a copy stays Not confirmed until V2. Contract merged (#110). (conductor, #8)
- Sat 01:34 Ruling: V2 contract approved: optional `PhotoLocation.matched_model_id`, `matched_property_id`, `room_label`; set for located_in_claimed and located_elsewhere (elsewhere names the OTHER building). (conductor, #41)
- Sat 01:42 Ruling: D9 aerial route contract approved: `GET /cases/{id}/aerial` -> `AerialProofResponse` (claimed + matched side, tile, record, image_url on our route; Vexcel key server side), 20 s bound, 7-day cache covered by `make purge`; `record` trimmed to company names and building facts (no phone hash, no site host); read token on both routes. Rishit builds builder + routes in ONE PR, Dev reviews api/. (conductor, #41)
- Sat 02:00 Ruling: an ACTIVE for-sale match gives HOLD (for-sale reason first) even when no photo was placed; it outranks "Could not place". DON'T PAY still only on proof. When the record has model ids but no index, Real reads "Not checked (this building's scan is not indexed yet)"; "no 3D scan" only when there are no model ids. Lane A task #119, PR #120. (conductor, #101)
- No "SAFE", "VERIFIED" or "SCAM" state anywhere. Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

Lanes and paths: `.github/CODEOWNERS` and `docs/ROLES.md`. Each lane has an epic issue (label
`epic`: A #8, T #9, V #10, D #11) with ordered task issues; each person's agent starts from `docs/agents/kickoff-<name>.md`.

| Person  | GitHub      | Lane                                 | Now                                                                                                                                                                                                                                                                                                        |
| ------- | ----------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev     | DevSingh05  | A. agent and backend                 | A10 live join #101 merged 02:04 (ebe491f). #106 A12 PASS 02:04 (merge by conductor). #107 A11 ready (evicts deleted case). Then #120 A16 for-sale HOLD + 'not indexed' wording (issue #119, assigned). Queued: #117 A14 reply flow. #96 A8 waits on V2. Next: A15, A13 #104                                |
| Vidyut  | vs-githjk   | T. front end (with Claude)           | T7/T8/T9/T11 done on fixtures. Next: T7 live wiring on V2 names (#111): map "Taken here" by `matched_property_id == claimed`, not by the chosen model (`apps/web/src/twin/landing.ts:43`), and read `photo.room_label`; then T9 live on D9 (#113), T10 #79 locked design                                   |
| Jeffrey | jeffrey-g05 | V. vision and ML                     | #111 V2 FIX r1 (H: claimed twin loses an equal match elsewhere by index order, false DON'T PAY; 2 M, 1 L): do FIRST. Then #112 V4 FIX r1 (H: train/test leakage across the split; 3 M, 1 L). Queued: #114 V3 (stacked on #111), #118 secure_delete. #62 V6 FIX open. V9 house via Rishit's picker #116     |
| Rishit  | RishitRai   | D. data, iMessage, challenge, safety | Claude Pro. #95 D7 FIX r3 done at 11115a2, in re-review. #100 D2b in review. #113 D9 aerial: Dev reviewed api/ (2 H: fixture case 7Q2M always 401, whole kit parsed per request; 2 M, 1 L), rest for the conductor. #115 DATA_USE right after #107; #116 house picker stacked on #95. Next: D8 replays #71 |

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

- Sat 01:55 Human list for 07:30 (lane V): browser check of kit photo URLs (403 to scripts, #68); V4 team photos (#30, about 40 genuine / 15 screen / 10 print each); V3 60 s walkthrough video plus one photo of a room we can stand in (#29)
- Fri 21:15 CoStar q1: may kit data go to Claude? (CoStar, via Discord)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed yet (NOT re-checked at 02:07). main = ebe491f (Sat 02:04, #101 A10). 24 merges since midnight.
- Merged 01:04-01:45: #61 V5, #82 D3, #83 D4, #84 D5, #87 A7 rules, #90 T8, #91 A9, #94 T9, #98 A10 contract, #99 V1 follow-ups, #105 CODEOWNERS, #108 T housekeeping, #110 A14 contract.
- Open FIX heads at 02:07: #111@e339dc7 (V2, H), #112@890152d (V4, H), #62@8a653b7 (V6). In review: #95@11115a2, #100@0f6aa7b. #106@53c14fe PASS. Queued: #107, #115, #113, #114, #116, #117, #118, #120. Blocked: #96 on V2. Reviews and merges: conductor only.
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
- Sat 01:45 V2 gate numbers (#28) are on RENDERS of the scans at unseen viewpoints, not phone photos. Say "renders" in any claim until real photos are run (A8).
- Sat 01:31 #91 and #101 both touch `CaseStore.create`; A13 waits until both merge (both now merged).
- Sat 02:02 Twin matching: never let index order break a tie between the claimed building and another one; check the claimed twin first and hold "elsewhere" to a stricter bar (#111). A tie must never produce DON'T PAY.
- Sat 02:03 ML splits: split train and test by building (or capture session), never by photo, or the score leaks (#112).
- Sat 01:59 A recorded case with no secret (fixture `7Q2M`) must go straight to `check_read`; an early "no token -> 401" locks it out for good (#113).
