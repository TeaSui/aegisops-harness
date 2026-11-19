# Agent Delegation Rules

Tiers are defined in `rules/workflow-routing.md`. The Fast path never dispatches a subagent; only the Full workflow does, and only the main session dispatches.

## Agent Registry

- **No spec-authoring agent:** the main session writes `requirements.md`, `design.md`, `contracts/`, ADRs, `glossary.md` and `measurement.md`; the contract gate (`scripts/check-contract.py`) checks contracts.
- **security-engineer-subagent:** first step of the Full workflow; writes `security.md`. Skip only under the escape hatch in `rules/workflow-routing.md`, which wins over any other skip list.
- **ui-ux-designer-subagent:** before frontend work when the change needs visual design; writes `ui-design.md`.
- **backend-engineer-subagent:** APIs, business logic, databases, LLM features (prompts, RAG, agent tools, evals, AI cost controls).
- **frontend-engineer-subagent:** UI components and user experience.
- **mobile-engineer-subagent:** Flutter/Dart, iOS, Android, React Native.
- **platform-engineer-subagent:** AWS CDK/serverless, other IaC, CI/CD, containers, Kubernetes, observability.
- **data-engineer-subagent:** ETL, data pipelines, warehouses.
- **code-reviewer:** after implementation, read-only; the main session dispatches it.
- **qa-subagent:** final gate after code review; required in the Full workflow. Includes live API validation when an authorized running service is in scope.

Model and effort per dispatch: `references/model-guide.md`.

## Dispatch and return

- Prompt shape: `rules/dispatch-prompt-contract.md`.
- Return shape and dispatcher checks: `rules/subagent-return-format.md`.
- Factual grounding: `rules/reduce-hallucinations.md`.

## Planning Skills Ordering

1. `writing-plans` writes the plan, after Security rules and (for an external contract change) contracts that pass the contract gate, so tasks can cite concrete contract paths.
2. `subagent-driven-development` executes the plan in the current session by dispatching leaf subagents.
3. `executing-plans` resumes a saved plan in a new session or after `/clear` or compaction; in the Full workflow it still dispatches through `subagent-driven-development`.

Do not start Full-workflow execution without a plan. The Fast path writes no plan.
