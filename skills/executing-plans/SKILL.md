---
name: executing-plans
description: Use when resuming or continuing a saved implementation plan (docs/specs/<feature>/plan.md, docs/plans/*.md), especially after a new session, /clear or compaction — reads the spec's stage and ready tasks, then continues the build from there without restarting finished work.
---

# Execute a saved plan

Retain the original goal, constraints and accepted decisions; do not restart completed work after compaction. Follow the routing tier, Security rules and contracts.

## Spec plans (`docs/specs/<feature>/plan.md`)

The stages, gates and CLI are in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. Below, `aidlc` stands for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run it yourself.

1. **Where am I.** Run `aidlc status` (the session-start snapshot already shows it when it ran this session). It gives each spec's stage and the blockers of its next gate. A spec that is not yet `planned` goes back to the step that owns its gate (`tea-sdlc:brainstorming`, `tea-sdlc:writing-plans`).
2. **Start the build.** When the spec is `planned`, work on a feature branch (not the default branch) and run `aidlc advance <feature> building`.
3. **Take the frontier.** `aidlc next <feature>` returns the ready tasks in batches whose tasks share no file. Dispatch one batch at a time, its tasks in parallel, through `tea-sdlc:subagent-driven-development`.
4. **Tick through the CLI.** When a task's review passes, run `aidlc task-done <feature> T<n> --cmd "<the task's exit check>"`. It runs the check and ticks the task only on exit 0. Never tick a spec plan's box by hand. On a failure, fix from the reproduced evidence and run it again.
5. **Rule instead of stopping.** When a choice comes up that the spec does not settle and that is not the user's to make (it is reversible and inside the authorized scope), make the most reasonable choice and record it: `aidlc ruling <feature> --decision "<what>" --why "<why>" --if-wrong "<cost and how to reverse it>" --task T<n>`. Then continue. List the rulings in the final reply. Stop only for a decision that is the user's (new scope, a changed requirement, destructive or external actions).
6. Repeat 3-5 until `aidlc next` returns no ready task. Then record the full test run and advance to `verified` as `tea-sdlc:subagent-driven-development` describes, and continue with `tea-sdlc:requesting-code-review` (`reviewed`) and `tea-sdlc:shipping` (`shipped`).

## Other plans (`docs/plans/*.md`)

Read the plan and existing evidence, continue from the first open `- [ ] Task N:` line in dependency order, and tick it `- [x]` when its exit check passes. In the full workflow, dispatch owned tasks through `tea-sdlc:subagent-driven-development`; on the fast path, implement in this session.

## Always

If tools or services are unavailable, record the missing gate instead of inventing a result. Use project isolation when concurrent changes or risk require it and the runtime supports it; do not initialize a Git repository merely to follow the plan. Preserve other changes. Reuse existing scope authorization and honor explicit human checkpoints; do not add confirmation loops for internal execution choices.

Bound fix and review attempts per `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`; stop dependent work and explain the blocker when no safe authorized path remains. Finish with actual verification and the already-authorized delivery action (`tea-sdlc:finishing-a-development-branch` for a Git branch).
