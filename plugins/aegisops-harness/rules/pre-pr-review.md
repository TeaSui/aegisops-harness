# Pre-PR review

Before opening a PR or handing a change to review, review it in a fresh context, not the implementation conversation.

## Without a spec (`/aegisops-harness:fix`, `skills/review/SKILL.md` §3)
1. Run verification and show its output.
2. Built-in `code-review` skill once on the diff: `low` effort, default on a trust-boundary change (unavailable → aegisops-harness:code-reviewer, `AXIS: both`). Trust boundary: it also checks the security pass (threats listed and tested, no PII or secrets in logs).
3. Fix each finding or clear it with a reason backed by evidence; a note alone clears nothing.
4. Re-review only the fix diff.
5. Commit, then `python3 scripts/mark-pr-review.py --reviewer <name> --open-findings <n>`.

## With a spec: the review stage
1. Spec at `verified` (latest `aidlc verify`: the pinned command green, the revert check red, both for the current code).
2. Spec axis (spec.md stories and decisions, ADRs, contracts/) and Standards axis (quality, the spec's security decisions, conventions, `REVIEW.md` if present): two separate aegisops-harness:code-reviewer dispatches, once each, in parallel with aegisops-harness:qa-subagent. The plugin stores each return in `returns/`; findings go into `review.md` as returned, never merged, re-ranked or dropped (the gate compares the two).
3. Close each finding `fixed:` or `cleared:` with evidence.
4. Re-run `aidlc verify`, then at most ONE diff-only re-review of the fixes by a single aegisops-harness:code-reviewer with `AXIS: both`; then `aidlc stamp <f> review`.
5. `aidlc advance <f> reviewed` checks all of it and writes the pre-PR record for HEAD; no `mark-pr-review.py` call.

## Enforcement
- `hooks/pr-review-gate.py` (PreToolUse on `pr.py create`, `gh pr create`, the API form of either provider, or a GitHub MCP `create_pull_request`) blocks unless a record for HEAD has zero open findings. On a branch bound to a spec it decides from the `reviewed` gate instead (keyed to the code fingerprint, so committing `review.md` or the ledger afterwards is fine).
- It also blocks while an active spec with `contract: external` fails `scripts/check-contract.py --scan`.
- It checks the record is current, not review quality. It guards GitHub and Bitbucket Cloud; on other hosts still run and record the pass, then hand the PR description to the user.

## Limits
One pass plus one diff-only re-review; no loops. Without a spec: record `--open-findings 0` only when every finding is fixed or cleared; a finding deferred to the human reviewer counts as cleared only if the PR description lists it with the reason. With a spec: an open finding blocks `reviewed`; the user decides it when it is theirs to decide, otherwise the spec goes back to `building`.
