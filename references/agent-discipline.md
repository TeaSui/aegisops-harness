# Agent discipline (implementation agents)

Domain test commands live in each agent definition.

- **TDD:** RED-GREEN-REFACTOR, one failing test at a time. ≥ 80% coverage on changed code. Mock only external HTTP APIs; data-layer tests use a real or in-memory DB.
- **Debugging:** root cause before any fix: read the error, reproduce, check `git diff`, trace the data flow, test ONE hypothesis with the smallest change.
- **Verification:** no completion claim without running tests and build and showing the output (test count, pass/fail, coverage %, build exit code). Never "should work", "probably passes", "looks good" without output. Write test output to a file outside the project tree (e.g. `/tmp/<slug>.log`) and Read it. Take totals only from the run you made: clear its result directory first or use the tool's own summary; never aggregate across result directories (e.g. Gradle `build/test-results/{test,unitTest,cucumberTest}`).
- **Escalate** (report what you tried, errors seen, root-cause guess, what would unblock you) after 2 failed fixes on one issue, > 10 files read without producing code, or > 3 consecutive build/test errors.
- **Paths:** `rules/`, `references/`, `skills/`, `scripts/` are relative to the tea-sdlc plugin root; `docs/…` is relative to the target project.
- **Stale docs:** before acting on an active spec or living doc, check it: stale if its module has ≥ 5 commits since the doc's last commit, the doc's last commit is not reachable from HEAD, or README `updated:` is > 90 days old with module commits since. Stale → return `DONE_WITH_CONCERNS` naming the doc, date/SHA and commit count.
- **Project first:** the target project's stack, architecture, security constraints and output locations win; agent-definition stack/region choices apply only when the project leaves them open; never migrate a stack in unrelated work.
- **Grounding:** never invent paths, symbols, flags, APIs or SHAs; cite `path:line`, command output or a doc for every load-bearing claim, else say "I don't know". A fabricated evidence path is treated as `BLOCKED`.
- **Memory:** only with an enabled memory directory, task authorization and tools that allow it: concise, dated, project-scoped findings, no secrets or personal data. Otherwise return learnings without claiming persistence. Never enable memory, invent a path or add tools; memory never authorizes extra edits.
