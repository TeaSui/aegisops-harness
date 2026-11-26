---
agent: aegisops-harness:code-reviewer
axis: both
fingerprint: af0a3fb884038d8e4ee1c06c9d00dba10cdab0dedf24ae9ad88d645061d478cf
sha256: 6dd291fbb86f4aec7686742cb395ced59247eccf66c8c9606f62ecc85d9a4ee5
recorded: 2026-11-26T17:07:25Z
---
### Findings
- [ ] S1 (must): ETA-6 / control 5 — the evidence guard lets the model run `aidlc approve <slug>` again after the user typed `/aegisops-harness:approve <slug>` once, with no limit. The guard only checks that the last typed harness command in the transcript is `approve` for that slug (hooks/evidence-guard.py:132). Ordinary user messages and later model edits do not reset it. So the model can edit spec.md, which story 6 and the approve skill say needs a new approval, and re-approve the new text. The accepted gate then passes on a text the person never saw. Fix: allow one approval per typed command, e.g. refuse when the ledger already holds an `approve` event newer than that command, or compare the transcript position of the command with the last approve. Reproduced: a transcript with one `/aegisops-harness:approve foo` command and a later plain user message; the guard returned rc 0 for `approve foo` and rc 2 for `approve bar` (my script `/private/tmp/claude-502/-Users-tungnguyen-TYME-AegisOps-Harness/d1c8f563-b2fd-4de5-ae55-93cd5ebaeffb/scratchpad/ap.py`). (confidence: medium; the code does what its docstring says, but the docstring does not say "once")
- [ ] S2 (should): ETA-7 / T9 criterion "the guard refuses edits to the ledger and the stored returns" — the shell-write check misses common shapes. `cd docs/specs/x && echo … >> ledger.md`, `cd docs/specs/x && rm ledger.md` and `rm returns/a.md` all returned rc 0, because EVIDENCE needs the full `docs/specs/<slug>/` path in the target (hooks/evidence-guard.py:24, 141-151). `dd of=docs/specs/x/ledger.md` also returned rc 0: `dd` is in WRITERS but the `of=` prefix defeats the path regex. `git checkout <rev> -- …/ledger.md` returned rc 0 too, so it can roll the ledger back to an earlier state. Fix: resolve targets against a tracked `cd`, as `invocations.git_calls` does; strip `of=`; add `git checkout`, `git restore`, `git apply` and `patch`. Reproduced (scripts `scratchpad/eg.py` and `eg2.py` in the scratchpad above). (confidence: high for the first three bypasses, medium for `git checkout`)
- [ ] S3 (should): ETA-8 — a merge through GraphQL is gated only for `gh api graphql` with the mutation name written on the command line (hooks/invocations.py:308). `curl -X POST https://api.github.com/graphql -d '{"query":"mutation{mergePullRequest…}"}'` returned `merge_targets == []`, so ship-gate lets it through. `gh api graphql -F query=@merge.graphql` is also not seen. The spec says "curl to either provider". Fix: treat a curl call to /graphql, or a `gh api graphql` call whose query comes from a file, as an unknown merge (`'$'`). Reproduced with `invocations.merge_targets`. (confidence: medium, because it is outside the "default path")
- [ ] S4 (should): CHANGELOG 6.0.0 "Verified" — says "460 unit tests". The suite now has 466 tests (I ran `unittest discover`: "Ran 466 tests … OK", and the ledger's latest verify says 466). The count went stale when round 1 added tests, so the claim in the changelog is wrong. at CHANGELOG.md:38 (confidence: high)
- [ ] S5 (nit): ETA-12 — the stale-baseline check only flags a different minor version. A patch release (4.0.3 against a 4.0.0 baseline) is "not stale", which the story ("another plugin version") and the changelog do not state. at evals/headless/harness.py:245-246 and scripts/check-setup.py:128-140. Fix: say so in the changelog or the spec, or compare the full version. (confidence: medium)
- [ ] Q1 (should): security-gate — `git add . && git commit -m x` commits an untracked file holding a token without a scan. The gate runs before the command, so the staged area is empty, and `worktree` is only set for `-a` or named paths (hooks/security-gate.py:79-84, `commit_takes_worktree`). The 6.0.0 "Fixed" entry says `git commit -a` and `commit && push` are now covered, which suggests the same guarantee for `add && commit`. Reproduced: in a scratch repo with an untracked `secret.env` holding `ghp_…`, the hook exited 0 for `git add . && git commit -m x`, `git add secret.env && git commit -m x` and `git add -A; git commit -m x`. After `git add secret.env`, plain `git commit` is blocked (exit 2). Fix: when the command line holds an earlier `git add`, or any earlier command, scan the worktree (`--pre-commit` without `--staged`, plus untracked files) as the `-a` case does. This behaviour already existed in 5.0.0, but it sits next to the claimed fix. (confidence: high that it is reproduced, medium that it is in scope)
- [ ] Q2 (should): ship-gate — `gh pr merge 5 -R other/repo` is judged as local PR #5 (`merge_of` returned `(True, '5')`), so the PR of another repository is checked against this checkout's spec, or is "unresolved" and judged by the checked-out branch. `-R/--repo` is skipped but never used. at hooks/invocations.py:289-300 and hooks/ship-gate.py:147-162. Read and run through `merge_of` only, not tried against gh. (confidence: low)
- [ ] Q3 (nit): evidence-guard — `shell_targets` treats every operand of `cp`, `mv`, `ln`, `install` and `touch` as a written path, so `cp docs/specs/x/ledger.md /tmp/backup` is refused (rc 2) although it only reads the ledger. at hooks/evidence-guard.py:141-151. Reproduced. (confidence: high)
- [ ] Q4 (nit): duplication — five hooks each repeat the importlib "load a sibling module" block (12 `spec_from_file_location` calls under hooks/). ship-gate keeps its own shlex merge parser (`merge_target`, hooks/ship-gate.py:46-75) next to `invocations`, as a documented floor. Share one loader helper. Complexity: `invocations._pulls` (hooks/invocations.py:289), `revert_check` and `cmd_ci` (scripts/aidlc.py:2395, 2764) are well over the Sonar cognitive-complexity 15, judged by reading, not measured. (confidence: medium)
- [ ] Q5 (nit): the plugin's own `lifecycle-gate` job runs `actions/checkout` without `persist-credentials: false`, although references/aidlc.md:273 tells users to add it because the pull request's own suite runs in that job. The token is `contents: read`, so the exposure is small. at .github/workflows/ci.yml:47 (confidence: medium)
- [ ] Q6 (nit): security-gate — the per-scan timeout dropped from 180 s to 60 s (hooks/security-gate.py:108) while hooks.json still allows 200 s. A scan that takes longer than 60 s, such as the first push of a large repo, now blocks as "could not complete", and a command with several git calls can exceed the hook timeout. Read only. (confidence: low)

### Assessment
**Axis:** both (S and Q).

**Scope and drift:** ccf82d0353268be65e37c12de1e0ac543378a6d5..064ef6b8ef61a0718c39533e52b8020193c5c47e. Both refs resolve, HEAD equals 064ef6b, and the working tree was clean at the start and after the test run. There is no REVIEW.md.

**Ready for the next step:** with fixes (fix S1 before shipping). **Status:** BLOCKED, because of the `must` S1. The rest is `should` or `nit`.

**Executed:**
- `python3 -m unittest discover -s tests` on Python 3.15.2 with gitleaks 8.30.1 and node: 466 tests, OK.
- `aidlc trace evidence-trust-anchor`: ETA-1 to ETA-14 show "pass"; ETA-15 shows only its `check:` line.
- `aidlc check … --to verified`: passes, with the onboarding warning.
- `check-setup.py`: ran and printed JSON. I did not read the PASS/FAIL line.
- Python 3.9 parse check by `ast.parse(feature_version=(3, 9))`: no syntax errors. No 3.9 interpreter is installed, so 3.9 behaviour was not run.
- Probes with scripts in the scratchpad: `inv.py` (command parsing), `eg.py`/`eg2.py` (evidence guard), `ap.py` (approval replay), the scratch git repo `r1` (secret gate).
- Not run: `aidlc ci --base origin/main` (the ETA-15 check; it would rewrite the tree), the gitleaks 8.21.2 claim, and the Python 3.13 claim.

**Fixes from the earlier round:**
- Case-only rename: holds. `_put_back` unlinks D paths before the checkout, and `revert_check` unlinks A paths before it writes (aidlc.py:2344-2360, 2437-2451). The `test_eta_3_a_case_only_rename_*` tests pass on this machine, which I did not confirm is case-insensitive.
- No bytecode: holds. `PYTHONDONTWRITEBYTECODE` is passed on the revert run only, which is enough (aidlc.py:2458).
- Guard reads shell wrappers: holds for `bash -c`, `eval`, `sudo`, `env` and `--repo`/`--json` before the subcommand, but see S1 and S2.
- One merge per command: holds. `gh pr merge 1 && gh pr merge 2` and the newline form give `'*'`, and ship-gate refuses it.
- gitleaks fixture token: holds. The two fixture tests pass on gitleaks 8.30.1.

**Stories:** each has `test_eta_<n>_…` tests (counts: ETA-1 16, 2 9, 3 17, 4 16, 5 9, 6 12, 7 17, 8 28, 9 4, 10 6, 11 9, 12 2, 13 6, 14 5, 15 1). The ID matcher keeps ETA-1 and ETA-15 apart.
- ETA-1: met.
- ETA-2: met.
- ETA-3: met. Its limits are documented.
- ETA-4: met by test. The CI command was not run against this repository.
- ETA-5: met.
- ETA-6: partly met (S1).
- ETA-7: partly met (S2).
- ETA-8: partly met (S3; Q2 and Q1 are adjacent).
- ETA-9: met.
- ETA-10: met.
- ETA-11: met.
- ETA-12: met, with the S5 deviation.
- ETA-13: met.
- ETA-14: met.
- ETA-15: partly met. The CI job and action exist and a test names the story, but the `check` command was not run.

**Security controls:**
1. Config from the default branch: holds. The config is read from the trusted ref, a branch-only config is onboarding, a nearer branch config is ignored, and the stated limit that locally the ref can be moved applies.
2. CI recomputation that ignores recorded verify lines: holds. `spec.fresh` replaces the ledger lines, and the approval and returns checks still read local files, as documented.
3. Cumulative gates: holds.
4. Revert check: holds. It refuses uncommitted work and symlinks, restores from HEAD with a marker, and its limits are documented.
5. Approval bound to the spec text: the gate side holds (hash compared). The guard side does not hold against re-approval after an edit (S1).
6. Verbatim reviewer returns with a content hash: holds with the stated limits. The guard against edits has the S2 gaps.
7. Command parsing and MCP matchers: holds with limits. S3, Q2 and Q1 are the gaps found.
8. Outcome-scored, fail-closed evals: holds. The tests cover it, and the paid suites were not run, as stated.

**Other checks:** no secrets or PII found in logs. The code uses the standard library only. The hooks now fail closed or open as their docstrings say.
