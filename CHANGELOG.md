# Changelog

## 2.7.0 — 2026-11-17

### Changed
- `brainstorming` runs first for any code-changing request, like Superpowers: `session-bootstrap` makes it the first action (before reading files, choosing a tier or asking questions), including when the prompt comes from `/prompt-builder`. The skill scales by tier (2-3 lines for a routine fix, a full design for trust-boundary work), confirms inputs that are already given, and never blocks a non-interactive or delegated run.
- `session-bootstrap` carries the tier table and the six trust-boundary items inline, so the tier is stated before any edit instead of depending on the model reading `rules/workflow-routing.md`.
- `/prompt-builder`: a contract is "external" only when it has consumers outside the changed module (HTTP/RPC API, event, shared schema, public library API). TechLead (contract-mode) and its ADRs are used only for an external contract change, and BA only when requirements are unresolved or need measurement; otherwise the main session writes `design.md`, `requirements.md` and the ADR. Generated SDLC prompts start with the `brainstorming` step.
- Agent definitions: when-to-use guidance for the Playwright tools (frontend, QA), the Slack / Microsoft 365 / web research tools (BA, read-only, cited, optional) and the draw.io tools (tech lead, UI/UX), each with a fallback when the connector is missing. `code-reviewer` frontmatter matches the other agents (`name` quoted, `color`).

- TDD runs passively: `session-bootstrap` requires the `test-driven-development` skill before production edits on behavior changes and bug fixes, and the skill opens with a gate that requires a shown failing run. Measured on one small rule change, 5 runs per configuration, TDD counted only with a failing test run before the production edit: no plugin 0/5; the 2.6.0 plugin as released 4/5; this release (bootstrap rule, skill gate and hook, each tried alone and together) 5/5. At this sample size the differences among the plugin variants are not distinguishable; the hook did intervene in 3 of the 5 hook-only runs, each time turning a combined test-and-code write into test, failing run, then code.

- New advisory hook `hooks/tdd-gate.py` (`tests/test_tdd_gate.py`): a `PostToolUse` Bash hook records a failing test run per session; a `PreToolUse` hook (Edit/Write/MultiEdit/Bash) blocks the first production-code change of a session that has no recorded failing run, once, with a reminder to write the test and see it fail. Later attempts pass, so refactors and doc/config changes cost one turn. Skipped for test files, non-code files, repositories without a test setup and with `TEA_SDLC_TDD_GATE=off`; it never blocks on its own errors.

### Removed
- `rules/user-facing-output.md`, `rules/session-scope.md`: nothing referenced them and the behavior already held without them; their essentials are now two short paragraphs in `session-bootstrap`.
- `rules/security.md`: duplicated each implementation agent's embedded security checklist and the Security agent's rules; secrets are enforced by the `security-gate` hook. References now point to the checklists.

### Moved
- `rules/single-source-of-truth.md` → `CONTRIBUTING.md`: it is an authoring rule for maintainers, not an agent runtime rule, so it is no longer a bundled rule.

## 2.6.0 — 2026-11-16

### Fixed
- Project instructions reach dispatched agents: before dispatching into a worktree or another checkout, the dispatcher checks that each cited instruction file exists there and is non-empty, else cites the main checkout's absolute paths (`rules/dispatch-prompt-contract.md`). `scripts/check-setup.py` warns when `CLAUDE.md` is tracked but empty at HEAD or `.claude/rules/` is untracked or ignored.
- Ignored docs: layout §6.7 requires docs to be tracked (`!/docs/` and `!/docs/**` in the repository `.gitignore` override a personal `core.excludesFile`); `/upgrade-service-docs` stops instead of creating a living file that is ignored or present in another checkout, and runs after `GO` on the merged or integration branch; `check-setup.py` warns when `docs/` paths are ignored.
- Spec status inflation: `source_revision` must name a commit that contains the change; an uncommitted or unmerged change stays `accepted` (layout §5 step 5).
- Test totals are read only from the result set of the command that ran, never aggregated across result directories such as Gradle's `build/test-results/*` (`references/agent-discipline.md` § Verification).
- CI YAML command items containing `: ` or starting with a YAML indicator are quoted and verified by parsing (`agents/platform-engineer-subagent.md`).
- Every count in a subagent return names what was counted and the command that produced it (`rules/subagent-return-format.md`).

### Changed
- Coordinated fast path: lanes run in parallel unless one needs another's output (e.g. a RED test before the fix); the plan states the order.
- Pre-PR review with a non-GitHub remote: the `gh` hook does not apply, so the pass is still run and recorded with `scripts/mark-pr-review.py`, and the PR description is handed to the user.
- `check-setup.py` takes `--project` (default: current directory) for the warnings above, skips them for the plugin's own repository, and reports `project` in its JSON. Covered by `tests/test_check_setup.py` (stdlib `unittest`, isolated from the user's git config).

## 2.5.0 — 2026-11-15

### Removed
- `/new-project`, `/tdd-feature` and `/map-codebase`, with the `codebase-mapper` agent and everything only they used: `references/planning/` and the whole `templates/planning/` tree. The TDD flow lives in the `test-driven-development` skill and the fast path in `rules/workflow-routing.md`; project initialization and `.planning/codebase/` maps are no longer part of the plugin.

### Changed
- Living docs absorb what the codebase maps covered: `architecture.md` gains **Code conventions** and **Test strategy**, `troubleshooting.md` gains **Known concerns / tech debt** (layout §2). `/generate-service-docs` builds them from source, `/upgrade-service-docs` refreshes them after a change, and `/prompt-builder` has implementers read them before writing tests.
- `references/documentation-layout.md`, `rules/`, `references/model-guide.md` and the README no longer mention the removed commands. `.planning/` is no longer referenced anywhere: the `Traces:` field in `requirements.md`, layout resolution rule 6 (`.planning/` workflow state; former rule 7 *Fast path* is now §6.6), the Spec Kit/GSD note and the `commit_docs` preference are removed.

## 2.4.0 — 2026-11-14

### Added
- Three thinking-tool skills that trigger from the situation (no slash command needed) and remain callable by name:
  - `clarify` — inspect the project first, then ask only the questions whose answers change the work, each with the default that applies if unanswered.
  - `expert-lens` — what the field's best practitioner would notice, do first and refuse to do, with evidence per observation.
  - `reframe` — strongest case against the current view, its load-bearing assumption, a different framing and the cheapest check that settles it.
- The eval-upgrade tool is bundled at `tools/eval-upgrade/` (Node ≥ 20, zero dependencies). `/eval-upgrade` no longer needs `$EVAL_UPGRADE_HOME` or any external checkout. Results, proposals, arena ledgers and the optional `config.json` live in `~/.claude/state/eval-upgrade` (`$EVAL_UPGRADE_STATE_DIR` overrides), so they survive plugin updates.
- `hooks/hooks.json` registers the eval-upgrade auto-trigger (`PostToolUse`, async). It is inert unless `autoTrigger.enabled` is set in the state `config.json`.

### Changed
- eval-upgrade arena: the challenger is auto-promoted only if it reaches `arena.pointsToWin` (10) before the champion reaches `arena.pointsToDefend` (4). The previous symmetric first-to-10 race promoted a challenger of equal quality half the time; the new rule does so about 5% of the time.
- eval-upgrade: models are family aliases (`sonnet`, `opus`) instead of pinned ids; headless calls run without tools or skills so an installed copy of the asset under test cannot leak into a duel; the judge scores the answers rather than the instruction-file rubric; promotion and apply are confined to the directory that was evaluated, so `--target` arenas can promote; plugin-namespaced skill and agent names resolve in the auto-trigger; dashboard output is HTML-escaped and `server.mjs --open` passes the session token straight to the browser.
- `/prove-it` covers factual claims (root cause, code facts, external API facts) as well as completion claims, requires each check to be one that would fail if the claim were false, and reports `VERIFIED` / `NARROWED` / `REFUTED` / `UNVERIFIED` with the record corrected.
- `verification-before-completion` rewritten in the plugin's plain register (142 → 43 lines): same four-step gate and claim/evidence table, reasons in place of threats, plus explicit handling for checks that cannot run or that the user waived. A 72-session comparison on Sonnet and Haiku found no behavioral difference from the previous text; the change is for consistency and size.

## 2.3.1 — 2026-11-12

### Fixed
- `/prompt-builder` SDLC-flow prompt now matches `references/documentation-layout.md` and the service-docs commands: scoped paths (`<service>/docs/` or system root), read-layout-first and reuse of existing locations, single writer per spec file, `plan.md` for coordinated tiers, ADR ownership/numbering/immutability, fast-path living-doc update, implementers never edit specs/ADRs/living docs, and protected folders are never moved or deleted.

## 2.3.0 — 2026-11-12

### Changed
- `/generate-service-docs` and `/upgrade-service-docs` now ensure `<service>/docs/adr/` (and the system-root `docs/adr/`) exists, index ADRs in the service `README.md`, and report missing/candidate ADRs. ADR content is still owned by tech-lead-subagent and never written by these commands.
- `/prompt-builder` has an SDLC-flow track for software changes: generated prompts follow spec → adr → tdd → implement → test → create PR with a gate per stage. Non-software prompts keep the minimal/full tracks.

## 2.2.0 — 2026-11-12

### Added
- `references/sonar-way.md`: SonarQube "Sonar way" quality gate and code rules for implementation agents (backend, frontend, mobile, data, platform), referenced from their required reading and from `rules/patterns.md`.

## 2.1.0 — 2026-11-10

### Removed
- Vendored `building-with-the-claude-api` skill (3.2 MB, self-described as largely obsolete). Replaced by Claude Code's built-in `/claude-api` skill plus live sources (docs `.md` pages, `llms.txt`, docs MCP server, Context7) listed in `references/ai-integration-patterns.md`.

### Changed
- Model guidance is version-agnostic: agents use family aliases that resolve to the latest release; API code resolves the latest ID via the Models API (`line`, `lifecycle`) and pins it in config. `check-setup.py` rejects versioned IDs in agent frontmatter.

## 2.0.0 — 2026-11-10

### Breaking
- Subagents consolidated 17 → 12:
  - `devops-engineer-subagent` + `aws-infrastructure-subagent` → `platform-engineer-subagent`
  - `ai-engineer-subagent` → merged into `backend-engineer-subagent`
  - `growth-marketer-subagent` → merged into `business-analyst-subagent` (measurement mode, `measurement.md`)
  - `api-test-agent` → merged into `qa-subagent` (Phase 2b live API validation)
  - `agent-orchestrator` → skill `orchestrating-multi-domain-work`, run by the main session (no nested subagents)
- Project documentation paths unified under `references/documentation-layout.md`: change specs in `docs/specs/<feature>/`, ADRs in `docs/adr/`, living reference docs in `docs/*.md`. Role folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, `docs/design/`, `docs/domain/`) are read as legacy only.

### Changed
- Model/effort per agent follow `references/model-guide.md`: Opus for tech-lead, security and code review; Sonnet for implementers, BA, UI/UX and QA; Haiku for codebase mapping.
- `/generate-service-docs` and `/upgrade-service-docs` share the canonical layout, never touch `specs/`, `adr/`, `plans/` or legacy folders, and `/upgrade-service-docs` owns spec promotion.
- Bundled files are referenced via `${CLAUDE_PLUGIN_ROOT}` (agents, commands, skills) or plugin-root-relative paths (rules, references) instead of `~/.claude/`. Planning templates are bundled under `templates/planning/` and `references/planning/`.
- `scripts/check-setup.py` rewritten as the plugin validator (manifests, frontmatter, bundled references, SessionStart contract).
