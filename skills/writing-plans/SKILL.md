---
name: writing-plans
description: Use after spec acceptance, or when the user asks for an implementation plan, a breakdown or tickets — slices the user stories into tracer-bullet vertical slices with Blocked-by edges, written beside the spec, and advances it to planned. Fast-path work does not need one.
---

# Tickets

Fast path: an in-context checklist, no file. Full workflow: `docs/specs/<feature>/tickets.md` after the spec is accepted. A plan tied to no feature: `docs/plans/YYYY-MM-DD-<topic>.md`, or where the user says. No git init, worktree or commit just to save a plan.

## Spec tickets

Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `tickets.md`.
- **Vertical slices:** each ticket a narrow but complete path through every layer at the spec's seams, demoable alone, sized for one fresh context. Prefactor first ("make the change easy, then make the easy change"). Wide mechanical refactor → expand, migrate in batches, contract.
- `Blocked by:` only what really gates it, so `aidlc next` returns wide batches. `Covers:` every story except `Verify: none`, ranges allowed.
- `What to build:` the end-to-end behaviour from the user's side; acceptance checkboxes = observable outcomes; glossary terms; no file paths or code in prose.
- `Test:` the runnable exit command when there is one. `Files:` only when the ticket should run in parallel with another (subagent dispatch); parallel tickets share no file.

Leave every `Status: ready-for-agent`; only `aidlc task-done` sets `done`. Then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <feature> planned`; fix what it lists and rerun.

## Other plans

`- [ ] Task N: <outcome>` with dependencies and exit check indented; tick `- [x]` by hand when the exit check passes.

## Then

Check for uncovered stories, invented blockers, horizontal slices and vague criteria. If implementation is authorized, continue with `tea-sdlc:subagent-driven-development` without asking; a resumed plan uses `tea-sdlc:executing-plans`.
