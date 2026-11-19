---
name: writing-plans
description: Use in the full workflow once the spec is accepted (requirements, Security rules and any external contracts exist), before dispatching implementers, or when the user asks for an implementation plan — writes a dependency-ordered task graph beside the spec, planned for parallel work, and moves the spec to planned. Fast-path work does not need one.
---

# Implementation plans

Use the routing tier to decide whether a written plan is needed. Fast path uses an in-context checklist. The plan follows the accepted spec, its actual Security artifacts and contracts, and precedes implementers.

Save substantial plans per `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`: a feature plan goes to `docs/specs/<feature>/plan.md` beside its spec; a plan not tied to one feature goes to `docs/plans/YYYY-MM-DD-<topic>.md`; honor the user's chosen location. Include goal, accepted design, scope exclusions, canonical inputs and validation as prose around the tasks. In existing/non-Git workspaces, preserve the user's files and workflow; no automatic git initialization, worktree or commit is required just to persist a plan.

## Spec plans: a task graph

A `plan.md` beside a full-workflow spec is a task graph that the `aidlc` CLI parses and gates; its exact format is §2 `plan.md` in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. Each task is one checkbox line `- [ ] T<n>: <outcome>` with these indented fields:

- `covers`: the requirement IDs it implements (`RFD-1, RFD-2`), or `none — <reason>` for enabling work. Every requirement in `requirements.md` is covered by at least one task.
- `depends`: the tasks that must finish first, or `none`.
- `owner`: the agent from `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` that does it, or `main`.
- `files`: every path the task may change, `(new)` for new files; globs such as `src/refunds/**` are allowed.
- `exit`: the observable check that proves it done. It becomes the command the task is ticked with, so make it a runnable test or check.

Plan for parallel work. Tasks with no dependency path between them may run at the same time, so they must not share a file. When two tasks need the same file, either make one depend on the other or move the shared edit into its own task that both depend on. Keep the chain short: a task depends only on what it really needs, so `aidlc next` can hand out wide batches. Put contract application, schema migrations and shared wiring (routes, DI registration) early, since many tasks touch them.

Within a task's fields, cite real artifacts (contract paths, Security rule IDs), its failure and rollback behavior when it has one, and handoff evidence. Include code only when it pins a contract or a fragile operation. Let implementers choose local details inside the contract. State versions and APIs only when verified. Prefer cohesive, independently verifiable tasks over fixed file-count or minute limits.

Leave every box open: only `aidlc task-done` ticks a spec plan's task. Then run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <feature> planned`. If the gate lists findings (an uncovered requirement, a missing owner, a cycle, two parallel tasks sharing a file), fix the plan and run it again.

## Other plans

A plan in `docs/plans/` may keep the simple form: one checkbox line `- [ ] Task N: <outcome>` per task, details indented beneath (owner, owned files, dependencies, exit check), ticked `- [x]` by hand when its exit check passes. Use checkboxes only for tasks; the session-start snapshot counts them.

## Then

Review the plan for missing requirements, invented dependencies, conflicting ownership and vague exit checks. If implementation is already authorized, continue in this session with `tea-sdlc:subagent-driven-development`; do not ask the user to choose an internal execution mechanism. A resumed or separate-session plan uses `tea-sdlc:executing-plans`.
