# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Fri Nov 13 2026, 23:48. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

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
- No "SAFE", "VERIFIED" or "SCAM" state anywhere. Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

Lanes and paths: `.github/CODEOWNERS` and `docs/ROLES.md`. Each lane has an epic issue (label
`epic`: A #8, T #9, V #10, D #11) with ordered task issues; each person's agent starts from `docs/agents/kickoff-<name>.md`.

| Person  | GitHub      | Lane                                 | Now                                                                                                                                                                  |
| ------- | ----------- | ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev     | DevSingh05  | A. agent and backend                 | A1-A4 merged (#49 #54 #56 #60). #58 A5 FIX open (regex DoS, more slow patterns found); agent hit usage limit 23:32, waits for Dev to restart it. #59 A6 waits on #58 |
| Vidyut  | vs-githjk   | T. front end (with Claude)           | #53 #55 #64 #65 merged (web wired to real API, read token); design direction A+C being built                                                                         |
| Jeffrey | jeffrey-g05 | V. vision and ML                     | V1 #63 merged; #61 V5 photo memory FIX (SQLite threads, screenshot crops); #62 V6 eval FIX (phantom bars, gate dodge, make eval)                                     |
| Rishit  | RishitRai   | D. data, iMessage, challenge, safety | D1-D6 pushed on 6 branches 23:07-23:26, no PRs yet; asked on #11 to open them (d/40 conflicts with main)                                                             |

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
- **Sun 02:00 feature freeze**: the 12 modules merged; stretch only after.
- Later: Sat 08:00 recapture v1 + challenge loop end to end; Sat 18:00 storyboard; Sat 20:00 recapture v2 frozen; Sun 02:00 feature freeze; Sun 04:00 code freeze; Sun 05:00 Devpost submitted.

## Open questions

- Fri 21:15 CoStar q1: may kit data go to Claude? (CoStar, via Discord)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed yet. main = e635d3c (Fri 23:33).
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
