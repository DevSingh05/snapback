# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Sat Nov 14 2026, 14:50. Standing rules for agents are in AGENTS.md; this file holds the changing facts. Morning direction and decisions (before 11:12): `docs/shared-memory-archive.md`.

## Product direction (Sat afternoon, Vidyut)

- **North star (14:19):** the renter's own world: looks cool, works cool, feels cool. Tagline stays "Trust the home, not the ad." Copy rules hold: "as of CoStar's last research", never "available now"; "for rent" is banned in card and walk copy; X1 line: "We can't tell you if it is offered, or at this price."
- **App shell (14:13-14:15):** the landing (home) is the main place; the map is a tab inside an app shell, not the front door. Tabs the renter picks and orders (remembered): Home (your checks), Listings, Map, Finder, Replays; Walk and Tour prep open from a case. Every page has one purpose (14:28).
- **Finder tab = the deep agent (14:28):** it learns from your choices and helps you find (M9 finder crew).
- **Theme (14:13, 14:23):** a visible Light/Dark switch, remembered; the map defaults dark, every other page light. The website (SNAPBACK Worlds, outside) and the app (inside) share one look, and the theme carries both ways.
- **Map (12:22-13:31):** OpenStreetMap / MapLibre map of every kit listing; Glass city is the default look, Dusk its dark mode; every building and place drawn in detail.
- **Walk the Ad / Walk it first (12:26-14:17):** shows the REAL thing first (ad photo, live Matterport view, kit listing photos); the 3D drawing sits in a FaceTime-style corner window and swaps on tap; drawings only as a labelled fallback. Walk it first plays like a video (autoplay, pause, scrub, chapters per room) plus a free explore mode. Every drawn 3D view must be super detailed.
- **Match view (14:15):** the ad photo vs scan lines and "8 of 30 needed" must read clearly, dynamically and beautifully (t/match-viz).
- **Event-driven (12:22, CoStar asked):** M3 event bus on main (#226).
- **iMessage (12:35):** the Photon sidecar may text first ONLY in a thread that sent "watch"; "stop" ends it; cap 3 a day.
- **Arlequin Track 1 (14:04):** AI forensics investigator view over SYNTHETIC rental-scam ads only (linked reused photos, phones, payment asks; every finding cites its evidence). Branch a/forensics.
- **CoStar value case (14:31, `plan/costar-deep-dive.md`):** Homes AI and Apartments.com Ai already guide Matterport tours, so never pitch "AI tour guide" as new; no CoStar tool checks an ad posted off their sites. That is our gap.

## Decisions (locked, Sat 12:00 onward)

- 12:35 R-M2 real CoStar kit pins may appear in the public video; R-M3 maplibre-gl install approved (a 6.x release at least 14 days old). (Vidyut)
- 13:06 **Dev owns deploy** (Vercel, his account). The conductor merges in order and pings Dev on #38 to redeploy after each batch. (Vidyut)
- 13:53 Vidyut approved the map, landing and walk screens ("phenomenal"). 14:28 #220 merged on his go. (Vidyut)
- 14:10 / 14:28 **UI hold:** UI branches merge to main only after Vidyut signs off on his own screen (main auto-deploys). Held now: t/shell, t/consistency, t/match-viz, t/preview. Backend-only PRs (no `apps/web`) merge on PASS + green CI. (Vidyut)
- 14:04 **ChatOverflow moves to Dev** (was Rishit's): general coding lessons only; never CoStar data, sponsor data, paths, keys or anything project-specific. Notes go to Dev on #41 as one JSON object per line; Dev screens and posts. (Vidyut)
- 14:45 **M10 iMessage watch (#232)** wires to M4 (`POST /finder/{sid}/watch`) and merges after M4. (conductor)
- 14:46 **Lane V (Jeffrey) owns the live evidence-file writer:** `LiveOutcome.points` into `EvidencePhoto.points`; the cache body keeps the pairs, never the cache key. (conductor, #231)
- Standing: no "SAFE" or "SCAM" state; VERIFIED only with phone confirmed, or the brokerage domain confirmed plus photos placed. Card words come from code, never a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what (14:50)

Lanes and paths: `.github/CODEOWNERS`, `docs/ROLES.md`. Epics: A #8, T #9, V #10, D #11; team inbox #41.

| Person  | GitHub      | Lane                            | Now                                                                                                                                                                                                                                                |
| ------- | ----------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev     | DevSingh05  | A backend, deploy, ChatOverflow | Deploys main to Vercel on the conductor's ping (#38). Runs ChatOverflow: 14:47 on #41, 47 of 57 teammate notes posted, 10 held back by his screen.                                                                                                 |
| Vidyut  | vs-githjk   | T front end (with Claude)       | Conductor reviews and merges. Open T PRs #214 #219 #221 (in review). Held for his preview sign-off: t/shell, t/consistency, t/match-viz, t/preview. a/forensics and a/todo-plan pushed, PRs wait on him. Builders running: walk player, M9 finder. |
| Jeffrey | jeffrey-g05 | V vision and ML                 | #231 merged 14:46 (9f28843). Next: live evidence-file writer (about 20 min, ruling 14:46). Last heartbeat #10 14:31.                                                                                                                               |
| Rishit  | RishitRai   | D data and iMessage             | #232 M10 watch at 4eab785: FIX list posted 14:43, merges after M4. Last push 14:26, last comment #41 14:41.                                                                                                                                        |

## Open questions

- 14:47 Dev asks every agent to run an upvote loop over all his ChatOverflow notes about once an hour (#41). Whether Vidyut's agent does so is Vidyut's call; the contest's voting rules are NOT CHECKED. (Vidyut)
- 14:04 Peri: Vidyut gets his uncle's consent plus one evidence item; Second Look page was being sent at 14:37. (Vidyut)
- 09:51 Ask CoStar: may the public repo keep kit field names in code; Matterport cache exception for the weekend. (Images to outside models settled 12:26: allowed, c1.) (Vidyut)
- 10:12 A8 real-photo totals PENDING CoStar c4 (totals on Dev's laptop, photos never committed). (Vidyut)

## Live facts

- **main = 9f28843** (#231, 14:46): node and hygiene success, python in progress at 14:48 (`gh api .../check-runs`). Previous main 1e51388 (#222): node, python, hygiene success.
- Merged since 11:12 (selection): #220 walk look + kit + landing (bc23728), #222 deepagents place agent (1e51388), #226 M3 event bus, #230 sibling-scan fix (ff29b3d), #231 live points (9f28843).
- Open PRs at 14:48: #214@24e70a3, #219@a919049, #221@50b6896 (T, in review), #232@4eab785 (D, FIX).
- **Which build is live on Vercel: NOT CHECKED** (no `plan/live.json`); master-guardian owns that answer.
- Published (private, Vidyut's account): team page v14, Second Look v8, SNAPBACK Worlds v16 (original 3D house hero plus a 6-frame storyboard).
- API: `POST /cases` returns `token` (write; Bearer header only) and `read_token` (header only, no `?token=`). `/c/:id` card stays public.

## Gates

- **Sun 01:00 new features stop**; after that polish, bug fixes and demo prep only. **Sun 08:00 hard deadline** (our cutoff 07:30). Event data use ends Sun 16:00: delete every copy and be ready to certify.

## Terms rules

- Sponsor imagery and records never go into git. Since 10:33 (q1) CoStar records and text may go to outside models until Sun 16:00, kept minimal; since 12:26 sponsor **images** (listing photos, scans) may go to outside models too (c1, Vidyut). Keep every send minimal; nothing sponsor-owned goes into git.
- Matterport's agreement bans caching API content; we asked CoStar for a weekend exception. Until answered, keep any cache local and purge after judging.
- Owner names: companies only; for a person, show only "matches owner of record: yes / no".
- No real addresses in code, fixtures, tests or docs.

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
