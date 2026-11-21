---
name: test-driven-development
description: Red-green-refactor before any production code — the new test run and shown failing for the expected reason, then made to pass; prose and config changes get proportionate structural checks. Read by /tea-sdlc:build, /tea-sdlc:fix and /tea-sdlc:receiving-code-review.
disable-model-invocation: true
user-invocable: false
---

# Test-Driven Development

**Hard rule:** RED-GREEN-REFACTOR, and before any production edit the new test has been run in this session and shown failing for the expected reason (it fails, not errors; the behavior is missing, not a typo). Show that output. A written but unrun test is not evidence. If tests cannot run in this repository, say so and name the check that stands in.

The `tdd-gate` hook blocks the first production edit of a session without a recorded failing run, once; retrying the same edit passes, for changes that need no new test (docs, config, refactor under existing coverage).

## What evidence each change needs

| Change | Evidence |
|---|---|
| New behavior, bug fix | RED → GREEN → REFACTOR; a regression test is shown failing before the fix and passing after |
| Refactor | regression coverage of the affected behavior first, green throughout; a missing behavior found on the way gets a failing test first |
| Prose, formatting, generated output, config only | the check that detects the actual defect (parse, schema or reference check, lint, build, isolated command fixture); config that changes runtime behavior also gets a behavior check when practical. No tests that restate the implementation |

Untested existing code you change gets tests for the behavior you touch. These choices need no extra permission. A check that cannot run is named as a gap with the best evidence used instead; never report a skipped check as passed.

## Seams

Tests live at seams: the public interface where behaviour is observed without reaching inside. Use the seams agreed in the spec's Testing Decisions (no spec: the highest existing seam, else the fewest new ones, ideally one; state it in one line). Never test internals or private methods; verify through the interface, not a side channel (querying the database instead of calling it). Expected values come from the story or a worked example, never recomputed the way the code does (tautological). Vertical slices: one test → one implementation → repeat; never all tests first. With a spec, name each test with its story ID (`RFD-3`); use glossary terms.

## Cycle

1. **RED:** one test, one behavior, named for the behavior, real code (mocks only when unavoidable), assertions derived from the story or requirement, never copied from the implementation.
2. **Verify RED.** Passes at once → the behavior exists or the test misses it; fix the test, never force an unrelated failure. Errors → fix the error until it fails correctly. A failure you cannot explain is not valid red.
3. **GREEN:** the simplest code that passes. No unrequested options (YAGNI), no unrelated refactor.
4. **Verify GREEN:** this test and the others pass, output clean (no new errors or warnings). A failure → fix the code, not the test.
5. **REFACTOR** on green only, adding no behavior. Then the next failing test.

Cannot see how to test it → write the wished-for API and the assertion first. Ask the user only when the expected behavior is theirs to decide, listing the approaches tried.

## Implementation already written

Preserve it. Write the test from the requirement, then show it failing against the pre-change behavior: in an isolated copy or worktree, or by temporarily reversing only your own known patch (keep a recoverable copy including untracked files; restore it after). Never use blanket delete, reset or checkout as recovery. With interleaved edits or unclear provenance use an isolated reproduction; if red cannot be established safely, report that, and never present a passing-only test as a red-green cycle.

## Mocks and test code

- Assert real behavior, never a mock's presence (`*-mock` test IDs).
- No test-only methods on production classes; cleanup lives in test utilities.
- Before mocking, know which side effects of the real method the test relies on; mock the slow or external layer beneath it. Unsure → run against the real implementation first.
- Mock data mirrors the complete real schema, not only the fields this test reads.
- Mock setup outweighs the test, or everything must be mocked → use an integration test or simplify the design (dependency injection).

## Done when

- Every new or changed behavior has a test seen failing for the right reason, then passing; edge cases and error paths are covered.
- Applicable checks pass; skipped ones are named; new failures and warnings are investigated and pre-existing ones distinguished.
