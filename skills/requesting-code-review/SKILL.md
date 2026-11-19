---
name: requesting-code-review
description: Use when work needs review before merge or a PR ("get it reviewed", "review my changes"), after a full-workflow task, or for the pre-PR pass — Full workflow dispatches the code-reviewer subagent; Fast path runs the built-in code-review skill once on the diff (rules/pre-pr-review.md). (tea-sdlc — follows the routing tiers and hook gates)
---

# Requesting Code Review

Get the change reviewed in a fresh context to catch issues before they cascade. In the Full workflow, dispatch the code-reviewer subagent; on the Fast path, run the built-in `code-review` skill once on the diff instead (no subagent). The reviewer gets precisely crafted context for evaluation — never your session's history. This keeps the reviewer focused on the work product, not your thought process, and preserves your own context for continued work.

**Core principle:** Review early, review often.

## When to Request Review

**Required when the routing tier/accepted plan calls for independent review:**
- Substantial implementation, trust-boundary changes and formal pre-merge gates
- Respect `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` and `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md`: Fast path runs the built-in `code-review` skill once on the diff before the PR (no subagent dispatch); Full workflow dispatches the code-reviewer subagent.

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

**1. Identify the actual review scope:**
Select one `REVIEW_SCOPE` and record its checked state:

- **Committed range:** verify the task's actual base/head refs, then inspect their diff. Never assume the previous commit represents the task.
- **Pending Git work:** inspect staged and unstaged diffs plus untracked owned files. Include deletions/renames and record baseline/content hashes or an equivalent snapshot so the reviewer can detect drift.
- **Non-Git work:** supply the owned changed-file manifest with original/changed copies and hashes.

For pending scope collect filenames without losing spaces/newlines:
```bash
git diff --name-only --no-renames -z
git diff --cached --name-only --no-renames -z
git ls-files --others --exclude-standard -z
```
Deduplicate with a NUL-aware collector and pass paths as arguments, never interpolated shell code. Review the actual scoped content; exclude unrelated/user/other-agent changes from the claimed work without hiding relevant context. Do not commit merely to enable review.

**2. Run the review for the tier:**

Fast path: run the built-in `code-review` skill once on the diff, then go to step 3.

Full workflow: use the available Agent tool (`Task` alias supported) with code-reviewer type and the template at `${CLAUDE_PLUGIN_ROOT}/skills/requesting-code-review/code-reviewer.md`. Choose model/effort from `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`.

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` - What you just built
- `{PLAN_OR_REQUIREMENTS}` - What it should do
- `{REVIEW_SCOPE}` - Mode (committed/pending/non-Git), owned paths, baseline and actual checked state/manifest
- `{BASE_SHA}` - Verified starting commit; required only for committed-range review
- `{HEAD_SHA}` - Verified ending commit; required only for committed-range review
- `{DESCRIPTION}` - Brief summary

**3. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Fix Suggestion/Minor issues too, or clear each with a one-line evidence-backed reason; a note alone does not clear it
- Push back if reviewer is wrong (with reasoning)

**4. Record the pre-PR pass (before opening a PR):**
After the fixes and one diff-only re-review of them (`${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`), commit, then record the review for the new HEAD:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <code-reviewer|code-review> --open-findings <n>
```
`<n>` is the number of findings neither fixed nor cleared, at any severity. The record is per HEAD: a later commit needs a new record. `gh pr create` stays blocked until the record for HEAD shows 0; findings still open after the one re-review go to the user as explicit open items rather than another loop.

## Example

```
[Just completed Task 2: Add verification function]

You: Let me request code review before proceeding.

[Inspect staged/unstaged diffs, listed untracked files and original baseline]
[Capture the owned changed-file manifest/content hashes]

[Dispatch code-reviewer subagent]
  WHAT_WAS_IMPLEMENTED: Verification and repair functions for conversation index
  PLAN_OR_REQUIREMENTS: Task 2 from docs/specs/deployment/plan.md
  REVIEW_SCOPE: pending Git work; owned verification/repair files and tests;
                baseline and content hashes in the supplied review manifest
  DESCRIPTION: Added verifyIndex() and repairIndex() with 4 issue types

[Subagent returns]:
  Strengths: Clean architecture, real tests
  Issues:
    Important: Missing progress indicators
    Minor: Magic number (100) for reporting interval
  Assessment: Ready to proceed

You: [Fix progress indicators; replace the magic number with a named constant]
[Continue to Task 3]
```

## Integration with Workflows

**Subagent-Driven Development:**
- Review substantial owned tasks at the checkpoints required by the tier/plan
- Catch issues before they compound
- Fix before moving to next task

**Executing Plans:**
- Review at the accepted checkpoints, sized to integration risk
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck

## Red Flags

**Never:**
- Skip a review gate required by the routing tier or accepted plan
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification

See template at: `${CLAUDE_PLUGIN_ROOT}/skills/requesting-code-review/code-reviewer.md`. Review results must name the checked state/scope and contain status, existing evidence paths and exit-criteria checks per `${CLAUDE_PLUGIN_ROOT}/rules/subagent-return-format.md`. A changed file after review invalidates only the affected scope; recheck it before carrying the verdict forward.
