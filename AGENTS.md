# Rules for coding agents in this repo

Four people are building this over one weekend, each with their own coding agent. The repo's
GitHub issues are the message board: scope, assignments, status and questions all live there.
This file holds the standing rules. The issues hold the plan.

## Start of every session

1. Read the pinned "Team inbox" issue labelled `start-here` (`gh issue list --label start-here`).
2. Read your lane epic (`gh issue list --label epic --label agent:<your-human>`; names: `dev`,
   `vidyut`, `jeffrey`, `rishit`), its newest comments, then your task issues in order.
3. Run `make setup && make check` before changing anything, so you know the baseline is green.
4. Read `docs/shared-memory.md` (decisions, data facts, gates, open questions) and your lane in
   `docs/ROLES.md`. Your paste-ready prompt: `docs/agents/kickoff-<name>.md`. Before you stop:
   `docs/agents/HANDOFF.md`.

## Commands

| Command        | What it does                                           |
| -------------- | ------------------------------------------------------ |
| `make setup`   | Install python (uv) and node (npm) dependencies        |
| `make check`   | Hygiene + lint + tests. Must pass before any PR merges |
| `make format`  | Fix formatting and lint in place                       |
| `make api`     | API on :8000                                           |
| `make web`     | Web app on :5173, proxies `/api` to :8000              |
| `make sidecar` | Intake sidecar stub                                    |

Python is managed with `uv` (`uv add <pkg>`, `uv run <cmd>`). Node uses npm workspaces
(`npm install -w apps/web <pkg>`). Do not introduce a second package manager.

## Hard rules

These exist for reasons that will not change this weekend. Do not work around them.

1. **Never commit sponsor data.** Anything read from the CoStar, Matterport or Vexcel
   hackathon services (scans, panoramas, records, CSVs, indexes, embeddings, caches, screenshots
   of them) stays under `data/`, which is git-ignored. The sponsor terms forbid exposing it and
   this repo goes public at submission. The same applies to issue and PR text: describe, do not
   paste.
2. **Never commit secrets.** Keys live in `.env`. Never print a key into a log, an issue or a PR.
3. **Code sets the verdict.** `snapback.verdict.decide` is the only place a verdict is chosen.
   A language model may write the explanation; it never picks the state.
4. **Sponsor data and outside models.** Until a human records the sponsor's answer in the
   `human-needed` issue, do not send sponsor images or records to any outside model API from
   product code. Send only text we derived ourselves (counts, statuses, reasons).
5. **LIVE or FIXTURE on everything.** Every screen, card and number shows which it is. Fixture
   data is synthetic and team-made (`fixtures/`), never a copy of sponsor data.
6. **No number before it is measured.** Every figure in the demo, README or Devpost comes from
   the eval harness, with n shown.
7. **Never call a named person a scammer.** The strongest verdict wording is
   "Don't pay · could not verify". No reply means HOLD, not failure.
8. **Humans do these, not agents:** accept terms, create accounts, generate sponsor keys, post in
   Discord, message anyone outside the team, spend money, change repo visibility, submit to
   Devpost. If your work needs one, label the issue `human-needed`, tag your human, and keep
   going on whatever is not blocked.
9. **Licences.** No copyleft (GPL/AGPL/LGPL) dependencies and no non-commercial-only model
   weights without a human's say-so; the sponsor terms restrict both. Check before you add.
   Exception decided by Vidyut (22:15): for the vision lane, SuperPoint vs ALIKED or DISK with
   LightGlue is **Jeffrey's call**. He picks whatever is best for the team and notes the choice
   and its licence in his PR.

## Working agreement

- **Branch and PR.** Never push to `main`. Branch as `<lane>/<issue#>-<slug>` (lane is `a`, `t`,
  `v` or `d`, e.g. `v/14-dinov2-index`), open a PR with `Closes #<task issue>`. Keep PRs small enough to review in five minutes.
- **One issue per PR.** `Closes #<n>` for a task issue, `Refs #<n>` for a lane or inbox issue
  (`Closes` would close it). Never force-push, never push to someone else's branch.
- **Plain commits.** No `Co-Authored-By` lines and no AI attribution in commits or PR text.
- **Stay in your lane's paths** (see the table in `README.md` and `.github/CODEOWNERS`). You may
  ask for a merge when `make check` is green and the PR touches only your lane's paths. Only the XO
  (on Vidyut's behalf) merges to `main`; agents never push or merge to `main`.
- **Shared contracts.** `src/snapback/contracts.py` and `fixtures/contracts/` are held by the XO,
  because every lane depends on them. Adding an optional field is fine in your PR; anything else
  (rename, remove, new required field) goes in an issue labelled `contracts` first.
- **Need something from another lane?** Open an issue with that lane's `agent:` label, say
  exactly what you need (interface, example payload, deadline) and what you will do meanwhile.
  Do not edit their files.
- **Report on the message board.** About every 30 minutes while working, comment on the task
  issue you are on (heartbeat): what is done, what is next, what is blocked, and any measured numbers with n.
  Say plainly when something does not work.
- **Blocked?** Say so within 15 minutes, not after two hours. Label `human-needed` if a human
  has to act.
- **Tests.** New behaviour in `src/` comes with a test. Do not weaken or delete a test to make
  a change pass; fix the change or raise it.
- **Fixtures first.** Build against the fixture backend so nobody waits on live data, then
  switch on live.

## Definition of done for any task

It runs from a clean checkout with `make setup`, `make check` passes, the PR says how you
verified it (commands and what you saw), and the lane issue has a comment recording the result.
