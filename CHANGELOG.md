# Changelog

## 2.9.0 — 2026-11-19

Autopilot: the user no longer has to remember or type a slash command or a skill name.

### Added
- `hooks/autopilot.py` (`tests/test_autopilot.py`, 52 tests), registered for three events:
  - **UserPromptSubmit**: a keyword router for English prompts. It adds a short `<tea-sdlc-autopilot>` note naming the skills to load and in what order (`brainstorming` → `systematic-debugging` → `test-driven-development`; `goal`, `clarify`, `expert-lens`, `reframe` first when asked for), the trust-boundary items the prompt mentions (→ Full workflow), up to three domain skills, and the command that fits (`finishing-a-development-branch` + pre-PR review, `generate-service-docs`, `upgrade-service-docs`, `incident-to-eval`, `prove-it`, `debug-parallel`). Trust items and domain skills are named only for code work. It stays silent for slash commands, questions (a prompt ending in `?`, where only `goal`, `clarify`, `expert-lens`, `reframe` and `prove-it` still apply), small talk, past-tense reports, and changes to prose or git/ops (prompts, rules, README, branches, versions, commits). Change verbs inside command names (`/eval-upgrade`, `create-pr`) do not count, a flow written as `spec → adr → … → create PR` is not a request for its steps, and Claude vocabulary is not auth (“a new session”, `<role>` tags, LLM tokens, “author”).
  - **PostToolUse**: tracks code edited since the last test run; after three failing runs in a row it points to `systematic-debugging`, after `git revert` to `incident-to-eval`, and after a merge while a spec is still `accepted` to `upgrade-service-docs`.
  - **Stop**: verification gate. When code changed since the last test run, the session is sent back once per change set (at most three times per session) to run the tests or state why none applies. It never blocks a continuation (`stop_hook_active`). Off with `TEA_SDLC_VERIFY_GATE=off`.
- `hooks/session-start` adds a project snapshot after the bootstrap: active specs with status, contract and plan progress plus their next step, a resumable `.goal/state.md`, open plans in `docs/plans/`, a repository with no `docs/`, the superpowers plugin enabled alongside (merged user, project and local `enabledPlugins`; the session is told to use the tea-sdlc twin of each of the 11 shared skills and not to run both versions of a step), and a missing `gitleaks`, which is also shown to the user with the install command instead of surfacing only when a commit is blocked. It now also runs on `resume`, prunes per-session gate state older than 30 days (`~/.claude/state/{tdd,contract-gate,tea-sdlc/autopilot}`), and reads its JSON input (the heredoc used to consume stdin).
- `session-bootstrap`: an Autopilot paragraph. The session treats the notes as a checklist, runs fitting commands itself (`upgrade-service-docs` after GO or a merge, `generate-service-docs` offered once, `prove-it` before claiming completion, `debug-parallel` across services), does what a gate asks and retries, and asks the user only for what only the user can do.
- `scripts/check-setup.py` fails when a hook does not compile or when a `tea-sdlc:<name>` reference, or any name the autopilot can emit (`autopilot.SKILL_NAMES`), is not a skill or command of the plugin, so renaming a skill cannot leave the router pointing at nothing. 3 tests on a scratch copy of the plugin.
- `TEA_SDLC_AUTOPILOT=off` turns off the prompt and follow-up notes and the session snapshot.

### Fixed
- `tdd-gate.py` blocked read-only commands such as `cat src/math.js; ls 2>/dev/null` because any `>` (including `2>/dev/null`) made every code path in the command count as written. Seen in a real session, where it cost a turn. Shell writes are now detected by target: `>`/`>>` (not `2>`, `&>`, `>&2`), `tee <file>`, and code paths in a segment that edits in place (`sed -i`, `perl -i`) or writes from inline code. `contract-gate.py` shares the detection.
- `tdd-gate.py` recognised few test runners, so failing runs under pnpm, yarn, bun, `python -m unittest`, `mvn verify`, `gradle check`, Playwright, tox, Cargo nextest, Swift, Deno, RSpec, PHPUnit and others were not recorded as RED.

### Changed
- Descriptions of `upgrade-service-docs`, `generate-service-docs`, `prove-it`, `debug-parallel`, `executing-plans`, `writing-plans`, `subagent-driven-development` and `validate-feature` now say when to use them, which is what the session reads to invoke them without being asked.
- `plugin.json` no longer names `./hooks/hooks.json`: Claude Code loads the standard file on its own (its debug log said “names the standard hooks/hooks.json, which loads on its own”).
- README: an Autopilot section (what fires on its own, with the switches), the hooks table and the version line, which still said 2.4.0.

### Passive-trigger audit
Every skill, command, rule, reference and agent was checked for whether it works when the session reaches it on its own (from a description, the bootstrap, a hook note or a pointer), in parallel: 18 headless sessions with prompts that describe a situation without naming the skill, four read-only audits split by area (workflow skills, quality/thinking/docs, domain skills and agents, rules/references reachability) and an independent review of the hook code. Fixes were applied by four agents with disjoint file ownership.
- **Router** (from the headless misses): “tests are red” is a bug; domain skills are named even without a change verb, with tighter keywords (no Datadog skill for CloudWatch alarms, no React skill for React Native, no messaging skill for Pact consumers) and a new `backend-languages` entry; “threat model” points to `security-engineer-subagent`; a question that opens with does/is/how stays a question even when it ends with an ask; new intents for readiness before a PR (`validate-feature`), “get it reviewed” (`requesting-code-review`) and “give me the source” (`find-docs`).
- **Hook code** (from the review): shell writes missed by the new detector are caught again (`1>`, `&>`, `&>>`, `>|`, every `tee` operand, `sed --in-place`, `perl -p -i`, inline Python writes across lines); a test run is a segment that starts with a runner, so `npm install -D jest`, `cat jest.config.js` or `mvn verify -DskipTests` no longer clear the verification gate or record RED, and a write chained after a test run is tracked; path detection is linear (a 40k-character command took 51 s before); state files are written atomically and not rewritten by read-only calls; `check-setup.py` loads each root's autopilot privately and runs the session-start hook with a scratch HOME so it never prunes real state; `rules_bytes` is replaced by `bootstrap_bytes` (the always-on cost).
- **Bootstrap and workflow skills**: skills are named `tea-sdlc:<name>` and win over same-named superpowers skills; opener skills (`goal`, `clarify`, `expert-lens`, `reframe`) may precede brainstorming (a headless “end-to-end” prompt never loaded `goal` before); brainstorming walks the trust-boundary check first and writes the spec folder (README frontmatter, requirements, design, contracts, ADRs) with one approval point in the full workflow only; `finishing-a-development-branch` commits, records the pre-PR review before `gh pr create`, finds the base branch itself, keeps the worktree after a PR and promotes docs after a merge; `subagent-driven-development` names its prompt templates and closes with QA and `upgrade-service-docs`; `dispatching-parallel-agents` no longer fires on the fast path; `writing-plans` uses one checkbox per task (what the snapshot and `executing-plans` read).
- **Quality skills and commands**: one owner per “before done” role (`verification-before-completion` routine, `prove-it` when the user doubts, `validate-feature` for a whole change set); `requesting-code-review` follows `rules/pre-pr-review.md` per tier and records `mark-pr-review.py`; `generate-service-docs` runs on the current repository when no service is named; `writing-software-docs` saves spec artifacts and creates the spec README; `find-polluter.sh` no longer reports “all clean” when no test file matched; `incident-to-eval` stops for a local revert; `context7-mcp` is removed (a subset of `find-docs`); superpowers leftovers removed from `receiving-code-review`.
- **Rules and references**: `workflow-routing.md` agrees with the bootstrap (brainstorming first, two tiers only); `rules/agents.md` is a short registry; the staleness check counts commits since the doc and uses the README `updated:` field; the dispatch contract reference lost its TechLead/BA wording and half its size; the README template no longer disables the contract gate; one canonical `references/observability-patterns.md`; unsourced regulatory deadlines removed from `data-privacy-patterns.md`; CONTRIBUTING gains a reachability rule.
- **Domain skills and agents**: `backend-languages` reads its language files by path and is usable on the fast path; `data-engineer` uses the reference's PII scale; agents preload only their core skill (data-engineer about 13k tokens lighter per dispatch); every agent ends with the status/evidence/exit-check contract; implementers escalate contract-gate findings instead of editing `contracts/`; `fintech-security` is a candidate-control catalogue for the security agent; corrected code that would mislead an implementer (money as floats, 2-decimal currency assumption, axum 0.8 paths, pact-go v2, Delta Z-order on a partition column, unbound JDBC watermark, NULL-blind SCD2, expand/contract rename, Gradle without `useJUnitPlatform()`, X-Ray wildcard IAM test), library facts checked with Context7 or the package registries where noted in the agent report.

### Verified
- `python3 -m unittest discover -s tests`: 107 tests pass. `python3 scripts/check-setup.py`: PASS.
- Headless runs with `claude -p --plugin-dir` (Claude Code 2.1.319, `sonnet`), one run per scenario. The prompt note reached the model verbatim. On “add mul()” the session loaded `brainstorming`, stated Fast path, and wrote and ran a failing test before the code. On a “pure rename” it first finished with “I ran no tests”; the Stop gate sent it back, and it checked the callers and ran `npm test` before reporting.
- Passive triggering, 18 headless sessions (Claude Code 2.1.319, default model, one run per case, prompts that describe the situation without naming the skill): 9/18 loaded an expected skill before the audit, 14/18 after it, 16/18 after the last router and brainstorming fixes. The two left are a one-line failing test the session fixed from the test output without `systematic-debugging`, and a single SQL query it wrote and ran without `database-patterns`.
- Router precision, replayed locally on 198 distinct past prompts of one user (not committed): the first version annotated 82 of them, mostly questions, prompt/README edits and git chores; this release annotates 16, each a code change, a bug report or a pasted implementation prompt.

## 2.8.0 — 2026-11-17

### Removed (breaking)
- `agents/tech-lead-subagent.md` and `agents/business-analyst-subagent.md`. Their runs added cost without value when acceptance criteria were given and no external contract changed. The main session now writes `requirements.md`, `design.md`, `contracts/`, ADRs and `glossary.md` (skills `brainstorming`, `writing-plans`, `writing-software-docs`); Security and UI/UX keep their agents. `references/documentation-layout.md` and `rules/strategic-output-persistence.md` name the main session as the single writer of those files.
- The orchestrator tier and the skill `orchestrating-multi-domain-work`: a trust-boundary change is now a full workflow whatever the number of domains (independent domain tasks run in parallel when safe, then code review, then QA).
- The coordinated-fast-path tier: fast path covers several domains without a trust boundary (task order in 2-3 lines, dependency order, integration check before merge). Routing now has two tiers.

### Added
- Skill `measurement-planning`: the measurement and growth part of the former BA agent (North Star, funnel, event taxonomy, experiments, GTM) as a specification skill; it writes `measurement.md`.
- Contract gate: `scripts/check-contract.py` checks a spec's `contracts/` when its README declares `contract: external` (OpenAPI full document or delta: operationId, 2xx response, `{error:{code,message}}` envelope, resolvable `$ref`; breaking-change detection against the authoritative source unless `breaking: approved`). YAML is parsed with PyYAML when installed, else with ruby (preinstalled on macOS); with neither, the gate warns and does not report a clean pass. `hooks/contract-gate.py` blocks the first production change of a session once when an active spec fails it; `hooks/pr-review-gate.py` blocks `gh pr create` while it fails. `qa-subagent` runs it. 23 unit tests.

### Changed
- `contract: none | external`, `contract_source` and `breaking` join the spec README frontmatter.

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
