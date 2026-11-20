---
name: requesting-code-review
description: Use when work needs review before merge or a PR ("get it reviewed", "review my changes"), or when a full-workflow spec reaches `verified` — the review stage runs two separate reviews in parallel (Spec axis, Standards axis), writes their findings to review.md, then `aidlc stamp` and `aidlc advance reviewed`, which records the pre-PR pass. Fast path runs the built-in code-review skill once on the diff (rules/pre-pr-review.md). (tea-sdlc — follows the routing tiers and hook gates)
---

# Requesting Code Review

The reviewer works in a fresh context from the inputs you hand it, never your session history.

| Situation | Path |
|---|---|
| Full-workflow spec at `verified` | §2 Review stage |
| Fast path, or no spec folder | §3 Fast path pass |
| One task inside the build stage | per-task templates of `tea-sdlc:subagent-driven-development` |
| Optional review (stuck, before a refactor, after a hard bug) | §3 without recording it |

## 1. Review scope

Pick one `REVIEW_SCOPE` and record its checked state:
- **Committed range:** verified base and head refs; never assume `HEAD~1` is the work.
- **Pending Git work:** staged + unstaged diffs + untracked owned files (deletions and renames included), with content hashes so drift is detectable. Collect names NUL-safe: `git diff --name-only --no-renames -z`, the same with `--cached`, `git ls-files --others --exclude-standard -z`; pass paths as arguments, never as interpolated shell.
- **Non-Git work:** manifest of owned files with original and changed copies and hashes.

Exclude unrelated user or other-agent changes from the claimed work.

## 2. Review stage (full workflow)

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`, `<f>` = spec folder or slug; you run it. Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `review.md`.

a. `aidlc status` shows the spec at `verified`. Commit the code first (the pre-PR record is tied to `HEAD`).

b. **One message, parallel, each axis exactly once:**

| Dispatch | Inputs |
|---|---|
| `tea-sdlc:code-reviewer`, `AXIS: spec` | `requirements.md`, `design.md`, `contracts/`, output of `aidlc trace <f>`, the scope |
| `tea-sdlc:code-reviewer`, `AXIS: standards` | `security.md`, project `REVIEW.md` and conventions, the scope |
| `tea-sdlc:qa-subagent` | `plan.md`, `aidlc trace <f>`, the scope; its verdict fills `## QA` |

Both reviewers get the template `${CLAUDE_PLUGIN_ROOT}/skills/requesting-code-review/code-reviewer.md`; they run on `sonnet` (effort medium; high for a large or trust-boundary diff).

c. **Write `review.md`:** frontmatter `reviewers: spec=<agent> standards=<agent>`, `## Spec` and `## Standards` holding each reviewer's lines exactly as returned, `## QA` with the verdict. Never merge across axes, change a severity, reorder or drop a finding; disagreement is a `cleared:` with evidence. An axis with no findings keeps its heading.

d. **Close every finding** (`tea-sdlc:receiving-code-review`): `— fixed: <where>` or `— cleared: <evidence>`. Fix QA blockers in the same round.

e. **Re-verify, then at most one re-review:** `aidlc verify <f> --cmd "<full suite>"` (the code changed). Then ONE diff-only re-review of the fixes by a single `tea-sdlc:code-reviewer` with `AXIS: both`, given the open findings and the fix diff, `FIRST_ID` = the next free number of each prefix. Close what it adds the same way. No second full round, no further loop. Skip it when nothing changed code.

f. **Stamp and advance:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" stamp <f> review
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> reviewed
```

On pass the pre-PR record for `HEAD` is written and `gh pr create` is allowed. Leave `review.md`, `README.md`, `ledger.md` uncommitted; `tea-sdlc:shipping` opens the PR from this `HEAD`, then commits them.

g. **Still open after the re-review** → the gate blocks. A decision only the user can make (accept a risk, change a requirement): ask once with the finding and options; the answer closes it as `cleared: accepted by <name> — <reason>`. Real rework: `aidlc advance <f> building --back --reason "<finding>"`.

Then `tea-sdlc:shipping`.

## 3. Fast path pass

1. Run verification and show its output.
2. Run the built-in `code-review` skill once on the diff, no subagent (effort `low` in lean mode, default in full mode). Unavailable → dispatch `tea-sdlc:code-reviewer` with the template and `AXIS: both`. On a trust-boundary change the review also checks the security pass: the threats listed, their tests, no PII or secrets in logs.
3. Fix each finding, or clear it with a one-line evidence-backed reason (a note alone does not clear it). Push back with technical reasoning when the reviewer is wrong.
4. One diff-only re-review of the fixes, commit, record the pass for the new `HEAD`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <code-review|tea-sdlc:code-reviewer> --open-findings <n>
```

`<n>` = findings neither fixed nor cleared, any severity. A finding deferred to the human reviewer counts as cleared only when the PR description lists it with the reason. The record is per `HEAD`; `gh pr create` stays blocked until it shows 0. Findings open after the re-review go to the user as explicit open items, not another loop.

## Template placeholders (`code-reviewer.md`)

`{AXIS}` spec | standards | both · `{WHAT_WAS_IMPLEMENTED}` · `{PLAN_OR_REQUIREMENTS}` (Spec axis: spec files + trace output) · `{REVIEW_SCOPE}` mode, owned paths, checked state or manifest · `{BASE_SHA}` `{HEAD_SHA}` committed range only · `{FIRST_ID}` first number per prefix: `S1, Q1`, or the next free ones on a re-review · `{DESCRIPTION}`.

Fix must and should findings before moving on; fix nits or clear each with evidence. A file changed after review invalidates only the affected scope; recheck it before carrying the verdict forward.
