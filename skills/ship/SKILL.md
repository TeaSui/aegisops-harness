---
name: ship
description: Stage 6 of the backend lifecycle (/tea-sdlc:ship, run by /tea-sdlc:aidlc) — for a spec at reviewed, opens the PR, waits for CI, writes the changelog per the project's convention and ship.md (GO/NO-GO, rollback, post-release verification), advances to shipped, merges through the ship gate on request and promotes the spec with /tea-sdlc:upgrade-service-docs. no-spec.md delivers /tea-sdlc:fix work.
disable-model-invocation: true
---

# Ship stage

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run every step yourself. Gate and `ship.md` format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §1 (`shipped` row) and §2 `ship.md`.

**Applies** when `aidlc status` shows the branch's spec at `reviewed` (or `shipped`, to resume). Earlier stage → `/tea-sdlc:review` first. No spec (`/tea-sdlc:fix`) → `skills/ship/no-spec.md`.

**User consent.** Merge and deploy only when the request covers delivery ("ship it", "merge", "release", "deploy", a `/tea-sdlc:aidlc` hand-off). Otherwise stop after step 5 and ask once whether to merge.

## 1. PR

`pr` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr.py"` (GitHub through `gh`, Bitbucket Cloud through its API; `pr auth` says whether this session can open PRs). Every PR action goes through it, never through `curl` or the provider's web UI.

If `pr view` exits 1 (no PR): push the `HEAD` that `aidlc advance <f> reviewed` recorded, `pr create --title … --body-file <file>` from it (body: summary, links to spec, `review.md`, `aidlc trace <f>`, ledger rulings, `RISK-ACCEPTANCE NEEDED` items first), then commit and push the review-stage files (`review.md`, spec `README.md`, `ledger.md`). If `HEAD` moved before the PR and only spec files changed, the gate still passes; if code changed, take the NO-GO path.

Only when `pr create` itself fails (push refused, `pr auth` exit 1, API error) stop the stage as BLOCKED: quote the error and name the fix (`git push` refused → repository access or SSH key; Bitbucket credentials → `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN`; gh → `gh auth login`), and hand the user the PR description.

## 2. CI

`pr checks <pr> --watch` (exit 0 green, 1 failed, 8 still pending at the timeout, 2 no checks reported). Exit 2, or no credentials to read CI: record what the user or the CI system shows as the `CI:` line, and say where it came from. Red is NO-GO unless unrelated and flaky: rerun once and note the rerun in `## Checks`.

## 3. Version and changelog

Follow the project's convention; find it, do not ask.
- Release tooling (release-please, semantic-release, changesets, release workflow) owns the version: `version: n/a — released by <tool>`.
- Manifest version (`package.json`, `pyproject.toml`, `plugin.json`, `VERSION`): semver (breaking contract major, capability minor, fix patch). The bump belongs before the final `aidlc verify`, because the fingerprint includes the manifest; here confirm it and copy it into `ship.md`. If missed: bump, re-run `aidlc verify`, diff-only look, `aidlc stamp <f> review`, re-check `reviewed`. A git tag comes after merge. Non-obvious choice → `aidlc ruling <f> --decision … --why … --if-wrong …`.
- `CHANGELOG.md` present: add the entry in its style (the gate checks it names the version). Changelog and Markdown are outside the fingerprint, so this keeps the review valid. Commit and push.
- No versioning: `version: n/a — <reason>`.

## 4. `ship.md`

Only the required sections:
- `decision: GO` only if CI is green, QA is `GO` (or `CONDITIONAL GO` with conditions met and listed) and no blocker remains; else `NO-GO`.
- `## Checks`: `CI:` line with source, QA verdict, migrations and order, flags, release notes for the reviewer.
- `## Rollback`: concrete steps (revert merge commit, disable flag, roll back deployment) plus any migration data step.
- `## Post-release verification`: commands and signals (smoke command, dashboards, alerts, duration), each with its pass condition.

## 5. Advance

`aidlc advance <f> shipped`; on failure `aidlc check <f> --to shipped` lists why. Commit and push `ship.md` and the stage change; if that re-runs CI, watch it again (the merge gate re-checks).

## 6. Merge, release, verify, promote

1. Merge with the repository's method (`pr merge <pr> --strategy squash`, or `merge` / `rebase` as configured). The `ship-gate` hook blocks until the `shipped` gate passes; fix what it reports and retry.
2. Release through the project's deploy path; wait for and read its result.
3. Run each post-release check and append results (command, outcome, time) under `## Post-release verification`. On failure, tell the user what failed and the rollback; roll back production only on their word unless `ship.md` makes it automatic. After a rollback, add a regression test for the defect with `/tea-sdlc:fix`.
4. On the merge target branch, follow `${CLAUDE_PLUGIN_ROOT}/commands/upgrade-service-docs.md` (traceability, spec → `implemented` or `partially-implemented`).

## 7. NO-GO

Real CI failure, QA `NO-GO`, code changed after review, or a conflict needing code:
1. `decision: NO-GO` with the reason in `## Checks`.
2. `aidlc advance <f> building --back --reason "<why>"`.
3. Fix via `/tea-sdlc:build` (new work = new `tickets.md` ticket), `aidlc verify`, advance `verified`, one diff-only review of the fixes appended to `review.md` (`/tea-sdlc:review` §2a re-entry), stamp, advance `reviewed`, return here.

## Report

Spec stage (`aidlc status`), PR link, CI, version, GO/NO-GO and why, post-release results, rulings, open user decisions.
