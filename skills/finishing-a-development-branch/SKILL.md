---
name: finishing-a-development-branch
description: Use when implementation is verified and must be delivered (merge, PR, keep, discard), or the user says open a PR / ship it / merge. Runs the pre-PR review record and the delivery the user already chose; asks only when no choice is known.
---

# Finishing a Development Branch

Deliver verified work with the choice the user already gave. Ask only when no delivery choice is known. If no Git branch or worktree is involved, report the verified artifact directly. Native permissions and destructive discard still require their own authorization.

**Core principle:** verify tests → determine base → commit → choose delivery (only if unknown) → pre-PR review record → execute → clean up.

## Step 1: Verify tests

Run the project's test suite (`npm test`, `cargo test`, `pytest`, `go test ./...` or the project's own command) and read the result.

If tests fail, report the failures and stop: do not merge or open a PR on failing tests. Fix them first (`tea-sdlc:systematic-debugging` when the cause is unclear).

## Step 2: Determine the base branch

Find it yourself; do not ask the user:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD        # e.g. origin/main
# or
gh repo view --json defaultBranchRef -q .defaultBranchRef.name
```

Without a remote, use the local `main` or `master` that `git merge-base HEAD <branch>` resolves. Ask only when none of these give an answer.

## Step 3: Commit pending changes

Run `git status`. Commit the changes this work owns in logical steps; leave other people's unrelated changes unstaged. The gitleaks gate scans on commit and push: if it blocks, remove the secret from the change and retry, never bypass it.

## Step 4: Choose the delivery

Use the choice already given. "Open a PR", "ship it" or "push it" means Option 2; "merge it" means Option 1; an autopilot or `tea-sdlc:goal` request that delegates delivery uses the project's normal path (Option 2 when a remote exists, else Option 1).

Only when no choice is known, present the four options once and wait:

```
Implementation complete. What would you like to do?

1. Merge back to <base-branch> locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work
```

## Step 5: Pre-PR review record (Options 1 and 2)

Run the single pre-PR pass in `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md`:

- Fast path: run the `code-review` skill once on the diff.
- Full workflow: dispatch `code-reviewer` on the diff, unless `tea-sdlc:subagent-driven-development` already recorded a pass for the current HEAD.

Fix each finding or clear it with evidence, commit the fixes, then record the pass for the current HEAD:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <name> --open-findings <n>
```

The `gh pr create` gate blocks unless the record matches HEAD with 0 open findings. A new commit needs a new record. Findings still open after one diff-only re-review go into the PR description as open items.

## Step 6: Execute the choice

### Option 1: Merge locally

```bash
git checkout <base-branch>
git pull
git merge <feature-branch>
<test command>                 # verify the merged result
git branch -d <feature-branch> # only if tests pass
```

Full workflow: after the merge, run `upgrade-service-docs <service> <feature>` yourself to promote the spec into the living docs. Then clean up the worktree (Step 7).

### Option 2: Push and create a PR

```bash
git push -u origin <feature-branch>
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary
<2-3 bullets of what changed; link the spec and ADRs>

## Test Plan
- [ ] <verification steps and evidence>
EOF
)"
```

With a non-GitHub remote nothing blocks `gh`; still record the pass, push, and give the user the PR description to open the PR. Full workflow: once the PR merges (or QA returns `GO`), run `upgrade-service-docs <service> <feature>` yourself. Keep the worktree: review fixes land there.

### Option 3: Keep as-is

Report: "Keeping branch <name>. Worktree preserved at <path>." Do not clean up the worktree.

### Option 4: Discard

Confirm first; this is a decision only the user can make:

```
This will permanently delete:
- Branch <name>
- All commits: <commit-list>
- Worktree at <path>

Type 'discard' to confirm.
```

Wait for the exact confirmation, then:

```bash
git checkout <base-branch>
git branch -D <feature-branch>
```

Then clean up the worktree (Step 7).

## Step 7: Clean up the worktree (Options 1 and 4 only)

Only when this task created an isolated worktree:

```bash
git worktree list | grep "$(git branch --show-current)"
git worktree remove <worktree-path>
```

Options 2 and 3 keep the worktree.

## Quick reference

| Option | Pre-PR record | Merge | Push | Keep worktree | Delete branch | upgrade-service-docs (Full workflow) |
|---|---|---|---|---|---|---|
| 1. Merge locally | yes | yes | - | - | yes | after merge |
| 2. Create PR | yes | - | yes | yes | - | after PR merge or QA `GO` |
| 3. Keep as-is | - | - | - | yes | - | - |
| 4. Discard | - | - | - | - | yes (force) | - |

## Rules

- Never merge or open a PR with failing tests, and verify tests on the merged result.
- Never open a PR without the pre-PR record for the current HEAD.
- Never discard work without typed confirmation.
- Never force-push without an explicit request.
- Ask for a delivery choice only when none is known; never ask an open-ended "what next?".

## Integration

Called by `tea-sdlc:subagent-driven-development` (after integration and required reviews) and `tea-sdlc:executing-plans` (after all tasks). Uses the worktree management of the runtime only when this task created an isolated checkout.
