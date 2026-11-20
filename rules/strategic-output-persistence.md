# Strategic output persistence

- Specs in `docs/specs/<feature>/`, ADRs in `docs/adr/NNNN-<decision>.md`, living docs in `docs/*.md`. Security writes `security.md`, UI/UX `ui-design.md`, the main session everything else. Reuse an existing equivalent location; return the exact path written.
- Glossary: the main session proposes terms and ratifies them in the top-scope `glossary.md`; specs, contracts and prompts link terms instead of redefining them.
- Implementation agents read these files and never regenerate them. Living docs are updated from verified code via `/upgrade-service-docs`.

## Staleness check
Applies to living docs and to specs that are still active (`proposed` … `shipped`). Implemented or superseded specs are history: never flag or refresh them; read the living docs.

```bash
git log --oneline -1 -- <doc-path>
git log --oneline "$(git log -1 --format=%H -- <doc-path>)"..HEAD -- <module-path> | wc -l
```

Stale when any holds: ≥ 5 module commits since the doc's last commit; the doc's last commit is not reachable from HEAD; README `updated:` older than 90 days with module commits since.

Stale → an implementation agent returns `DONE_WITH_CONCERNS` with `CONCERN: <doc> last updated <date/SHA>; <N> commits to <module> since.` The main session decides: proceed with the concern noted, re-draft its own files, or re-dispatch Security/UI-UX for theirs. Never silently use a stale doc.
