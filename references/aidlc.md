# AIDLC lifecycle (full workflow only)

Read only the section for the current stage. `scripts/aidlc.py` wins over this file. Gates check that evidence exists and is current, not that it is good; what they can and cannot stop is in "Trust model" at the end.

## 0. Open questions (every stage)

A question about business rules, domain terms, existing behaviour, limits, owners or product intent. Take the first step that settles it:

1. **Files:** the spec, `GLOSSARY.md`, ADRs, contracts, the code and its tests, git history.
2. **Atlassian Rovo MCP** (the Atlassian server, whatever its prefix, e.g. `mcp__plugin_operations_atlassian__*`): `search` (Rovo search over Confluence and Jira) with the glossary term, the feature name and any Jira key, then `fetch` / `getConfluencePage` / `getJiraIssue` on the best hits; `searchConfluenceUsingCql` / `searchJiraIssuesUsingJql` to narrow. Record what settled it (page title + URL, or issue key): in `spec.md` Further Notes under `Sources:`, or in the ruling. Sources disagree → the newer and more specific one wins; record the conflict.
3. **Recorded assumption:** still open → take the most reasonable answer and continue; at the spec stage write it into spec.md (story or decision, listed for the approval), later `aidlc ruling … --why "<no source; reasoning>"`.
4. **Ask the user** only after step 2 ran for that question, when no safe default exists and the answer is one of: accepting a security or compliance risk, money movement or regulatory behaviour with no source, an irreversible or production action, sources that contradict each other on observable behaviour. One batched question per stage, each with your recommended answer. A missing contract, endpoint or integration detail with a configurable default (a connector with the path in config, confirmed before release) is step 3, not 4.

**Delegated input** (`do not ask`, `not available for questions`, `end to end`, or a spec with `Status: ready-for-agent`): there is no step 4. Take the recommended option, record it (spec.md `Assumptions:`, or `aidlc ruling`) with the decision starting `RISK-ACCEPTANCE NEEDED:` when it accepts a security or compliance risk, and list those first in the final report. The only stops are the ones `/aegisops-harness:aidlc` names (merge and deploy need words for it).

Rovo not connected or failing → say so once in the stage report and go on with 3–4. Subagents have no Rovo: they return NEEDS_CONTEXT with a recommended answer, the main session answers through this order. Never ask what steps 1–2 answer. `hooks/question-gate.py` enforces this: inside an AegisOps-Harness command it blocks every question in delegated input, and otherwise the first question asked before any Rovo call.

## 1. Stages

```
proposed ─▶ accepted ─▶ planned ─▶ building ─▶ verified ─▶ reviewed ─▶ shipped ─▶ implemented
```

README `status:` holds the stage; active = `proposed`…`shipped`. Only `aidlc advance` moves it, when the target gate passes. Every gate from `planned` to `shipped` includes the gates before it (`building` aside: it is about the checkout), so a stage set by hand or evidence that went stale grants nothing up to `shipped`; `implemented` records a merge and checks that `shipped` was reached and the traceability table exists. `--back --reason` moves back; back to `proposed` clears `accepted_by:` and voids the approval. Side states: `abandoned --reason` (from any active stage), `superseded` (needs README `superseded_by:`), `partially-implemented` (from `shipped`, `implemented` gate). `check SPEC --to STAGE` re-checks any gate; `--back` never reopens tickets; re-entering `verified` needs a fresh `verify`. Specs without `key:` are legacy and ungated until given a key.

| Target | Gate |
|---|---|
| `accepted` | README `key:` unique in repo; `spec.md` has every template section (Problem Statement, Solution, User Stories, Implementation Decisions, Testing Decisions, Out of Scope) filled, ≥1 numbered user story, numbers unique, any `(Verify: …)` tag valid; security decisions in Implementation Decisions unless README `security: not-applicable — <reason>` (a non-trust change the user chose to run through this workflow); `spec-check.md`, when present, has no open guess; contract gate passes when `contract: external`; an approval of this spec text (the latest `approve` event carries the SHA-256 of spec.md: an edit after it needs a new approval) and `accepted_by:` set by it |
| `planned` | `accepted` still passes; `tickets.md` parses; unique `T<n>`; `Blocked by` targets exist, no cycle; every story covered except `Verify: none`; every ticket covers ≥1 story or `Covers: none — <reason>`; tickets that may run in parallel and declare `Files:` share none |
| `building` | README `branch:` = current branch, not the default branch |
| `verified` | `planned` still passes; every ticket `Status: done` with a green `task-done` event and every criterion ticked; every `Verify: test` story referenced by ≥1 test file; the repository config resolves (§4); latest `verify` ran the pinned command and is green (exit 0, code unchanged during run, fingerprint = current); with a JUnit glob: a readable report in which every `Verify: test` story has a passing test that carries its ID, none failed; latest `revert-check` is for this code and red, or skipped with its reason |
| `reviewed` | `verified` still passes; `review.md` has `## Spec` and `## Standards`, no open finding, each closed one says `fixed:`/`cleared:`; `## QA` says `Verdict: GO` or `Verdict: CONDITIONAL GO — <conditions>` (unless README `qa: not-applicable — <reason>`); stored reviewer returns (`returns/`) cover both axes and QA, every returned finding is in review.md with the severity it was given, and the QA verdict is the latest QA return's (unless the config waives returns); `fingerprint:` = current; evidence chain holds; no uncommitted code. On pass writes the pre-PR record for HEAD |
| `shipped` | `reviewed` still passes; `ship.md` `decision: GO`, non-empty `## Rollback` and `## Post-release verification`; CI green according to the provider (`scripts/pr.py checks`: gh for GitHub, PR statuses for Bitbucket Cloud). No result from it (no gh, not signed in, no PR, no CI) fails the gate; only when the config waives CI is the `CI:` line in `## Checks` taken at its word; `version:` mentioned in `CHANGELOG.md` when both exist |
| `implemented` | README `## Traceability` (`aidlc trace --write`); set by `upgrade-service-docs` |

`ship-gate` blocks a merge (`pr.py merge`, `gh pr merge`, the API form, a GitHub MCP merge) on a spec-bound branch until `shipped` passes.

- **Code fingerprint:** over all non-ignored files except `docs/**`, `**/docs/specs/**`, `*.md`, `CHANGELOG*`, `LICENSE*`. Code, config or manifest edits invalidate a test run — bump a manifest version **before** `verify`. Prefixes match only at ≥12 hex chars.
- **Evidence chain:** latest `verify` green on F, review stamped on F, working tree = F with no uncommitted code (so HEAD = F).
- **Traceability:** user story n of a spec with `key: RFD` is `RFD-n`. A test carries it as the exact upper-case token, or in an identifier starting `test` containing `_rfd_1` (any case). With a JUnit glob in the config the proof is the report: a test case whose `classname`/`name` carries the ID ran and passed in the pinned run; stale or empty reports count as missing. Only behind the JUnit waiver does the weaker check stand alone (the ID appears in a test file), with a warning.
- **Revert check:** `aidlc verify` first puts the production source changed since the merge base with the default branch back to its base version, runs the pinned command, and restores HEAD. The run must fail (a timeout does not count); with JUnit at least one story of the spec must have a test that stopped passing. Stories whose tests still pass are listed as a warning. Needs the code committed. Skipped, with the reason logged, when no production source changed. `verify.revert_check: false` turns it off.
- **Legacy specs** (a `requirements.md` and no `spec.md`; a `plan.md` and no `tickets.md`) keep the pre-3.3.0 rules: keyed `### RFD-1:` requirements with `Acceptance:`, a required `spec-check.md` and `security.md`, `- [ ] T<n>` tasks with `owner` and `files`. New specs use the files below.

## 2. Spec folder

`docs/specs/<feature>/`: `README.md` (state), `spec.md`, `tickets.md`, `ledger.md`, then `returns/` (what each reviewer returned), `review.md`, `ship.md`; `contracts/` only for `contract: external`; `spec-check.md` only when a blind check ran. Project level: `GLOSSARY.md` (domain terms only, no implementation; reuse an existing `CONTEXT.md`) and `docs/adr/NNNN-<slug>.md` (only for a decision that is hard to reverse, surprising without context and a real trade-off). The main session writes every file except `ledger.md` and `returns/`, which are `aidlc` only (`hooks/evidence-guard.py` refuses an edit or a shell write). `aidlc` alone sets README `status`/`updated`/`branch`/`accepted_by`, sets tickets to `Status: done` (`task-done`) and writes review.md `fingerprint:` (`stamp review`).

Budgets: spec.md = the template, no file paths or code in decisions (except a prototype snippet that pins a decision); tickets = vertical slices; review.md = finding lines; ship.md = required sections.

### README frontmatter (AIDLC fields)

```yaml
---
schema: 1               # format version, written by `aidlc init` (Compatibility)
status: proposed
key: RFD                # 2-6 capital letters, unique per repository; story n is RFD-n
branch: feat/refunds    # written by `aidlc advance building`
security: required      # or: not-applicable — <reason>
contract: external      # or: none (layout §4)
accepted_by: <name> (<date>)   # written by `aidlc approve`; or: <name> (delegated in request)
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
- 2026-11-19T09:58:40Z approve spec=5d1f0c7a9b3e4f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8 by="Tea" how=approved
- 2026-11-19T10:02:11Z advance accepted→planned
- 2026-11-19T10:40:03Z task-done T1 exit=0 fingerprint=3f9c0b7d21e4… cmd="npm test -- refunds/model"
- 2026-11-19T10:41:20Z ruling T2: Use the PSP idempotency key as the refund key — why: the PSP rejects duplicates already — if wrong: double refunds on PSP outage; reverse via ledger replay
- 2026-11-19T11:14:02Z revert-check exit=1 fingerprint=8a01c6e95f3b… base=4c2e9a117d03 files=3 junit=39 passed, 3 failed
- 2026-11-19T11:15:47Z verify exit=0 fingerprint=8a01c6e95f3b… cmd="npm run test:ci" pinned=base junit=42 passed, 0 failed req-pass=RFD-1
- 2026-11-19T11:30:00Z stamp review fingerprint=8a01c6e95f3b…
```

`approve`: `how=approved` (a person approved this text) or `how=delegated` (the request handed the decisions over: nobody read the spec). `pinned=base` = the command came from the default branch's config, `pinned=onboarding` = from this branch's own. `junit=missing`/`unreadable` or a `before=` field (run changed code) is not green. A **ruling** = a decision taken instead of asking (what, why, cost if wrong); list them at the end of the run.

### `review.md`

```markdown
---
fingerprint: 8a01c6e95f3b…   # written by `aidlc stamp review` (in full)
reviewers: spec=aegisops-harness:code-reviewer standards=aegisops-harness:code-reviewer
---
## Spec
- [x] S1 (must): RFD-2 is not implemented — fixed: src/refunds/api.ts:41, test RFD-2 "rejects over-capture"
## Standards
- [x] Q1 (should): repository leaks the ORM entity — fixed: src/refunds/repo.ts:12
- [x] Q2 (nit): rename `amt` — cleared: matches the PSP field name (GLOSSARY.md)
## QA
Verdict: GO
```

Spec axis: vs spec.md stories and decisions, ADRs, contracts (missing, scope creep, wrong behaviour). Standards: quality, the spec's security decisions, conventions. Never merged or re-ranked. Severities `must` | `should` | `nit`. A finding-ID bullet that is not a checkbox fails the gate. `## QA` = aegisops-harness:qa-subagent verdict.

**`returns/`**: when a review-stage reviewer returns, `hooks/record-returns.py` stores its text verbatim as one file (agent, axis, code fingerprint, SHA-256 of the text). The gate compares review.md with these files: copy each finding line as returned and close it with `fixed:` or `cleared:`; never leave one out or change its severity. A NO-GO from QA is lifted only by a new QA return. Dispatch reviewers in the foreground (a background dispatch returns nothing to the hook). A review done elsewhere: a person stores it with `aidlc attest`.

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
| `verify SPEC [--timeout S]` | Revert check, then the pinned command (§4); log exit, fingerprint, JUnit totals, `req-pass`/`req-fail`. No command to choose: another `--cmd` is a usage error |
| `approve SPEC [--by NAME] [--delegated]` | Log the approval of spec.md as it is (its SHA-256) and write `accepted_by`. A person's act: `/aegisops-harness:approve <slug>` or their own terminal; `--delegated` when the request handed the decisions over |
| `attest SPEC --agent NAME --axis spec\|standards\|both\|qa [--file F]` | Store a reviewer's return in `returns/` (the hook does it when a reviewer agent returns; a person for a review done elsewhere) |
| `config init --cmd CMD --junit GLOB` · `config show` | Write the repository config · show the one the gates use and where it comes from |
| `ci [--base REF] [--branch NAME] [--require STAGE]` | §5: recompute the evidence on the head with the base's config |
| `ruling SPEC --decision TEXT --why TEXT --if-wrong TEXT [--task T<n>]` | Append a ruling |
| `stamp SPEC review` | Write the current fingerprint into review.md and log it |
| `trace SPEC [--write]` | Story → tickets → tests → result; `--write` into README `## Traceability` |
| `init SPEC --key KEY` | Create folder with README, spec.md, tickets.md, ledger.md skeletons |

`SPEC` = folder path, or slug (`refunds` finds `<any>/docs/specs/refunds`; `init` with a slug creates `<repo>/docs/specs/<slug>`; pass a path for service/system scope).

## 4. Repository config

### `.aidlc.json`

```json
{
  "schema": 1,
  "verify": {
    "cmd": "npm run test:ci",
    "junit": "reports/*.xml",
    "revert_check": true
  }
}
```

- `verify.cmd`: the full test suite. `verify.junit`: the glob of the JUnit reports it writes, or `"none — <reason>"` (traceability then falls back to a text search, with a warning). Reports and build output belong in git-ignored paths, or every run changes the code fingerprint. `verify.revert_check`: default `true`.
- Optional: `"ci": "none — <reason>"` (a repository without CI: the `CI:` line of ship.md is then taken at its word) and `"review": {"returns": "none — <reason>"}` (reviews happen another way). Each waiver is printed by the gate that would have checked it.
- **Where it is read from:** the default branch as the remote has it (`origin/<default>`), else the local default branch; `aidlc ci` reads the base ref. A branch that edits or deletes the file still gets that version: change the pin in its own change, read by a person. A file that exists only on the branch is **onboarding** (trust on first use): the gates use it and say so, and a person must read it before the merge.
- A service with its own `docs/specs/` may carry its own `.aidlc.json`; the command runs in the folder that holds the file. A config on the default branch wins over one that exists only on the branch, wherever it is (the branch-only file is named in a warning and ignored). The default branch is `origin/HEAD`, else `main`, `master` or `init.defaultBranch`; when `origin` exists and none of them does, the gates refuse (`git remote set-head origin -a`) instead of reading the branch's own file.
- The revert check rewrites the production source of the change (the TDD gate's rule: code extensions outside test folders; `.mjs`, `.sql`, shell scripts and the like are not reverted) and refuses to run over uncommitted work or a symbolic link in those files. Reports and scripts the pinned command names belong to the branch: protect them (CODEOWNERS) like the config.
- No config: `aidlc verify` stops and names `aidlc config init`. In a delegated run, write the file with the project's real full-suite command (onboarding), and list it first in the final report.

## 5. CI gate

`aidlc ci` is the same checks run where the session cannot write: it reads the config from the base ref, runs the revert check and the pinned command on the checked-out head, and evaluates every spec bound to the head branch (up to its recorded stage, at least `--require`, default `reviewed`) with that fresh result. It reads no `verify` or `revert-check` line from a ledger and writes nothing to a spec folder. Its summary lists what it cannot check: who is said to have approved and reviewed, every waiver, and `ONBOARDING` when the verify command comes from the change itself.

GitHub (make the job a required status check; check out the head with history, and set up whatever your verify command needs first):

```yaml
- uses: actions/checkout@v4
  with:
    ref: ${{ github.event.pull_request.head.sha }}
    fetch-depth: 0
- uses: TeaSui/aegisops-harness/.github/actions/aidlc-gate@<tag-or-sha>  # not @main: the gate is the trust anchor
```

Bitbucket Pipelines (pin the plugin to a tag or commit; fetch the destination branch with its history, because a pipeline clone is shallow and single-branch):

```yaml
pipelines:
  pull-requests:
    '**':
      - step:
          name: lifecycle gate
          script:
            - git fetch --unshallow origin || true
            - git fetch origin "+refs/heads/$BITBUCKET_PR_DESTINATION_BRANCH:refs/remotes/origin/$BITBUCKET_PR_DESTINATION_BRANCH"
            - git clone --depth 1 --branch <tag> https://bitbucket.org/<you>/aegisops-harness.git /tmp/aegisops-harness
            - python3 /tmp/aegisops-harness/scripts/aidlc.py ci
```

Use a tag or a commit SHA in `uses:` and in the clone, not `@main`: the gate is the trust anchor, so its version is a decision a person makes. Add `persist-credentials: false` to the checkout step, since the pull request's own suite runs in that job.

## Trust model

Three layers; only the last one is enforcement.

1. **Prompts** (skills, rules, agents) advise.
2. **Hooks and local gates** are a guard rail for the default path: they catch the session that forgets or takes the short way, with the commands it writes by default. They read files that same session can write (ledger, review.md, the transcript), so a session that sets out to forge them can. Do not present them to an auditor as a control.
3. **`aidlc ci` as a required status check on a protected branch**, with a required review by a person (CODEOWNERS on `.aidlc.json`, `docs/specs/`, the scripts and workflow the pinned command and the gate job run), enforces: the session cannot write CI's result, the base branch's config, or another person's approval. Switching branch protection on is the repository owner's act.

Limits of the hooks and local gates that this release knows and does not close (each is why layer 3 exists):
- `git add … && git commit` in one command: the scan runs before the command, when nothing is staged yet, so an untracked file added by the same line is not scanned (`git commit -a` and paths on the line are). Run the add first, or rely on CI and the host's secret scanning. This predates 6.0.0.
- A merge made with `curl` against GitHub's GraphQL endpoint, or `gh api graphql` with the query in a file, is not seen; `gh pr merge N -R other/repo` is judged by this checkout, not the other repository.
- A baseline counts as stale when it was measured on another `major.minor` plugin version; a patch release does not flag it.
- A command read from shell text is read for the forms a session writes by default. A pipe into a shell (`echo "git push" | sh`), a here-string, a line continuation inside a word, an alias or a script are not seen.
- GitHub MCP tools that write file content (`push_files`, `create_or_update_file`) are not routed to the secret scan; only creating and merging a pull request is gated. CI and the repository's own secret scanning are the backstop.
- The revert check proves the suite goes red without the change. With JUnit it also needs a story test that stopped passing; without a usable report a red exit is all it can see, so a test that only imports a new module goes red when that file is removed. Keep JUnit on.
- A change made after the last reviewer return is a warning in the gate, not a failure: the reviewer read an earlier commit. The CI summary lists it for the person who approves.
- The axis a stored return covers comes from the dispatch prompt; a return is the reviewer's text, but who it was asked to review is the session's word.
- Another `aidlc` command run while a revert check is in progress finishes that run's restore early; run one verify at a time per checkout.
- This repository's own gate job runs the plugin from the pull request head, because the plugin is developed here. Protect `scripts/`, `hooks/` and `.github/` with CODEOWNERS or run the gate from the base ref.

What stays a claim even then, and is printed in the CI summary for the reviewer: who approved the spec (`accepted_by`), who reviewed (`reviewers:`), every waiver, and every ruling marked `RISK-ACCEPTANCE NEEDED`.

## Compatibility

The spec README and `.aidlc.json` carry `schema: 1`; a spec README without the field is read as schema 1, an `.aidlc.json` without it is refused (the file is new in 6.0.0, so every one has it). A file with a newer schema than the plugin reads is refused with a message, never guessed at. The formats in §2 and §4 and the ledger events are frozen at schema 1: a release may add optional fields and new event kinds; a change that would make an existing schema-1 file mean something else needs schema 2, a major version, and one major version in which both are read.
