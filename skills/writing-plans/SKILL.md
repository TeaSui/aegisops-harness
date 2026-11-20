---
name: writing-plans
description: Use in the full workflow once the spec is accepted (requirements, Security rules and any external contracts exist), before dispatching implementers, or when the user asks for an implementation plan — writes a dependency-ordered task graph beside the spec, planned for parallel work, and moves the spec to planned. Fast-path work does not need one.
---

# Implementation plans

Fast path: an in-context checklist, no file. Full workflow: `docs/specs/<feature>/plan.md` after the spec is accepted. A plan tied to no feature: `docs/plans/YYYY-MM-DD-<topic>.md`, or where the user says. No git init, worktree or commit just to save a plan.

## Spec plans: task graph

Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `plan.md`. One line `- [ ] T<n>: <outcome>` per task, with indented fields:
- `covers`: requirement IDs, or `none — <reason>`. Every requirement covered by ≥1 task.
- `depends`: task IDs or `none`.
- `owner`: an agent from `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` (`tea-sdlc:<agent>`) or `main`.
- `files`: every path the task may change, `(new)` for new files; globs allowed.
- `exit`: the observable check that proves it done.
- `test` (optional): the runnable exit command; `aidlc task-done` runs it when no `--cmd` is given.

Parallel work: tasks with no dependency path between them must share no file; otherwise add a dependency or split the shared edit into a task both depend on. Depend only on what is really needed so `aidlc next` returns wide batches. Put contract application, migrations and shared wiring (routes, DI) first. Cite real artifacts (contract paths, Security rule IDs) and rollback behaviour where relevant; include code only to pin a contract or fragile operation.

Leave every box open (only `aidlc task-done` ticks). Then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <feature> planned`; fix the findings it lists (uncovered requirement, missing owner, cycle, parallel tasks sharing a file) and rerun.

## Other plans

`- [ ] Task N: <outcome>` with owner, files, dependencies and exit check indented; tick `- [x]` by hand when the exit check passes. Checkboxes only for tasks (the session-start snapshot counts them).

## Then

Check for missing requirements, invented dependencies, ownership conflicts and vague exits. If implementation is authorized, continue with `tea-sdlc:subagent-driven-development` without asking; a resumed plan uses `tea-sdlc:executing-plans`.
