# AIDLC lifecycle (full workflow only)

Read only the section for the current stage. `scripts/aidlc.py` wins over this file. Gates check that evidence exists and is current, not that it is good.

## 0. Open questions (every stage)

A question about business rules, domain terms, existing behaviour, limits, owners or product intent. Take the first step that settles it:

1. **Files:** the spec, `GLOSSARY.md`, ADRs, contracts, the code and its tests, git history.
2. **Atlassian Rovo MCP** (the Atlassian server, whatever its prefix, e.g. `mcp__plugin_operations_atlassian__*`): `search` (Rovo search over Confluence and Jira) with the glossary term, the feature name and any Jira key, then `fetch` / `getConfluencePage` / `getJiraIssue` on the best hits; `searchConfluenceUsingCql` / `searchJiraIssuesUsingJql` to narrow. Record what settled it (page title + URL, or issue key): in `spec.md` Further Notes under `Sources:`, or in the ruling. Sources disagree → the newer and more specific one wins; record the conflict.
3. **Recorded assumption:** still open → take the most reasonable answer and continue; at the spec stage write it into spec.md (story or decision, listed for the approval), later `aidlc ruling … --why "<no source; reasoning>"`.
4. **Ask the user** only after step 2 ran for that question, when no safe default exists and the answer is one of: accepting a security or compliance risk, money movement or regulatory behaviour with no source, an irreversible or production action, sources that contradict each other on observable behaviour. One batched question per stage, each with your recommended answer. A missing contract, endpoint or integration detail with a configurable default (a connector with the path in config, confirmed before release) is step 3, not 4.

**Delegated input** (`do not ask`, `not available for questions`, `end to end`, or a spec with `Status: ready-for-agent`): there is no step 4. Take the recommended option, record it (spec.md `Assumptions:`, or `aidlc ruling`) with the decision starting `RISK-ACCEPTANCE NEEDED:` when it accepts a security or compliance risk, and list those first in the final report. The only stops are the ones `/tea-sdlc:aidlc` names (merge and deploy need words for it).

Rovo not connected or failing → say so once in the stage report and go on with 3–4. Subagents have no Rovo: they return NEEDS_CONTEXT with a recommended answer, the main session answers through this order. Never ask what steps 1–2 answer. `hooks/question-gate.py` enforces this: inside a tea-sdlc command it blocks every question in delegated input, and otherwise the first question asked before any Rovo call.

## 1. Stages

```
proposed ─▶ accepted ─▶ planned ─▶ building ─▶ verified ─▶ reviewed ─▶ shipped ─▶ implemented
```

README `status:` holds the stage; active = `proposed`…`shipped`. Only `aidlc advance` moves it, when the target gate passes. `--back --reason` moves back; back to `proposed` clears `accepted_by:`. Side states: `abandoned --reason` (from any active stage), `superseded` (needs README `superseded_by:`), `partially-implemented` (from `shipped`, `implemented` gate). `check SPEC --to STAGE` re-checks any gate; `--back` never reopens tickets; re-entering `verified` needs a fresh `verify`. Specs without `key:` are legacy and ungated until given a key.

| Target | Gate |
|---|---|
| `accepted` | README `key:` unique in repo; `spec.md` has every template section (Problem Statement, Solution, User Stories, Implementation Decisions, Testing Decisions, Out of Scope) filled, ≥1 numbered user story, numbers unique, any `(Verify: …)` tag valid; security decisions in Implementation Decisions unless README `security: not-applicable — <reason>` (a non-trust change the user chose to run through this workflow); `spec-check.md`, when present, has no open guess; contract gate passes when `contract: external`; `accepted_by:` set |
| `planned` | `tickets.md` parses; unique `T<n>`; `Blocked by` targets exist, no cycle; every story covered except `Verify: none`; every ticket covers ≥1 story or `Covers: none — <reason>`; tickets that may run in parallel and declare `Files:` share none |
| `building` | README `branch:` = current branch, not the default branch |
| `verified` | `planned` checks still pass; every ticket `Status: done` with a green `task-done` event and every criterion ticked; every `Verify: test` story referenced by ≥1 test file; latest `verify` green (exit 0, code unchanged during run, fingerprint = current; with JUnit: every `Verify: test` story has a passing test, none failed) |
| `reviewed` | `review.md` has `## Spec` and `## Standards`, no open finding, each closed one says `fixed:`/`cleared:`; `## QA` says `Verdict: GO` or `Verdict: CONDITIONAL GO — <conditions>` (unless README `qa: not-applicable — <reason>`); `fingerprint:` = current; evidence chain holds; no uncommitted code. On pass writes the pre-PR record for HEAD |
| `shipped` | `ship.md` `decision: GO`, non-empty `## Rollback` and `## Post-release verification`; CI green (`scripts/pr.py checks`: gh for GitHub, PR statuses for Bitbucket Cloud, when it can tell; else a `CI:` line in `## Checks` saying green/pass); `version:` mentioned in `CHANGELOG.md` when both exist; fingerprint = reviewed one; evidence chain holds; no uncommitted code |
| `implemented` | README `## Traceability` (`aidlc trace --write`); set by `upgrade-service-docs` |

`ship-gate` blocks a merge (`pr.py merge`, `gh pr merge`, a Bitbucket API merge) on a spec-bound branch until `shipped` passes.

- **Code fingerprint:** over all non-ignored files except `docs/**`, `**/docs/specs/**`, `*.md`, `CHANGELOG*`, `LICENSE*`. Code, config or manifest edits invalidate a test run — bump a manifest version **before** `verify`. Prefixes match only at ≥12 hex chars.
- **Evidence chain:** latest `verify` green on F, review stamped on F, working tree = F with no uncommitted code (so HEAD = F).
- **Traceability:** user story n of a spec with `key: RFD` is `RFD-n`. A test references it by the exact upper-case token, or an identifier starting `test` containing `_rfd_1` (any case). Test files: code on a test path or `.feature`. JUnit matches `classname`/`name`; stale or empty reports count as missing.
- **Legacy specs** (a `requirements.md` and no `spec.md`; a `plan.md` and no `tickets.md`) keep the pre-3.3.0 rules: keyed `### RFD-1:` requirements with `Acceptance:`, a required `spec-check.md` and `security.md`, `- [ ] T<n>` tasks with `owner` and `files`. New specs use the files below.

## 2. Spec folder

`docs/specs/<feature>/`: `README.md` (state), `spec.md`, `tickets.md`, `ledger.md`, then `review.md`, `ship.md`; `contracts/` only for `contract: external`; `spec-check.md` only when a blind check ran. Project level: `GLOSSARY.md` (domain terms only, no implementation; reuse an existing `CONTEXT.md`) and `docs/adr/NNNN-<slug>.md` (only for a decision that is hard to reverse, surprising without context and a real trade-off). The main session writes every file; `ledger.md` is `aidlc` only. `aidlc` alone sets README `status`/`updated`/`branch`, sets tickets to `Status: done` (`task-done`) and writes review.md `fingerprint:` (`stamp review`).

Budgets: spec.md = the template, no file paths or code in decisions (except a prototype snippet that pins a decision); tickets = vertical slices; review.md = finding lines; ship.md = required sections.

### README frontmatter (AIDLC fields)

```yaml
---
status: proposed
key: RFD                # 2-6 capital letters, unique per repository; story n is RFD-n
branch: feat/refunds    # written by `aidlc advance building`
security: required      # or: not-applicable — <reason>
contract: external      # or: none (layout §4)
accepted_by: <name> (<date>)   # or: <name> (delegated in request)
updated: 2026-11-19
---
```

### `spec.md`

```markdown
# Refunds

Status: ready-for-agent

## Problem Statement

Support staff cannot return money for a captured payment; customers wait days for a manual bank transfer.

## Solution

A support agent refunds a captured payment in full from the console, once, and the ledger records it.

## User Stories

1. As a support agent, I want to refund a captured payment in full, so that the customer gets the money back.
2. As a support agent, I want a refund above the captured amount rejected, so that we never pay out more than we took.
3. As a support agent, I want a refund visible in the console within 1 minute, so that I can confirm it on the call. (Verify: check — k6 run load/refund-visibility.js)
4. As a customer, I want a refund email, so that I know the money is on its way. (Verify: none — the notifications service sends it)

## Implementation Decisions

- One seam: the refund service; the API handler and the console call it.
- The PSP idempotency key is the refund key (ADR 0003).

### Security

- Assets: payment amount, card token. Threats: replayed refund (T), over-refund (E), card token in logs (I).
- Controls: one refund per payment via the idempotency key; amount ≤ captured; the token is never logged.

## Testing Decisions

- Test only through the refund service seam, with a fake PSP; assert the result, the ledger entry and the PSP calls.
- Good tests: full refund once; a second refund rejected; an amount above capture rejected.
- Prior art: the capture service tests.

## Out of Scope

- Partial refunds.

## Further Notes

- The PSP client already retries; no retry here.
```

Template sections are required except Further Notes. `Status: ready-for-agent` = the spec is complete enough to build without asking; README `status:` is the lifecycle stage. Only top-level numbered items under `## User Stories` are stories (subheadings may group them). A story may end with `(Verify: check — <command>)`, `(Verify: manual — <reason>)` or `(Verify: none — <reason>)` (not delivered in this repository: no ticket, no test); default `test`. Security decisions = a `### Security` subsection or a `**Security**` bullet under Implementation Decisions: assets, threats (STRIDE / OWASP), controls.

### `tickets.md`

```markdown
## T1: Full refund of a captured payment
Blocked by: none
Covers: RFD-1, RFD-2
Status: ready-for-agent
What to build: a support agent refunds a captured payment once; the ledger records it; a second refund and an over-capture amount are rejected.
- [ ] A full refund returns REFUNDED and writes one ledger entry
- [ ] A second refund returns ALREADY_REFUNDED
- [ ] An amount above the capture returns REFUND_EXCEEDS_CAPTURE
Test: npm test -- refunds
Files: src/refunds/**

## T2: Refund visibility under load
Blocked by: T1
Covers: RFD-3
Status: ready-for-agent
What to build: a refund shows in the support console within 1 minute at the load-test profile.
- [ ] p95 refund-to-console delay ≤ 60 s
Test: k6 run load/refund-visibility.js
```

One ticket = one tracer-bullet vertical slice through every layer, demoable alone, sized for one fresh context; prefactoring first; a wide refactor goes expand → migrate batches → contract. `Covers:` takes IDs and ranges (`RFD-3..RFD-6`). The implementer ticks each criterion when a test shows it; `aidlc task-done` runs `Test:` (or `--cmd`) and sets `Status: done`. `Files:` is optional; only tickets that declare it can share a parallel batch. `Owner:` optional (default `main`).

### `spec-check.md` (optional)

```markdown
- [ ] G1: Is a partial refund allowed, and can several partial refunds exceed the capture?
- [x] G2: Which currency does the refund use? — resolved: story 1 now says "in the capture currency"
- [x] G3: Retry policy for the PSP call — accepted risk: PSP client already retries, see Further Notes
```

One blind pass by a fresh agent that read only the spec, when the spec was not grilled with the user. Close with `resolved:` (where the spec now answers it) or `accepted risk:`. Nothing found → `Checked: no guesses.`

### `ledger.md`

```markdown
- 2026-11-19T10:02:11Z advance accepted→planned
- 2026-11-19T10:40:03Z task-done T1 exit=0 fingerprint=3f9c0b7d21e4… cmd="npm test -- refunds/model"
- 2026-11-19T10:41:20Z ruling T2: Use the PSP idempotency key as the refund key — why: the PSP rejects duplicates already — if wrong: double refunds on PSP outage; reverse via ledger replay
- 2026-11-19T11:15:47Z verify exit=0 fingerprint=8a01c6e95f3b… cmd="npm test" junit=42 passed, 0 failed req-pass=RFD-1
- 2026-11-19T11:30:00Z stamp review fingerprint=8a01c6e95f3b…
```

`junit=missing`/`unreadable` or a `before=` field (run changed code) is not green. A **ruling** = a decision taken instead of asking (what, why, cost if wrong); list them at the end of the run.

### `review.md`

```markdown
---
fingerprint: 8a01c6e95f3b…   # written by `aidlc stamp review` (in full)
reviewers: spec=tea-sdlc:code-reviewer standards=tea-sdlc:code-reviewer
---
## Spec
- [x] S1 (must): RFD-2 is not implemented — fixed: src/refunds/api.ts:41, test RFD-2 "rejects over-capture"
## Standards
- [x] Q1 (should): repository leaks the ORM entity — fixed: src/refunds/repo.ts:12
- [x] Q2 (nit): rename `amt` — cleared: matches the PSP field name (GLOSSARY.md)
## QA
Verdict: GO
```

Spec axis: vs spec.md stories and decisions, ADRs, contracts (missing, scope creep, wrong behaviour). Standards: quality, the spec's security decisions, conventions. Never merged or re-ranked. Severities `must` | `should` | `nit`. A finding-ID bullet that is not a checkbox fails the gate. `## QA` = tea-sdlc:qa-subagent verdict.

### `ship.md`

```markdown
---
decision: GO            # GO | NO-GO
version: 2.4.0          # or: n/a — <reason>
---
## Checks
- CI: green (gh pr checks 42)
- Migration: expand step only; contract step ships in 2.5.0
## Rollback
Revert the merge commit; the migration is additive, no data step needed.
## Post-release verification
Smoke: `curl -fsS $BASE/health`; watch refund error rate for 30 min (alert REFUND-5XX).
```

## 3. CLI

`python3 scripts/aidlc.py <command>` (plugin-relative); all accept `--json` and `--repo DIR`. Exit `0` pass, `1` gate findings, `2` usage/input error.

| Command | Does |
|---|---|
| `status [--fast]` | Every spec: stage, next stage, gate result, first blockers (`--fast`: no `gh`, no contract gate) |
| `check SPEC [--to STAGE]` | Run a gate (default: next stage) |
| `advance SPEC STAGE [--back --reason TEXT]` | Gate, then update README + ledger (+ pre-PR record for `reviewed`) |
| `next SPEC` | Ready tickets in conflict-free parallel batches |
| `task-done SPEC T<n> [--cmd CMD]` | All criteria ticked → run CMD (default the ticket's `Test:`); exit 0 → `Status: done` + log, else change nothing |
| `verify SPEC --cmd CMD [--junit GLOB] [--timeout S]` | Run tests; log exit, fingerprint, JUnit totals, `req-pass`/`req-fail` |
| `ruling SPEC --decision TEXT --why TEXT --if-wrong TEXT [--task T<n>]` | Append a ruling |
| `stamp SPEC review` | Write the current fingerprint into review.md and log it |
| `trace SPEC [--write]` | Story → tickets → tests → result; `--write` into README `## Traceability` |
| `init SPEC --key KEY` | Create folder with README, spec.md, tickets.md, ledger.md skeletons |

`SPEC` = folder path, or slug (`refunds` finds `<any>/docs/specs/refunds`; `init` with a slug creates `<repo>/docs/specs/<slug>`; pass a path for service/system scope).
