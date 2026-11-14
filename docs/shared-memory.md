# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Sat Nov 14 2026, 11:12. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

## Product direction (Sat 09:46, Vidyut approved 09:07-09:38)

- **SNAPBACK is the renter's agent.** Tagline: **"Trust the home, not the ad."** (backup "Don't trust the ad. Check the home."; in the README since #193, 823fd8a). First screen: paste the ad you found, get the real one, plus **researched places that fit your budget (as of CoStar's last research)**; "checked" only for what the card actually checked (09:25). A small "Just show places that fit my budget" entry is allowed (09:21); the full budget card waits for 16:00 if gates are green.
- **Search:** CoStar's researched apartments by budget and must-haves, over about 980 Houston communities (#184, merged 9d556c7), always labelled "as of CoStar's last research"; budget vs asking price is computed in code; the tour request is a draft to the office on record, sent only through the approval gate. Never pays, never rates neighbourhoods (fair housing).
- **Demo opener = the Conroe pattern** (amends 03:32): a replay of a reported case (ABC13, Feb 15 2025; inside demo and replays "a renter in the Houston area"; pitch and README may say "Conroe, near Houston"; no victim names, 09:32): the poster claimed to be the landlord; the owner of record is a rental company whose published rule says it takes applications only on its own site. Rishit's D8 replay is #189; the web gets a "Real case: Conroe" tab (what happened / with SNAPBACK, plus a button that runs the staged case's real card, 09:35). **Beat 2 = the for-sale house** (Scottsdale pattern).
- **Pitch hook (true facts only):** the SF realtor who gave round-1 feedback is Vidyut's uncle; Vidyut has been **misled** twice in San Francisco by places booked from photos that did not match. Say "misled", never "scammed" (he never was). Premise: everyone picks homes from photos; SNAPBACK checks what you see against the home itself (CoStar 3D scan, county owner of record, the real office). Conroe is the stakes example.
- **Trust rules (09:07):** the contact line softens (#182 rule) only when presence is also PROVEN (fresh in-home photo with the challenge code). **Call 3 REVOKED (09:3x):** licence + sponsor + photos placed + presence never makes VERIFIED (a self-tour scammer with a door code passes all four). VERIFIED needs `phone_confirmed`, **or** (09:38) office confirmation through the brokerage's own website domain from CoStar's record (one-time link, exact domain match) together with photos placed in the claimed home (or record facts matching) and no other HOLD or red-flag reason.
- **Spanish (09:38):** nobody on the team reads it, so no Spanish in the demo, pitch, README or Devpost; ES strings and parity tests stay in code, EN only on stage.
- **Rights (09:51):** no LICENSE file and no open licence; the README carries the rights notice (rights assigned to CoStar under the HackPrinceton Fall 2026 hackathon agreement, no licence granted, third-party libraries under their own licences). MIT or Apache only if CoStar says yes in writing.
- **Event data use ends Sun Nov 15 16:00** (terms 2.2, 2.3): no sharing outside the registered team; after judging, delete every copy, cache and derivative, and be ready to certify it in writing.
- **Sponsor asks at the 11:00 fair, by person (10:33):** Vidyut asks CoStar, Jeffrey asks LangChain, Rishit asks Photon, Dev asks Amazon. Questions page v10 (conductor).
- **Use all three CoStar layers** (records, Matterport, Vexcel) with real use cases; make the photo-to-scan match visibly stronger (Vidyut 09:30, preference). Plan: `plan/layers-plan.md`.

- **Walk the Ad is GO (10:48).** The renter walks the ad they were sent through the home that is really there (Matterport scan, Vexcel aerials, CoStar record), room by room, in their own world ("they come in and see everything"). Pitch it as the renter-side check CoStar's own Homes AI (AI-guided Matterport tours, Feb 2026) lacks. Design page a612f628; plans `plan/walk-plan.md` and `plan/ml-agent-plan.md` (conductor's plan dir, not in the repo).
- **Intelligence layer in plain sight (10:48, joined plan 10:58):** deepagents place and walk sub-agents run DINOv2/LightGlue as tools under a fixed budget; a case-notes file system; an agent rail of real trace events only; a "How we know" drawer with matched points and bar gauges; every step stamped model or policy. Code still sets every placement and verdict; the model sees counts and bars, never photos.
- **Wow beat X1 (approved 10:57):** "the photos lead to the real home": in case b the walk opens in the building where the photos were really taken (two aerials) and the card names that home's office on CoStar's record. Must look phenomenal; every tool allowed (Fable for design). R-E1 (a retry may find "taken in a different building" on the strict bar) also taken. 14:00 checkpoint: if E2a is not merged or E1 is not green on stubs, X1 moves after 18:00.
- **Video:** 90-120 s, 22 shots about 1:52 (ml-agent-plan section 6), after 18:00, storyboard gate first. Two recorded deepagents runs (cases a and b) approved 10:57.
- **Look (zing feedback 10:59):** no red verdict band, no orange or amber accent, redraw the house glyph; the first screen (sky block + house) is liked more than the card. Applies to the walk and wow-beat design too.
- **Priority order (10:57):** (1) realtor second round (second-look page with new ideas, how the app works, consent asks); (2) other sponsors: Arlequin T1 from about 14:00 if ahead (Vidyut + Claude); (3) everything else. The real website starts about 16:00 on the worlds artifact.

## Decisions (locked)

- Fri 20:59-21:53 decisions (team, rentals first, who controls main, kit, CoStar Terms, scope, final lane split): `docs/shared-memory-archive.md`.
- Sat 00:35-01:08 decisions (plan v3.2, issues #66-#79, overnight mode, eval public, card words, schedule: features stop Sun 01:00 / deadline Sun 08:00, recapture not proof, A10 order, phone match supporting only): `docs/shared-memory-archive.md`.
- Sat 01:20 **Realtor reframe (LOCKED):** (1) premise: scammers copy real listings, swap in their own contact, and ask for a deposit before you tour or sign; SNAPBACK checks the listing against the building's own records and tells you who to call (never "pay to view"); (2) PERSON: property manager, leasing office or listing agent/brokerage on record all count; a name mismatch alone is Not confirmed + "call the office on record yourself", never a red flag; (3) never claim lease status; "recently rented" is an informational prompt, no flag; (4) the pitch and demo lead with real sourced cases; (5) second realtor check Sat 10-11:00. (Vidyut, #41)
- Sat 01:28 Overnight: master-planner drafts 2-3 reframe directions, master-council judges (budget about $2.50), conductor decides; result for Vidyut at 07:30. (Vidyut)
- Sat 01:31-02:29 rulings (A9 staged poster, A14 reply, V2 contract, D9 aerial route, ACTIVE for-sale = HOLD, phone mismatch = Not confirmed, Direction A, HCAD cleared, header-only read token, owner + licence claim): `docs/shared-memory-archive.md`.
- Sat 02:45-04:58 rulings (challenge code not proof, house picker trio, A14 no_retry_left, owner-of-record contract, A20 report, V2 thresholds, family trusts = PERSON, published_rule, locate semantics, VERIFIED needs phone match, for-sale wording, card renders API text, for sale + office on record, phone_confirmed, ambiguity 3.0, decoy subdivision, V2 recall, D10 licence by number only, licence statuses): `docs/shared-memory-archive.md`. The 03:32 demo-opener ruling is amended by Sat 09:11 below.
- Sat 05:05-08:04 rulings (council 2 agentic depth A with model/policy stamps never cut, no victim names, A18 NOT_FOUND licence line, A24 honesty, trace stream via fetch + header token, D12 owner kind by shape, A24 renter licence number, 07:35 Vidyut approvals incl. TX licence info line, Jeffrey back for lane V, V2 claimed_min_spread, councils 3 and 4 budget agent and shared core, Lab chips, owner display only for known companies): `docs/shared-memory-archive.md`.
- Sat 09:07 **Vidyut approved the three pending calls:** first screen = paste the ad; contact softening needs presence PROVEN; VERIFIED rule as in Product direction above. (Vidyut)
- Sat 09:11 **Demo opener = Conroe** (amends 03:32); for-sale house = beat 2. Sat 09:12 pitch hook locked (Product direction). (Vidyut)
- Sat 09:1x **Ad vs record lines:** "the ad says X, the record shows Y" (room labels, listing features, must-haves) and pretext checks ("new management", "just sold", "owner away" vs CoStar contacts and sale comps) are INFO lines "as of CoStar's last research"; they never change the verdict by themselves. (Vidyut)
- Sat 09:2x **Ambiguity rule amended:** for the ambiguity comparison only, a rival blocks a claimed pass with >= `elsewhere_min_inliers` and >= 3x the claimed inliers, no spread needed; result `not_located`; a rival still never places a photo elsewhere unless it passes the strict bar. (conductor, #74)
- Sat 09:35 **Rishit takes Photon (#38) right after #189 merges.** (Vidyut)
- Sat 09:43 Packet: deadline Sun 08:00 hard (our cutoff 07:30), 2-minute pitch, judging 09:30-14:30, CoStar + Best Overall qualify (`plan/submission.md`). (finder)
- Sat 09:51 **Rights notice, not a licence** (Product direction); CoStar terms: data use ends Sun 16:00, delete and certify afterwards. (Vidyut)
- Sat 10:03 **"Run this case" always runs as a FIXTURE case** (F- id, `demo_modules`, FIXTURE chip) on any server, never LIVE; a `demo_case` sent with text, link, photos or property_id gets 422. (conductor, #198)
- Sat 10:03 **Conroe replay hold step** ("asked to pay to move in") shows the owner's own payment rule (`owner.rule_beside_payment`) in Warning tone. (conductor, #198)
- Sat 10:03 **Card gap, queued for a lane A builder:** an ad that asks for money before move-in (rent and/or deposit) must not read "Payment ask: Matches"; when the owner of record has a stated payment channel or is not the poster, the price row shows Warning with the owner's rule beside it (tone only, verdict unchanged). Plus a house wording of `place.located`: "Taken in this home". **10:32 Dev took it (#8)**, sequenced after #199 and #201 (both edit verdict.py, strings.py, contracts.py). (conductor)
- Sat 10:24 **"Checked" only when a lookup ran;** otherwise the line reads "On record:". Done in #195 (602dd7f, 10:26, merged with Vidyut's OK): the model picks the deep checks, plus preference memory. (conductor, #195 review)
- Sat 10:33 **q1 LOCKED (human-confirmed by Vidyut from Dev's screenshots):** CoStar staff said in #costar-group (Fri 22:48 and 23:52) the data may go to third-party models for the duration of the hackathon. Effect: CoStar **records and text** may go to outside model APIs until the event ends (Sun 16:00). **Listing photos and scan images are not covered and stay held** until CoStar answers c1 at the fair. Keep sends minimal (terms 3.2 still read otherwise). Exact wording: `plan/decisions.md`. (Vidyut + Dev, #72)
- Sat 10:48 **GO WALK** plus the visible intelligence layer and a 90-120 s video; anything stronger found is pre-approved for the storyboard and build (Product direction). (Vidyut)
- Sat 10:57 **Second recorded deepagents run approved** (cases a and b); **wow beat X1 approved** (must look phenomenal); **priority order** realtor round, then sponsors, then the rest. (Vidyut)
- Sat 10:59 **Zing #212 preference:** no red, no amber, redraw the house, improve card colouring. (Vidyut)
- Sat 11:04 **#201 ruling:** office confirmation through the brokerage's own domain does NOT lift a phone mismatch; the result stays HOLD, but the card says clearly that the office confirmed the ad and why it still holds. (Vidyut)
- Sat 11:04 **ChatOverflow is Rishit's** (#11): no CoStar data and nothing about sponsor data in anything he shares; outward posts are his. (Vidyut)
- Sat 11:04 **Real website starts about 16:00** on the worlds artifact; A-lane PRs (#216 E0, #217 deepagents) opened on Vidyut's OK; realtor page: strong hero images, the realtor pitch/storyboard, the Peri proof (feedback changed the product) visible. Vidyut travelling about 20 min: take the recommended option on open decisions. (Vidyut)
- No "SAFE" or "SCAM" state anywhere, and VERIFIED only as in Product direction (phone confirmed, or brokerage domain confirmed plus photos placed). Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

Lanes and paths: `.github/CODEOWNERS` and `docs/ROLES.md`. Each lane has an epic issue (label
`epic`: A #8, T #9, V #10, D #11) with ordered task issues; each person's agent starts from `docs/agents/kickoff-<name>.md`.

| Person  | GitHub      | Lane                                 | Now                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------- | ----------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev     | DevSingh05  | A. agent and backend                 | Active 11:05. **#218@37a3f47** card gap (money before move-in never reads "Matches"; "Taken in this home"; additive `ModuleEvidence.property_type`), in conductor review. **A8 PENDING** CoStar c4 (n=78 totals held on his laptop). Asks Amazon at the fair.                                                                                                                                                                    |
| Vidyut  | vs-githjk   | T. front end (with Claude)           | Conductor reviews and merges. Merged 10:55-11:10: #198 (a1cf009), #199 (0261fac), #215 (41392df). Builders: A builder on E0 #216 then deepagents #217, E1, E5, E6, X1 card; walk builder on #213 (W1-W3, W6, W7, X1 walk); T2 builder #214 (W4, W5, E3); designer on zing redo #212 then E4 drawer + AgentRail (t/walk-look). Realtor page v7 for his uncle (Vidyut shares). Arlequin about 14:00 if ahead; website about 16:00. |
| Jeffrey | jeffrey-g05 | V. vision and ML                     | Heartbeat 11:04. **#207@bdbb8b6** top 12 candidates (in review), **#211@9246ae5** index warm command (conflicts with main: merge main), **#194@a0cdb52** gate twins by property. Next: E2a retry primitive (by 12:30) and E2b match points (#10). Warm on his machine: houses 1,698 faces in 1,254 s; demo index warming.                                                                                                        |
| Rishit  | RishitRai   | D. data, iMessage, challenge, safety | Claude Pro. #204 merged 10:34. Next: live Photon round trip (#38), then **ChatOverflow** leaderboard (asked on #11 at 11:05). Last activity 10:23 (#204).                                                                                                                                                                                                                                                                        |

## Data facts (REPORTED until our probe confirms)

- CoStar data is a JSONL file in the kit (`commercial-property.jsonl`, about 3,339 records), not an API.
- Houston research market id 14: about 1,758 records, about 1,314 multifamily, about 1,732 with a Matterport model id.
- Matterport model ids: `attachments[]` entries with `videoExternalReferenceType` 36 or 234; `videoKey` is the model id.
- Apartment scans are model units per floor plan ("2BR, 2BA ..."), not the exact unit. A match claims "this building, this floor plan", never a unit number.
- Matterport Model API: `POST https://api.matterport.com/api/models/graph`, HTTP Basic (token id : secret); six 1024 px skybox faces per sweep.
- Vexcel REST: `https://api.vexcelgroup.com/v2`, header `X-API-KEY`, rate limited (back off on 429).
- No rent, owner or leasing contact field is known yet. Plan for NO until the probe shows one.

## Terms rules

- Sponsor imagery and records never go into git. Since 10:33 (q1) CoStar records and text may go to outside models until Sun 16:00, kept minimal; sponsor **images** (listing photos, scans) never go to an outside AI until CoStar answers c1. Matching runs on our machines.
- Matterport's agreement bans caching API content; we asked CoStar for a weekend exception. Until answered, keep any cache local and purge after judging.
- Owner names: companies only; for a person, show only "matches owner of record: yes / no".
- No real addresses in code, fixtures, tests or docs.

## Gates

- **Fri 22:15 data gate** (issue #5): GO if at least 3 Houston (or LA) multifamily buildings load a Matterport model on our keys (`scripts/probe_kit.py` prints `DATA GATE`).
- **Fri 22:45**: if the data gate failed, switch to PRETEXT+.
- **Sat 02:00 locate and learn gate**: 15 of 20 held-out real photos located; recapture v0 trained (150 genuine, 150 attacks); Photon round trip with a photo; card from a live record.
- **Sat about 10:00 feedback round 1**; evening feedback round 2.
- **Sat 12:00 hard gate** (#74): 3 kit-house photos located with pose, including the decoy landing as "different home". Pass: the house case opens the demo and the report pack ships. Fail: B's apartment opener stays, the house case is one beat; owner and license lines still ship.
- **Sun 01:00 new features stop** (replaces the old Sun 02:00 freeze); after that polish, bug fixes, demo prep only.
- **Sun 08:00 hard deadline.** Older interim gates (Sat 08:00 recapture v1, Sat 18:00 storyboard, Sat 20:00 recapture v2) still stand as targets.

## Open questions

- Sat 10:58 Vidyut may still veto X1 or R-E1 (both taken under the 10:48 pre-approval). (Vidyut)
- Sat 11:00 Realtor second-look page v7 is PRIVATE on Vidyut's account: he decides whether to share it with his uncle, and asks the consent questions (name, business, quotes, face) for Peri credit. (Vidyut)
- Sat 09:51 **Ask CoStar in person (Vidyut):** (1) may the repo stay public with kit field names in our code; (2) MIT or Apache, or keep the CoStar rights notice; (3) q1 answered in chat (Decisions 10:33); still ask c1: may listing photos and scan images go to outside models too. Licence itself is settled (rights notice, Decisions 09:51).
- Sat 09:43 **Agreement 3.2** lists "schemas" as confidential and bars them from public repos; our adapters name kit field names (no rows). Recommend asking CoStar in #costar-group with q1; the repo stays as is until answered (private is his call). (Vidyut)
- Sat 10:12 **A8 real photos PENDING (CoStar c4):** Dev's agent saved 66 kit photos by driving his own Chrome (browser extension, about 3 s apart; disclosed, not by hand); eval on n=78 finished, totals held on Dev's laptop. Vidyut asks CoStar c4 at 11:00 with this disclosed: yes, post totals labelled "real listing photos, n=78"; no, Dev deletes photos and results. Photos never committed. (Vidyut, #72)
- Sat 07:33 Vidyut's quick looks still open: Invitation Homes fraud page (rule checked only via a summariser), T10 draft #122, footer two-rules wording (M3 below), Matterport moveTo sign / Y-up frame, `uv sync --locked --extra agent --extra intake` on the main checkout, realtor second-look page before 10:00; plus a look over the overnight rulings 01:49-07:28. (Vidyut; `plan/decisions.md` PENDING-VIDYUT)
- Sat 03:10 Red team M3: the footer's "two rules" would not have saved the NW Houston victim (lease plus door code). Footer words are locked, so a change is Vidyut's call. (Vidyut)
- Sat 01:55 Human list for 07:30 (lane V): browser check of kit photo URLs (403 to scripts, #68); V4 team photos (#30, about 40 genuine / 15 screen / 10 print each); V3 60 s walkthrough video plus one photo of a room we can stand in (#29)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed (NOT re-checked at 11:12). **main = 41392df** (#215, 11:1x): CI success (VERIFIED `gh run list` 16:11Z). **Main was red 10:54-11:11** after #198 (a1cf009) and #199 (0261fac) failed: `styles.test` found `#fff` hex in `replay.css` against the #122 token rule; #215 moved it to the `--on-act` token (also fixed unreadable dark-mode text).
- Published (private, Vidyut's account): realtor second-look page https://claude.ai/code/artifact/753dbcf2-8571-4a45-9915-bfce03ecaada (new; Vidyut decides whether to send; the first realtor page is unchanged); team page https://claude.ai/code/artifact/02692146-1751-437c-a78e-276c9f94c586; landing (worlds) https://claude.ai/code/artifact/a96c4cf3-27b3-4c6d-a2fc-b4f0ea616aee. All three republished about 03:35 with the red-team text fixes (landing r10b).
- TREC licensee data (Socrata `data.texas.gov/resource/s7ft-44qi.json`) is live with no key: 327,540 rows (conductor, 02:18). Use lightly and cache demo answers locally.
- Open at 11:12 (reviews and merges: conductor only): **#200**@ebe7507 tour-prep pack (FIX, builder); **#201**@ed460e6 office domain confirmation (FIX: sticky decline, L1 naming, plus the 11:04 HOLD ruling; builder); **#207**@bdbb8b6 (Jeffrey, in review); **#210**@e978665 record-leak tests (FIX M1 drop `_TOKEN` mask, builder); **#211**@9246ae5 (Jeffrey, conflicts with main); **#212**@07b4d4a zing (redo pushed: one ink band, aqua accent, new house; conflicts with main); **#213** draft walk base (walk builder); **#214** draft T2 walk W4/W5/E3; **#216**@e7debfb E0 contract (merge after #215); **#217**@3834205 deepagents sub-agents (in review); **#218**@37a3f47 Dev card gap (in review); #194@a0cdb52 (Jeffrey). Merged today since 10:38: #198, #199, #209, #122, #205, #215.
- Contract fields on main (#88, #92), additive and optional: `PropertyRecord.site_phone_hash` (keyed hash, never digits; both lanes use the same phone hash helper), `website_host` (host only), `floor_plan_rents[]` (name, beds 0=studio, rent_min, rent_max, per_bed), `units[]` (unit, beds, floor_plan); `AuthorityResult.office_phone_match`, `link_domain` (yes/no only); `ForSaleMatch` (status active / recently_rented / none, site, listed_on, changed_on) on `ModuleEvidence.for_sale` and `Card.for_sale`. Pending in #87: `PriceResult.compared_beds`.
- Fri 22:10 data gate GO: 3/3 Houston multifamily Matterport models load on Vidyut's key (issue #5); apartment-listing has min/max rent per floor plan and the management company.
- API: `POST /cases` returns `token` (write; Bearer header only) and `read_token` (trace, status, aerial, images; header only since the 02:27 ruling, no `?token=`). `/c/:id` card stays public.

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
- Sat 02:02 Twin matching: never let index order break a tie between the claimed building and another one; check the claimed twin first and hold "elsewhere" to a stricter bar (#111). A tie must never produce DON'T PAY.
- Sat 02:03 ML splits: split train and test by building (or capture session), never by photo, or the score leaks (#112).
- Sat 02:55 A lane D adapter is only done when it has run once on the real kit (counts only). A fixture that invents the record shape passes its tests and finds nothing on the real kit (#116: `homeListingId`, `attachments[].videoExternalReferenceType` don't exist there; again in D13 #152: beds, floors, year_built). Copy the real key paths into fixtures.
- Sat 03:25 `models_of(None)` is empty: with no claimed home, every true photo went to "elsewhere" (red team H2 repro on f42cb92). "No claimed home" is never "claimed home not matched".
- Sat 03:40 CI runs the eval gate (`python -m snapback.eval --baseline eval/baseline.csv`) once #150 merges: a PR that changes the verdict rules or the case bank can fail it. Rebaseline only on purpose (`make eval-baseline`) and say so in the PR.
- Sat 03:40 Squash merges must pass `--body ""`: the #62 squash (8691062) kept a human `Co-authored-by:` trailer and main's hygiene job failed. The hygiene loop only ever reports the HEAD commit (the `cut` gives an empty sha for every later record), so a trailer deeper in history is never caught. #142 (767dbdd, 03:4x) was squashed without it and failed hygiene the same way (human trailers); #150 used `--body ""` and passed. Hygiene is green again once a clean commit lands on top. The check also matches the trailer phrase anywhere in the HEAD commit message, subject included: never write it in a commit message, even to describe the bug (da50c7b failed that way).
- Sat 03:46 A teammate agent can run out of usage mid-lane with no warning (Dev 03:46, back 03:53). Heartbeats on the epic name what is ready, unanswered and not started; a takeover builds on the author's head in a NEW PR (never pushes to their branch), and the author is told which branches not to touch.
- Sat 04:25 A PR that conflicts with main gets no CI at all (0 checks, mergeable CONFLICTING), so "no checks yet" can mean a conflict, not a slow runner. Check `git merge-tree --write-tree --name-only origin/main <ref>` (#158 and #160 at 04:25).
- Sat 03:22 `plan/` is not in the repo. When a teammate's agent needs test text from a plan file (red-team sentences), paste it on their issue (#144).
- Sat 04:42 A replay (D8) may only show checks SNAPBACK actually runs: build the findings from a real card run of today's code (never typed by hand), add a "what this can't catch" line, and take every date and gap from the source (the Conroe story was written as "four days"; ABC13 says move-in Sat Feb 8, call "the following Monday": 2 days; fixed in `docs/research/need-evidence.md` 04:47). (#162)
- Sat 05:08 The repo is public: no victim names, even in docs/research. A test that guards against names stores SHA-256 digests of them, never the names (#166, e3792b8).
- Sat 05:44 Run `node_modules/.bin/prettier --check docs/shared-memory.md` (then `--write`) before every push of this file: CI `format:check` covers docs, and XO commit 78ef7b9 turned main red (fixed at 8906874).
- Sat 06:45 A main run showed `cancelled` when the next merge landed within minutes (concurrency group). Fixed 10:16 by #203 (main runs never cancelled); check each merge SHA's own run from 0c4da65 on.
- Sat 11:03 `styles.test` bans raw hex colours in app CSS (#122 token rule): a CSS file written before #122 (replay.css in #198) passed its own PR CI and still turned main red on merge. Use tokens (`--on-act`, etc.) and merge main into old CSS branches before review.
- Sat 11:04 The auto-mode classifier denies some builder actions (`gh pr create`, unattended merge loops, branch deletes): never retry a denied action; ask Vidyut, then the conductor does it.
- Sat 10:31 Record-leak tests that grep logs for record numbers can match timestamps or tokens ('1600' in .160025Z); #210 tightens them.
