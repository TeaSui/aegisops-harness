---
name: plan
description: Stage 2 of the backend lifecycle (/aegisops-harness:plan, run by /aegisops-harness:aidlc) — slice an accepted spec's user stories into tracer-bullet vertical slices with Blocked-by edges in tickets.md beside the spec, then advance it to planned.
disable-model-invocation: true
---

# Tickets

`/aegisops-harness:fix` writes no plan. A spec: `docs/specs/<feature>/tickets.md` after it is accepted. A plan tied to no feature: `docs/plans/YYYY-MM-DD-<topic>.md`, or where the user says. No git init, worktree or commit just to save a plan.

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

Check for uncovered stories, invented blockers, horizontal slices and vague criteria. If implementation is authorized, continue with `/aegisops-harness:build` without asking (it also resumes a saved plan).
