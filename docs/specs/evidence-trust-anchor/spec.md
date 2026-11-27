# Evidence trust anchor

Status: ready-for-agent

## Problem Statement

The lifecycle gates check evidence that the gated session writes itself. A session can pass `verified`, `reviewed` and the PR gate with red tests (`verify --cmd true`, a story ID in a comment, a hand-typed review), reach `shipped` on four text files, and skip the secret, PR and merge hooks with an equivalent command or a GitHub MCP tool. The lifecycle eval passes the same broken repository because it scores the paperwork, and the eval job was green on sessions that never reached a model. Fourteen reproducible proofs of 2026-11-26 show each point.

## Solution

Move the trust anchor to where the session cannot write: a config read from the default branch pins the test command, and one CI command recomputes the evidence on the pull request head. Local gates stay as guard rails for the default path and say so. The evals score the outcome and fail when they carry no signal. The formats get a schema version, and the plugin is developed through its own lifecycle.

## User Stories

1. As a repository owner, I want the test command that counts as gate evidence pinned in a config read from the default branch, so that the session being gated cannot choose its own exam.
2. As a reviewer, I want every story verified by test to need a test that ran and passed in the JUnit report of the pinned command, so that a comment or an unexecuted file is not traceability.
3. As a reviewer, I want the pinned suite to go red when the production change is taken out, so that I know the new tests depend on the change.
4. As a repository owner, I want one CI command that recomputes the evidence on the pull request head with the base branch's config and ignores the ledger's verify lines, so that the gate holds when the local files were written by hand.
5. As a repository owner, I want every gate to re-check the gates before it and the shipped gate to need a real CI result, so that a hand-set stage or a typed "CI: green" grants nothing.
6. As a product owner, I want the approval bound to the text of the spec and recorded by a command the model is kept from running, so that the spec I approved is the spec that is built.
7. As a reviewer, I want each reviewer's return recorded verbatim and checked against review.md, so that the implementer cannot drop or downgrade a finding.
8. As a repository owner, I want the secret, PR and merge gates to recognise equivalent commands and the GitHub MCP tools, so that the default path is covered wherever the session runs.
9. As a maintainer, I want the lifecycle eval to pass only when the test suite and the hidden outcome checks pass, so that the score measures working software.
10. As a maintainer, I want a session that never reached a model counted as an infrastructure failure and a run with too few judged sessions to fail, so that the eval job cannot be green without signal.
11. As a maintainer, I want a control arm without the plugin and cases on brownfield, migration and concurrency work, so that the eval can show what the plugin adds.
12. As a maintainer, I want the eval report to say when the baseline was measured on another plugin version, so that stale numbers are not read as current.
13. As a user, I want the artifact formats to carry a schema version with a written compatibility rule, so that an upgrade does not silently change what my specs mean.
14. As a maintainer, I want the rename defects fixed and covered by tests, and README or changelog version drift to fail the structure check, so that a mechanical edit cannot ship them again.
15. As a maintainer, I want the plugin built through its own lifecycle with CI running its own gate, so that we meet what users meet. (Verify: check — python3 scripts/aidlc.py ci --base origin/main)

## Implementation Decisions

- **Three layers, named in the docs.** Prompts advise. Hooks and local gates guard the default path and can be defeated by a session that sets out to. CI on a protected branch enforces. Local evidence files are a cache of what CI recomputes.
- **Repository config, schema 1.** One JSON file at the repository root (a service root may carry its own): the verify command, a JUnit glob or a waiver with a reason, the revert check on or off, CI required or a waiver with a reason, reviewer returns required or a waiver with a reason. The gates read it from the default branch. A branch that introduces the first config runs in onboarding mode with a warning (trust on first use); a branch that edits an existing config still gets the default branch's version.
- **Verify runs the pinned command only.** A different command is a usage error. Ticket commands (`task-done`) stay free: they track progress and are not gate evidence.
- **Dynamic traceability.** With a JUnit glob configured, a verify without a readable report fails the gate, and each story verified by test needs a passing test case whose name carries its ID.
- **Revert check.** On committed code, production source files changed since the merge base with the default branch are put back to the base version, the pinned command must exit non-zero (a timeout does not count), and the files are restored from HEAD. When every story test still passes without the change the run fails; when only some do, those stories are listed as a warning. "Production source" is the TDD gate's rule (code extensions outside test folders): a change only in other files is skipped with its reason. Not applicable when no production source changed. It refuses to run over uncommitted work in, or a symbolic link at, a file it rewrites.
- **Cumulative gates.** `reviewed` includes `verified`; `shipped` includes `reviewed`. The shipped gate needs a CI result from the provider unless the config waives CI.
- **CI command.** Reads the config from the base ref, runs the pinned command and the revert check on the checked-out head, and evaluates every spec bound to the head branch up to its recorded stage with that fresh evidence. It never reads verify or revert lines from the ledger and never writes to the spec folder. Shipped as a composite GitHub action with a Bitbucket Pipelines snippet.
- **Approval.** A ledger event that carries the SHA-256 of spec.md, the approver and the kind (approved or delegated). The accepted gate needs the latest approval to match the current spec text, so an edit after approval needs a new approval.
- **Reviewer returns.** A hook stores each review-stage return of the code reviewer and the QA agent as its own file in the spec folder with the agent, axis, code fingerprint and the SHA-256 of the body. The reviewed gate needs both axes and QA covered, every returned finding present in review.md with the same severity, and the QA verdict equal to the latest QA return.
- **Evidence guard.** A hook keeps the model from editing the ledger and the stored returns, and from running the approval and return-recording subcommands unless the user's own command authorises it (approval) or the request delegated it. A person at a terminal is not affected.
- **Hooks parse commands.** The git and gh invocations are tokenised (global options, absolute paths, `gh api` on the pulls endpoints) and the GitHub MCP create and merge tools are routed to the PR and merge gates. Direct pushes to the default branch stay a branch-protection matter.
- **Evals.** The lifecycle judge needs green tests and every hidden check; a run with no model turn is infrastructure; a suite with too few judged runs fails the comparison with its own exit code; the report flags a baseline from another plugin version; a control arm runs the same cases without the plugin and is judged on outcome; three new cases (brownfield fee, storage migration, concurrent transfers) each ship a hidden check.
- **Schema version.** Spec README and the config carry `schema: 1`; an unknown newer schema is a gate failure; the compatibility rule is written in the lifecycle reference.
- **Version 6.0.0.** Gates get stricter (pinned command, JUnit, real CI, approval event), which breaks specs in flight until the repository adds its config.

### Security

- Assets: the evidence chain (ledger, review, approval), the pinned verify command, the merge decision, the eval verdict.
- Threats: a session that fabricates evidence or picks a trivially green command (tampering, elevation); a branch that edits the gate's own config (tampering); an equivalent command or another tool that skips a hook (bypass); a finding dropped by the implementer (repudiation); an eval job that is green without signal (integrity of the measurement).
- Controls: (1) config from the default branch, (2) CI recomputation that ignores recorded verify lines, (3) cumulative gates, (4) revert check, (5) approval bound to the spec text, (6) verbatim reviewer returns with a content hash, (7) command parsing and MCP matchers in the hooks, (8) outcome-scored, fail-closed evals.
- Limit, stated in the docs: controls 1, 3 and 5–7 stop the default path, not a session that sets out to forge local files (locally the trusted ref is one the session can move with git, and the revert evidence is a ledger line; only CI recomputes them). The pinned command is a command line: the scripts it names (package scripts, a Makefile, the runner) are the branch's, so protect them and the workflow that calls the gate like `.aidlc.json`. `aidlc ci` judges the specs whose README binds them to the head branch and whose stage is active; a head that unbinds a spec gets the suite only, which the summary says, so a reviewer reads the diff of `docs/specs/`. Enforcement is control 2 behind branch protection, which only the repository owner can switch on.

## Testing Decisions

- Each proof of the assessment becomes a failing test first. Seams: the lifecycle CLI entry point, the hook scripts through stdin and exit code, the eval runner entry point with a fake `claude` binary, and the judges' `judge` function. No test calls a model or the network.
- Good tests: the red-test repository of proof A is rejected by the verified gate and by the CI command; the four-file forgery of proof B is rejected by the shipped gate and by the CI command; a branch that rewrites the config still runs the default branch's command; a vacuous test fails the revert check; a dropped or downgraded finding fails the reviewed gate; a session with no model turn is excluded and an all-excluded run fails the comparison.
- The hidden check of each new eval case must pass on a reference solution and fail on the fixture as shipped.
- Prior art: the `Base` fixture and stage builders in the lifecycle tests; the fake `claude` binary in the eval tests.

## Out of Scope

- Measuring a new baseline: it needs paid model runs and the owner's go-ahead.
- Branch protection and required status checks: the repository owner's settings.
- Signing keys or a remote attestation service.
- The self-recorded pre-PR review of the no-spec `fix` path.

## Further Notes

- Sources: the assessment and the 14 reproduced proofs of 2026-11-26; CI run 45165209409 (eval job green on 18 sessions with an empty API key); the Claude Code hooks reference (tool name `Agent`, `SubagentStop` fields, matcher syntax, MCP tool names).
- Assumptions: Python 3.9 and the standard library only, as today. The transcript tags the question gate already reads are also used to authorise an approval; they are not a documented interface, so the guard fails closed for an approval and a person can always approve from a terminal.
- Approved by the repository owner in session on 2026-11-26 ("agree with all six items").
