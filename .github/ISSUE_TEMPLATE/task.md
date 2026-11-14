---
name: Task
about: One unit of work for one person (or their agent). One task, one branch, one PR.
title: "[<lane>] <short task>"
labels: task
assignees: ""
---

## Goal

<!-- One sentence: what is true when this is done. -->

## Lane

<!-- integrator (A) | web (T) | vision (V) | data (D). See docs/ROLES.md. -->

## Files

<!-- Folders and files this task may touch. Anything else: ask on this issue first. -->

-

## Failing test first

<!-- The test to write before any code, and the command that runs it. -->

- Test:
- Command:

## Done when

<!-- Checkable items. Each one is something a reviewer can run or see. -->

- [ ]
- [ ] Tests pass: `<command>`
- [ ] PR opened with the template, `Closes #<this issue>`

## Due

<!-- Clock time, EST. -->

## Notes and limits

<!-- Data rules that apply, fixtures to use, what NOT to do. -->

- No sponsor data, real addresses or keys in git.
- Branch: `<lane>/<short-topic>` (AGENTS.md)
