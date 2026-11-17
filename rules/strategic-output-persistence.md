# Strategic Output Persistence

Strategic agents persist outputs so they survive across sessions. **Paths, file ownership and lifecycle are owned by `references/documentation-layout.md`** — read it before writing; this rule only adds the obligations below.

- Each strategic agent writes only its own file in the feature's change-spec folder (`docs/specs/<feature>/`): UI/UX → `ui-design.md`, Security → `security.md`. The integrating (main) session writes `requirements.md`, `design.md`, `contracts/` (+ ADRs in `docs/adr/`, ratified terms in `glossary.md`) and `measurement.md` (skill `measurement-planning`, when measurement is in scope), so a file never has two writers (`references/documentation-layout.md` §6.3).
- Glossary terms: The integrating session proposes and ratifies them in the top-scope `glossary.md`. Specs, contracts and dispatch prompts link to named terms instead of redefining them (link, do not restate).
- Reuse an existing equivalent location in the target project instead of creating a parallel tree, and return the exact path written.

Implementation agents READ these files, never regenerate them. Living reference docs (`docs/*.md`) are updated from verified code via `/upgrade-service-docs`, not by strategic agents.

## Staleness check

Applies to living reference docs and to change specs whose `README.md` status is `proposed` or `accepted` (see `references/documentation-layout.md` §7). Implemented or superseded specs are history: never flag or refresh them; read the living docs instead.

Before an implementation agent acts on a strategic doc, it MUST run:

```bash
git log --oneline -1 -- <doc-path>          # last commit that touched the doc
git log --oneline -- <module-path> | wc -l  # total commits on the module since doc was written
```

**Flag for review when any of the following is true:**
- The module has ≥ 5 commits since the doc's last update (`git log <doc-hash>..HEAD -- <module-path>`).
- The doc's last-updated commit is not reachable from the current branch HEAD (i.e., the doc was written on a different branch and never merged).
- The doc contains a `Last updated:` footer date older than 90 days AND the module has any commits since then.

**When flagged:** the implementation agent returns `DONE_WITH_CONCERNS` (not `DONE`) and includes a staleness note:
```
CONCERN: docs/specs/foo/design.md last updated <date/SHA>; <N> commits to <module> since then.
Recommend re-drafting the contract and re-running `scripts/check-contract.py` before the next dispatch that touches it.
```

The dispatcher (the main session) decides whether to re-run the strategic agent or proceed with the concern noted. Do NOT silently use a stale doc.
