---
name: incident-to-eval
description: Turn a revert, rollback or production incident caused by a merged change into a regression case for review quality. Use when a commit is reverted, a rollback happens, or the user asks to add an incident to the review eval set.
---

# Incident to eval

0. Reverted commit never reached a shared branch → no incident; say so in one line.
1. Identify the PR or commit, the defect and when it was introduced.
2. Why review missed it: no test, absent from `REVIEW.md`, or misread; "unknown" if so.
3. Add one case to the project's review eval set (e.g. `evals/review/`, its conventions): input = offending diff or minimal fixture, expected = the finding or a pass. Redact PII, credentials and request bodies (`${CLAUDE_PLUGIN_ROOT}/references/data-privacy-patterns.md`). No eval set → add the miss to `REVIEW.md` "Known misses", skip step 5, say no baseline exists.
4. Close the gap: reviewer prompt, `REVIEW.md` or a test.
5. Run the full case set against the previous baseline; a reviewer, prompt or tool change must not lower the pass rate.
6. Report the case path (or `REVIEW.md` entry), baseline and new pass rates, and the output path.

Scope: review quality on product code; agent and command assets are measured by `/eval-upgrade`.
