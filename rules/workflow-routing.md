# Workflow Routing

## Trust Boundary Check

Does this change touch **any** of the following? Any single YES → trust boundary.

1. Reads, writes, or logs PII or sensitive data (names, emails, phones, addresses, IDs, financial data, health data, auth credentials).
2. Creates, validates, or mutates auth / session / authorization rules (login, tokens, permissions, roles).
3. Processes money, billing, or third-party payment flows.
4. Exposes a new URL, endpoint, webhook, or public surface consumable outside the trust domain.
5. Integrates with a new external vendor, partner API, or third-party script.
6. Modifies a security-relevant dependency, config key, or secret-handling path (TLS, JWT keys, IAM, encryption).

If unsure on any item, treat as YES. Under-classification is the dominant failure mode.

## Domain Count

A "domain" = a distinct stack surface: backend, frontend, mobile, AWS/infra, data pipeline, AI/LLM, DevOps pipeline. Shared libraries touched by one stack do not add a domain.

## Routing Tiers

| Trust boundary? | Tier |
|---|---|
| **NO** (any number of domains) | **Fast path** |
| **YES** (any number of domains) | **Full workflow** |

### Fast path
Implement with TDD + verification. Brainstorming only if design genuinely unclear. Before editing, state the approach in 2–3 lines in the reply (no artifact). No plan document. No worktree. No subagent dispatch. No review loops. Before opening a PR or handing off, run the single pre-PR pass in `rules/pre-pr-review.md`.
When the change spans several domains: write the task order in 2-3 lines before touching the second domain, edit in dependency order (a RED test that must exist before another domain's fix comes first), follow TDD in each domain, and run the smoke test at the integration point before merge; do not skip it because each side passed in isolation.

### Full workflow (any trust boundary, any number of domains)
scope/design clarification → coordination outline → Security subagent → **draft `design.md` + `contracts/` and pass the contract gate (`scripts/check-contract.py`) if an external contract changes** → implementation plan → `subagent-driven-development` (independent domain tasks run in parallel when safe; dependent ones in order) → code review → QA (with live API validation when a service is running) → after GO/merge, `/upgrade-service-docs` promotes the spec into living docs.
Contract drafting is needed only for an external contract change (HTTP/RPC API, event, shared schema, public library API); skip it when there is no new contract surface (e.g., tightening validation on an existing endpoint). The main session drafts the contracts and the contract gate verifies them; the main session dispatches implementers using custom agent definitions as context.

## Mid-execution domain expansion

If a task begins in one tier but discovers additional scope mid-execution, re-classify before proceeding:

- Fast path → discovers trust boundary → **stop**, promote to full workflow. Do not retrofit Security after the fact on in-flight code; dispatch Security on the unmerged work.
- Full workflow → discovers another domain: keep the full workflow, add that domain's tasks to the plan, reuse the existing Security output, and re-run the contract gate if the contract grows.

Do not silently stay in the lower tier. Promotion is mandatory once the trigger is met.

## Small-change escape hatch

A trust-boundary change may use the tier **one step lighter** if ALL of the following hold:
1. Diff is ≤ 30 lines of production code across ≤ 3 files (test code excluded).
2. No new endpoint, no new external surface, no new dependency, no schema/migration change.
3. The trust-boundary trigger is a touch, not a new decision (e.g., renaming a field already classified as PII, not introducing a new PII field).
4. An existing Security rule or threat model already covers the touched code path (cite the resolved Security artifact path, default `docs/specs/<feature>/security.md` per `references/documentation-layout.md`).

With all four true: full workflow → fast path with TDD. Document the decision in the commit message: "Escape hatch applied: <cite rule>". If any condition fails, use the full tier.

## Ambiguous?

Walk the 6-item checklist above. If any item is YES, full workflow. Otherwise fast path. Do not rely on a single gut-check question.

## Design Decision Quality

For non-trivial design decisions (architecture, API contracts, skill/agent design, data models), use the Agent tool to challenge your draft before presenting to the user:
1. Draft the design with full context
2. Spawn an agent to find flaws, gaps, and counter-arguments
3. Resolve material counter-arguments within `rules/review-loop-limits.md`; report unresolved concerns rather than forcing consensus
4. Present only the final version

Skip for: implementation tasks, bug fixes, simple questions, single-file changes.

## Authorization and runtime
Reuse explicit authorization already given for the same scope. Present substantive decisions without adding repeated approval gates for choices the user delegated. Native permission prompts and separately controlled actions still apply. If agents/services are unavailable, state the missing gate; use a safe authorized fallback without fabricating an independent review or API result.
