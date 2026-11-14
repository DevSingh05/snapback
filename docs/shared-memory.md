# SNAPBACK shared memory

Every person and agent reads this first. Owner: the XO agent (on Vidyut's behalf). Newest at the bottom of each list. Times are EST. Last updated Fri Nov 13 2026, 21:50. Standing rules for agents are in AGENTS.md; this file holds the changing facts.

## Decisions (locked)

- Fri 20:59 Team is Vidyut, Jeffrey, Rishit, Dev. Product: SNAPBACK. (Vidyut)
- Fri 21:10 Real addresses are OK in the demo video, but stay out of this repo. (Vidyut, from CoStar staff)
- Fri 21:15 Judges watch the presence challenge on team phones; they do not use their own. (Vidyut)
- Fri 21:22 Rentals for the build. Buying (seller impersonation) is the named next market. (Vidyut)
- Fri 21:22 Data gate moved to 22:15; switch to the fallback idea (PRETEXT+) by 22:45 if the data gate fails. (Vidyut)
- Fri 21:22 `main` is controlled by Vidyut + the conductor + the XO. Everyone else works on branches from issues. (Vidyut)
- Fri 21:22 All four download the CoStar kit now; this repo's README has the steps. (Vidyut)
- Fri 21:39 Dev's skeleton (1406815) is the base: layout, tooling, AGENTS.md, CI, hygiene guard. Only the XO merges to main; agents never push to main. (Vidyut + Dev)
- Fri 21:40 Nobody clicks "I Agree" on the sponsor Terms until Vidyut confirms the team decision (the Terms include an IP assignment to CoStar). (Vidyut)
- No "SAFE", "VERIFIED" or "SCAM" state anywhere. Card words come from code, never from a model. Say "could not verify", never "scam", about a person. (spec v3)

## Who is doing what

- Lanes per `.github/CODEOWNERS` (see docs/ROLES.md); Vidyut confirms.
- Everyone, now: get the kit (README), run `python3 scripts/probe_kit.py`, paste output on the kit issue.

| Person  | GitHub      | Lane                   | Status                  |
| ------- | ----------- | ---------------------- | ----------------------- |
| Vidyut  | vs-githjk   | A. integrator          | kit download            |
| Dev     | DevSingh05  | V. vision (repo owner) | skeleton pushed 1406815 |
| Jeffrey | jeffrey-g05 | T. web                 | kit download            |
| Rishit  | RishitRai   | D. data                | kit download            |

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

- **Fri 22:15 data gate**: GO if at least 3 Houston (or LA) multifamily buildings load a Matterport model on our keys (`scripts/probe_kit.py` prints `DATA GATE`).
- **Fri 22:45**: if the data gate failed, switch to PRETEXT+.
- **Sat 02:00 locate and learn gate**: 15 of 20 held-out real photos located; recapture v0 trained (150 genuine, 150 attacks); Photon round trip with a photo; card from a live record.
- Later: Sat 08:00 recapture v1 + challenge loop end to end; Sat 18:00 storyboard; Sat 20:00 recapture v2 frozen; Sun 02:00 feature freeze; Sun 04:00 code freeze; Sun 05:00 Devpost submitted.

## Open questions

- Fri 21:15 CoStar q1: may kit data go to Claude? (CoStar, via Discord)
- Fri 21:15 CoStar: may we cache Matterport faces and embeddings locally for the weekend? (CoStar)
- Fri 21:15 Does the kit have listing photos, owner of record, rent or leasing contact? (our probe first)
- Fri 21:15 Vexcel key rate limit, oblique views by lat/lon? (CoStar)

## Live facts

- Nothing deployed yet.

## Gotchas

- Env names are Dev's: `MATTERPORT_API_KEY`, `MATTERPORT_API_TOKEN`, `VEXCEL_API_KEY`, `COSTAR_ZIP_PASSWORD` (`.env.example`). Kit goes in `data/` (git-ignored).
- Null fields are omitted from CoStar records: always use `.get`.
- Enum 0 and missing keys mean unknown, not "no".
