# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Sat Nov 14 2026, 09:14. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

## Product direction (Sat 09:14, Vidyut approved 09:07-09:12)

- **SNAPBACK is the renter's agent.** First screen: **"Paste the ad you found, get the real one, plus checked places that fit your budget."** The budget card comes as a second entry at the 16:00 checkpoint only if the gates are green.
- **Search:** CoStar's researched apartments by budget and must-haves, over about 980 Houston communities (#184, merged 9d556c7), always labelled "as of CoStar's last research"; budget vs asking price is computed in code; the tour request is a draft to the office on record, sent only through the approval gate. Never pays, never rates neighbourhoods (fair housing).
- **Demo opener = the Conroe pattern** (amends 03:32): a replay of a reported case (ABC13, Feb 15 2025; "A renter in Conroe, TX", no victim names): the poster claimed to be the landlord; the owner of record is a rental company whose published rule says it takes applications only on its own site. Rishit builds it as a D8 replay (#11). **Beat 2 = the for-sale house** (Scottsdale pattern).
- **Pitch hook (true facts only):** the SF realtor who gave round-1 feedback is Vidyut's uncle; Vidyut has been **misled** twice in San Francisco by places booked from photos that did not match. Say "misled", never "scammed" (he never was). Premise: everyone picks homes from photos; SNAPBACK checks what you see against the home itself (CoStar 3D scan, county owner of record, the real office). Conroe is the stakes example.
- **Trust rules (09:07):** the contact line softens (#182 rule) only when presence is also PROVEN (fresh in-home photo with the challenge code). The headline may read VERIFIED only for: active Texas licence checked by number + sponsor = brokerage on record + photos placed in the claimed home + presence PROVEN.
- Slogan: pending Vidyut (open questions).

## Decisions (locked)

- Fri 20:59-21:53 decisions (team, rentals first, who controls main, kit, CoStar Terms, scope, final lane split): `docs/shared-memory-archive.md`.
- Sat 00:35-01:08 decisions (plan v3.2, issues #66-#79, overnight mode, eval public, card words, schedule: features stop Sun 01:00 / deadline Sun 08:00, recapture not proof, A10 order, phone match supporting only): `docs/shared-memory-archive.md`.
- Sat 01:20 **Realtor reframe (LOCKED):** (1) premise: scammers copy real listings, swap in their own contact, and ask for a deposit before you tour or sign; SNAPBACK checks the listing against the building's own records and tells you who to call (never "pay to view"); (2) PERSON: property manager, leasing office or listing agent/brokerage on record all count; a name mismatch alone is Not confirmed + "call the office on record yourself", never a red flag; (3) never claim lease status; "recently rented" is an informational prompt, no flag; (4) the pitch and demo lead with real sourced cases; (5) second realtor check Sat 10-11:00. (Vidyut, #41)
- Sat 01:28 Overnight: master-planner drafts 2-3 reframe directions, master-council judges (budget about $2.50), conductor decides; result for Vidyut at 07:30. (Vidyut)
- Sat 01:31-02:29 rulings (A9 staged poster, A14 reply, V2 contract, D9 aerial route, ACTIVE for-sale = HOLD, phone mismatch = Not confirmed, Direction A, HCAD cleared, header-only read token, owner + licence claim): `docs/shared-memory-archive.md`.
- Sat 02:45-04:58 rulings (challenge code not proof, house picker trio, A14 no_retry_left, owner-of-record contract, A20 report, V2 thresholds, family trusts = PERSON, published_rule, locate semantics, VERIFIED needs phone match, for-sale wording, card renders API text, for sale + office on record, phone_confirmed, ambiguity 3.0, decoy subdivision, V2 recall, D10 licence by number only, licence statuses): `docs/shared-memory-archive.md`. The 03:32 demo-opener ruling is amended by Sat 09:11 below.
- Sat 05:05 **Council 2, agentic depth: A** (3 of 5 A, 2 of 5 D, chair concurs, $0.09; `plan/council/2026-11-14-0452-snapback-agentic`). An evidence-driven planner: the model picks the next check from code-written options (record, brokerage, TREC, HCAD owner, report pack) with a visible reason; deepagents with the policy fallback; **every trace step stamped model or policy (never cut)**; runs on apartment cases a and b and on houses; the model never sees or argues the verdict. Stretch: `ask_renter_for(license_number)` on the REPLY wait/resume, cut first if behind at 18:00. **A24 #163 in build since 05:2x: conductor builder on branch `a24-planner`** (no longer unassigned). Vidyut confirms at 07:30; the recorded model run needs a model key on the demo machine (his call on spend).
- Sat 05:08 **Ruling: no victim names anywhere in the public repo,** docs/research included: write "A renter in <city>, <state>" and keep every source URL, date and fact. Git history is not rewritten. Done in a4dd2ce (05:07, 4 research files); a guard regex that lists the names arrives with #162 in `tests/test_replays.py`. (conductor)
- Sat 05:45 **Ruling: A18 card, NOT_FOUND licence line** uses the red-flag tone ("Doesn't match" / ES equivalent) on the licence row; verdict stays HOLD, never DON'T PAY alone. A phone mismatch stays "Not confirmed" + a HOLD reason even when the licence is NOT_FOUND (supersedes the 02:10 clause); one red flag per fact. (conductor, #167 review)
- Sat 05:48 **Ruling: A24 honesty.** A planner menu with only one open option is never sent to the model and is stamped policy ("only option"); "picked by model" appears only where the model chose between 2 or more options (demo cases a and b gave the model a list of one). (conductor, #168 review)
- Sat 06:58 **Ruling: the trace stream reads with fetch plus the read token in a header** (applies 02:27; EventSource cannot send headers), no stream ticket. Done: #176 (web, 3b9d4bc) then #179 (no case route takes a token in the address, bb26c44). (conductor, #8)
- Sat 07:28 **Ruling: D12 owner kind is shape-based** (supersedes the 07:10 "single whole company entity" rule and the marker list). PERSON on any non-name character or any person token (AND, FBO, CUSTODIAN, ATTN, TTEE/TRSTE/TRST, ETAL/ET/EST/ESTATE, IRA, AS, AGENT, JR/SR/II-IV, UX, FAMILY, LIVING, trust words); COMPANY only when the last token is an entity suffix or company word with nothing after it (or CITY/STATE/COUNTY OF, ... CHURCH, CHURCH OF x, ... TRUST COMPANY). When unsure, PERSON ("a private owner"). (conductor, #160 round 3; Vidyut may reverse)
- Sat 07:14 **Ruling: A24 stretch, a licence number typed by the renter** with no active row reads "Not confirmed" tone + HOLD, never a red flag (typo risk; a second answer is refused), worded "The license number you gave..."; renter-sourced facts never enter the report pack. (conductor, #177 review)
- Sat 07:35 **Vidyut approved:** (1) merge A24 stretch #177; rules-only mode also asks the renter; the honest claim is "the model chooses when to ask"; one recorded deepagents run (model key and spend on the demo machine are his to provide); (2) an ACTIVE Texas licence checked by number whose sponsor is the brokerage on record turns the contact "Not confirmed" line into an info line: contact line only, never VERIFIED on a licence alone, owner line unchanged (amends 02:25); (3) push this file to main. (Vidyut)
- Sat 07:35 **Jeffrey is back online; lane V work goes to him for the 12:00 gate** (the 09:00 conductor fallback is not needed). (Vidyut)
- Sat 07:43 **Ruling: V2 `claimed_min_spread`** (a spread floor on the claimed bar), set from measured true-claimed spreads with n and the recall cost shown; a photo that fails it is `not_located`, never elsewhere or DON'T PAY; lives in `thresholds.toml` (version + cache key). Reason: seed-6 replay had 1 false claimed placement (70 inliers, spread 0.018) the ambiguity rule misses. (conductor, #28)
- Sat 07:43 **Council 3 (budget-agent reframe): C, the floor** (5 of 5, $0.06): a bounded "your rental agent": budget and must-haves, a budget vs CoStar rent-band check in code, a tour-request draft to the office on record through the approval gate; asks before anything is sent, never pays. Widened by council 4 below. `plan/council/2026-11-14-0737-snapback-budget-agent`. (council + conductor)
- Sat 07:46 **Ruling: D12 classify extension.** Person tokens also ETUX, ETVIR, AKA, FKA, NKA, OR, CARE, HEIRS, EXECUTOR, EXECUTRIX, ADMINISTRATOR, GUARDIAN, TENANT, MGR, and OF before an entity; dotted single-letter runs, lone `-`/`.` tokens and trailing hyphens are PERSON; the institution whole-name check runs after the person-token check. A few real institutions reading as PERSON is accepted (fails safe). (conductor, #160 round 4)
- Sat 07:52 **Ruling: Lab chips.** Calibration rows measured on renders carry their own chip "Measured on renders of our scans, n=<n>"; the panel FIXTURE chip covers only synthetic rows (AGENTS.md rule 5). Done in #183. (conductor)
- Sat 07:53 **Council 4 (3 D2 / 2 D1, chair, $0.08): build the shared core now:** CoStar apartment search by budget and must-haves, shown "as of CoStar's last research"; budget vs asking price computed in code; a checked-alternatives strip; model-chosen deep checks and trade-off questions; a tour-request draft to the office on record through the approval gate. No fee split. Twin label: "a 3D scan in this building". The first screen is still Vidyut's call (open questions). Transcript: `plan/council/2026-11-14-0749-snapback-holistic`. (council + conductor)
- Sat 08:04 **Ruling: owner display.** The card, API, trace and report print an owner's company name ONLY when it matches a known company (the A19 published-rule table or an office or brokerage on record in the kit, via `same_company`); any other company shows "a company owner"; a person stays "a private owner". Done in #160 (00381a6). (conductor, #160 r5)
- Sat 09:07 **Vidyut approved the three pending calls:** first screen = paste the ad; contact softening needs presence PROVEN; VERIFIED rule as in Product direction above. (Vidyut)
- Sat 09:11 **Demo opener = Conroe** (amends 03:32); for-sale house = beat 2. Sat 09:12 pitch hook locked (Product direction). (Vidyut)
- No "SAFE" or "SCAM" state anywhere, and VERIFIED only under the four conditions approved Sat 09:07. Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

Lanes and paths: `.github/CODEOWNERS` and `docs/ROLES.md`. Each lane has an epic issue (label
`epic`: A #8, T #9, V #10, D #11) with ordered task issues; each person's agent starts from `docs/agents/kickoff-<name>.md`.

| Person  | GitHub      | Lane                                 | Now                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------- | ----------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev     | DevSingh05  | A. agent and backend                 | **Handed off at 07:30** (HANDOFF on #8); no open PRs. Lane A work is now the conductor's builders. Still watching #8.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| Vidyut  | vs-githjk   | T. front end (with Claude)           | Conductor builders: **#187@e819dbb** first screen "paste the ad you found" (branch `t-paste-first`, opened 09:14) and the **presence / VERIFIED rule** (09:07; branch `a/licence-presence`, PR not open at 09:14). Conductor reviews #185 #186 and holds draft #122 (T10) for Vidyut. Merged 08:23-09:13: #182 (e3c7796), #160 (00381a6), #184 search core (9d556c7), #181 (06d67d2).                                                                                                                                                                                                                     |
| Jeffrey | jeffrey-g05 | V. vision and ML                     | **#74 three-house index** for the 12:00 gate: picker ran on the real kit (for_sale, recently_sold, decoy; 3 house models); scan downloads kept dropping, so **#185@b0e671e** (Matterport retry with backoff) and he is fetching with it; his ETA about 09:30, then the probe. **#186@b1dd371** `claimed_min_spread` 0.05 (07:43 ruling). **A8 BLOCKED** (#10, 09:09): the kit has no image files, and photo links return HTTP 403 to scripts; unblock steps posted on #10 09:11 (open one link in a normal browser; if it loads, ask CoStar on Discord; draft given). The gate runs on renders meanwhile. |
| Rishit  | RishitRai   | D. data, iMessage, challenge, safety | Claude Pro. #160 D12 merged 09:10 after seven rounds. **Now: the Conroe D8 replay** (demo opener, assigned on #11 09:11), built like #162 from a real card run. Later: #161 `_unit_on_record`, #100, #129 D11.                                                                                                                                                                                                                                                                                                                                                                                            |

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
- **Sat 12:00 hard gate** (#74): 3 kit-house photos located with pose, including the decoy landing as "different home". Pass: the house case opens the demo and the report pack ships. Fail: B's apartment opener stays, the house case is one beat; owner and license lines still ship.
- **Sun 01:00 new features stop** (replaces the old Sun 02:00 freeze); after that polish, bug fixes, demo prep only.
- **Sun 08:00 hard deadline.** Older interim gates (Sat 08:00 recapture v1, Sat 18:00 storyboard, Sat 20:00 recapture v2) still stand as targets.

## Open questions

- Sat 09:12 **Slogan:** "See the real place before you pay." (recommended) or keep "Check any rental before you pay". (Vidyut)
- Sat 09:09 **A8 kit photos:** the kit holds photo links only and they return 403 to scripts. Does a link open in a normal browser, and may we fetch them? (Jeffrey or Vidyut by hand, then CoStar on Discord; #10)
- Sat 07:33 Vidyut's quick looks still open: Invitation Homes fraud page (rule checked only via a summariser), T10 draft #122, footer two-rules wording (M3 below), Matterport moveTo sign / Y-up frame, `uv sync --locked --extra agent --extra intake` on the main checkout, realtor second-look page before 10:00; plus a look over the overnight rulings 01:49-07:28. (Vidyut; `plan/decisions.md` PENDING-VIDYUT)
- Sat 03:10 Red team M3: the footer's "two rules" would not have saved the NW Houston victim (lease plus door code). Footer words are locked, so a change is Vidyut's call. (Vidyut)
- Sat 01:55 Human list for 07:30 (lane V): browser check of kit photo URLs (403 to scripts, #68); V4 team photos (#30, about 40 genuine / 15 screen / 10 print each); V3 60 s walkthrough video plus one photo of a room we can stand in (#29)
- Fri 21:15 CoStar q1: may kit data go to Claude? (CoStar, via Discord)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed yet (NOT re-checked at 09:14). **main = 06d67d2** (#181, 09:13), CI in progress at 09:14; last green main run e3c7796 (#182; 00381a6 and 9d556c7 cancelled by the next merge). Earlier merges: see git log.
- Published (private, Vidyut's account): realtor second-look page https://claude.ai/code/artifact/753dbcf2-8571-4a45-9915-bfce03ecaada (new; Vidyut decides whether to send; the first realtor page is unchanged); team page https://claude.ai/code/artifact/02692146-1751-437c-a78e-276c9f94c586; landing (worlds) https://claude.ai/code/artifact/a96c4cf3-27b3-4c6d-a2fc-b4f0ea616aee. All three republished about 03:35 with the red-team text fixes (landing r10b).
- TREC licensee data (Socrata `data.texas.gov/resource/s7ft-44qi.json`) is live with no key: 327,540 rows (conductor, 02:18). Use lightly and cache demo answers locally.
- Open at 09:14: #185@b0e671e (Jeffrey, Matterport retry), #186@b1dd371 (Jeffrey, claimed_min_spread), #187@e819dbb (conductor, paste-the-ad screen), draft #122 (held for Vidyut); `a/licence-presence` PR not open yet. Reviews and merges: conductor only.
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
- Sat 01:31 #91 and #101 both touch `CaseStore.create`; A13 waits until both merge (both now merged).
- Sat 02:02 Twin matching: never let index order break a tie between the claimed building and another one; check the claimed twin first and hold "elsewhere" to a stricter bar (#111). A tie must never produce DON'T PAY.
- Sat 02:03 ML splits: split train and test by building (or capture session), never by photo, or the score leaks (#112).
- Sat 01:59 A recorded case with no secret (fixture `7Q2M`) must go straight to `check_read`; an early "no token -> 401" locks it out for good (#113).
- Sat 02:55 A lane D adapter is only done when it has run once on the real kit (counts only). A fixture that invents the record shape passes its tests and finds nothing on the real kit (#116: `homeListingId`, `attachments[].videoExternalReferenceType` don't exist there; again in D13 #152: beds, floors, year_built). Copy the real key paths into fixtures.
- Sat 03:05 When a PR is superseded, retarget any PR stacked on its branch at once (#114 sat on `v/28-verify-pose` after #139 replaced #111); base stacks on `main` or the live branch only.
- Sat 03:25 `models_of(None)` is empty: with no claimed home, every true photo went to "elsewhere" (red team H2 repro on f42cb92). "No claimed home" is never "claimed home not matched".
- Sat 03:40 CI runs the eval gate (`python -m snapback.eval --baseline eval/baseline.csv`) once #150 merges: a PR that changes the verdict rules or the case bank can fail it. Rebaseline only on purpose (`make eval-baseline`) and say so in the PR.
- Sat 03:40 Squash merges must pass `--body ""`: the #62 squash (8691062) kept a human `Co-authored-by:` trailer and main's hygiene job failed. The hygiene loop only ever reports the HEAD commit (the `cut` gives an empty sha for every later record), so a trailer deeper in history is never caught. #142 (767dbdd, 03:4x) was squashed without it and failed hygiene the same way (human trailers); #150 used `--body ""` and passed. Hygiene is green again once a clean commit lands on top. The check also matches the trailer phrase anywhere in the HEAD commit message, subject included: never write it in a commit message, even to describe the bug (da50c7b failed that way).
- Sat 03:46 A teammate agent can run out of usage mid-lane with no warning (Dev 03:46, back 03:53). Heartbeats on the epic name what is ready, unanswered and not started; a takeover builds on the author's head in a NEW PR (never pushes to their branch), and the author is told which branches not to touch.
- Sat 04:25 A PR that conflicts with main gets no CI at all (0 checks, mergeable CONFLICTING), so "no checks yet" can mean a conflict, not a slow runner. Check `git merge-tree --write-tree --name-only origin/main <ref>` (#158 and #160 at 04:25).
- Sat 03:22 `plan/` is not in the repo. When a teammate's agent needs test text from a plan file (red-team sentences), paste it on their issue (#144).
- Sat 04:42 A replay (D8) may only show checks SNAPBACK actually runs: build the findings from a real card run of today's code (never typed by hand), add a "what this can't catch" line, and take every date and gap from the source (the Conroe story was written as "four days"; ABC13 says move-in Sat Feb 8, call "the following Monday": 2 days; fixed in `docs/research/need-evidence.md` 04:47). (#162)
- Sat 05:08 The repo is public: no victim names, even in docs/research. A test that guards against names stores SHA-256 digests of them, never the names (#166, e3792b8).
- Sat 05:44 Run `node_modules/.bin/prettier --check docs/shared-memory.md` (then `--write`) before every push of this file: CI `format:check` covers docs, and XO commit 78ef7b9 turned main red (fixed at 8906874).
- Sat 06:45 A main run shows `cancelled` when the next merge lands within minutes (concurrency group). Check the last SHA's run is green and history is linear, not each cancelled one.
