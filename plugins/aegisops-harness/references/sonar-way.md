# SonarQube "Sonar way"

All implementation agents write code that passes the Sonar way gate on the first scan. The project's `sonar-project.properties`, custom gate/profile, `NOSONAR` conventions and CI config override this file; the server or SonarLint is the source of truth for rule text.

## Gate (new code)
| Condition | Required |
|---|---|
| Reliability / Security / Maintainability | A (no new bugs, vulnerabilities, blocker/high smells) |
| Security hotspots reviewed | 100%; flag each to the dispatcher, never dismiss silently |
| Coverage on new code | ≥ 80% (from TDD, not added afterwards) |
| Duplicated lines on new code | ≤ 3% |

## Rules to write to
Cognitive complexity ≤ 15 per function (S3776); ≤ 7 parameters (S107); a literal used 3+ times becomes a constant (S1192); no nested ternaries, duplicated functions, unused code, commented-out code, empty blocks, committed `TODO`/`FIXME` (S1135), hardcoded credentials, unhandled nulls or unclosed resources.

## Verification
1. Scanner or SonarLint configured → run the project's scan and fix new issues before returning. Never install or configure a server unprompted.
2. No scanner → self-review the diff against these rules and return `Sonar way: self-reviewed, scan not run`.
3. Never suppress (`NOSONAR`, `@SuppressWarnings`, `eslint-disable`) to pass; report a false positive with rule key and `path:line`.
4. New code only: report notable legacy findings, don't fix untouched code.
