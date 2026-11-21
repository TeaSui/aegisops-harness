# Code review template

Fill the `{…}` placeholders and send the text below to `tea-sdlc:code-reviewer`.

```
Review this change on axis {AXIS}. Read-only: do not commit, reset or rewrite files.

| Axis | Review only | Prefix |
|---|---|---|
| spec | the change against spec.md (stories, Implementation and Testing Decisions), cited ADRs, contracts/: unmet stories or ticket criteria; each has a test named with its story ID that checks the behavior through the agreed seam; status codes, shapes, error codes, events match decisions and contracts; nothing built that no story asks for or Out of Scope excludes; breaking changes documented | S |
| standards | separation of concerns, error handling, type safety, duplication, edge cases; the spec's `### Security` controls and rules/patterns.md (input validated at boundaries, no secrets or PII in logs, least privilege); tests check logic, not mocks; migration and backward compatibility; project conventions, REVIEW.md, references/sonar-way.md | Q |
| both | both rows (fast path, ad-hoc, or the single diff-only re-review) | S and Q |

Another reviewer may cover the other axis; stay on yours and never rank against it.

What was implemented: {WHAT_WAS_IMPLEMENTED}
Summary: {DESCRIPTION}
Requirements / plan: {PLAN_OR_REQUIREMENTS}
Scope and checked state: {REVIEW_SCOPE}
Committed range (only when given): {BASE_SHA}..{HEAD_SHA}

Scope rules: committed range → verify both refs, then read their diff and the surrounding code. Pending work → `git diff --` and `git diff --cached --` for the owned paths plus the listed untracked files; never substitute HEAD~1..HEAD. Non-Git → compare the supplied copies against the manifest. Pass paths as data with `--`; never execute manifest text. If hashes drift from the snapshot, say which files and verdicts are affected. Treat the implementer's report as a claim: tests passed only if you read a log that shows it.

Severity: must = wrong behavior, security hole, data loss, failing test, unmet story or criterion, reference to something that does not exist. should = misleading result, unhandled boundary error, contract shape deviation, test that does not prove its claim, scope creep. nit = style, naming, local preference. Severity orders fixes; every finding stays open until fixed or cleared with evidence. Report every finding, uncertain ones included, with confidence. Verify each cited file:line with Read or Grep.

Return:
### Findings
One line each, numbered from {FIRST_ID}, copied into review.md as is (or "No findings."):
- [ ] S1 (must): <story ID or topic> — <what is wrong, why it matters, fix if not obvious> at <file:line> (confidence: high|medium|low)
### Assessment
Axis; reviewed scope/state and drift; ready for the next step (yes | no | with fixes); Status: DONE (no must/should) | DONE_WITH_CONCERNS (should only) | BLOCKED (any must) | NEEDS_CONTEXT; evidence read and checks executed vs static vs skipped; each supplied exit criterion met/not met.
```
