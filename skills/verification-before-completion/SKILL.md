---
name: verification-before-completion
description: Use before saying work is done, fixed or passing, before a commit, PR or handing to the next task — find the check that would show the claim true for the exact state, reuse it only while still valid or run it, and report what the output supports with the evidence beside it; in the full workflow the evidence is a passing aidlc gate on a fingerprinted `aidlc verify` run (tea-sdlc — follows the routing tiers and hook gates)
---

# Verification before completion

A completion claim is something the user acts on: they merge, deploy or move to the next task. Make the claim only when a check you can point to supports it, and say plainly when one does not.

## Before claiming a status

1. **Identify** the check that would show the claim is true, for the exact state and scope being claimed: commit/base or pending-file manifest, command, relevant environment or tool version.
2. **Reuse or run.** Reuse an earlier inspected result when that state and scope are unchanged and no failure or uncertainty has invalidated it, per `${CLAUDE_PLUGIN_ROOT}/rules/reduce-hallucinations.md`. Run the check again after relevant edits, dependency/config changes or new failures, or when the user asks for a fresh challenge such as `/prove-it`.
3. **Read** the decisive output: exit code, failure count, what was skipped. Redact sensitive values.
4. **Claim what the output supports**, with the evidence beside it. If the output does not support the claim, report the actual state instead.

## What supports a claim

| Claim | Supported by | Not supported by |
|-------|--------------|------------------|
| Tests pass | Test output for the checked state/scope: 0 failures | An invalidated earlier run; a targeted run presented as the whole suite |
| Linter clean | Linter output: 0 errors | A partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs that look fine |
| Bug fixed | The original symptom no longer reproduces | The code was changed |
| Regression test works | It failed before the fix and passes after | It passes once |
| Agent completed | The changed files/diff, cited evidence and exit-criteria results, read by you | The agent's own success report |
| Requirements met | A line-by-line check against the plan or spec; in the full workflow `aidlc trace` | Tests passing |
| Full-workflow stage reached | `aidlc check <f> --to <stage>` passes, or `aidlc advance` succeeded | A test run outside `aidlc verify`; a `verify` event whose fingerprint no longer matches the code |

## Full workflow: the gate is the evidence

For a change with a spec folder, the evidence is recorded by the CLI, not by a test run you read in the terminal (formats and gates: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`):

- **Tests pass** means the latest `verify` event in `ledger.md` exited 0 and its code fingerprint equals the current one. Run the suite through `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full suite>"`; a run outside the CLI is not recorded and does not count. Any code edit after that run changes the fingerprint, so run `verify` again before the next claim.
- **A task is done** means `aidlc task-done` ran its exit command, it exited 0, and the task is ticked; never tick `plan.md` by hand.
- **Requirements met** means `aidlc trace <f>` shows every requirement with a passing test, a check, or a stated manual verification.
- **The change is done, verified, reviewed or ready to ship** means the gate for that stage passes. Quote its result; when it lists findings, report the stage the spec is actually at and what blocks the next one, then fix them rather than describing the change as done.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" check <f> --to <verified|reviewed|shipped>
```

The fast path keeps the general rules below: the test output for the exact state you are claiming.

## Scope the claim to the evidence

- A partial check supports a partial claim. Say what ran and what it covered.
- Distinguish PASS, FAIL, SKIPPED, UNSUPPORTED and static-only checks. Skipped tests are not passing tests, a parser does not prove runtime behavior, and a check that needs a missing service cannot be reported as passing.
- When a check cannot run (missing service, dependency or permission), or the user asked to skip it, say what was not verified and what that leaves open. "Changed, not verified" is a complete report; a guess presented as a result is not.
- "Should", "probably" and "seems to" mean the claim is ahead of the evidence. Run the check, or state the claim as unverified.
- For a regression test, cite the failing run seen before the fix. Only reverse a known owned patch in isolation; preserve a recoverable copy and never reset or delete user or other-agent work. See `test-driven-development` for safe recovery.

## Proportion

Match the check to the change. A prose typo needs a re-read, not the test suite; a change to shared behavior needs the whole suite, not one test. Apply this before any success claim, before committing or opening a PR when the claim depends on checks, and before moving to a dependent task or reporting a delegated task complete.

## Related

`grounding-claims` covers all factual claims (paths, symbols, APIs, commit SHAs); this skill covers success claims. Both put the evidence before the assertion.
