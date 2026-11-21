# Subagent return format

The final message of every dispatched subagent carries three things, in any shape (prose, markdown, XML):

1. **Status**, keyword verbatim:

| Status | When | Also include |
|---|---|---|
| `DONE` | all exit criteria met with evidence | summary |
| `DONE_WITH_CONCERNS` | done, with doubts worth reading before proceeding | the concerns |
| `NEEDS_CONTEXT` | inputs missing or ambiguous and the dispatcher can supply them | what is needed, next step |
| `BLOCKED` | scope, spec, approach or environment must change (incl. a review-loop limit hit) | what was tried, the blocker, failure category (transient/environment vs scope/spec/approach), partial results and what they cover, next step |

2. **Evidence paths** the dispatcher can Read: changed files (not diffs); test/build output in a file, with the exact command; persisted docs. No long pasted output.
3. **One line per exit criterion** from the prompt: `met` or `not met — reason`.

- A check that ran and found nothing is `DONE`; a tool failure is not an empty result.
- Every count names what was counted and the command that produced it (e.g. `20 baseline entries — grep -vc '^#' baseline.txt`).
- Implementers also list the requirement IDs covered and the tests proving each; test names carry the ID (e.g. `RFD-1 rejects over-capture`).
- tea-sdlc:security-engineer-subagent returns only its `### Security` subsection (it writes no files); never paste a contract into a return.

## Dispatcher
- Read every cited path (missing → `BLOCKED` whatever the claim), the decisive results and open concerns. Report what the subagent said, unreshaped.
- Criterion lines missing → re-dispatch for completeness; still missing on the second try → diagnose the prompt.
- `DONE_WITH_CONCERNS` → address material concerns first. `NEEDS_CONTEXT` → supply, amend, re-dispatch. `BLOCKED` → find the root cause; split, simplify or change approach; user-level → escalate.
- Never invent an agent result when dispatch is unavailable.
