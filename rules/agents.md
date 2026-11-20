# Agent delegation (full workflow only)

Only the main session dispatches, and only in the full workflow; the fast path never dispatches.

## Registry
- **No spec-authoring agent:** the main session writes `requirements.md`, `design.md`, `contracts/`, ADRs, `glossary.md`, `measurement.md`; `scripts/check-contract.py` checks contracts.
- **tea-sdlc:security-engineer-subagent:** first step; writes `security.md`. Skipped only under the full-mode escape hatch.
- **tea-sdlc:ui-ux-designer-subagent:** before frontend work that needs visual design; writes `ui-design.md`.
- **tea-sdlc:backend-engineer-subagent:** APIs, business logic, databases, LLM features (prompts, RAG, agent tools, evals, AI cost controls).
- **tea-sdlc:frontend-engineer-subagent:** UI. **tea-sdlc:mobile-engineer-subagent:** Flutter/Dart, iOS, Android, React Native. **tea-sdlc:data-engineer-subagent:** ETL, pipelines, warehouses.
- **tea-sdlc:platform-engineer-subagent:** AWS CDK/serverless, other IaC, CI/CD, containers, Kubernetes, observability.
- **tea-sdlc:code-reviewer:** read-only. Build stage: reviews each task. Review stage: one dispatch per axis (Spec, Standards); returns `review.md` finding lines.
- **tea-sdlc:qa-subagent:** required; review stage, parallel to the reviews; reads `plan.md` and `aidlc trace`, reports per requirement ID; verdict → `## QA`. Live API validation when an authorized service runs. Deployment-heavy risk → run again on the release candidate.

## Implementer dispatch
- One task from `plan.md`: its block, the requirement IDs it covers with their acceptance criteria, and its `files` as the only paths it may change.
- Implementers never edit `docs/specs/**` (contracts, plan, ledger, review); a contract that looks wrong comes back as `NEEDS_CONTEXT`.

## Planning skills order
1. `writing-plans` writes `plan.md` after Security rules and gated contracts (tasks cite contract paths).
2. `subagent-driven-development` runs the build stage in this session (`aidlc next` batches, `aidlc task-done`).
3. `executing-plans` resumes a saved plan in a new session or after `/clear`/compaction, still dispatching through `subagent-driven-development`.

No full-workflow execution without a plan that passes the `planned` gate. The fast path writes no plan.
