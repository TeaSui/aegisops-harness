---
name: finishing-a-development-branch
description: Use when fast-path or non-spec work is verified and must be delivered (merge, PR, keep, discard), or the user says open a PR / push it / merge. Runs the single pre-PR review record and the delivery the user already chose; asks only when no choice is known. A branch with an active full-workflow spec goes to tea-sdlc:shipping instead.
---

# Finishing a development branch

If `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" status` lists an active spec whose `branch:` is the current branch, use `tea-sdlc:shipping` (or `tea-sdlc:requesting-code-review` first if it is not yet `reviewed`). No Git involved: report the verified artifact.

1. **Tests.** Run the full suite and read the result. Failing → report and stop; never merge or open a PR on red.
2. **Base branch.** Find it yourself: `git symbolic-ref --short refs/remotes/origin/HEAD`, `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`, or local `main`/`master`. Ask only if all fail.
3. **Commit** only this work's changes, in logical steps. If the gitleaks gate blocks, remove the secret; never bypass.
4. **Delivery.** Use the choice given: "open a PR"/"push it" → PR; "merge it" → local merge; delegated (autopilot, `tea-sdlc:goal`) → PR if a remote exists, else merge. Only if none is known, offer once: 1 merge locally, 2 push and PR, 3 keep as-is, 4 discard.
5. **Pre-PR record** (merge or PR): one pass per `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md` (built-in `code-review` on the diff). Fix or clear each finding with evidence, commit, at most one diff-only re-review, then `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <name> --open-findings <n>`. The `gh pr create` gate needs a record for the current HEAD with 0 open; any new commit needs a new record. Findings left open go in the PR description.
6. **Execute.**
   - Merge: checkout base, pull, merge, run tests on the merged result, `git branch -d` only if green; remove the worktree.
   - PR: `git push -u origin <branch>`, `gh pr create` with Summary (link spec/ADRs) and Test Plan (evidence). Decide from what `gh` answers, never from the remote URL (a local path or mirror may still be served by `gh`); only when `gh` itself fails, push and hand the user the description. A change asked for "ready to ship" is done only with the PR open. Keep the worktree.
   - Keep: report branch and worktree path; touch nothing.
   - Discard: list branch, commits and worktree to be deleted and require the user to type `discard`; then `git branch -D` and remove the worktree.
7. **Worktree cleanup** only for merge/discard and only if this task created it (`git worktree remove <path>`).

Never force-push without an explicit request. Never ask an open-ended "what next?". Fast-path changes update affected living docs in the same change.
