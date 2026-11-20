# AIDLC: the spec → plan → build → test → review → ship lifecycle

Owner of the stage machine, the artifact formats and the gates for **full-workflow** changes (any trust boundary, `rules/workflow-routing.md`). Fast-path changes keep their lighter path (TDD gate, verification gate, single pre-PR pass) and need no spec folder.

`scripts/aidlc.py` implements everything below; when this file and the script disagree, the script is the truth and this file is the bug. Every gate is deterministic (no model call). It checks that the evidence exists and is current. It cannot judge whether a requirement is good; the blind spec check and the two-axis review do that.

## 1. Stages

```
proposed ─▶ accepted ─▶ planned ─▶ building ─▶ verified ─▶ reviewed ─▶ shipped ─▶ implemented
   spec        gate        plan       build        test        review      ship       promote
```

`status:` in the spec `README.md` frontmatter holds the stage. Terminal side states: `partially-implemented` (promotion with pending requirements), `superseded`, `abandoned`. A spec is **active** in every stage from `proposed` to `shipped`.

Only `aidlc advance` moves a spec forward, and only when the gate of the target stage passes. It records the transition in the ledger and sets `updated:`. Moving backwards (for example `reviewed → building` after a late finding) is allowed with `--back --reason`, and is recorded; going back to `proposed` clears `accepted_by:`, so a changed spec needs a fresh approval. Side states: `advance SPEC abandoned --reason …` from any active stage, `advance SPEC superseded` when README `superseded_by:` is set, `advance SPEC partially-implemented` from `shipped` with the `implemented` gate.

| Target | The gate requires |
|---|---|
| `accepted` | README `key:` set and unique across the repository's specs; `requirements.md` defines ≥1 requirement, every ID is `<KEY>-<n>`, unique, with ≥1 acceptance criterion and a valid `Verify:`; `spec-check.md` records a check (≥1 guess line, or a `Checked:` line when the checker found nothing) and has no open guess; `security.md` exists unless README says `security: not-applicable — <reason>` (a non-trust change the user chose to run through this workflow; the reason is required); the contract gate passes when `contract: external`; `accepted_by:` set |
| `planned` | `plan.md` parses; task IDs `T<n>` unique; every `depends` target exists; no cycle; every requirement is covered by ≥1 task; every task covers ≥1 requirement or says `covers: none — <reason>`; every task has `owner` and `files`; two tasks that may run at the same time (no dependency path between them) share no file |
| `building` | README `branch:` is recorded (current branch, which must not be the default branch) |
| `verified` | the `planned` checks still pass (tasks added later are validated too); every task is `[x]` in `plan.md` **and** has a green `task-done` ledger event; every requirement with `Verify: test` is referenced by ≥1 test file; the latest `verify` is **green**: it exited 0, the code did not change during the run, its fingerprint equals the current one, and, when it recorded JUnit results, every `Verify: test` requirement has a passing test there and none failed (without JUnit results the gate passes with a warning that traceability is static) |
| `reviewed` | `review.md` has both axes (`## Spec`, `## Standards`), no open finding (a finding bullet that is not a checkbox counts as open), every closed finding says `fixed:` or `cleared:`; its `## QA` section says `Verdict: GO` or `Verdict: CONDITIONAL GO — <conditions>`, unless README says `qa: not-applicable — <reason>`; its `fingerprint:` equals the current code fingerprint; the **evidence chain** holds (the latest `verify` is green and current, and the review stamp is that same verified code); **no uncommitted code** (the record and the PR are for commits). On pass, the pre-PR record for `HEAD` is written; `hooks/pr-review-gate.py` also accepts any branch-bound spec that passes this gate, so committing the spec files afterwards does not block `gh pr create` |
| `shipped` | stage `reviewed` or later; `ship.md` says `decision: GO`, has non-empty `## Rollback` and `## Post-release verification`; CI is green (`gh pr checks -- <branch>` when `gh` and a PR exist, else a `CI:` line in `## Checks` that says green or pass); when `version:` is set and the repository has a `CHANGELOG.md`, that file mentions the version; the code fingerprint still equals the reviewed one; the evidence chain holds; no uncommitted code |
| `implemented` | stage `shipped` or later; README has a `## Traceability` table (`aidlc trace --write`); set by `upgrade-service-docs` after the living docs are updated |

The `ship-gate` hook blocks `gh pr merge` for a branch bound to an active spec until that spec passes the `shipped` gate.

`check SPEC --to STAGE` evaluates a gate's evidence whatever the current stage, so a gate already passed can be re-checked; only `advance` enforces stage order. `--back` never unticks tasks; re-entering `verified` needs a fresh `verify` run.

Specs without `key:` (written before AIDLC) are listed by `status` as legacy and are not gated; moving one to `accepted` or later needs a key.

**Code fingerprint.** SHA-256 over the sorted list of (path, git blob ID) of every tracked or untracked, not ignored file **except** `docs/**`, `**/docs/specs/**`, `*.md`, `CHANGELOG*` and `LICENSE*`. Unmodified tracked files use the blob ID already in the index (no file is read), so it stays fast on large repositories; modified and untracked files are hashed the way git would store them. The same function over a commit (`git ls-tree`) gives the same value for the same code, so a clean working tree's fingerprint equals `HEAD`'s, and "is this commit the verified code?" is one comparison. Writing `review.md`, the ledger, the README or the changelog does not invalidate a test run; changing code, configuration or a manifest does (bump a manifest version **before** `verify`). A recorded fingerprint may be shortened in prose, but only a prefix of ≥12 hex characters ever matches.

**Evidence chain.** `reviewed` and `shipped` require one chain from tests to commit: the latest `verify` is green on fingerprint F, the review was stamped on F, the working tree is F and has no uncommitted code, so `HEAD` is F. Hooks can ask the same for any commit (`evidence_findings(spec, rev)`).

**Traceability.** A file references `RFD-1` when it contains the exact upper-case token `RFD-1` (not `RFD-10`, `XRFD-1` or `rfd-1` in prose), or an identifier that starts with `test` and contains `_rfd_1` in any case (`test_rfd_1_rejects_over_capture`, `test_RFD_1`). Test files are files with a code extension on a test path (the `TEST_PATH` rule of `hooks/tdd-gate.py`) or `.feature` files. JUnit test cases are matched the same way on `classname` and `name`; `verify --junit` ignores report files older than the run and treats reports without any test case as missing.

## 2. Spec folder

`docs/specs/<feature>/` per `references/documentation-layout.md` §4, plus the AIDLC files:

| File | Writer | Stage |
|---|---|---|
| `README.md` | main session; `aidlc advance` edits `status`, `updated`, `branch` | all |
| `requirements.md` | main session | proposed |
| `spec-check.md` | blind spec checker (skill `spec-check`), then the main session closes each guess | proposed |
| `security.md` | tea-sdlc:security-engineer-subagent | proposed |
| `design.md`, `contracts/` | main session | proposed |
| `plan.md` | main session (`writing-plans`); `[x]` set only by `aidlc task-done` | planned |
| `ledger.md` | `aidlc` only (append-only) | from accepted |
| `review.md` | main session, from the reviewers' findings; `aidlc stamp review` writes its fingerprint | reviewed |
| `ship.md` | main session (skill `shipping`) | shipped |

### README frontmatter (AIDLC fields added to layout §4)

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

Each requirement is a heading whose first token is its ID. Acceptance criteria are the bullets under an `Acceptance:` line. `Verify:` defaults to `test`.

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

`Verify:` is `test` (a test file must reference the ID), `check — <command or procedure>` (a non-unit verification, reported in the trace), or `manual — <reason>` (reported in the trace as manual). Business rules, terms and story text may follow in any form; only `ID` headings define requirements.

### `spec-check.md`

Written by a fresh agent that read only the spec files and could not ask the author. One line per thing it would have to guess:

```markdown
- [ ] G1: Is a partial refund allowed, and can several partial refunds exceed nothing but the capture?
- [x] G2: Which currency does the refund use? — resolved: RFD-1 acceptance now says "in the capture currency"
- [x] G3: Retry policy for the PSP call — accepted risk: PSP client already retries, see design.md §4
```

Open = `- [ ]`. A closed guess says `resolved:` (where the spec now answers it) or `accepted risk:` (why it may stay open). A second run appends further guesses with continuing numbers. When the checker finds nothing it writes `Checked: no guesses.`; the empty skeleton from `init` does not pass the gate.

### `plan.md`

One checkbox line per task, its fields as indented bullets. Any prose may surround the tasks.

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

`owner` is an agent from `rules/agents.md` or `main`. `test` (optional) is the task's exit test command; `aidlc task-done` runs it when no `--cmd` is given. `files` lists the paths the task may change (`(new)` marks new files); globs such as `src/refunds/**` are allowed. `aidlc next` returns the **frontier**: open tasks whose dependencies are all done, grouped so that tasks in one batch share no file. Dispatch a batch in parallel.

### `ledger.md`

Append-only, written by `aidlc`. One line per event:

```markdown
- 2026-11-19T10:02:11Z advance accepted→planned
- 2026-11-19T10:40:03Z task-done T1 exit=0 fingerprint=3f9c0b7d21e4… cmd="npm test -- refunds/model"
- 2026-11-19T10:41:20Z ruling T2: Use the PSP idempotency key as the refund key — why: the PSP rejects duplicates already — if wrong: double refunds on PSP outage; reverse via ledger replay
- 2026-11-19T11:15:47Z verify exit=0 fingerprint=8a01c6e95f3b… cmd="npm test" junit=42 passed, 0 failed req-pass=RFD-1
- 2026-11-19T11:30:00Z stamp review fingerprint=8a01c6e95f3b…
```

`aidlc` writes fingerprints in full (shortened here); a prefix shorter than 12 hex characters never matches. `cmd` is JSON-quoted. A `verify` with `--junit` adds `req-pass=` / `req-fail=` (requirement IDs whose referencing tests passed or failed); `junit=missing` (no report written by this run, or no test case) or `junit=unreadable` fails the `verified` gate. When the test command changed code during the run, the event also carries `before=<fingerprint>` and is not green. A backward move is logged as `advance verified→building back reason="…"`, a side state as `advance building→abandoned reason="…"`. An unknown event is a warning; a malformed line is a finding with its line number.

A **ruling** is a decision the session made instead of stopping to ask: what, why, and the cost if it is wrong. Rulings are listed again at the end of the run and kept in the ledger; they are the decision record a reviewer reads.

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

The **Spec** axis compares the change with `requirements.md`, `design.md` and `contracts/`: missing requirements, scope creep, wrong behavior. The **Standards** axis reviews code quality, security rules and conventions. They are separate reviews and their findings are never merged or re-ranked. Severities: `must`, `should`, `nit`. Finding IDs are any capital letters plus a number; `fixed:` or `cleared:` may follow a location such as `at src/x.ts:4 (confidence: high)`. Every finding is a checkbox and stays open until `fixed:` or `cleared:`; a bullet in `## Spec` or `## Standards` that starts with a finding ID but is not a checkbox (`- S1 (must): …`, `- **Q1 (must)**: …`) fails the gate, because nothing tracks it. Other prose bullets are allowed. The **QA** section holds the tea-sdlc:qa-subagent verdict.

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

`python3 scripts/aidlc.py <command>` (plugin-relative; skills and agents prefix it with the plugin-root variable). Every command accepts `--json` (one object; `exit` is always the CLI exit code, `command_exit` the exit code of the command that `task-done` or `verify` ran) and `--repo DIR` (any folder of the repository; normalized to its git top level). Exit codes: `0` pass, `1` gate findings, `2` usage or input error. Commands that write `plan.md`, `README.md` or `ledger.md` hold an exclusive lock on the spec folder, so parallel `task-done` runs never lose a tick; `task-done` re-reads `plan.md` after its command and ticks the task by ID. Files keep their line endings (CRLF stays CRLF).

| Command | Does |
|---|---|
| `status [--fast]` | Every spec: stage, next stage, whether its gate passes, the first blockers. `--fast` (the session-start snapshot) runs no `gh` and no contract gate |
| `check SPEC [--to STAGE]` | Run the gate of STAGE (default: the next stage) and list findings |
| `advance SPEC STAGE [--back --reason TEXT]` | Run the gate; on pass, update README and the ledger (and, for `reviewed`, the pre-PR record) |
| `next SPEC` | The frontier: ready tasks in conflict-free parallel batches |
| `task-done SPEC TASK [--cmd CMD]` | Run CMD (default: the task's `test:` field); on exit 0 tick the task in `plan.md` and log `task-done`; otherwise print the failure and change nothing |
| `verify SPEC --cmd CMD [--junit GLOB]` | Run the test command, log exit code, fingerprint, JUnit totals and the requirement IDs whose tests passed or failed |
| `ruling SPEC --decision TEXT --why TEXT --if-wrong TEXT [--task T<n>]` | Append a ruling |
| `stamp SPEC review` | Write the current code fingerprint into `review.md` and log it |
| `trace SPEC [--write]` | Requirement → tasks → tests → result matrix; `--write` puts it in README `## Traceability` |
| `init SPEC --key KEY` | Create the folder with README, requirements, spec-check, plan and ledger skeletons |

`SPEC` is the spec folder path (used as given) or its slug (`refunds` finds `<any folder>/docs/specs/refunds`, at any depth, among tracked and untracked non-ignored files; `init` with a slug creates `<repo>/docs/specs/<slug>`; pass a path for a service- or system-scoped spec). Key uniqueness, `status` and the hooks see the same set of specs.

Hooks use the Python API documented at the top of `scripts/aidlc.py` (`check`, `status(repo, fast)`, `specs_for_branch` — any status, the hook decides — `fingerprint(repo, rev)`, `code_dirty`, `evidence_findings(spec, rev)`).
