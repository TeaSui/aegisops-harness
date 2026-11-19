---
name: writing-plans
description: Use in the full workflow once requirements, Security rules and any external contracts exist, before dispatching implementers, or when the user asks for an implementation plan — writes an actionable, dependency-ordered plan beside the spec. Fast-path work does not need one.
---

# Implementation plans

Use the routing tier to decide whether a written plan is needed. Fast path uses an in-context checklist. Before dispatching Security or UI/UX, note their dependencies in `design.md` or the reply. The implementation plan follows the actual Security artifacts and contracts and precedes implementers.

Save substantial plans per `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`: a feature plan goes to `docs/specs/<feature>/plan.md` beside its spec; a plan not tied to one feature goes to `docs/plans/YYYY-MM-DD-<topic>.md`; honor the user's chosen location. Include goal, accepted design, scope exclusions, canonical inputs and validation. In existing/non-Git workspaces, preserve the user's files and workflow; no automatic git initialization, worktree or commit is required just to persist a plan. Use isolation when concurrent work or risky changes warrant it and the runtime supports it.

Write each task as one checkbox line, `- [ ] Task N: <outcome>`, with its details indented beneath it, and tick it `- [x]` when its exit criteria are met. The session-start snapshot counts these lines and `tea-sdlc:executing-plans` resumes from the first open one, so use checkboxes in the plan only for tasks.

For each task record:
- The owning agent from `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` (for example `backend-engineer-subagent`).
- Outcome and exact owned files/modules, marking new paths as new.
- Dependencies and strategic/security constraints; cite real artifacts.
- Observable exit criteria and exact verification appropriate to the change.
- Integration owner, relevant failure/rollback behavior and handoff evidence.

Include code when it pins a contract or a fragile operation, not a duplicate completed implementation for every step. Let implementers choose local details inside the contract. State versions and APIs only when verified. Prefer cohesive independently verifiable tasks over fixed file-count or minute limits.

Review for missing requirements, invented dependencies, conflicting ownership and vague acceptance criteria. If implementation is already authorized, proceed in the current session with `tea-sdlc:subagent-driven-development`; do not ask the user to choose an internal execution mechanism again. Use `tea-sdlc:executing-plans` for a resumed/separate-session plan. Track progress with the plan's task checkboxes (task tools may mirror them).
