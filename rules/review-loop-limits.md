# Review loop limits (full workflow)

The fast path has no review loops: one pre-PR pass plus one diff-only re-review. Any leaf dispatch: 2 failed fix attempts on the same issue → return `BLOCKED`. Debugging: 3 failed fixes → stop and question the approach.

## Per task in the build stage
- Max 2 fix rounds per review (spec compliance, code quality); max 4 review iterations per task in total.
- Round 2 still failing usually means a deeper problem: check that before patching again.
- At the limit the same implementer gets no further round. Re-dispatch the task once to a fresh implementer one model tier up (haiku → sonnet → opus → fable) with the findings and the failed approaches. If that fails too → split the task or ask the user.

## Review stage
Spec and Standards once each (in parallel with QA), then at most ONE diff-only re-review of the fixes by a single tea-sdlc:code-reviewer with `AXIS: both`.

## Convergence
- A re-review covers the fix diff only, unless the fix touched shared behaviour.
- Fix a bug class across the whole diff in one round, not instance by instance.
- Never re-raise a finding already fixed or cleared with a reason; cite the earlier round.
- A finding that survives two fix rounds is structural → escalate.

## Escalate
Stop and tell the user which task, what was tried and what keeps failing; propose split, simpler spec or different approach; wait for the decision.
