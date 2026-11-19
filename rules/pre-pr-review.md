# Pre-PR Self-Review

Before opening a PR, and before handing a change to review, the change is reviewed in a fresh context, not in the implementation conversation. Which review depends on the tier (`rules/workflow-routing.md`).

## Full workflow: the review stage

The pre-PR pass is the review stage of the AIDLC lifecycle (`references/aidlc.md`; procedure in `skills/requesting-code-review/SKILL.md`):

1. The spec is at `verified`: the latest `aidlc verify` run is green and matches the current code.
2. Two separate reviews run in parallel, the Spec axis (against `requirements.md`, `design.md`, `contracts/`) and the Standards axis (code quality, security rules, conventions, `REVIEW.md` if present). Their findings go into the spec's `review.md` as returned, never merged or re-ranked.
3. Each finding is closed with `fixed:` or `cleared:` and evidence. A note alone does not clear a finding.
4. After a re-run of `aidlc verify`, one diff-only re-review of the fixes; then `aidlc stamp <f> review`.
5. `aidlc advance <f> reviewed` checks all of this and, on pass, writes the pre-PR record for `HEAD`. No separate `mark-pr-review.py` call is needed.

## Fast path

1. Run verification and show its output (see `references/agent-discipline.md` § Verification).
2. Run Claude Code's built-in `code-review` skill once on the diff; if unavailable, use the `tea-sdlc:requesting-code-review` skill with a fresh-context reviewer.
3. Fix each finding, or clear it with a stated reason backed by evidence. A note alone does not clear a finding.
4. Re-review only the diff added by those fixes.
5. Commit, then record the pass with `scripts/mark-pr-review.py --reviewer <name> --open-findings <n>`.

## Enforcement

The `gh pr create` PreToolUse gate (`hooks/pr-review-gate.py`) blocks unless a record exists for the current `HEAD` with zero open findings: written by `aidlc advance <f> reviewed` in the full workflow, by `scripts/mark-pr-review.py` on the fast path. On a branch bound to a full-workflow spec the gate decides from the spec instead: it allows the PR when the spec passes the `reviewed` gate (keyed to the code fingerprint, so committing `review.md` or the ledger afterwards is fine) and blocks with the gate's findings when it does not. The gate checks that the record exists and is current, not that the review was thorough; the reviewers own that. It also blocks while an active spec with `contract: external` fails `scripts/check-contract.py --scan`. The hook only guards `gh`: with a Bitbucket, GitLab or other non-GitHub remote nothing blocks, so still run the pass, record it, and hand the PR description to the user to open the PR.

## Limits

One review pass plus one diff-only re-review; do not loop (`rules/review-loop-limits.md`). On the fast path, record `--open-findings 0` only when each finding is fixed or cleared; a finding deferred to the human reviewer counts as cleared only when the PR description lists it with the reason. In the full workflow an open finding blocks `reviewed`: the user decides it when it is theirs to decide, otherwise the spec goes back to `building`.
