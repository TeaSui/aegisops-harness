---
name: verify
description: "Stage 4 of the backend lifecycle — prove the built change works for the exact code state: the full suite through aidlc verify, every story traced to a passing test, integration checks, a placeholder scan, then advance the spec to verified. Also the evidence rules for any done, fixed or passing claim."
argument-hint: "[spec slug]"
disable-model-invocation: true
---

# Stage 4: verify

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`, `<f>` = spec folder or slug; run every command yourself.

## 1. Spec stage
1. `aidlc status`: spec at `building` with every ticket `Status: done` (else `/aegisops-harness:build`).
2. **Version:** a manifest that holds the release version (`package.json`, `pyproject.toml`, `build.gradle`, `plugin.json`, `VERSION`) gets its semver bump now (breaking major, capability minor, fix patch; skip when release tooling owns it): a manifest change after `verify` invalidates the evidence.
3. **Full suite through the CLI**, with `--junit` when the runner writes JUnit XML so failing story tests are seen:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full test suite>" --junit "<junit glob>"
```
4. **Integration:** run the project's integration or contract tests when they exist and need no new service; a check that needs a service you cannot start is BLOCKED, named in the report, not skipped silently.
5. **Placeholders:** scan the changed production code for stubs, sample data, `TODO`/`FIXME`, hard-coded `localhost`; fix real ones (tests and fixtures are fine).
6. `aidlc trace <f>`: every `Verify: test` story has a passing test; `check`/`manual` stories have their evidence.
7. `aidlc advance <f> verified`. Fails → `aidlc check <f> --to verified` names it (open ticket or criterion, story without a test, failing story test, code changed after `verify`): fix test-first and rerun from 3.

Next: `/aegisops-harness:review`.

## 2. Without a spec (`/aegisops-harness:fix`)
Run the full suite (not a selection) and read exit code and counts; the regression test was seen failing before the fix.

## 3. Evidence for any claim

| Claim | Needs | Not enough |
|---|---|---|
| Tests pass | 0 failures for this state and scope; with a spec, the latest `aidlc verify` green at the current fingerprint | a stale run; a selection sold as the full suite |
| Bug fixed | the original symptom no longer reproduces | code changed |
| Regression test | failed before the fix, passes after | passes once |
| Agent done | its diff, evidence and exit results read by you | its own report |
| Stories met | `aidlc trace <f>` | tests green |
| Stage reached | `aidlc check <f> --to <stage>` passes, quoted | your reading of the files |

Partial check → partial claim. Keep PASS, FAIL, SKIPPED, BLOCKED and static-only distinct. "Should", "probably", "seems" = a claim ahead of its evidence.
