---
name: verification-before-completion
description: Use before saying work is done, fixed or passing, before a commit, PR or handing to the next task — find the check that would show the claim true for the exact state, reuse it only while still valid or run it, and report what the output supports with the evidence beside it; in the full workflow the evidence is a passing aidlc gate on a fingerprinted `aidlc verify` run (tea-sdlc — follows the routing tiers and hook gates)
---

# Verification before completion

1. Name the check that proves the claim for the exact state and scope (commit or pending files, command, environment).
2. Reuse an earlier result only if that state is unchanged and nothing invalidated it; rerun after relevant edits, dependency or config changes, new failures, or `/prove-it`.
3. Read the decisive output (exit code, failures, skips); redact secrets.
4. Claim only what it supports, evidence beside the claim; otherwise report the actual state.

| Claim | Needs | Not enough |
|---|---|---|
| Tests pass | 0 failures for this state and scope | stale run; targeted run sold as full suite |
| Build / lint clean | exit 0 / 0 errors from that command | another tool passing |
| Bug fixed | original symptom no longer reproduces | code changed |
| Regression test | failed before the fix, passes after | passes once |
| Agent done | diff, cited evidence and exit results read by you | its own report |
| Requirements met | line-by-line against plan/spec (`aidlc trace`) | tests green |

## Full workflow

Evidence is what the CLI recorded (`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`):
- Tests pass = the latest `aidlc verify <f> --cmd "<full suite>"` exited 0 and its fingerprint equals the current code. A run outside the CLI does not count; any code edit needs a new `verify`.
- Task done = `aidlc task-done` exited 0 and ticked it; never tick by hand.
- Requirements met = `aidlc trace <f>` shows each requirement with a passing test, check or stated manual verification.
- Done / verified / reviewed / ready to ship = `aidlc check <f> --to <stage>` passes; quote it. If it lists findings, report the actual stage and blockers, then fix them.

## Scope

- Partial check → partial claim; say what ran. Keep PASS, FAIL, SKIPPED, UNSUPPORTED and static-only distinct.
- A check that cannot run: say what is unverified and what that leaves open. "Changed, not verified" is a valid report.
- "Should", "probably", "seems" = claim ahead of evidence.
- To show a regression test failing, reverse only your own patch in isolation; never reset others' work.
- Proportion: a prose typo needs a re-read; shared behaviour needs the whole suite.
