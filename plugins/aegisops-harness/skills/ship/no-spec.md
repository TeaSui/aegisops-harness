# Delivering work without a spec (`/aegisops-harness:fix`)

If `python3 "scripts/aidlc.py" status` lists an active spec whose `branch:` is the current branch, use `/aegisops-harness:ship` (or `/aegisops-harness:review` first if it is not yet `reviewed`). No Git involved: report the verified artifact.

1. **Tests.** Run the full suite and read the result. Failing → report and stop; never merge or open a PR on red.
2. **Base branch.** Find it yourself: `git symbolic-ref --short refs/remotes/origin/HEAD`, `python3 "scripts/pr.py" default-branch`, or local `main`/`master`. Ask only if all fail.
3. **Commit** only this work's changes, in logical steps. If the gitleaks gate blocks, remove the secret; never bypass.
4. **Delivery.** Use the choice given: "open a PR"/"push it" → PR; "merge it" → local merge; none given (`/aegisops-harness:fix`) → PR if a remote exists, else merge. Keep and discard only on request.
5. **Pre-PR record** (merge or PR): one pass per `rules/pre-pr-review.md` (built-in `code-review` on the diff). Fix or clear each finding with evidence, commit, at most one diff-only re-review, then `python3 "scripts/mark-pr-review.py" --reviewer <name> --open-findings <n>`. The PR gate (`pr.py create`, `gh pr create`) needs a record for the current HEAD with 0 open; any new commit needs a new record. Findings left open go in the PR description.
6. **Execute.**
   - Merge: checkout base, pull, merge, run tests on the merged result, `git branch -d` only if green; remove the worktree.
   - PR: `git push -u origin <branch>`, `python3 "scripts/pr.py" create --title … --body-file <file>` with Summary (link spec/ADRs) and Test Plan (evidence); it uses `gh` for GitHub and the API for Bitbucket Cloud. Only when it fails, report BLOCKED with the error and its fix, and hand the user the description. A change asked for "ready to ship" is done only with the PR open. Keep the worktree.
   - Keep: report branch and worktree path; touch nothing.
   - Discard: list branch, commits and worktree to be deleted and require the user to type `discard`; then `git branch -D` and remove the worktree.
7. **Worktree cleanup** only for merge/discard and only if this task created it (`git worktree remove <path>`).

Never force-push without an explicit request. Never ask an open-ended "what next?". Update affected living docs in the same change.
