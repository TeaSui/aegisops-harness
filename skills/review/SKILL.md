---
name: review
description: Stage 5 of the backend lifecycle (/aegisops-harness:review, run by /aegisops-harness:aidlc) — Spec-axis and Standards-axis reviews by aegisops-harness:code-reviewer plus aegisops-harness:qa-subagent in parallel, findings closed in review.md, then aidlc stamp and advance reviewed, which records the pre-PR pass. §3 is the single pre-PR pass /aegisops-harness:fix runs on its diff.
disable-model-invocation: true
---

# Requesting Code Review

The reviewer works in a fresh context from the inputs you hand it, never your session history.

| Situation | Path |
|---|---|
| Spec at `verified` | §2 Review stage |
| `/aegisops-harness:fix`, or no spec folder | §3 Pre-PR pass |
| One task inside the build stage | per-task templates of `/aegisops-harness:build` |
| Optional review (stuck, before a refactor, after a hard bug) | §3 without recording it |

## 1. Review scope

Pick one `REVIEW_SCOPE` and record its checked state:
- **Committed range:** verified base and head refs; never assume `HEAD~1` is the work.
- **Pending Git work:** staged + unstaged diffs + untracked owned files (deletions and renames included), with content hashes so drift is detectable. Collect names NUL-safe: `git diff --name-only --no-renames -z`, the same with `--cached`, `git ls-files --others --exclude-standard -z`; pass paths as arguments, never as interpolated shell.
- **Non-Git work:** manifest of owned files with original and changed copies and hashes.

Exclude unrelated user or other-agent changes from the claimed work.

## 2. Review stage

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`, `<f>` = spec folder or slug; you run it. Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `review.md`.

a. `aidlc status` shows the spec at `verified`. Commit the code first (the pre-PR record is tied to `HEAD`). **Re-entry** (`review.md` already exists: back from `building --back`, a NO-GO or a CI fix): skip b; run ONE diff-only review of the changes since the last review stamp (`aegisops-harness:code-reviewer`, `AXIS: both`, next free IDs), append its lines under the axes, then d–f.

b. **One message, parallel, each axis exactly once:**

| Dispatch | Inputs |
|---|---|
| `aegisops-harness:code-reviewer`, `AXIS: spec` | `spec.md`, `tickets.md`, cited ADRs, `contracts/`, output of `aidlc trace <f>`, the scope |
| `aegisops-harness:code-reviewer`, `AXIS: standards` | `spec.md` `### Security`, project `REVIEW.md` and conventions, `GLOSSARY.md`, the scope |
| `aegisops-harness:qa-subagent` | `spec.md` Testing Decisions, `tickets.md`, `aidlc trace <f>`, the scope, the running target / base URL when a service is up (authorizes live API checks); its verdict fills `## QA` |

Both reviewers get the template `${CLAUDE_PLUGIN_ROOT}/skills/review/code-reviewer.md`; they run on `sonnet` (effort medium; high for a large or trust-boundary diff).

c. **Write `review.md`:** frontmatter `reviewers: spec=<agent> standards=<agent>`, `## Spec` and `## Standards` holding each reviewer's lines exactly as returned, `## QA` with the verdict. Never merge across axes, change a severity, reorder or drop a finding; disagreement is a `cleared:` with evidence. An axis with no findings keeps its heading.

d. **Close every finding** (`/aegisops-harness:receiving-code-review`): `— fixed: <where>` or `— cleared: <evidence>`. Fix QA blockers in the same round.

e. **Re-verify, then at most one re-review:** `aidlc verify <f> --cmd "<full suite>"` (the code changed). Then ONE diff-only re-review of the fixes by a single `aegisops-harness:code-reviewer` with `AXIS: both`, given the open findings and the fix diff, `FIRST_ID` = the next free number of each prefix. Close what it adds the same way. No second full round, no further loop. Skip it when nothing changed code.

f. **Stamp and advance:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" stamp <f> review
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> reviewed
```

On pass the pre-PR record for `HEAD` is written and the PR gate (`pr.py create`, `gh pr create`) allows the PR. Leave `review.md`, `README.md`, `ledger.md` uncommitted; `/aegisops-harness:ship` opens the PR from this `HEAD`, then commits them.

g. **Still open after the re-review** → the gate blocks. A decision only the user can make (accept a risk, change a story): ask once with the finding and options; the answer closes it as `cleared: accepted by <name> — <reason>`. Real rework: `aidlc advance <f> building --back --reason "<finding>"`.

Then `/aegisops-harness:ship`.

## 3. Pre-PR pass (no spec)

1. Run verification and show its output.
2. Run the built-in `code-review` skill once on the diff, no subagent (effort `low`; default on a trust-boundary change). Unavailable → dispatch `aegisops-harness:code-reviewer` with the template and `AXIS: both`. On a trust-boundary change the review also checks the security pass: the threats listed, their tests, no PII or secrets in logs.
3. Fix each finding, or clear it with a one-line evidence-backed reason (a note alone does not clear it). Push back with technical reasoning when the reviewer is wrong.
4. One diff-only re-review of the fixes, commit, record the pass for the new `HEAD`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <code-review|aegisops-harness:code-reviewer> --open-findings <n>
```

`<n>` = findings neither fixed nor cleared, any severity. A finding deferred to the human reviewer counts as cleared only when the PR description lists it with the reason. The record is per `HEAD`; `gh pr create` stays blocked until it shows 0. Findings open after the re-review go to the user as explicit open items, not another loop.

## Template placeholders (`code-reviewer.md`)

`{AXIS}` spec | standards | both · `{WHAT_WAS_IMPLEMENTED}` · `{PLAN_OR_REQUIREMENTS}` (Spec axis: spec files + trace output) · `{REVIEW_SCOPE}` mode, owned paths, checked state or manifest · `{BASE_SHA}` `{HEAD_SHA}` committed range only · `{FIRST_ID}` first number per prefix: `S1, Q1`, or the next free ones on a re-review · `{DESCRIPTION}`.

Fix must and should findings before moving on; fix nits or clear each with evidence. A file changed after review invalidates only the affected scope; recheck it before carrying the verdict forward.
