---
name: systematic-debugging
description: Use when a bug, failing test, error or unexpected behavior appears, before proposing or making a fix — reproduce it, trace the root cause, test one hypothesis at a time, then fix it with a failing test first (tea-sdlc — follows the routing tiers and hook gates)
---

# Systematic Debugging

Find the root cause before attempting a fix. Random fixes waste time and create new bugs; a fix aimed at the symptom masks the underlying issue.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

Until Phase 1 is complete, do not propose a fix.

## When to use

Any technical issue: test failures, production bugs, unexpected behavior, performance problems, build failures, integration issues.

It matters most when guessing is tempting: under time pressure, when a quick fix looks obvious, when the issue seems simple, when a previous fix did not work, or when you do not fully understand the issue. Simple bugs have root causes too, and the process is fast for them. Systematic debugging is faster than guess-and-check thrashing.

## The four phases

Complete each phase before moving to the next.

| Phase | Key activities | Exit condition |
|-------|---------------|----------------|
| 1. Root cause | Read errors, reproduce, check changes, gather evidence, trace data flow | You understand WHAT fails and WHY |
| 2. Pattern | Find working examples, compare | The differences are identified |
| 3. Hypothesis | Form one theory, test it minimally | Hypothesis confirmed, or a new one formed |
| 4. Implementation | Failing test, single fix, verify | Bug resolved, tests pass |

### Phase 1: Root cause investigation

1. **Read the error messages.** Read warnings and stack traces completely; note line numbers, file paths and error codes. They often contain the solution.
2. **Reproduce consistently.** Find the exact steps and check whether it happens every time. If it is not reproducible, gather more data instead of guessing.
3. **Check recent changes.** Git diff, recent commits, new dependencies, config changes, environment differences.
4. **Gather evidence across components.** When the system has several components (CI → build → signing, API → service → database), add diagnostic instrumentation before proposing fixes. At each component boundary:
   - log presence, counts, safe identifiers or explicitly redacted metadata;
   - never log raw environment values, credentials, PII, auth headers or payloads;
   - verify environment/config propagation with presence-only checks;
   - check state at each layer without exposing sensitive contents.

   Run once to see WHERE it breaks, then investigate that component.

   ```bash
   # One presence-only probe per boundary, then a single run
   echo "[workflow] API_TOKEN $([ -n "${API_TOKEN:-}" ] && echo present || echo missing)"   # in the CI step
   echo "[build]    API_TOKEN $([ -n "${API_TOKEN:-}" ] && echo present || echo missing)"   # in the build script
   # workflow: present, build: missing → the break is the workflow → build boundary
   ```

   **When the failure crosses two or more services** (an error raised in one service caused by a call to or from another), run the `debug-parallel` command yourself with the error text; do not ask the user to run it.
5. **Trace the data flow.** When the error is deep in the call stack, ask where the bad value originates and what called this with it, and keep tracing up to the source. Fix at the source, not at the symptom. See `root-cause-tracing.md` in this directory for the complete backward tracing technique.

### Phase 2: Pattern analysis

1. **Find working examples.** Locate similar working code in the same codebase.
2. **Compare against references.** When implementing a pattern, read the reference implementation completely, every line, before applying it. Partial understanding produces bugs.
3. **Identify differences.** List every difference between working and broken, however small. Do not assume one cannot matter.
4. **Understand dependencies.** Which components, settings, config and environment does it need, and what does it assume?

### Phase 3: Hypothesis and testing

1. **Form a single hypothesis.** Write it down, specifically: "I think X is the root cause because Y."
2. **Test minimally.** Make the smallest change that tests the hypothesis. One variable at a time.
3. **Verify before continuing.** Confirmed → Phase 4. Not confirmed → form a new hypothesis; do not stack more fixes on top.
4. **When you don't know,** say "I don't understand X". Research more or ask for help instead of pretending.

### Phase 4: Implementation

1. **Create a failing test case.** The simplest reproduction: an automated test if possible, a one-off script if there is no framework. For behavior changes, demonstrate the expected failure before the fix. For prose/config-only defects, use the applicable structural or isolated command check. Use `test-driven-development` for red-green checks and safe recovery; preserve pre-existing, user and other-agent changes.
2. **Implement a single fix.** Address the identified root cause, one change at a time. No "while I'm here" improvements or bundled refactoring; several changes at once hide which one worked.
3. **Verify the fix.** The test passes, no other tests break, and the issue is actually resolved. Use `verification-before-completion` before claiming success.
4. **If the fix doesn't work,** stop and count the fixes tried. Follow any applicable formal bound in `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md` first; this heuristic does not extend it. Below that bound, return to Phase 1 and re-analyze with the new information. At 3 failed exploratory hypotheses (or earlier if the formal bound is reached), stop and reassess the approach (step 5) before any fourth fix.
5. **After 3 failed fixes, question the architecture.** Signs of an architectural problem: each fix reveals new shared state, coupling or a problem in a different place; fixes need massive refactoring; each fix creates new symptoms elsewhere. Ask whether the pattern is fundamentally sound, whether you are keeping it out of inertia, and whether to refactor the architecture instead of fixing symptoms.

   Repeated failures are evidence to reassess the approach, not proof that the architecture is wrong. If the next step is a decision only the user can make (change the architecture, accept a workaround, drop the requirement), ask for it and report the tested hypotheses and unresolved evidence in that same message. Otherwise pick the next approach yourself and continue.

## Signs you skipped the process

Any of these means: stop and return to Phase 1. If 3+ fixes have failed, go to Phase 4, step 5.

| Thought or signal | What it means |
|-------------------|---------------|
| "Quick fix for now, investigate later" / "Just try this first" | The first fix sets the pattern. Investigate first. |
| "Just try changing X and see" / "It's probably X" / "I see the problem, let me fix it" | Seeing a symptom is not understanding the root cause. |
| "Add multiple changes, run tests" | You cannot isolate what worked, and it causes new bugs. |
| "Skip the test, I'll verify manually" / "I'll write the test after the fix works" | Untested fixes don't stick. The failing test comes first. |
| "I don't fully understand but this might work" | Say what you don't understand and investigate it. |
| "The pattern says X but I'll adapt it" / "The reference is too long" | Read the reference completely before adapting it. |
| Listing fixes, or proposing solutions, before tracing the data flow | Phase 1 is not done. |
| "One more fix attempt" after 2+ failures / each fix reveals a new problem elsewhere | Likely an architectural problem. Question the pattern (Phase 4, step 5). |
| The user asks "Is that not happening?" / "Will it show us...?" | You assumed without verifying; add evidence gathering. |
| The user says "Stop guessing" / "Ultrathink this" / "We're stuck?" | You are proposing fixes without understanding; question fundamentals, not symptoms. |

## When the process finds no root cause

If the investigation shows the issue is truly environmental, timing-dependent or external, the process is complete. Document what you investigated, implement appropriate handling (retry, timeout, error message) and add monitoring or logging for future investigation. Most "no root cause" cases are incomplete investigations, so check that first.

## Supporting techniques

These techniques are part of systematic debugging and available in this directory:

- **`root-cause-tracing.md`** - Trace bugs backward through call stack to find original trigger
- **`defense-in-depth.md`** - Add validation at multiple layers after finding root cause
- **`condition-based-waiting.md`** - Replace arbitrary timeouts with condition polling
- **`find-polluter.sh`** - Find the test that creates unwanted files or state: `bash "${CLAUDE_PLUGIN_ROOT}/skills/systematic-debugging/find-polluter.sh" '.git' './src/**/*.test.ts'` (assumes `npm test <file>`; exit 2 means no test files matched)

**Related skills:** `test-driven-development` for the failing test case (Phase 4, step 1); `verification-before-completion` to verify the fix worked before claiming success.
