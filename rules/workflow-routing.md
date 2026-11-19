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

## Routing Tiers

| Trust boundary? | Tier |
|---|---|
| **NO** (any number of domains) | **Fast path** |
| **YES** (any number of domains) | **Full workflow** |

### Fast path
Implement with TDD + verification. Brainstorming runs first for every code change (session bootstrap, First action rule); on the fast path keep it to 2-3 lines — it is the "state the approach" step (no artifact). No plan document. No worktree. No subagent dispatch. No review loops. Before opening a PR or handing off, run the single pre-PR pass in `rules/pre-pr-review.md`.
When the change spans several domains (a domain is a distinct stack surface: backend, frontend, mobile, AWS/infra, data pipeline, AI/LLM, DevOps pipeline; a shared library touched by one stack adds none): write the task order in 2-3 lines before touching the second domain, edit in dependency order (a RED test that must exist before another domain's fix comes first), follow TDD in each domain, and run the smoke test at the integration point before merge; do not skip it because each side passed in isolation.

### Full workflow (any trust boundary, any number of domains)
The AIDLC stages in `references/aidlc.md`. A spec enters a stage only through `scripts/aidlc.py advance`, and only when that stage's gate passes; the session runs the CLI itself.

1. **proposed → accepted.** Brainstorming and design clarification, then the spec: keyed requirements with acceptance criteria and `Verify:`, `security.md` from the Security subagent, `design.md` + `contracts/` and the contract gate (`python3 scripts/check-contract.py docs/specs/<feature>`) if an external contract changes, and the blind spec check with every guess closed. Then the one user approval.
2. **planned.** The implementation plan as a task graph (covers, depends, owner, files), every requirement covered, no shared file between tasks that may run in parallel.
3. **building.** On a feature branch, `subagent-driven-development` dispatches the ready tasks (`aidlc next`) in parallel batches; each task is ticked by `aidlc task-done`; decisions the session takes instead of asking are recorded with `aidlc ruling`.
4. **verified.** All tasks done, every `Verify: test` requirement referenced by a test, the full test run green at the current code fingerprint.
5. **reviewed.** Two separate reviews in `review.md`: Spec (against requirements, design, contracts) and Standards (code quality, security rules, conventions), every finding fixed or cleared; QA runs in the same stage (with live API validation when a service is running).
6. **shipped.** The PR with CI green and `ship.md`: GO, rollback and post-release verification.
7. **implemented.** After merge, `/upgrade-service-docs` promotes the spec into the living docs.

Contract drafting is needed only for an external contract change (HTTP/RPC API, event, shared schema, public library API); skip it when there is no new contract surface (e.g., tightening validation on an existing endpoint). The main session drafts the contracts and the contract gate verifies them; the main session dispatches implementers using custom agent definitions as context.

## Mid-execution domain expansion

If a task begins in one tier but discovers additional scope mid-execution, re-classify before proceeding:

- Fast path discovers a trust boundary → **stop**, promote to Full workflow, dispatch Security on the unmerged work and apply its rules before writing more code.
- Fast path promoted to Full workflow: create the spec (`aidlc init`) and take it through the stages from `proposed`; work already done is cited in the plan, not redone.
- Full workflow → discovers another domain: keep the full workflow, add that domain's tasks to the plan and re-run its gate (`aidlc check <feature> --to planned`), reuse the existing Security output, and re-run the contract gate if the contract grows. New requirements go back through the spec check and the user's approval.

Do not silently stay in the lower tier. Promotion is mandatory once the trigger is met.

## Small-change escape hatch

A trust-boundary change may use the fast path if ALL of the following hold:
1. Diff is ≤ 30 lines of production code across ≤ 3 files (test code excluded).
2. No new endpoint, no new external surface, no new dependency, no schema/migration change.
3. The trust-boundary trigger is a touch, not a new decision (e.g., renaming a field already classified as PII, not introducing a new PII field).
4. An existing Security rule or threat model already covers the touched code path (cite the resolved Security artifact path, default `docs/specs/<feature>/security.md` per `references/documentation-layout.md`).

With all four true: full workflow → fast path with TDD. Document the decision in the commit message: "Escape hatch applied: <cite rule>". If any condition fails, use the full tier.

## Ambiguous?

Walk the 6-item checklist above. If any item is YES, full workflow. Otherwise fast path. Do not rely on a single gut-check question.

## Design Decision Quality

For a non-trivial design decision (architecture, API contract, data model, skill/agent design), have an agent look for flaws and counter-arguments in your draft before presenting it; resolve material ones within `rules/review-loop-limits.md` and report the rest. Skip for implementation tasks, bug fixes and single-file changes.
