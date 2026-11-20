---
name: brainstorming
description: Use first, before reading files or editing, whenever a request builds, adds, modifies, fixes or refactors code (after an opener skill such as goal or clarify when one applies). Runs the trust-boundary check, clarifies the outcome, constraints and acceptance evidence, compares approaches when the tradeoff matters, writes the spec for full-workflow work and ends with the routing tier. Scales from three lines (routine fix) to a full design (trust-boundary or new system).
---

# Design clarification

Runs first for code-changing work, after any opener skill that applies (`tea-sdlc:goal`, `tea-sdlc:clarify`, `tea-sdlc:expert-lens`, `tea-sdlc:reframe`). It scales with the change and is never a reason to stop.

## 1. Trust-boundary check

Trust boundary = YES if the change touches any of: (1) PII or financial data, (2) auth, session or permission rules, (3) money, billing or payments, (4) a new endpoint, webhook or public surface, (5) a new external vendor, (6) security config or secrets (TLS, JWT, IAM, encryption). Unsure = YES.

| Change | Depth |
|---|---|
| Routine fix, no trust boundary | 2-3 lines: outcome, acceptance evidence, approach; continue. Bug or failing test → `tea-sdlc:systematic-debugging` next. |
| Feature or behavior change, no trust boundary | Add constraints, and 2-3 approaches only when the tradeoff is real; recommend one. |
| Trust boundary, lean mode (default) | 3-6 lines before the first edit: approach, assets touched, threats (STRIDE / OWASP), controls kept or added (`tea-sdlc:fintech-security` as catalogue; honour an existing `security.md`). Then tests for the security behaviour (authz denied, input rejected, no PII in logs, idempotent money movement); `check-contract.py` if an external contract changes; the pre-PR pass covers security and the PR lists threats checked. No spec, no subagents. |
| Trust boundary or new system, full mode (`TEA_SDLC_WORKFLOW=full`, the user asked for it, or a spec on the branch is in progress) | Spec per AIDLC (§3-§4). |

## 2. Clarify

Request already carries goals, acceptance criteria and a tier (e.g. a `/prompt-builder` prompt) → confirm in one line, state assumptions, continue. Non-interactive, or choices delegated → answer your own questions with the most reasonable assumption and say so.

Read project context and existing sources before asking. Identify outcome, constraints, acceptance evidence, material unknowns. Ask one concise question only when the answer changes the design. Compare 2-3 approaches when the tradeoff matters; recommend one with cost, risk, validation. Keep domain conventions and security controls. Size the design to the change: a config change is a few sentences; a new system states interfaces, ownership, data flow, failure behavior. Challenge a significant architecture decision once; record unresolved concerns.

Visual decision the user should compare (layouts, mockups, diagrams) → browser companion: `${CLAUDE_PLUGIN_ROOT}/skills/brainstorming/visual-companion.md` (its `skills/brainstorming/scripts/…` run from `${CLAUDE_PLUGIN_ROOT}`). Not for text questions.

## 3. Spec (full workflow only)

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run it yourself. Formats: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 (`requirements.md`, README frontmatter); folder placement: `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md` §4 (reuse the project's existing locations).

1. Stable kebab-case slug; a 2-6 letter key unused by other specs (`aidlc status`). `aidlc init <feature> --key <KEY>` (pass a folder path when the spec is not in the repository's own `docs/specs/`).
2. `README.md`: summary, file index, frontmatter `scope`, `affects`, `contract: none|external`, `security: required` (or `not-applicable — <reason>` only under the small-change escape hatch of `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`).
3. `requirements.md`: keyed requirements only, no narrative: `### <KEY>-<n>: <title>`, acceptance bullets under `Acceptance:` (Given/When/Then or EARS, one observable outcome each, unhappy paths included), a `Verify:` line.
4. Dispatch `tea-sdlc:security-engineer-subagent` for `security.md` (threat table + numbered rules) and, when the UI needs design, `tea-sdlc:ui-ux-designer-subagent` for `ui-design.md`; they run while you write the design.
5. Only when a contract or the architecture changes: `design.md` (≤ ~120 lines) and `contracts/`, following the security rules; an ADR per decision that outlives the change. `contract: external` → `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py" <spec-dir>` until it passes.
6. `tea-sdlc:spec-check`, then close every guess in the spec; a product-choice guess gets your most reasonable answer, listed for approval.

Do not commit or scaffold an existing repository just because a template says so.

## 4. One approval point (full workflow only)

Present once: summary, requirements, design, security rules, contract result, choices made closing guesses. Approval is the user's; skip asking only when the request explicitly delegated it ("end to end without checking in"). Record `accepted_by: <name> (<date>)` or `<name> (delegated in request)` in the README, then `aidlc advance <feature> accepted` (never set `status:` by hand). Gate findings → fix and rerun; that is not a new approval round unless the fix changes what was approved (say so in one line). No other confirmation rounds. Approval never authorizes destructive actions, external publishing or bypassing native controls.

Fast path: no approval gate, no spec folder.

## 5. Tier line

End with exactly one line:

`Tier: fast path | fast path + security pass | full workflow — <trust-boundary items hit, or none>`

Then: fast path (with or without security pass) → `tea-sdlc:test-driven-development` in this session, no subagent dispatch, single pre-PR pass before a PR. Full workflow → `tea-sdlc:writing-plans` on the accepted spec.
