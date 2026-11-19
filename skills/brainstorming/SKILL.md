---
name: brainstorming
description: Use first, before reading files or editing, whenever a request builds, adds, modifies, fixes or refactors code (after an opener skill such as goal or clarify when one applies). Runs the trust-boundary check, clarifies the outcome, constraints and acceptance evidence, compares approaches when the tradeoff matters, writes the spec for full-workflow work and ends with the routing tier. Scales from three lines (routine fix) to a full design (trust-boundary or new system).
---

# Design clarification

This skill runs first for code-changing work, after any opener skill (`tea-sdlc:goal`, `tea-sdlc:clarify`, `tea-sdlc:expert-lens`, `tea-sdlc:reframe`) that applies. It scales with the change; it never becomes a reason to stop.

## 1. Trust-boundary check

Walk the six items first; the answer sets the depth. Trust boundary = YES if the change touches any of:

1. PII or financial data
2. auth, session or permission rules
3. money, billing or payments
4. a new endpoint, webhook or public surface
5. a new external vendor
6. security config or secrets (TLS, JWT, IAM, encryption)

Unsure counts as YES.

| Change | Depth |
|---|---|
| Routine fix, no trust boundary | 2-3 lines: outcome, acceptance evidence, approach. Then continue immediately; for a bug or a failing test the next step is `tea-sdlc:systematic-debugging` (root cause before any fix). |
| Feature or behavior change, no trust boundary | Add constraints and 2-3 approaches only if the tradeoff is real; recommend one. |
| Trust boundary or new system | Full design and spec below (Full workflow). |

## 2. Clarify

If the request already carries goals, acceptance criteria and a tier (for example a `/prompt-builder` prompt), confirm them in one line, state any assumption you make, and continue. If you cannot ask the user (non-interactive run) or they delegated the choices, answer your own questions with the most reasonable assumption, say what you assumed, and proceed.

Read the applicable project context, then identify the outcome, constraints, acceptance evidence and material unknowns. Consult available sources before asking for information they already contain. Ask one concise question only when the answer changes the design; otherwise state the assumption and continue.

Compare two or three approaches when the tradeoff matters. Recommend one with its costs, risks and validation. Preserve existing domain conventions and security controls. A configuration change may need a few sentences; a new system needs interfaces, ownership, data flow and failure behavior. Make components understandable and independently testable. For significant architecture decisions, challenge the design once; keep review iterations bounded and record unresolved concerns.

For an actual visual decision (layouts, mockups, diagrams the user should compare), use the browser companion in `${CLAUDE_PLUGIN_ROOT}/skills/brainstorming/visual-companion.md`; its `skills/brainstorming/scripts/…` commands run from `${CLAUDE_PLUGIN_ROOT}`. It is not an intake ceremony.

## 3. Spec (Full workflow only)

The stages, gates and file formats are in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`; the folder and its writers are in `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md` §4 (reuse the project's existing locations, §6). Run the CLI yourself, never ask the user to. Below, `aidlc` stands for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`.

1. Pick a stable kebab-case slug for this one change and a 2-6 letter key that no other spec uses (`aidlc status` lists the existing specs). Run `aidlc init <feature> --key <KEY>` to create the folder in the owning scope (pass the folder path instead of the slug when it is not the repository's own `docs/specs/`).
2. Fill `README.md`: summary, file index and the frontmatter fields `scope`, `affects`, `contract: none|external` and `security: required` (or `not-applicable — <reason>`, only under the escape hatch in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`).
3. Write `requirements.md`: one `### <KEY>-<n>: <title>` heading per requirement, its acceptance criteria as bullets under `Acceptance:` (Given/When/Then or EARS, one observable outcome per bullet, unhappy paths included), and a `Verify:` line (`aidlc.md` §2). Business rules and new terms may follow in any form.
4. Dispatch `security-engineer-subagent` for `security.md` (threat model and numbered rules), and `ui-ux-designer-subagent` for `ui-design.md` when the UI needs design. Both can run while you write the design.
5. When a contract or the architecture changes, write `design.md` and `contracts/`, following the Security rules. Write an ADR for each decision that outlives the change. For `contract: external`, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py" <spec-dir>` and fix the contracts until it passes.
6. Once the spec files exist, invoke `tea-sdlc:spec-check`. Close every guess it lists: answer it in the spec, or accept the risk with a reason. A guess that needs a product choice gets your most reasonable answer, written into the spec and listed for the approval below.

Do not commit or scaffold an existing repository only because a template says so.

## 4. One approval point (Full workflow only)

Present the spec once: summary, requirements, design, security rules, contract result, and the choices you made while closing guesses. Ask the user to approve it; approval is a decision only the user can make. If the original request explicitly delegated approval (for example "handle this end to end without checking in"), do not ask.

Record `accepted_by: <name> (<date>)`, or `<name> (delegated in request)`, in the README frontmatter. Then run `aidlc advance <feature> accepted`. Do not set `status:` by hand. If the gate lists findings, fix them and run it again; fixing a gate finding is not a new approval round, unless the fix changes what the user approved, which you then say in one line. Do not add confirmation rounds for sections, the plan or execution.

Fast path has no approval gate and no spec folder: state the approach and continue.

This never authorizes destructive actions, external publishing or bypassing native controls beyond the user's scope.

## 5. Tier line

End with one line: `Tier: fast path | full workflow — <trust-boundary items hit, or none>`. Then continue:

- Fast path: `tea-sdlc:test-driven-development` in this session, no subagent dispatch, single pre-PR pass before a PR.
- Full workflow: `tea-sdlc:writing-plans` on the accepted spec.
