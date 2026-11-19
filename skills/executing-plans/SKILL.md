---
name: executing-plans
description: Use when resuming or continuing a saved implementation plan (docs/specs/<feature>/plan.md, docs/plans/*.md), especially after a new session, /clear or compaction — rereads progress and continues from the first open task with the plan's review checkpoints.
---

# Execute a saved plan

Read the plan and existing progress/evidence first; continue from the first open `- [ ] Task N:` line and tick it `- [x]` when its exit criteria are met. Retain the original goal, constraints and accepted decisions; do not restart completed work after compaction. Resolve material gaps before dependent work, using available sources and safe assumptions for routine details.

Follow the routing tier, Security rules and contracts. Execute tasks in dependency order, mark progress, run relevant checks and read their results. In the full workflow, use `tea-sdlc:subagent-driven-development` for owned tasks; on the fast path, implement in this session. If tools or services are unavailable, record the missing gate instead of inventing a result.

Use project isolation when concurrent changes/risk require it and the runtime supports it; do not require a missing worktree skill or initialize a Git repository merely to follow the plan. Preserve other changes. Reuse existing scope authorization and honor explicit human checkpoints; do not add new confirmation loops for internal execution choices.

Debug failures from reproduced evidence. Bound fix/review attempts per `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`; stop dependent work and explain the blocker when no safe authorized path remains. Finish with actual verification and the already-authorized delivery action. Use `tea-sdlc:finishing-a-development-branch` for a Git branch when applicable.
