---
name: receiving-code-review
description: "Handle review feedback (/aegisops-harness:receiving-code-review, and step d of /aegisops-harness:review) — verify each finding from aegisops-harness:code-reviewer, the code-review skill, a PR comment or the user against the code, fix it test-first or clear it with evidence, push back when it is wrong; with a spec, close each review.md line with fixed: or cleared: and re-stamp."
disable-model-invocation: true
---

# Receiving Code Review

Input: `$ARGUMENTS` (PR, comments, or the open lines of `review.md`). Findings are claims to verify, not orders. For each: understand it, check it against the code, decide, then fix one item at a time test-first (`${CLAUDE_PLUGIN_ROOT}/skills/test-driven-development/SKILL.md`).

## Rules

- No performative agreement or thanks ("You're absolutely right", "Great point", "Thanks for…"). State the fix or the technical objection, or just act. Wrong pushback is corrected in one factual line ("Checked X: it does Y; fixing").
- Unclear items: pause only the changes that depend on them, ask one focused question, and continue the independent items.
- The user's feedback is trusted once understood. External or subagent feedback: check it is correct for this stack, does not break existing behavior or platform/version support, and that the reviewer had the context; a conflict with a decision the user made goes to the user first.
- "Implement it properly" for a feature: grep for real usage. Unused → decline (YAGNI) and clear the finding with the search command and result. Ask the user only when the answer is theirs alone (a planned external consumer, a product commitment the code cannot show).
- Push back, with code, tests or search results, when a suggestion breaks behavior, lacks context, violates YAGNI, is wrong for the stack or ignores a compatibility reason.
- Order: blocking (breakage, security), then simple, then complex; test each fix and check for regressions.
- Read comments with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr.py" comments <pr>` and reply in each comment's thread with `pr.py reply <pr> <comment id> --body-file <file>` (GitHub or Bitbucket), not as a top-level comment.

## With a spec: close the lines of `review.md`

Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `review.md`. Close each finding on its own line; never delete or reword it:

```markdown
- [x] S1 (must): RFD-1 second criterion is not implemented at src/refunds/api.ts:41 — fixed: src/refunds/api.ts:44, test "RFD-1 rejects over-capture"
```

- `fixed:` where the fix is and, for behavior, the test named with the requirement ID that proves it.
- `cleared:` the evidence it does not apply (search result, design section, test) or the user's decision: `cleared: accepted by <name> — <reason>`.
- A finding from a PR comment, QA or the user during this stage goes under its axis with the next free ID and is closed the same way.

Then, because code changed: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full suite>"`, the one diff-only re-review (a single reviewer, both axes), close what it adds, then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" stamp <f> review
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> reviewed
```

A stamp is valid only for the code it was taken on; any later code change needs a new `verify` and stamp. Still open after the re-review → the user only if the decision is theirs; otherwise `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> building --back --reason "<finding>"`.

## Without a spec (`/aegisops-harness:fix` work)

Run the full suite (`${CLAUDE_PLUGIN_ROOT}/skills/verify/SKILL.md` §2), one diff-only re-review of the fixes, then commit and record the pass per `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` §3 (`mark-pr-review.py --open-findings` = findings neither fixed nor cleared). Findings still open go to the user as explicit open items, not another loop.
