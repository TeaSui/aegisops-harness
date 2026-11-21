# Agent delegation (full workflow only)

Only the main session dispatches, and only in the full workflow; the fast path never dispatches.

## Registry
- **No spec-authoring agent:** the main session writes `spec.md`, `tickets.md`, `contracts/`, ADRs, `GLOSSARY.md`, `measurement.md`; `scripts/check-contract.py` checks contracts.
- **tea-sdlc:security-engineer-subagent:** reviews the draft `spec.md`, returns its `### Security` subsection (the main session pastes it under Implementation Decisions). Skipped only under the full-mode escape hatch.
- **tea-sdlc:ui-ux-designer-subagent:** before frontend work that needs visual design; returns UI decisions for `spec.md` (or writes the project's design doc).
- **tea-sdlc:backend-engineer-subagent:** APIs, business logic, databases, LLM features (prompts, RAG, agent tools, evals, AI cost controls).
- **tea-sdlc:frontend-engineer-subagent:** UI. **tea-sdlc:mobile-engineer-subagent:** Flutter/Dart, iOS, Android, React Native. **tea-sdlc:data-engineer-subagent:** ETL, pipelines, warehouses.
- **tea-sdlc:platform-engineer-subagent:** AWS CDK/serverless, other IaC, CI/CD, containers, Kubernetes, observability.
- **tea-sdlc:code-reviewer:** read-only. Build stage: reviews each ticket. Review stage: one dispatch per axis (Spec, Standards); returns `review.md` finding lines.
- **tea-sdlc:qa-subagent:** required; review stage, parallel to the reviews; reads `tickets.md` and `aidlc trace`, reports per requirement ID; verdict → `## QA`. Live API validation when an authorized service runs. Deployment-heavy risk → run again on the release candidate.

## Implementer dispatch
- One ticket from `tickets.md`: its block (What to build, acceptance checkboxes), the stories it covers, and its `Files:`, when declared, as the only paths it may change.
- Implementers never edit `docs/specs/**` (spec, contracts, ledger, review) except ticking their ticket's acceptance checkboxes; a contract that looks wrong comes back as `NEEDS_CONTEXT`.

## Planning skills order
1. `plan` writes `tickets.md` after the spec's security decisions and gated contracts (tickets cite contract paths).
2. `build` runs the build stage in this session (`aidlc next` batches, `aidlc task-done`), and resumes it in a new session or after `/clear`/compaction.

No full-workflow execution without a plan that passes the `planned` gate. The fast path writes no plan.
