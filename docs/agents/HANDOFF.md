# Handoff prompt

Paste the box below into your agent before you stop, sleep or hand the task to someone else.
Replace `<ISSUE#>` and `<NEXT OWNER>` (a name, or "next session"). The rules in
[AGENTS.md](../../AGENTS.md) still apply.

```text
We are stopping work on issue #<ISSUE#>. Write a handoff and post it as ONE comment on that issue
(`gh issue comment <ISSUE#> --body-file <file>`). Do not post anywhere else.

First:
1. Commit finished work on the current branch with a plain message (no co-author or AI lines).
   Do not commit half-broken code to a branch with an open PR; leave it uncommitted and say so.
2. Push the branch (never main): `git push -u origin HEAD`
3. Run `make check` and capture the exact result lines.
4. Get the state: `git rev-parse --short HEAD`, `git status --porcelain`, the PR number if any.

Then post this, filled in, short and factual:

HANDOFF for #<ISSUE#> to <NEXT OWNER>
- Branch / SHA: <branch> @ <sha> (dirty: yes/no, what is uncommitted)
- PR: #<n> or none
- Done: <what works now, each with how it was checked>
- make check: <result lines>
- Not done: <what is left from the issue's done criteria>
- Open risks: <what might be wrong, what you guessed, anything flaky>
- Blocked on: <person or answer, or "nothing">
- Next step: <the ONE next action, specific enough to start without asking>
- Files touched: <list>

No keys, sponsor data, real addresses or record values in the comment. Say NOT CHECKED for
anything you did not run.
```
