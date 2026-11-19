---
name: test-driven-development
description: Use before writing production code for a new behavior or a bug fix — write the test, run it and show it failing for the expected reason, then make it pass; prose and config changes get proportionate structural checks instead (tea-sdlc — follows the routing tiers and hook gates)
---

# Test-Driven Development (TDD)

Write the test first. Watch it fail. Write the minimal code that makes it pass.

**Gate (check before every production edit):** have you run the new test and seen it fail for the expected reason in this session? If not, run it now and show the output before touching production code. Writing the test first is not enough; the failing run is the evidence. In a repository you cannot run tests in, say so and state which check stands in for it. The `tdd-gate` hook backs this up: the first production edit of a session without a recorded failing test run is blocked once. Retrying the same edit passes, for changes that need no new test (docs, config, refactor under existing coverage).

A regression test needs evidence that it detects the missing behavior, followed by a passing result after the fix.

## When to use

- New runtime behavior and bug fixes: red-green-refactor.
- Refactoring: first establish regression coverage for the affected behavior and keep it passing. Add a failing test when you expose a missing behavior.
- Prose, formatting, generated output or configuration-only changes: use the checks that can detect the actual defect (parsing, schema or reference checks, lint, a build, an isolated command fixture). Configuration that changes runtime behavior still needs a behavior check when practical. Do not invent tests that merely repeat the implementation.

Reuse the existing authorization and the accepted plan. Follow explicit user constraints. These applicability choices need no new permission gate and no routine exception-approval loop. If the required check is unavailable, state the gap and use the best applicable evidence; never claim a skipped check passed.

## The Iron Law

```
NEW BEHAVIOR: DEMONSTRATE A RELEVANT FAILURE, THEN IMPLEMENT AND VERIFY GREEN
```

### Recover safely when implementation came first

1. Inspect the current diff and ownership before changing anything. Preserve pre-existing, user and other-agent edits, including edits in the same file.
2. Write the test from the requirement, independently of the implementation details.
3. Demonstrate the expected failure against the pre-change behavior in an isolated copy/worktree or by temporarily reversing only your known owned patch. Preserve a recoverable copy, including new/untracked files, and restore it afterward. Never use blanket deletion, reset or checkout as TDD recovery.
4. If edits are interleaved or provenance is uncertain, keep the work intact and use an isolated reproduction. If you cannot safely establish red, report that limitation; do not label a passing-only test as a completed red-green cycle.
5. Implement or restore the smallest owned change and verify green, then run the relevant regression checks.

The goal is evidence that the test catches the defect, not erasing work to recreate the order of a past session.

## Red-Green-Refactor

RED → verify red → GREEN → verify green → REFACTOR (stay green) → next test. A wrong failure sends you back to RED; a test that does not pass sends you back to GREEN.

### 1. RED: write one failing test

One minimal test showing what should happen:
- one behavior (an "and" in the name means split it);
- a clear name that describes the behavior;
- it shows the desired API and intent;
- real code, no mocks unless unavoidable.

```typescript
// Good: clear name, real behavior, one thing
test('retries failed operations 3 times', async () => {
  let attempts = 0;
  const operation = () => { attempts++; if (attempts < 3) throw new Error('fail'); return 'success'; };
  expect(await retryOperation(operation)).toBe('success');
  expect(attempts).toBe(3);
});
// Bad: test('retry works') that only asserts a jest.fn() mock was called 3 times. Vague name, tests the mock.
```

### 2. Verify RED: watch it fail

Always run it: `<project-supported command selecting this test file>`. A valid failing test:
- fails, not errors;
- fails with the expected message;
- fails because the behavior is missing, not because of a typo.

If you cannot explain why it failed, it is not valid red yet.

- **Test passes?** Check whether the requirement is already satisfied or the test misses the change. For a new regression test, establish red with the recovery steps above; do not force an unrelated failure.
- **Test errors?** Fix the error and re-run until it fails correctly.

### 3. GREEN: minimal code

Write the simplest code that passes the test. Do not add features, refactor other code or "improve" beyond the test. Options nobody asked for (configurable retries, backoff strategies, callbacks) are YAGNI.

### 4. Verify GREEN: watch it pass

Run it again. Confirm the test passes, other tests still pass, and the output is pristine (no errors, no warnings).
- **Test fails?** Fix the code, not the test.
- **Other tests fail?** Fix them now.

### 5. REFACTOR

After green only: remove duplication, improve names, extract helpers. Keep the tests green and add no behavior. Then write the next failing test for the next behavior.

### Example: bug fix

Bug: an empty email is accepted.

```typescript
test('rejects empty email', async () => {                  // RED
  expect((await submitForm({ email: '' })).error).toBe('Email required');
});
// Verify RED:   $ npm test  ->  FAIL: expected 'Email required', got undefined
function submitForm(data: FormData) {                      // GREEN
  if (!data.email?.trim()) return { error: 'Email required' };
  // ...
}
// Verify GREEN: $ npm test  ->  PASS. REFACTOR: extract validation if more fields need it.
```

The same applies to any bug found while debugging: a failing test that reproduces it proves the fix and prevents the regression. For a prose or config defect, use the applicable structural or isolated check described above.

## Excuses and what is true

Each of these means: stop extending the unverified behavior, preserve the current work, and follow the recovery steps.

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Choose the smallest check that detects the relevant behavior defect. |
| "I'll test after" / "Tests after achieve the same goals" / "It's the spirit, not the ritual" | A test written after the code passes at once, which proves nothing: it may test the wrong thing or the implementation, and you never saw it catch the bug. Tests-after answer "what does this do?", biased by what you built; tests-first answer "what should this do?" and surface edge cases before implementing. |
| "I already tested it manually" / "Manual is faster" | Manual testing is ad hoc: no record, no re-run when the code changes, easy to miss cases. You will re-test every change. |
| "The implementation is already written" / "Keep it as reference" / "Already spent hours on it" | Preserve it and demonstrate the failure against pre-change behavior with the recovery steps. A passing-only test is not a red-green cycle; do not present tests written afterward as tests that failed first. |
| "Copy the implementation into the assertion" | Derive assertions from requirements so they can expose an incorrect implementation. |
| "Need to explore first" | Isolate exploration from user work; use requirement-based checks for the final behavior. |
| "TDD is dogmatic / will slow me down" | It finds bugs before commit, prevents regressions, documents behavior and makes refactoring safe. Debugging after is slower. |
| "Existing code has no tests" | You are changing it, so add tests for the behavior you touch. |
| "Just this once" / "This case is different" | The exceptions are the ones listed under When to use. Everything else follows the cycle. |

## When stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test | Write the wished-for API. Write the assertion first. Ask the user only when the expected behavior is theirs to decide, and list the test approaches you tried in that same message. |
| Test too complicated / hard to write | The design is too complicated: hard to test means hard to use. Simplify the interface. |
| Must mock everything | The code is too coupled. Use dependency injection. |
| Test setup huge | Extract helpers. Still complex? Simplify the design. |

When adding mocks or test utilities, read @testing-anti-patterns.md to avoid common pitfalls:
- testing mock behavior instead of real behavior;
- adding test-only methods to production classes;
- mocking without understanding dependencies.

## Verification checklist

Before marking work complete:

- [ ] New or changed behavior has meaningful coverage
- [ ] Observed the expected regression failure before the fix (or safely against pre-change behavior)
- [ ] Each test failed for the expected reason (behavior missing, not a typo)
- [ ] Wrote minimal code to pass each test
- [ ] Applicable checks pass for the reviewed scope; skipped/unavailable checks are explicit
- [ ] New failures and warnings are investigated; pre-existing issues are distinguished
- [ ] Tests use real code (mocks only if unavoidable)
- [ ] Edge cases and errors covered

If a box is unmet, report the precise gap and address it within the owned scope. Do not delete unrelated work or claim unexecuted checks passed.

```
Behavior change → expected failure demonstrated, then green
Prose/config-only change → applicable structural or isolated checks
Every path → preserve existing work and state the actual evidence
```
