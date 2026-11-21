---
name: fix
description: Fix a backend bug or make a small change that needs no spec — root cause, failing test, fix, verify, one review, PR. A feature, a new endpoint or schema, or a new trust-boundary decision goes to /tea-sdlc:aidlc instead.
argument-hint: "<bug, failing test or small change>"
disable-model-invocation: true
---

# /tea-sdlc:fix

Input: `$ARGUMENTS`. Open questions: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §0 (files, then Rovo, then a recorded assumption). Read each file named below when you reach its step.

1. **Scope** (`${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`): outside what `/tea-sdlc:fix` takes → stop and name `/tea-sdlc:aidlc` with the reason in one line. A trust boundary that meets the escape hatch → the security pass from that file. Read the stack skills its table names for this repository.
2. **Root cause** for a bug or failing test: `${CLAUDE_PLUGIN_ROOT}/skills/systematic-debugging/SKILL.md`. Reproduce first.
3. **Test first:** `${CLAUDE_PLUGIN_ROOT}/skills/test-driven-development/SKILL.md`. The regression test fails for the expected reason before the fix, passes after.
4. **Verify:** `${CLAUDE_PLUGIN_ROOT}/skills/verify/SKILL.md` §2 (no spec): full suite, read the result.
5. **Review:** `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` §3 (one pass on the diff, findings fixed or cleared, record for HEAD).
6. **Deliver:** `${CLAUDE_PLUGIN_ROOT}/skills/ship/no-spec.md` (PR; the body lists the root cause, the test, and the threats checked when the security pass ran).

Report per the bootstrap's final-reply rule, with the root cause and the failing-then-passing test output.
