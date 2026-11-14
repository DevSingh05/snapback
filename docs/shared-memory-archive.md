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
- Sat (superseded by 04:24) 02:25 Ruling: D10 license (#128) contract approved with 3 amendments. NOT_FOUND only when no active licensee shares the last name with a compatible first name (nicknames, initials); ambiguous or more than 25 rows = NOT_CHECKED; companies checked as Broker Company; NOT_FOUND = Doesn't match + a HOLD reason, never DON'T PAY alone; LICENSED is supporting only. Flagging a real agent is the worst realtor failure. (conductor, #41)
- Sat (superseded by 04:24) 02:50 **Ruling (tightens 02:25, D10 #134):** NOT_FOUND only when the poster makes an explicit, well-formed self-claim ("I'm/My name is First Last, a licensed agent/realtor/broker/locator" or a "First Last, Realtor" signature), the name is exactly two tokens with no company word or particle, and there are zero ACTIVE rows for that last name AND zero for `like '% LAST'`. Anything else is NOT_CHECKED (an ambiguous person = LICENSED with sponsor None). A company is NOT_FOUND only on zero Broker Company prefix rows. Reason: 8 of 10 realistic sentences gave a false NOT_FOUND in round 2; a real agent must never be wrongly flagged. (conductor, #134)
- Sat (superseded by 04:24) 03:05 **Ruling (amends 02:50 rule (c), D10 #134):** strip suffixes (JR, SR, II, III); split the surname on space, hyphen and apostrophe; any ACTIVE row with `last_name like %PART%` for any part (or more than 25 rows) = NOT_CHECKED; hyphenated and apostrophe surnames are never strict. **Companies are NEVER NOT_FOUND** (LICENSED or NOT_CHECKED only). Reason: round 3 still gave 5 of 8 false NOT_FOUND (compound, hyphen, JR, DBA). (conductor, #134)

- (moved 07:36) Sat 04:35 Where the licence wording lives now: the **rule** is on #157 (head d26e53e, commit 0d8e166, `adapters/trec.py`: a name gives LICENSED or NOT_CHECKED, NOT_FOUND only from the ad's licence number), CI green, in review. The **card text** belongs to A18 #137, which at d4ee744 still says "We found no active Texas license under that name" (`apps/web/src/cardStrings.ts:118`); that line goes when #137 follows the 04:24 rule. (XO, checked on both branches)
- (moved 07:36) **Order: A23 #144 before A22 #141** (the H1 rule lands before the locator is wired). (conductor, #141)
- (moved 07:36) **A22 houses (Sat 04:45): houses are now in the live catalog on #155 (1,401 records, 1,460 models), round 2 review** (was 0 of 1,253 houses at 04:35). The house opener still needs #155 merged and V9 houses indexed under the same model ids (Jeffrey, #74). (REPORTED by the conductor; XO did not re-count)
- (moved 07:36) **Sat 07:30 V9 probe** (Jeffrey, #74): can one kit-house image or a render from a house scan go through V2? Yes or no on #74. Vidyut confirms direction A at 07:30.
