# AIDLC lifecycle (full workflow only)

Read only the section for the current stage. `scripts/aidlc.py` wins over this file. Gates check that evidence exists and is current, not that it is good.

## 1. Stages

```
proposed ─▶ accepted ─▶ planned ─▶ building ─▶ verified ─▶ reviewed ─▶ shipped ─▶ implemented
```

README `status:` holds the stage; active = `proposed`…`shipped`. Only `aidlc advance` moves it, when the target gate passes. `--back --reason` moves back; back to `proposed` clears `accepted_by:`. Side states: `abandoned --reason` (from any active stage), `superseded` (needs README `superseded_by:`), `partially-implemented` (from `shipped`, `implemented` gate). `check SPEC --to STAGE` re-checks any gate; `--back` never unticks tasks; re-entering `verified` needs a fresh `verify`. Specs without `key:` are legacy and ungated until given a key.

| Target | Gate |
|---|---|
| `accepted` | README `key:` unique in repo; ≥1 requirement, IDs `<KEY>-<n>` unique, each with ≥1 acceptance bullet and valid `Verify:`; `spec-check.md` has ≥1 guess line or `Checked:` line and no open guess; `security.md` exists unless README `security: not-applicable — <reason>` (a non-trust change the user chose to run through this workflow; reason required); contract gate passes when `contract: external`; `accepted_by:` set |
| `planned` | `plan.md` parses; unique `T<n>`; `depends` targets exist, no cycle; every requirement covered; every task covers ≥1 requirement or `covers: none — <reason>`; every task has `owner` and `files`; tasks with no dependency path between them share no file |
| `building` | README `branch:` = current branch, not the default branch |
| `verified` | `planned` checks still pass; every task `[x]` with a green `task-done` event; every `Verify: test` requirement referenced by ≥1 test file; latest `verify` green (exit 0, code unchanged during run, fingerprint = current; with JUnit: every `Verify: test` requirement has a passing test, none failed) |
| `reviewed` | `review.md` has `## Spec` and `## Standards`, no open finding, each closed one says `fixed:`/`cleared:`; `## QA` says `Verdict: GO` or `Verdict: CONDITIONAL GO — <conditions>` (unless README `qa: not-applicable — <reason>`); `fingerprint:` = current; evidence chain holds; no uncommitted code. On pass writes the pre-PR record for HEAD |
| `shipped` | `ship.md` `decision: GO`, non-empty `## Rollback` and `## Post-release verification`; CI green (`gh pr checks` if available, else a `CI:` line in `## Checks` saying green/pass); `version:` mentioned in `CHANGELOG.md` when both exist; fingerprint = reviewed one; evidence chain holds; no uncommitted code |
| `implemented` | README `## Traceability` (`aidlc trace --write`); set by `upgrade-service-docs` |

`ship-gate` blocks `gh pr merge` on a spec-bound branch until `shipped` passes.

- **Code fingerprint:** over all non-ignored files except `docs/**`, `**/docs/specs/**`, `*.md`, `CHANGELOG*`, `LICENSE*`. Code, config or manifest edits invalidate a test run — bump a manifest version **before** `verify`. Prefixes match only at ≥12 hex chars.
- **Evidence chain:** latest `verify` green on F, review stamped on F, working tree = F with no uncommitted code (so HEAD = F).
- **Traceability:** a test references `RFD-1` by the exact upper-case token, or an identifier starting `test` containing `_rfd_1` (any case). Test files: code on a test path or `.feature`. JUnit matches `classname`/`name`; stale or empty reports count as missing.

## 2. Spec folder

`docs/specs/<feature>/`. The main session writes every file except `security.md` (tea-sdlc:security-engineer-subagent), `spec-check.md` (blind checker, skill `spec-check`) and `ledger.md` (`aidlc` only). `aidlc` alone sets README `status`/`updated`/`branch`, ticks `plan.md` (`task-done`) and writes review.md `fingerprint:` (`stamp review`). `design.md`/`contracts/` only when a contract or the architecture changes.

Budgets: requirements = keyed requirements only, no narrative; design.md ≤ ~120 lines; security.md = threat table + numbered rules; review.md = finding lines; ship.md = required sections.

### README frontmatter (AIDLC fields)

```yaml
---
status: proposed
key: RFD                # 2-6 capital letters, unique per repository; prefixes every requirement ID
branch: feat/refunds    # written by `aidlc advance building`
security: required      # or: not-applicable — <reason>
contract: external      # see layout §4
accepted_by: <name> (<date>)   # or: <name> (delegated in request)
updated: 2026-11-19
---
```

### `requirements.md`

```markdown
### RFD-1: Refund a captured payment
Priority: must
Acceptance:
- Given a captured payment, when a refund for the full amount is requested, then the payment is refunded and the ledger records it.
- Given a refund request above the captured amount, then it is rejected with `REFUND_EXCEEDS_CAPTURE`.
Verify: test

### RFD-2: Refunds are visible to support staff within 1 minute
Acceptance:
- p95 delay between refund and support-console visibility ≤ 60 s under the load test profile.
Verify: check — k6 run load/refund-visibility.js
```

Only `### <ID>:` headings define requirements. `Verify:` (default `test`) = `test` (a test references the ID) | `check — <command>` | `manual — <reason>`.

### `spec-check.md`

```markdown
- [ ] G1: Is a partial refund allowed, and can several partial refunds exceed nothing but the capture?
- [x] G2: Which currency does the refund use? — resolved: RFD-1 acceptance now says "in the capture currency"
- [x] G3: Retry policy for the PSP call — accepted risk: PSP client already retries, see design.md §4
```

One blind pass by a fresh agent that read only the spec. Close with `resolved:` (where the spec now answers it) or `accepted risk:`. Nothing found → `Checked: no guesses.`

### `plan.md`

```markdown
- [ ] T1: Refund domain model and repository
  - covers: RFD-1
  - depends: none
  - owner: tea-sdlc:backend-engineer-subagent
  - files: src/refunds/model.ts (new), src/refunds/repo.ts (new)
  - exit: refund model tests green
  - test: npm test -- refunds/model
- [ ] T2: POST /payments/{id}/refunds endpoint
  - covers: RFD-1
  - depends: T1
  - owner: tea-sdlc:backend-engineer-subagent
  - files: src/refunds/api.ts (new), src/routes.ts
  - exit: endpoint tests green; contract gate passes
- [ ] T3: Load test for support visibility
  - covers: RFD-2
  - depends: T2
  - owner: tea-sdlc:platform-engineer-subagent
  - files: load/refund-visibility.js (new)
  - exit: k6 threshold passes
```

`owner`: a `tea-sdlc:` agent or `main`. `files`: the only paths the task may change (globs allowed). `test`: optional, run by `task-done` without `--cmd`. Dispatch each `aidlc next` batch in parallel.

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
- [x] S1 (must): RFD-1 second criterion is not implemented — fixed: src/refunds/api.ts:41, test RFD-1 "rejects over-capture"
## Standards
- [x] Q1 (should): repository leaks the ORM entity — fixed: src/refunds/repo.ts:12
- [x] Q2 (nit): rename `amt` — cleared: matches the PSP field name, see design.md §2
## QA
Verdict: GO
```

Spec axis: vs requirements, design, contracts (missing, scope creep, wrong behaviour). Standards: quality, security rules, conventions. Never merged or re-ranked. Severities `must` | `should` | `nit`. A finding-ID bullet that is not a checkbox fails the gate. `## QA` = tea-sdlc:qa-subagent verdict.

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
| `next SPEC` | Ready tasks in conflict-free parallel batches |
| `task-done SPEC TASK [--cmd CMD]` | Run CMD (default the task's `test:`); exit 0 → tick + log, else change nothing |
| `verify SPEC --cmd CMD [--junit GLOB] [--timeout S]` | Run tests; log exit, fingerprint, JUnit totals, `req-pass`/`req-fail` |
| `ruling SPEC --decision TEXT --why TEXT --if-wrong TEXT [--task T<n>]` | Append a ruling |
| `stamp SPEC review` | Write the current fingerprint into review.md and log it |
| `trace SPEC [--write]` | Requirement → tasks → tests → result; `--write` into README `## Traceability` |
| `init SPEC --key KEY` | Create folder with skeletons |

`SPEC` = folder path, or slug (`refunds` finds `<any>/docs/specs/refunds`; `init` with a slug creates `<repo>/docs/specs/<slug>`; pass a path for service/system scope).
