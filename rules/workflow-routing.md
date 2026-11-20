# Workflow routing

## Trust-boundary check
Walk all six; any YES or unsure → trust boundary.
1. Reads, writes or logs PII or sensitive data (identity, contact, ID numbers, financial, health, credentials).
2. Creates, validates or changes authN, session or authZ rules (login, tokens, permissions, roles).
3. Processes money, billing or third-party payments.
4. Exposes a new URL, endpoint, webhook or other surface reachable from outside the trust domain.
5. Integrates a new external vendor, partner API or third-party script.
6. Changes a security-relevant dependency, config key or secret-handling path (TLS, JWT keys, IAM, encryption).

## Workflow mode
- **lean (default):** main session only; no subagent, `debug-parallel` or AIDLC spec unless the user asks. If full would clearly pay off, say so in one line and let the user choose.
- **full:** `TEA_SDLC_WORKFLOW=full` (e.g. `.claude/settings.json` `env`), the user asks ("full workflow", "AIDLC", "use subagents"), or a spec bound to the branch is past `proposed`.

The session-start note states the mode.

| Trust boundary | lean | full |
|---|---|---|
| NO (any number of domains) | Fast path | Fast path |
| YES (any number of domains) | Fast path with a security pass | Full workflow |

## Fast path
TDD + verification. Brainstorming first, 2-3 lines stating the approach (no artifact). No plan, worktree, subagent or review loop. Before a PR or hand-off: the single pre-PR pass (`rules/pre-pr-review.md`). Update a living doc whose documented behaviour changed in the same change.

Several domains (backend, frontend, mobile, AWS/infra, data pipeline, AI/LLM, DevOps; a shared library used by one stack adds none): write the task order in 2-3 lines before the second domain; edit in dependency order; TDD per domain; smoke-test the integration point before merge even if each side passed.

## Lean mode: fast path with a security pass
In the main session, no dispatch:
1. Before the first edit write 3-6 lines: assets touched, applicable threats (STRIDE / OWASP), controls kept or added. Control catalogue: `tea-sdlc:fintech-security`; honour an existing `docs/specs/<feature>/security.md`.
2. Test the security behaviour (authZ denied, input rejected, no PII in logs, idempotent money movement), not only the happy path.
3. External contract change → `python3 scripts/check-contract.py` on the drafted contract.
4. The pre-PR review covers security explicitly; the PR description lists the threats checked and any left to the human reviewer.

## Full workflow (full mode, trust boundary)
The session runs `python3 scripts/aidlc.py` itself; a stage is entered only via `aidlc advance` when its gate passes. Read only the current stage's part of `references/aidlc.md` (§1 gates, §2 formats, §3 CLI).
1. **accepted:** clarify; `requirements.md` (acceptance bullets + `Verify:` only); `security.md` (threat table + numbered rules) from tea-sdlc:security-engineer-subagent; `design.md` (≤ ~120 lines) + `contracts/` + `python3 scripts/check-contract.py docs/specs/<feature>` only when a contract or the architecture changes; ONE blind spec check, guesses closed in the spec; one user approval.
2. **planned:** task graph; every requirement covered; parallel tasks share no file.
3. **building:** feature branch; `subagent-driven-development` dispatches `aidlc next` batches; `aidlc task-done`; decisions taken instead of asking → `aidlc ruling`.
4. **verified:** `aidlc verify` green at the current fingerprint.
5. **reviewed:** Spec and Standards axes once each, in parallel with tea-sdlc:qa-subagent; `review.md` = finding lines, each fixed or cleared; then at most ONE diff-only re-review by a single tea-sdlc:code-reviewer with `AXIS: both`, never a second full round.
6. **shipped:** PR, CI green, `ship.md` (required sections only).
7. **implemented:** after merge, `/upgrade-service-docs`.

External contract change = HTTP/RPC API, event, shared schema or public library API; tighter validation on an existing endpoint is not one.

## Mid-execution promotion
Re-classify when scope grows; promotion is mandatory.
- Fast path hits a trust boundary → stop. Full mode: `aidlc init`, run from `proposed` (cite done work in the plan), dispatch Security on the unmerged work and apply its rules before more code. Lean: do the security pass on the work so far first.
- Full workflow gains a domain → add its tasks, `aidlc check <feature> --to planned`, reuse Security output, re-run the contract gate if the contract grows; new requirements go back through spec check and approval.

## Escape hatch (full mode)
A trust-boundary change may take the fast path with TDD only if ALL hold:
1. ≤ 30 lines of production code across ≤ 3 files (tests excluded).
2. No new endpoint, external surface, dependency, schema or migration.
3. The trigger is a touch, not a new decision (renaming a field already classified as PII, not adding one).
4. An existing Security rule or threat model covers the path; cite it (default `docs/specs/<feature>/security.md`).

Commit message: `Escape hatch applied: <cite rule>`. Any condition fails → full workflow. This wins over any other skip list for Security.

## Design-decision quality
Non-trivial design decision (architecture, API contract, data model, skill/agent design): seek flaws and counter-arguments in your draft before presenting (full mode: an agent does it); resolve material ones in ≤ 2 rounds, report the rest. Skip for implementation, bug fixes, single-file changes.
