# Agent Delegation Rules

See `rules/workflow-routing.md` for two-tier routing: fast path / full workflow.

## Agent Registry
- **Spec authoring has no agent:** the main session writes `requirements.md`, `design.md`, `contracts/`, ADRs, `glossary.md` and `measurement.md` (skills `brainstorming`, `writing-plans`, `writing-software-docs`, `measurement-planning`). Structure and compatibility of contracts are checked by the contract gate, not by an agent.
- **security-engineer-subagent**: Threat modeling, security rules. BEFORE implementation for: new auth flows, payment processing, PII handling, new external API exposure. Skip for: internal utilities, UI changes, non-security config updates, existing API field additions that do NOT change the security posture (no new PII field, no auth semantics change). **Do not skip** for changes matching `rules/workflow-routing.md` trust-boundary item 6 (TLS, JWT keys, IAM, encryption, secret-handling paths) — those are trust-boundary config changes and Security is required. When `workflow-routing.md` and this skip list appear to disagree, `workflow-routing.md` wins.
- **backend-engineer-subagent**: APIs, business logic, databases, and LLM features (prompts, RAG, agent tools, evals, AI cost controls)
- **frontend-engineer-subagent**: UI components, user experience
- **platform-engineer-subagent**: AWS CDK/serverless (Lambda, Step Functions, DynamoDB, SQS, API Gateway, EventBridge), non-AWS IaC, CI/CD, containers, Kubernetes, observability
- **data-engineer-subagent**: ETL, data pipelines, warehouses
- **mobile-engineer-subagent**: Flutter/Dart, iOS (Swift/SwiftUI), Android (Kotlin/Compose), React Native
- **ui-ux-designer-subagent**: Wireframes, component specs, user flow design — activate before frontend when visual design needed
- **qa-subagent**: Final validation gate. AFTER implementation. Includes live API validation (endpoint smoke, performance, security smoke, stress) when an authorized running service is in scope. Optional for single-file fixes and trivial changes.
- **code-reviewer**: Reviews completed work against plan and standards. Read-only tools (no Write/Edit). In the full workflow, the main session MUST dispatch code-reviewer after implementation when a structured review is needed — no other agent owns this gate.

Per-dispatch model selection (override the agent's default `model:` frontmatter): see `skills/dispatching-parallel-agents/references/model-routing.md`.

Subagents may not be able to spawn further subagents (version/config dependent). A subagent that cannot dispatch returns the dispatch plan to the main session instead of calling Task.

## Dispatch Contract
- Every `Task` dispatch by the main session (any tier that dispatches) MUST follow `rules/dispatch-prompt-contract.md` — the nine contract fields (role, context, inputs, task, exit_criteria, out_of_scope, evidence, bailout, return_format; XML recommended, markdown headings compliant). Review/advisory dispatches use the lighter minimum defined there.
- Dispatch prompts are model-aware: style content for the dispatch's resolved model per the "Model-Specific Steering" section of `skills/dispatching-parallel-agents/references/model-routing.md` (literal scope enumeration for sonnet/opus, coverage-not-filtering for literal reviewers, slot-filling for haiku, terse for frontier overrides).
- Every subagent's return MUST include three things (prose, markdown, or XML — shape is flexible): status ∈ {DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED}, evidence paths the dispatcher can `Read`, and an exit-criteria check. Full conventions: `rules/subagent-return-format.md`.
- Dispatchers verify every cited evidence path and confirm each exit criterion is marked met before accepting `DONE`.
- Fast-path work does not dispatch subagents, so no exemption clause is needed.

## Quality Gates
- Which tiers require a QA gate (and its live API validation) is owned by `rules/workflow-routing.md` (tier table + per-tier sequences). Do not restate the tier logic here — the full-workflow tier carries the gate; fast path does not.
- Agent-level QA scope (optional for single-file/trivial changes; live API validation only for authorized running services) is in the Agent Registry entries above.

## Factual Grounding
- All agents MUST follow `rules/reduce-hallucinations.md` — no invented file paths, function names, flags, APIs, or commit SHAs. Cite the source or say "I don't know".
- Dispatchers: treat fabricated evidence paths in subagent returns as BLOCKED, per `rules/subagent-return-format.md`.

## Planning Skills Ordering

Three skills cover plan/execution and can be confused. Use this order:

1. **`writing-plans`** — produces the plan document. Create an initial coordination outline after scope clarification. Persist the implementation plan once Security rules and, for an external contract change, the drafted contracts (passing the contract gate) exist, before implementation dispatches; advisory/strategic dispatches may precede that plan. Outputs a written plan that downstream skills consume.
2. **`subagent-driven-development`** — executes the plan **within the current session** by dispatching leaf subagents for independent tasks. Use when the plan has parallelizable leaf work and the dispatcher is the main session. Also use for single-session + checkpoints by pausing between tasks to confirm with the user.
3. **`executing-plans`** — executes the plan **in a separate session with review checkpoints**. Use when the plan spans multiple review gates, or when the user wants human-in-the-loop checkpoints between phases that must survive a context reset.

Decision: single-session + many leaves → `subagent-driven-development` (with or without intra-session checkpoints). Multi-session + checkpoints → `executing-plans`. Both skills assume a `writing-plans` output exists; do not start execution without a plan document for full-workflow paths.

**Plan vs. contract:** for an external contract change the main session drafts `design.md` and `contracts/`, and `scripts/check-contract.py` (the contract gate) verifies their structure and compatibility. The `writing-plans` output is the execution plan (task breakdown, ordering, parallelism); the contracts are the design artifact (API shape, data model). Write the plan AFTER the contracts pass the gate so tasks can reference concrete contract paths.

Fast-path work skips all three.
