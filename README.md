# tea-sdlc

> Software Development Life Cycle plugin for Claude Code — specialist subagents, trust-boundary routing, a canonical documentation layout and automated quality gates.

**Version 2.9.0** · [Changelog](CHANGELOG.md) · MIT

`tea-sdlc` turns Claude Code into a coordinated engineering team: 9 specialist subagents, a 2-tier workflow router that escalates on trust boundaries, one documentation structure shared by every agent and command, and hooks that block secret leaks and unreviewed PRs — plus an **autopilot**, so you never have to remember a slash command or a skill name.

---

## 🚀 Install

### From the marketplace (recommended)

```text
/plugin marketplace add TeaSui/tea-sdlc
/plugin install tea-sdlc@tea-sdlc
```

### From a local clone (development)

```bash
claude --plugin-dir /path/to/tea-sdlc
```

### Updating

Releases are driven by `version` in `.claude-plugin/plugin.json`; pushing commits without bumping it does not reach installed users. Third-party marketplaces do not auto-update by default:

```text
/plugin marketplace update tea-sdlc
/reload-plugins
```

### Requirements

| Tool | Used by |
|---|---|
| `python3` | All hooks and `scripts/` |
| [`gitleaks`](https://github.com/gitleaks/gitleaks) | Secret gate on `git commit` / `git push` (fails closed when missing) |
| `gh` | PR review gate (`gh pr create`) |
| `ruby` (optional) | Full YAML parsing in `scripts/check-setup.py` and `scripts/check-contract.py` (when PyYAML is absent) |

---

## 🛫 Autopilot — nothing to remember

You describe the work in English; the plugin decides which skill, command and gate applies and the session runs them itself. Every slash command below still works when you want it, but none is required.

| When | What fires on its own | Hook |
|---|---|---|
| Session start, resume, `/clear`, compaction | Bootstrap plus a project snapshot: active specs with their plan progress and next step, a resumable `.goal/state.md`, open plans, a repository with no `docs/` yet, the superpowers plugin enabled alongside (use the tea-sdlc twin of each shared skill), a missing `gitleaks` (also shown to you, with the install command). Gate state older than 30 days is pruned | `session-start` |
| Every prompt | Keyword router: code change → `brainstorming` → `test-driven-development`; bug or error → `systematic-debugging` (`debug-parallel` across services); trust-boundary words (PII, auth, money, new endpoint, vendor, secrets) → Full workflow; domain skills by name, even without a change verb (Go/Spring/FastAPI, SQL, Kafka, CDK, React, Flutter, Datadog, threat model → `security-engineer-subagent`); readiness (“ready before I open a PR”), review (“get it reviewed”), PR, docs, incident, “are you sure?”, “give me the source”, “end-to-end” → the matching skill or command. English keywords only. Silent for questions (ending in `?`, or opening with does/is/how… and containing one), small talk, and changes to prose or git/ops (prompts, rules, README, branches, versions, commits) | `autopilot.py prompt` |
| Before the first production edit | Write a failing test first (once per session) · fix a failing external contract first | `tdd-gate.py`, `contract-gate.py` |
| After tool calls | Three failing test runs in a row → `systematic-debugging`; `git revert` → `incident-to-eval`; a merge while a spec is still `accepted` → `upgrade-service-docs` | `autopilot.py post` |
| Before the session says “done” | Code changed since the last test run → run the tests or say why none applies (once per change set, at most 3 per session) | `autopilot.py stop` |
| `git commit` / `git push` / `gh pr create` | Secret scan · pre-PR review recorded for `HEAD` | `security-gate.py`, `pr-review-gate.py` |

Notes are hints, not orders: the session skips any that does not fit and names what it applied. Measured on real headless sessions (Claude Code 2.1.319, `sonnet`): with the prompt note the session loaded `brainstorming`, stated the tier and wrote a failing test before the code; on a “pure rename” it first answered *“I ran no tests”*, the stop gate sent it back, and it ran the suite before reporting.

Switches (environment variables, all default on): `TEA_SDLC_AUTOPILOT=off` (prompt and follow-up notes, session snapshot), `TEA_SDLC_VERIFY_GATE=off`, `TEA_SDLC_TDD_GATE=off`, `TEA_SDLC_CONTRACT_GATE=off`.

---

## 🧭 Workflow routing

Every substantive task is classified by `rules/workflow-routing.md` on two axes: does it cross a **trust boundary** (PII, auth, payments, new public surface or vendor, secrets/IAM/crypto config) and how many **domains** it touches.

```
Trust boundary?
 ├─ NO  ──► Fast path       TDD, no subagents, single pre-PR review (several domains: edit in order, integration check)
 └─ YES ──► Full workflow   Security → contract gate (external contract) → plan → implement → review → QA
```

Gated tiers end with `/upgrade-service-docs` after QA `GO` or merge, which promotes the shipped change into the living docs. Promotion to a heavier tier mid-task is mandatory when scope grows (e.g. a fast-path change discovers a trust boundary).

---

## 🤖 Subagents (`agents/`)

Agents use **family aliases**, so they always run on the latest release of that model family. Rationale and override guidance: [`references/model-guide.md`](references/model-guide.md).

| Agent | Responsibility | Model | Effort |
|---|---|---|---|
| `security-engineer-subagent` | Threat model (STRIDE, OWASP), numbered security rules before implementation | opus | high |
| `code-reviewer` | Read-only, independent review against plan, contract and standards | opus | medium |
| `ui-ux-designer-subagent` | Flows, wireframes, component states, accessibility specs | sonnet | medium |
| `backend-engineer-subagent` | APIs, business logic, databases, integrations, LLM/RAG/agent features with evals | sonnet | high |
| `frontend-engineer-subagent` | Web UI, accessibility, client performance | sonnet | high |
| `mobile-engineer-subagent` | Flutter, iOS, Android, React Native, secure storage, offline | sonnet | high |
| `platform-engineer-subagent` | AWS CDK/serverless, non-AWS IaC, CI/CD, containers, Kubernetes, observability | sonnet | high |
| `data-engineer-subagent` | Data models, migrations, ETL/ELT, warehouses, data quality | sonnet | high |
| `qa-subagent` | Final release gate (GO / NO-GO) plus live API smoke, performance, security-smoke and stress checks | sonnet | medium |

The main session dispatches every specialist as a first-level dispatch. Every dispatch follows the nine-field contract in `rules/dispatch-prompt-contract.md`, and every return carries a status, evidence paths and an exit-criteria check (`rules/subagent-return-format.md`).

---

## 📚 Documentation layout

One structure for every agent, command and skill, owned by [`references/documentation-layout.md`](references/documentation-layout.md). Documents are separated by **lifecycle**, not by author:

| Kind | Location | Lifecycle |
|---|---|---|
| Living reference — what the system does now | `docs/*.md` per service; `docs/00-overview … 04-ai-friendly/` at system level | Rewritten to match verified code by `/generate-service-docs` and `/upgrade-service-docs` |
| Change spec — what we are changing and why | `docs/specs/<feature>/` | `proposed → accepted → implemented / superseded` |
| Decision record | `docs/adr/NNNN-<decision>.md` | Immutable once accepted |
| Workflow state | `docs/specs/<feature>/plan.md`, `docs/plans/` | Disposable |

```
<service>/docs/
├── README.md  architecture.md  business-logic.md  api-contracts.md  data-model.md
├── events.md  security.md  configuration.md  troubleshooting.md  diagrams/
├── adr/                      NNNN-<decision>.md (main session)
└── specs/<feature>/
    ├── README.md             status frontmatter + traceability (integrating session)
    ├── requirements.md       main session
    ├── measurement.md        main session, skill measurement-planning (when in scope)
    ├── ui-design.md          ui-ux-designer
    ├── security.md           security-engineer
    ├── design.md, contracts/ main session (contracts checked by scripts/check-contract.py)
    └── plan.md               writing-plans
```

Existing projects keep their established locations; the layout file maps legacy folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, …) and nothing is migrated automatically.

---

## ⌨️ Slash commands (`commands/`)

| Command | Purpose |
|---|---|
| `/generate-service-docs` | Build or normalize the living service and system docs from source code |
| `/upgrade-service-docs` | Promote an implemented change into the living docs and close its spec |
| `/debug-parallel` | Parallel config, diagnostics, code-path and history investigation for multi-service errors |
| `/prove-it` | List every claim just made and run a check that would fail if it were false; narrow or withdraw what the evidence does not support |
| `/prompt-builder` | Design a Claude prompt from a description; software changes follow spec → adr → tdd → implement → test → PR |
| `/eval-upgrade` | Score, upgrade and A/B-duel Claude Code assets with the bundled tool in `tools/eval-upgrade/` (Node ≥ 20, no dependencies); state is kept in `~/.claude/state/eval-upgrade` |

---

## 🧩 Skills (`skills/`)

| Area | Skills |
|---|---|
| Workflow | `session-bootstrap`, `brainstorming`, `measurement-planning`, `writing-plans`, `subagent-driven-development`, `executing-plans`, `dispatching-parallel-agents`, `goal` |
| Quality | `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `validate-feature`, `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch`, `incident-to-eval` |
| Grounding | `grounding-claims` (codebase and command facts), `find-docs` (library, SDK and CLI facts via Context7 or official docs) |
| Thinking tools | `clarify` (ask only what changes the work), `expert-lens` (what the best practitioner would notice, do first, refuse), `reframe` (strongest case against the current view) — triggered by the situation or as `/clarify`, `/expert-lens`, `/reframe` |
| Documentation | `writing-software-docs` (BRD, PRD, FRD, user stories, RFC, ADR, specification, concern report) |
| Domain | `backend-languages`, `frontend-react`, `fintech-mobile`, `fintech-security`, `database-patterns`, `messaging-patterns`, `data-pipeline-patterns`, `api-contract-testing`, `bdd-cucumber`, `cdk-testing`, `observability` |

Claude API work uses Claude Code's built-in **`/claude-api`** skill plus live documentation; the sources and the "resolve the latest model ID, pin it in config" rule are in [`references/ai-integration-patterns.md`](references/ai-integration-patterns.md).

---

## 🛡️ Hooks (`hooks/hooks.json`)

| Hook | Event | Behavior |
|---|---|---|
| `security-gate.py` | PreToolUse (Bash) | Runs `gitleaks` before `git commit` (staged content) / `git push`; blocks on findings or when gitleaks is unavailable. `git commit -a` is not covered — keep CI scanning as the backstop |
| `pr-review-gate.py` | PreToolUse (Bash) | Blocks `gh pr create` until a pre-PR review with zero open findings is recorded for `HEAD` via `scripts/mark-pr-review.py`, and while an active external contract fails the contract gate |
| `contract-gate.py` | PreToolUse (Edit/Write/Bash) | Advisory: when an active spec declares an external contract that fails `scripts/check-contract.py`, blocks the first production-code change of a session once. Off with `TEA_SDLC_CONTRACT_GATE=off` |
| `tdd-gate.py` | PreToolUse (Edit/Write/Bash) + PostToolUse (Bash) | Advisory: records a failing test run per session and blocks the first production-code change that has none, once. Recognises npm/pnpm/yarn/bun, vitest/jest/playwright, pytest/unittest/tox, Gradle/Maven, Go, Cargo, .NET, Flutter, Swift, RSpec and more; shell writes are detected by their target (`>`, `tee`, `sed -i`, inline `open(…,'w')`), not by any code path in a command. Off with `TEA_SDLC_TDD_GATE=off` |
| `autopilot.py` | UserPromptSubmit, PostToolUse (Edit/Write/Bash), Stop | Prompt router, follow-up notes and the verification gate described in **Autopilot**. Never blocks a tool call; fails silent |
| `session-start` | SessionStart | Injects the `session-bootstrap` skill (≤ 48 KiB) with the plugin root resolved, plus the project snapshot |

---|---|---|
| `security-gate.py` | PreToolUse (Bash) | Runs `gitleaks` before `git commit` (staged content) / `git push`; blocks on findings or when gitleaks is unavailable. `git commit -a` is not covered — keep CI scanning as the backstop |
| `pr-review-gate.py` | PreToolUse (Bash) | Blocks `gh pr create` until a pre-PR review with zero open findings is recorded for `HEAD` via `scripts/mark-pr-review.py` |
| `contract-gate.py` | PreToolUse (Edit/Write/Bash) | Advisory: when an active spec declares an external contract that fails `scripts/check-contract.py`, blocks the first production-code change of a session once. `pr-review-gate.py` enforces it strictly before a PR. Off with `TEA_SDLC_CONTRACT_GATE=off` |
| `tdd-gate.py` | PreToolUse (Edit/Write/Bash) + PostToolUse (Bash) | Advisory: records a failing test run per session and blocks the first production-code change that has none, once, with a reminder to write the test and see it fail. Off with `TEA_SDLC_TDD_GATE=off` |
| `session-start` | SessionStart | Injects the `session-bootstrap` skill (≤ 48 KiB) with the plugin root resolved |

---

## 📐 Rules & references

- **`rules/`** — routing (`workflow-routing.md`), agent registry (`agents.md`), dispatch contract and return format, review-loop limits, pre-PR review, strategic-output persistence and staleness, hallucination reduction, code patterns (API envelope). Authoring rules for maintainers are in `CONTRIBUTING.md`.
- **`references/`** — documentation layout, model guide, agent discipline, AI integration, AWS, observability, data privacy, bootstrap checklist, security-review checklist and OWASP mapping.

**Path convention:** agents, commands and `SKILL.md` files reference bundled files as `${CLAUDE_PLUGIN_ROOT}/…` (substituted by Claude Code). Inside `rules/`, `references/` and other files opened with Read, paths such as `rules/…` are relative to the plugin root. Project paths such as `docs/…` are relative to the target project. Nothing depends on `~/.claude/`.

---

## ✅ Validating changes

```bash
python3 scripts/check-setup.py
```

Checks manifests and version, agent/skill/command frontmatter (alias-only models, valid effort, YAML), that every bundled path reference resolves, that every hook compiles and every `tea-sdlc:<name>` the autopilot can name is a real skill or command, that no `~/.claude/` path or misplaced `${CLAUDE_PLUGIN_ROOT}` remains, and the SessionStart output contract. Run it and `python3 -m unittest discover -s tests` before every release, then bump `version` in `.claude-plugin/plugin.json` and add a `CHANGELOG.md` entry.

`scripts/validate.sh` starts a headless Claude session that validates pending work in a target project with the `validate-feature` skill.

---

## 📁 Repository structure

```
tea-sdlc/
├── .claude-plugin/
│   ├── plugin.json          # Manifest (name, version, hooks)
│   └── marketplace.json     # Marketplace entry
├── agents/                  # 9 subagent definitions
├── commands/                # 6 slash commands
├── hooks/                   # hooks.json, autopilot.py, security-gate.py, pr-review-gate.py, tdd-gate.py, contract-gate.py, session-start
├── references/              # Shared guidance (documentation layout, model guide, …)
├── rules/                   # Routing, contracts, review and persistence rules
├── scripts/                 # check-setup.py, check-contract.py, validate.sh, mark-pr-review.py
├── skills/                  # Workflow, quality and domain skills
├── CHANGELOG.md
└── README.md
```

---

## 📄 License

MIT © [Tea Nguyen](https://github.com/TeaSui)
