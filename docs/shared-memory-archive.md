# SNAPBACK shared memory archive

Old items moved out of docs/shared-memory.md. Newest at the bottom.

## Decisions (Fri)

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

## Live facts (old)

- Merged 01:04-01:45: #61 V5, #82 D3, #83 D4, #84 D5, #87 A7 rules, #90 T8, #91 A9, #94 T9, #98 A10 contract, #99 V1 follow-ups, #105 CODEOWNERS, #108 T housekeeping, #110 A14 contract.

## Decisions archived Sat 03:55 (from shared-memory.md)

- Sat 00:35 Plan v3.2 (plan/snapback-v3.2.md, planner summary): one product, three proofs (PLACE, PERSON, PRICE), plus replays of real reported scams (#71, LOCKED 00:35). (Vidyut)
- Sat 00:35 New issues #66-#79: D7 #66, A7 #67, V8 #68, eval route #69, D8 #71, A8 #72, A9 #73, V9 #74, T7-T11 #75-#79. #18, #19, #34 closed as design-only.
- Sat 00:35 Overnight mode 01:30-07:30: humans sleep, agents work their v3.2 queue on their epic issue (#8 #10 #11, plan on #41). (Vidyut)
- Sat 00:35 Token ruling: `GET /eval/results.csv` is public (aggregate only, no case data). (conductor, #69/#70)
- Sat 00:35 Card words are locked; use the locked wording everywhere (CardPage.tsx included, #76). (conductor)
- Sat 00:50 Schedule LOCKED: sleep 01:30-07:30 (agents keep working their queues); feedback round about 10:00 (we go and talk to people), build all day, second feedback round in the evening; demo video made in parallel during the day. **New features stop Sun 01:00**; after that only rest, polish, bug fixes, demo prep. Hard deadline Sun 08:00. (Vidyut, #41)
- Sat 00:38 Ruling: a recapture flag is a model score, not proof: it stays WAITING and asks for a new photo, never FORGED. FORGED only for a wrong or missing code, or a confirmed copy of a listing photo. (conductor, #37) **The code part is revised by the 02:45 ruling below.**
- Sat 00:40 Ruling (wording revised 03:25 below): home actively listed for sale = HOLD, never DON'T PAY. DON'T PAY only on proof (presence FORGED or a photo taken elsewhere). (conductor, #67)
- Sat 00:44 Ruling: eval results are public and read-only (`GET /eval/results.csv`, no token, aggregate only). (conductor, #70)
- Sat 01:03 Ruling: the `unverified` headline is the locked "Could not place these photos" (strings.py), in every surface incl. iMessage (#83). (conductor)
- Sat 01:03 Ruling: Dev does A10 live modules join (CoStar record #80 + D7 lookup #95 into the price, unit and contact rules) BEFORE the A8 harness; then A11 register_case, A12 card.png cache + zone label, A13 end-to-end API test of DEMO_CASE a/b/c. (conductor, #8)
- Sat 01:08 Ruling: a poster phone that matches the leasing office on record is a supporting yes/no line only ("call that number yourself"); it never sets authority to MATCHES_RECORD on its own. A phone-only match never verifies. (conductor)
