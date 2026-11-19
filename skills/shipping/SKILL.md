---
name: shipping
description: Use when a reviewed full-workflow change is ready to release, merge or deploy, or the user says ship it, release or deploy — opens the PR if none is open, waits for CI, bumps the version and changelog per the project's convention, writes ship.md (GO/NO-GO, rollback, post-release verification), advances the spec to `shipped`, merges through the ship gate, runs the post-release verification and promotes the spec with upgrade-service-docs. Fast-path or non-spec work goes to finishing-a-development-branch.
---

# Ship stage

Stage machine, the `shipped` gate and the `ship.md` format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. `aidlc <command>` below is `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" <command>`; you run every step yourself.

**Which skill.** Run `aidlc status`. When the current branch belongs to a spec at stage `reviewed` (or `shipped`, to resume), this skill applies. A spec still at `verified` or earlier needs its earlier stages first (`tea-sdlc:requesting-code-review`). No spec, or a fast-path change: use `tea-sdlc:finishing-a-development-branch`.

**What needs the user.** Merging to the default branch and deploying publish the change. Do both when the user's request covers delivery ("ship it", "merge", "release", "deploy", or a `tea-sdlc:goal` hand-off of the whole outcome). Otherwise go as far as step 5 (PR open, CI green, `ship.md` written, spec `shipped`) and ask once whether to merge.

## 1. Open the PR

If no PR is open for the branch (`gh pr view --json number,state`):

1. Push the `HEAD` that `aidlc advance <f> reviewed` recorded and open the PR from it. The `gh pr create` gate accepts it because the pre-PR record is tied to that `HEAD`.
2. Then commit the files `aidlc` wrote during review (`review.md`, the spec `README.md`, `ledger.md`) and push them to the PR.

```bash
git push -u origin <branch>
gh pr create --title "<title>" --body "<summary; links to the spec, review.md and the traceability (aidlc trace <f>); the rulings from ledger.md>"
```

If `HEAD` moved before the PR was opened and only spec files changed, `aidlc check <f> --to reviewed` still passes (the fingerprint ignores docs); record the pass for the new `HEAD` with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer aidlc-review --open-findings 0`. If code changed, the review no longer matches: go back (NO-GO path).

With a non-GitHub remote nothing blocks `gh`: push, and give the user the PR description to open it.

## 2. Wait for CI

```bash
gh pr checks <pr> --watch
```

Without `gh`, read the pipeline status with the provider's CLI; when no tool can see it, ask the user for the CI result (a fact only they have) and record it as the `CI:` line. A red check is a NO-GO (section 7) unless it is unrelated and flaky: rerun it once, and record the rerun in `## Checks`.

## 3. Version and changelog

Follow the project's own convention; find it, do not ask:

- Release tooling (release-please, semantic-release, changesets, a release workflow) owns the version: do not bump by hand; set `version: n/a — released by <tool>`.
- Otherwise bump where the project keeps the version (`package.json`, `pyproject.toml`, `plugin.json`, a `VERSION` file, git tags) by semver from the change: a breaking contract change is major, a new capability minor, a fix patch. When the choice is not obvious, decide it and record it with `aidlc ruling <f> --decision … --why … --if-wrong …`.
- Add the entry to `CHANGELOG.md` in its existing style when the repository has one; the `shipped` gate checks that it mentions the version.
- A library or service with no versioning: `version: n/a — <reason>`.

Version files and changelogs do not change the code fingerprint, so the review stays valid. Commit and push them.

## 4. Write `ship.md`

In the spec folder, per the format in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` § ship.md:

- `decision: GO` only when CI is green, the QA verdict is `GO` (or `CONDITIONAL GO` with its conditions met and listed), and no known blocker remains. Otherwise `NO-GO` (section 7).
- `## Checks`: the `CI:` line with its source, the QA verdict, migrations and their order, feature flags, anything the reviewer of this release needs to know.
- `## Rollback`: the concrete steps (revert the merge commit, disable a flag, roll back a deployment) and any data step a migration needs.
- `## Post-release verification`: commands and signals to watch after release (smoke command, dashboards, alert names, how long), each with what passing looks like.

## 5. Advance to `shipped`

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> shipped
```

If the gate fails, `aidlc check <f> --to shipped` lists why (CI not green, changelog missing the version, code changed since review). Fix and retry. Commit `ship.md` and the stage change and push them; when that push re-runs CI, wait for it again (`gh pr checks <pr> --watch`), since the merge gate re-checks it.

## 6. Merge, release, verify, promote

1. **Merge** with the project's merge method (`gh pr merge <pr> --squash` or as the repository is configured). The `ship-gate` hook blocks `gh pr merge` until the spec passes the `shipped` gate; when it blocks, do what it reports and retry.
2. **Release** through the project's deploy path (the pipeline that runs on merge, a release workflow, a tag). Wait for it to finish and read its result.
3. **Post-release verification:** run each item of `## Post-release verification` and append the results under that heading (command, outcome, time). When a check fails, tell the user what failed and the rollback from `ship.md`, and run the rollback on their word; a production rollback is their decision unless `ship.md` names it as automatic. Load `tea-sdlc:incident-to-eval` after a rollback.
4. **Promote:** on the branch the change merged into, run the `upgrade-service-docs` command yourself. It builds the traceability table and moves the spec to `implemented` (or `partially-implemented`).

## 7. NO-GO

When CI fails for a real reason, QA says `NO-GO`, the gate finds code changed after review, or a merge conflict needs a code change:

1. Set `decision: NO-GO` in `ship.md` and say why under `## Checks`.
2. Go back, which the ledger records:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> building --back --reason "<why: failing check, QA blocker>"
```

3. Fix through the build stage (`tea-sdlc:subagent-driven-development`; new work gets a task in `plan.md`), run `aidlc verify` and advance to `verified`, review the new diff on both axes (`tea-sdlc:requesting-code-review`, appending findings to `review.md`), stamp and advance to `reviewed`, then return here and set `decision: GO` when it holds.

## Report

Lead with where the spec stands (`aidlc status`), then the PR link, CI result, version, the GO/NO-GO decision with its reason, post-release verification results, the rulings made in this stage, and anything the user still has to decide.
