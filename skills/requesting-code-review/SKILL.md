---
name: requesting-code-review
description: Use when work needs review before merge or a PR ("get it reviewed", "review my changes"), or when a full-workflow spec reaches `verified` — the review stage runs two separate reviews in parallel (Spec axis, Standards axis), writes their findings to review.md, then `aidlc stamp` and `aidlc advance reviewed`, which records the pre-PR pass. Fast path runs the built-in code-review skill once on the diff (rules/pre-pr-review.md). (tea-sdlc — follows the routing tiers and hook gates)
---

# Requesting Code Review

Get the change reviewed in a fresh context, with precisely crafted inputs and never your session's history, so the reviewer judges the work product rather than your reasoning.

Pick the path:

| Situation | Path |
|---|---|
| Full-workflow spec at stage `verified` | **Review stage** (below) |
| Fast path, or work with no spec folder | **Fast path pass** (below), unchanged |
| One task inside the build stage | the per-task templates of `tea-sdlc:subagent-driven-development` |

Optional reviews (when stuck, before a refactor, after a hard bug) use the fast path pass without recording it.

## 1. Identify the review scope

Select one `REVIEW_SCOPE` and record its checked state:

- **Committed range:** verify the actual base and head refs, then inspect their diff. Never assume the previous commit represents the work.
- **Pending Git work:** staged and unstaged diffs plus untracked owned files, including deletions and renames, with content hashes so the reviewer can detect drift.
- **Non-Git work:** the owned changed-file manifest with original and changed copies and hashes.

For pending scope collect filenames without losing spaces or newlines:
```bash
git diff --name-only --no-renames -z
git diff --cached --name-only --no-renames -z
git ls-files --others --exclude-standard -z
```
Pass paths as arguments, never as interpolated shell code. Exclude unrelated user or other-agent changes from the claimed work without hiding relevant context.

## 2. Review stage (full workflow)

Formats of `review.md` and the gates: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. `aidlc <command>` below is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" <command>`; you run it yourself.

**a. Start from `verified`.** `aidlc status` shows the spec at `verified`. Commit the code first: the pre-PR record that `advance reviewed` writes is tied to `HEAD`.

**b. Dispatch two separate reviews in one message**, so they run in parallel and neither sees the other's findings:

| Axis | Reviewer | Inputs | Checks |
|---|---|---|---|
| Spec | `tea-sdlc:code-reviewer` with `AXIS: spec`, or a reviewer using `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/spec-reviewer-prompt.md` in its review-stage mode | `requirements.md`, `design.md`, `contracts/`, the output of `aidlc trace <f>`, the scope | missing requirements or acceptance criteria, scope creep, behavior that contradicts design or contracts, tests that do not prove their requirement |
| Standards | `tea-sdlc:code-reviewer` with `AXIS: standards` | `security.md`, the project's `REVIEW.md` and conventions, the scope | code quality, security rules, error handling, tests, conventions, `${CLAUDE_PLUGIN_ROOT}/references/sonar-way.md` |

Both use the template `${CLAUDE_PLUGIN_ROOT}/skills/requesting-code-review/code-reviewer.md` (or the spec reviewer template) and return findings as `review.md` lines: `- [ ] S1 (must): …` for Spec, `- [ ] Q1 (should): …` for Standards. In the same message, dispatch `tea-sdlc:qa-subagent` when `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` places QA in this stage.

**c. Write `review.md`** in the spec folder: frontmatter `reviewers: spec=<agent> standards=<agent>`, then `## Spec` with the Spec reviewer's lines and `## Standards` with the Standards reviewer's lines, copied as returned. Do not merge duplicates across axes, change a severity, reorder or drop a finding; a finding you disagree with is cleared with evidence, not deleted. An axis with no findings keeps its heading.

**d. Close every finding** with `tea-sdlc:receiving-code-review`: each one ends `— fixed: <where>` or `— cleared: <evidence>`. Fix QA blockers in the same round.

**e. Re-verify and re-review once.** Fixes changed code, so run `aidlc verify <f> --cmd "<full suite>"` again. Then send each axis's reviewer only its own findings and the diff the fixes added. New findings are appended with the next free ID (`S4`, `Q3`) and closed the same way. One re-review, no further loop (`${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`).

**f. Stamp and advance:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" stamp <f> review
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> reviewed
```

The `reviewed` gate needs both axes, no open finding, every closed one with `fixed:` or `cleared:`, and one fingerprint across the verify run, the stamp and the current code. On pass it writes the pre-PR record for `HEAD`, so `gh pr create` is allowed. Leave the files `aidlc` just wrote (`review.md`, `README.md`, `ledger.md`) uncommitted: `tea-sdlc:shipping` opens the PR from this `HEAD`, then commits them.

**g. A finding that stays open after the re-review** blocks the gate. When it is a decision only the user can make (accepting a risk, changing a requirement), ask them once, with the finding and the options; their answer closes it as `cleared: accepted by <name> — <reason>`. When it needs real rework, go back: `aidlc advance <f> building --back --reason "<finding>"`.

Then continue with `tea-sdlc:shipping`.

## 3. Fast path pass (unchanged)

1. Run the built-in `code-review` skill once on the diff (no subagent). If it is unavailable, dispatch `tea-sdlc:code-reviewer` with the template and `AXIS: both`.
2. Fix each finding, or clear it with a one-line evidence-backed reason; a note alone does not clear it. Push back with technical reasoning when the reviewer is wrong.
3. One diff-only re-review of the fixes, then commit and record the pass for the new `HEAD`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <code-review|tea-sdlc:code-reviewer> --open-findings <n>
```

`<n>` counts findings neither fixed nor cleared, at any severity. The record is per `HEAD`; a later commit needs a new one. `gh pr create` stays blocked until it shows 0; findings still open after the re-review go to the user as explicit open items rather than another loop.

## Template placeholders

`${CLAUDE_PLUGIN_ROOT}/skills/requesting-code-review/code-reviewer.md`:
- `{AXIS}` — `spec`, `standards`, or `both` (fast path, ad-hoc review)
- `{WHAT_WAS_IMPLEMENTED}` — what was built
- `{PLAN_OR_REQUIREMENTS}` — what it should do (Spec axis: the spec files and the trace output)
- `{REVIEW_SCOPE}` — mode, owned paths, baseline and checked state or manifest
- `{BASE_SHA}`, `{HEAD_SHA}` — verified refs, only for a committed range
- `{FIRST_ID}` — the first finding number to use (1, or the next free one on a re-review)
- `{DESCRIPTION}` — brief summary

Choose model and effort from `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md` (`tea-sdlc:code-reviewer` defaults to `opus`, medium; high for a large or trust-boundary diff).

## Example (review stage)

```
[Spec refunds is at verified; code committed]

[One message, two dispatches]
  tea-sdlc:code-reviewer  AXIS: spec       inputs: requirements.md, design.md, contracts/, `aidlc trace refunds`
  tea-sdlc:code-reviewer  AXIS: standards  inputs: security.md, REVIEW.md

[Returns]
  Spec:      - [ ] S1 (must): RFD-1 second criterion is not implemented at src/refunds/api.ts:41 (confidence: high)
  Standards: - [ ] Q1 (should): repository leaks the ORM entity at src/refunds/repo.ts:12 (confidence: medium)
             - [ ] Q2 (nit): rename `amt` at src/refunds/model.ts:8 (confidence: low)

[review.md written with both sections as returned]
[S1 and Q1 fixed, Q2 cleared (matches the PSP field name, design.md §2); aidlc verify; diff-only re-review: no new findings]
[aidlc stamp refunds review; aidlc advance refunds reviewed → pre-PR record written]
[tea-sdlc:shipping]
```

## Rules

- Never skip a review the routing tier requires; never merge or re-rank the two axes.
- Fix must and should findings before moving on; fix nits too or clear each with evidence.
- Review results name the checked state and scope and carry status, evidence paths and exit-criteria checks per `${CLAUDE_PLUGIN_ROOT}/rules/subagent-return-format.md`. A file changed after review invalidates only the affected scope; recheck it before carrying the verdict forward.
