---
decision: GO
version: 6.0.0
---
## Checks
- CI: green — `pr.py checks 10`: `checks (python 3.9)` pass, `checks (python 3.12)` pass, `lifecycle gate (aidlc ci)` pass (its first run on a pull request; it re-ran the pinned suite and the revert check on the head).
- QA: CONDITIONAL GO, conditions met: the gitleaks fixture token (failed on gitleaks 8.30) was replaced and the pinned suite exits 0 with 467 tests; the stale-bytecode observation is fixed (`PYTHONDONTWRITEBYTECODE` on the reverted run). The QA return is from the review round on `63b08c2`; it was attested by hand because the authoring sessions ran subagents in the background.
- Review: `review.md`, every finding closed; stored returns in `returns/`.
- Version: `.claude-plugin/plugin.json`, `marketplace.json`, README and the `CHANGELOG.md` 6.0.0 entry agree (`check-setup` PASS). A git tag comes after the merge.
- Migrations and flags: none. Upgrade note for users is in `CHANGELOG.md` ("Breaking": `.aidlc.json`, `aidlc approve` for specs in flight, reviewer returns).
- For the person who merges: `.aidlc.json` exists only on this branch, so the gates run in onboarding mode: read it first. Branch protection (required check `lifecycle gate`), CODEOWNERS and the `ANTHROPIC_API_KEY` secret are the owner's to set; the paid eval re-baseline is not done (baseline still 4.0.0, flagged stale).
## Rollback
- Revert the merge commit of PR #10 on the default branch. Users pinned to 5.0.0 are unaffected; users on 6.0.0 return to 5.0.0 behaviour, and their `.aidlc.json` and `docs/specs/*/returns/` files are simply ignored by 5.0.0.
- Specs approved under 6.0.0 keep a recorded approval in their ledger; 5.0.0 reads `accepted_by` only.
## Post-release verification
- `python3 scripts/check-setup.py` on the default branch after the merge: status PASS, version 6.0.0.
- `python3 scripts/aidlc.py ci --base origin/main` run once on a throwaway branch with a bound spec: exit 0 for an honest change, exit 1 after a hand-edited ledger over a red suite (same scenario as the QA pass).
- First pull request after the merge: the `lifecycle gate` job appears as a check and passes; with branch protection on, it is listed as required.
- Watch for a week: issues about `onboarding` warnings or about the evidence guard blocking a legitimate command.
