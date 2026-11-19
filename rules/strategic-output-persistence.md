# Strategic Output Persistence

Specs and decisions are persisted so they survive across sessions. **Paths, the single writer of each file and the lifecycle are owned by `references/documentation-layout.md`** (§4 for the change-spec files and their writers); read it before writing. This rule only adds the obligations below.

- Glossary terms: the main session proposes and ratifies them in the top-scope `glossary.md`. Specs, contracts and dispatch prompts link to named terms instead of redefining them.
- Reuse an existing equivalent location in the target project instead of creating a parallel tree, and return the exact path written.

Implementation agents READ these files and never regenerate them. Living reference docs (`docs/*.md`) are updated from verified code via `/upgrade-service-docs`.

## Staleness check

Applies to living reference docs and to change specs whose `README.md` status is `proposed` or `accepted` (`references/documentation-layout.md` §7). Implemented or superseded specs are history: never flag or refresh them; read the living docs instead.

Before acting on a spec or living doc, run:

```bash
git log --oneline -1 -- <doc-path>   # last commit that touched the doc
git log --oneline "$(git log -1 --format=%H -- <doc-path>)"..HEAD -- <module-path> | wc -l   # module commits since then
```

**Flag for review when any of the following is true:**
- The module has ≥ 5 commits since the doc's last commit (second command above).
- The doc's last commit is not reachable from the current branch HEAD (the doc was written on another branch and never merged).
- The spec README `updated:` date is older than 90 days and the module has commits since.

**When flagged:** an implementation agent returns `DONE_WITH_CONCERNS` (not `DONE`) with a staleness note:
```
CONCERN: docs/specs/foo/design.md last updated <date/SHA>; <N> commits to <module> since then.
Recommend re-drafting the contract and re-running scripts/check-contract.py before the next dispatch that touches it.
```

The main session decides whether to proceed with the concern noted, re-draft the files it owns, or re-dispatch Security or UI/UX for their own file. Do NOT silently use a stale doc.
