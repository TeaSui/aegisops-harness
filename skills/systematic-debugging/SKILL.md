---
name: systematic-debugging
description: Root-cause debugging before any fix — reproduce, trace to the source, test one hypothesis at a time, then fix with a failing test first; Read by /tea-sdlc:fix, and by build when a test fails for an unexplained reason or a fix fails twice.
disable-model-invocation: true
user-invocable: false
---

# Systematic Debugging

No fix, and no proposed fix, before the root cause is found. Applies to every failure, simple ones included. Phases run in order.

## 1. Root cause

1. Read the whole error, warnings and stack trace (file, line, code).
2. Reproduce reliably: exact steps, every time? Not reproducible → gather more data, do not guess.
3. Check what changed: diff, recent commits, dependencies, config, environment.
4. Isolate:
   - Regression with a known-good commit → `git bisect`.
   - A test leaves files or state behind → `bash "${CLAUDE_PLUGIN_ROOT}/skills/systematic-debugging/find-polluter.sh" '<path that appears>' '<test glob>'`. It runs each test file alone with `npm test <file>` (adapt that line for other runners); exit 0 = no polluter, 1 = found, 2 = no test matched or the path existed before the first run.
   - Several components (CI → build → signing, API → service → DB) → one probe per boundary, one run, then investigate the boundary that breaks. Probes log presence, counts and safe IDs only: never raw env values, secrets, PII, auth headers, payloads or absolute user paths. In tests use `console.error` (loggers may be suppressed) and log before the dangerous operation.
5. Trace backward from the bad value (what called this with it?) to the original trigger. Fix at the source, never where the symptom appears. Cannot trace by reading → log a sanitized stack (`new Error().stack`, project-relative frames only) just before the failing operation.

## 2. Pattern

Find similar working code. Read any reference implementation completely before adapting it. List every difference between working and broken, however small, plus the config, environment and assumptions it depends on.

## 3. Hypothesis

Write one hypothesis: "X is the root cause because Y". Test it with the smallest change, one variable at a time. Not confirmed → a new hypothesis; never stack fixes. Say "I don't understand X" and investigate rather than guess.

## 4. Fix

1. Regression test first (`skills/test-driven-development/SKILL.md`): show it failing for this bug. Prose/config defect → the structural or isolated check that detects it. Preserve pre-existing, user and other-agent changes.
2. One change at the root cause; no bundled refactors or "while I'm here" edits.
3. Verify: the test passes, nothing else breaks, the symptom is gone (`/tea-sdlc:verify` before claiming it).
4. When invalid data caused it, validate at each layer it crosses: entry point, business logic, environment guard (e.g. refuse destructive operations outside tmpdir under test), debug logging.
5. Fix failed → back to §1 with the new evidence. **After 3 failed fixes, stop before a fourth** and question the architecture (each fix exposes new shared state or coupling, or symptoms move elsewhere). A subagent stops earlier: 2 failed attempts on the same issue → return BLOCKED. If the next step is the user's decision (change the architecture, accept a workaround, drop the requirement), ask once, listing the tested hypotheses and open evidence; otherwise choose the next approach and continue.

## Timing and flakiness

Replace arbitrary sleeps with condition polling: poll about every 10 ms, always with a timeout that names what was awaited, re-read state inside the loop. A fixed delay is allowed only for timed behavior (debounce, ticks): first wait for the triggering condition, derive the delay from known timing, comment why.

## No root cause found

Most "environmental" verdicts are incomplete investigations; check that first. If it truly is environmental, timing-dependent or external: record what was investigated, add handling (retry, timeout, clear error) and logging or monitoring for next time.

Return to §1 whenever you catch yourself listing fixes before tracing the data flow, changing several things at once, or skipping the failing test, or the user says "stop guessing" or asks whether something is actually happening.
