---
name: executing-plans
description: Use when resuming or continuing a saved implementation plan (docs/specs/<feature>/plan.md, docs/plans/*.md), especially after a new session, /clear or compaction — reads the spec's stage and ready tasks, then continues the build from there without restarting finished work.
---

# Execute a saved plan

Keep the original goal, constraints and decisions; never redo finished work. `aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run it yourself.

## Spec plans (`docs/specs/<feature>/plan.md`)

1. `aidlc status` (or the session-start snapshot): stage and next-gate blockers. Not yet `planned` → back to `tea-sdlc:brainstorming` or `tea-sdlc:writing-plans`.
2. `planned`: on a feature branch (never the default), `aidlc advance <feature> building`.
3. `aidlc next <feature>`: dispatch one batch at a time, its tasks in parallel, via `tea-sdlc:subagent-driven-development`.
4. After a task's review passes: `aidlc task-done <feature> T<n> --cmd "<exit check>"` (omit `--cmd` if the task has `test:`). Never tick by hand. On failure, fix from the evidence and rerun.
5. A choice the spec leaves open that is reversible and in scope: decide and record `aidlc ruling <feature> --decision "…" --why "…" --if-wrong "<cost, reversal>" --task T<n>`, continue, list rulings in the final reply. Stop only for the user's decisions (new scope, changed requirement, destructive or external action).
6. Repeat 3-5 until `next` is empty, then `verified` per `tea-sdlc:subagent-driven-development`, `tea-sdlc:requesting-code-review`, `tea-sdlc:shipping`.

## Other plans (`docs/plans/*.md`)

Continue from the first open `- [ ] Task N:` in dependency order; tick `- [x]` when its exit check passes. Full workflow dispatches via `tea-sdlc:subagent-driven-development`; fast path implements here.

## Always

Record a missing tool or service as a missing gate, never an invented result. No git init just to follow a plan; preserve others' changes. Bound fix and review attempts per `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`; stop dependent work when no safe path remains. Deliver as already authorized (`tea-sdlc:finishing-a-development-branch` for a non-spec branch).
