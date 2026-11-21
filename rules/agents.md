# Agent delegation

Only the main session dispatches, and only inside the lifecycle commands; `/tea-sdlc:fix` dispatches only the fallback reviewer of `skills/review/SKILL.md` §3. Four agents, all backend:

## Registry
- **No spec-authoring agent:** the main session writes `spec.md`, `tickets.md`, `contracts/`, ADRs, `GLOSSARY.md`; `scripts/check-contract.py` checks contracts.
- **tea-sdlc:security-engineer-subagent:** reviews the draft `spec.md`, returns its `### Security` subsection (the main session pastes it under Implementation Decisions). Only for a spec that crosses a trust boundary.
- **tea-sdlc:backend-engineer-subagent:** implements a ticket of a parallel batch (tickets declaring disjoint `Files:`): APIs, business logic, databases, messaging, IaC the service owns. A lone ticket is built in the main session.
- **tea-sdlc:code-reviewer:** read-only. Build stage: reviews each ticket. Review stage: one dispatch per axis (Spec, Standards); returns `review.md` finding lines.
- **tea-sdlc:qa-subagent:** required; review stage, parallel to the reviews; reads `tickets.md` and `aidlc trace`, reports per requirement ID; verdict → `## QA`. Live API validation when an authorized service runs. Deployment-heavy risk → run again on the release candidate.

## Implementer dispatch
- One ticket from `tickets.md`: its block (What to build, acceptance checkboxes), the stories it covers, and its `Files:`, when declared, as the only paths it may change.
- Implementers never edit `docs/specs/**` (spec, contracts, ledger, review) except ticking their ticket's acceptance checkboxes; a contract that looks wrong comes back as `NEEDS_CONTEXT`.

## Planning skills order
1. `plan` writes `tickets.md` after the spec's security decisions and gated contracts (tickets cite contract paths).
2. `build` runs the build stage in this session (`aidlc next` batches, `aidlc task-done`), and resumes it in a new session or after `/clear`/compaction.

No build without a plan that passes the `planned` gate; `/tea-sdlc:fix` writes no plan.
