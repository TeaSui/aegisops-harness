# Agent Delegation Rules

Tiers are defined in `rules/workflow-routing.md`. The Fast path never dispatches a subagent; only the Full workflow does, and only the main session dispatches. The Full workflow follows the AIDLC stages in `references/aidlc.md`.

## Agent Registry

- **No spec-authoring agent:** the main session writes `requirements.md`, `design.md`, `contracts/`, ADRs, `glossary.md` and `measurement.md`; the contract gate (`scripts/check-contract.py`) checks contracts.
- **security-engineer-subagent:** first step of the Full workflow; writes `security.md`. Skip only under the escape hatch in `rules/workflow-routing.md`, which wins over any other skip list.
- **ui-ux-designer-subagent:** before frontend work when the change needs visual design; writes `ui-design.md`.
- **backend-engineer-subagent:** APIs, business logic, databases, LLM features (prompts, RAG, agent tools, evals, AI cost controls).
- **frontend-engineer-subagent:** UI components and user experience.
- **mobile-engineer-subagent:** Flutter/Dart, iOS, Android, React Native.
- **platform-engineer-subagent:** AWS CDK/serverless, other IaC, CI/CD, containers, Kubernetes, observability.
- **data-engineer-subagent:** ETL, data pipelines, warehouses.
- **code-reviewer:** read-only; the main session dispatches it. In the build stage it reviews each task; in the review stage it runs once per axis (Spec, Standards), as two separate dispatches, and returns findings as `review.md` lines.
- **qa-subagent:** required in the Full workflow. Runs in the review stage (spec at `verified`), in parallel with the two code reviews; it reads `plan.md` and `aidlc trace` and reports against requirement IDs, and its verdict becomes the QA line of `ship.md`. For a change whose risk is mostly in deployment, run it again before ship against the release candidate. Includes live API validation when an authorized running service is in scope.

Model and effort per dispatch: `references/model-guide.md`.

## Dispatch and return

- Prompt shape: `rules/dispatch-prompt-contract.md`. Implementers get one task from `plan.md`: its block, the requirement IDs it covers with their acceptance criteria, and its `files` as the only paths they may change.
- Return shape and dispatcher checks: `rules/subagent-return-format.md`. Implementers also return the requirement IDs they covered and the names of the tests that prove each one; tests carry the requirement ID in their name (for example `RFD-1 rejects over-capture`) so the trace gate finds them.
- Implementers do not edit `docs/specs/**` (contracts, plan, ledger, review): a contract that looks wrong comes back as `NEEDS_CONTEXT`.
- Factual grounding: `rules/reduce-hallucinations.md`.

## Planning Skills Ordering

1. `writing-plans` writes `plan.md` (the task graph in `references/aidlc.md`), after Security rules and (for an external contract change) contracts that pass the contract gate, so tasks can cite concrete contract paths.
2. `subagent-driven-development` runs the build stage in the current session: it dispatches each batch that `aidlc next` returns and finishes tasks with `aidlc task-done`.
3. `executing-plans` resumes a saved plan in a new session or after `/clear` or compaction; in the Full workflow it still dispatches through `subagent-driven-development`.

Do not start Full-workflow execution without a plan that passes the `planned` gate. The Fast path writes no plan.
