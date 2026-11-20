---
name: validate-feature
description: Use when asked to validate a whole branch or change set, or to check that the pending change is ready before opening a PR (or headless via scripts/validate.sh) — resolves the exact target, runs every applicable project check including integration/e2e prerequisites and a placeholder scan, and reports VALIDATED/PARTIAL/BLOCKED. For an ordinary completion claim use verification-before-completion.
---

# Validate feature

Not authorized by this workflow: starting services, installing dependencies, mutating HTTP requests, production access, seeding data.

1. **Target.** Use the commit, range, base or file list given (verify refs; say whether it is committed history or base-to-working-tree). Never default to the previous commit. Otherwise take all pending work: `git diff --name-only --no-renames -z`, `git diff --cached --name-only --no-renames -z`, `git ls-files --others --exclude-standard -z`; dedupe NUL-safely, note additions, renames, deletions, and record the file list with content hashes. Pass paths as arguments (with `--`), never interpolated into shell strings. Outside Git, use the given manifest. Nothing resolvable → ask; never validate unrelated history.
2. **Checks.** Discover the runner from project instructions, manifests, lockfiles and CI; use the installed one (no `npx` auto-download). Behaviour change: unit/regression + affected integration. Refactor: regression + build/type/lint. Prose/config: parse, schema, reference, lint (runtime tests if config changes behaviour). Service/API: integration/e2e only for a scoped safe target. Find tests by behaviour and imports, not basename. Mark each check required or N/A with a reason.
3. **Run** and read exit codes and counts. A failed prerequisite blocks its dependents only. Never report a full-suite pass from a selection.
4. **Services** only when an applicable integration/e2e check needs them: use the documented readiness check (an open port is not readiness). Unavailable → that check is BLOCKED; continue the rest. Start a service only when startup is in the task's scope and its config is known.
5. **Placeholders.** Review changed production code for stubs, sample data and incomplete behaviour; `TODO`, `FIXME`, `mock`, `dummy`, `fake`, `localhost`, `127.0.0.1` hits are candidates, not defects (tests, fixtures and configured local endpoints are fine). Report `file:line` and the issue only; never print secrets or payloads.
6. **Report:**
```text
Target: <range or pending manifest>
Checks: <check, PASS/FAIL, counts, evidence path>
Services: <readiness or NOT APPLICABLE + reason>
Integration/e2e: <PASS/FAIL/BLOCKED/NOT APPLICABLE + reason>
Placeholder review: <file:line issues or none>
Skipped/unsupported: <list and limit>
Status: VALIDATED FOR <scope> / PARTIAL / BLOCKED
```
`VALIDATED FOR <scope>` only when every required check passed for that state. A missing required check → PARTIAL or BLOCKED; label static-only validation as such; never imply production readiness.
