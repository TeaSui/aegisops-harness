# Pre-PR Self-Review

Before opening a PR, and before handing a change to review:

1. Run verification and show its output (see `references/agent-discipline.md` § Verification).
2. Review the diff in a fresh context, not in the implementation conversation:
   - Full workflow: dispatch `code-reviewer` with the diff, the plan and contract paths, and `REVIEW.md` if present. The code-reviewer gate counts as this pass when it reviewed the current HEAD.
   - Fast path: run Claude Code's built-in `code-review` skill once on the diff; if unavailable, use the `tea-sdlc:requesting-code-review` skill with a fresh-context reviewer.
3. Fix each finding, or clear it with a stated reason backed by evidence. A note alone does not clear a finding.
4. Re-review only the diff added by those fixes.

Enforcement: the `gh pr create` PreToolUse gate (`hooks/pr-review-gate.py`) blocks unless a record exists for the current HEAD with zero open findings. Record it with `scripts/mark-pr-review.py --reviewer <name> --open-findings <n>`. The gate checks that the record exists and is current, not that the review was thorough; the reviewer owns that. It also blocks while an active spec with `contract: external` fails `scripts/check-contract.py --scan`. The hook only guards `gh`: with a Bitbucket, GitLab or other non-GitHub remote nothing blocks, so still run the pass, record it with `scripts/mark-pr-review.py`, and hand the PR description to the user to open the PR.

Limits: one pre-PR pass plus one diff-only re-review; do not loop (`rules/review-loop-limits.md`). Record `--open-findings 0` only when each finding is fixed or cleared. A finding you defer to the human reviewer counts as cleared only when the PR description lists it with the reason; otherwise record it as open.
