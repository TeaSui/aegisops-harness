# tea-sdlc

> Software Development Life Cycle plugin for Claude Code — specialist subagents, trust-boundary routing, a canonical documentation layout and automated quality gates.

**Version 3.3.0** · [How it works (one page)](HOW-IT-WORKS.md) · [Changelog](CHANGELOG.md) · MIT

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
| Every prompt | Keyword router: code change → `brainstorming` → `test-driven-development`; bug or error → `systematic-debugging` (`debug-parallel` across services); trust-boundary words (PII, auth, money, new endpoint, vendor, secrets) → fast path with a security pass (lean, the default) or Full workflow (full mode); domain skills by name, even without a change verb (Go/Spring/FastAPI, SQL, Kafka, CDK, React, Flutter, Datadog, threat model → `fintech-security`, plus `tea-sdlc:security-engineer-subagent` in full mode); readiness (“ready before I open a PR”), review (“get it reviewed”), PR, docs, incident, “are you sure?”, “give me the source”, “end-to-end” → the matching skill or command. English keywords only. Silent for questions (ending in `?`, or opening with does/is/how… and containing one), small talk, and changes to prose or git/ops (prompts, rules, README, branches, versions, commits) | `autopilot.py prompt` |
| Before the first production edit | Write a failing test first (once per session) · fix a failing external contract first | `tdd-gate.py`, `contract-gate.py` |
| After tool calls | Three failing test runs in a row → `systematic-debugging`; `git revert` → `incident-to-eval`; a merge while a spec is `shipped` (or a pre-AIDLC spec is `accepted`) → `upgrade-service-docs` | `autopilot.py post` |
| Before the session says “done” | Code changed since the last test run → run the tests or say why none applies (once per change set, at most 3 per session) | `autopilot.py stop` |
| A subagent starts | The house rules travel with it (subagents never see the bootstrap) | `autopilot.py subagent` |
| `git commit` / `git push` / `gh pr create` / `gh pr merge` | Secret scan · review stage done · ship stage done | `security-gate.py`, `pr-review-gate.py`, `ship-gate.py` |

Notes are hints, not orders: the session skips any that does not fit and names what it applied. Measured on real headless sessions (Claude Code 2.1.319, `sonnet`): with the prompt note the session loaded `brainstorming`, stated the tier and wrote a failing test before the code; on a “pure rename” it first answered *“I ran no tests”*, the stop gate sent it back, and it ran the suite before reporting.

Switches (environment variables, all default on): `TEA_SDLC_WORKFLOW=full` (opt in to the subagent-based full workflow; the default is lean), `TEA_SDLC_AUTOPILOT=off` (prompt and follow-up notes, session snapshot, subagent rules), `TEA_SDLC_SHIP_GATE=off`, `TEA_SDLC_VERIFY_GATE=off`, `TEA_SDLC_TDD_GATE=off`, `TEA_SDLC_CONTRACT_GATE=off`.

---

## 🧭 Workflow routing

Every substantive task is classified by `rules/workflow-routing.md`: does it cross a **trust boundary** (PII, auth, payments, new public surface or vendor, secrets/IAM/crypto config)?

```
Trust boundary?
 ├─ NO  ──► Fast path                        TDD, no subagents, single pre-PR review (several domains: edit in order, integration check)
 └─ YES ─┬─ lean mode (default) ──► Fast path + security pass   same session, no subagents: assets/threats/controls
         │                                                       before the first edit, security tests, threats in the PR
         └─ full mode ───────────► Full workflow                the AIDLC stage machine below, every stage behind a gate
```

**Workflow mode.** Specialist subagents multiply token cost, so the default is **lean**: every change stays in the main session. Turn on **full** mode per project or per user with `TEA_SDLC_WORKFLOW=full` (for example `"env": {"TEA_SDLC_WORKFLOW": "full"}` in `.claude/settings.json`), or for one task by asking for it ("full workflow", "AIDLC", "use subagents"). A spec already in progress on the branch finishes in full mode. The session-start note states the mode.

When a fast-path change discovers a trust boundary mid-task, it moves up to that mode's trust-boundary tier before writing more code.

---

## 🔁 AIDLC — spec → plan → build → test → review → ship

A full-workflow change lives in `docs/specs/<feature>/` and moves through stages. Only `scripts/aidlc.py advance` moves it, and only when the gate of the next stage passes. The gates are code (no model call): they check that the evidence exists and still matches the code. Formats and gates: [`references/aidlc.md`](references/aidlc.md).

| Stage | Artifact | Gate checks | Skill |
|---|---|---|---|
| **spec** → `accepted` | `spec.md`: Problem Statement, Solution, numbered User Stories (story n = `RFD-n`), Implementation Decisions with `### Security`, Testing Decisions, Out of Scope | every template section filled, story numbers unique, `Verify:` tags valid, security decisions present, any `spec-check.md` guess closed, contract gate, one recorded approval | `brainstorming`, `spec-check` |
| **plan** → `planned` | `tickets.md`: tracer-bullet vertical slices (`Blocked by`, `Covers`, acceptance checkboxes, `Test`, `Files`) | every story covered, no cycle, no file shared by tickets that may run in parallel | `writing-plans` |
| **build** → `building` | feature branch; `ledger.md` | branch recorded, not the default branch | `subagent-driven-development` |
| **test** → `verified` | `aidlc task-done` / `aidlc verify` ledger events | every ticket `done` by a passing test command, every story referenced by a test, a green run whose **code fingerprint** matches the current code, no failing story test in JUnit | `subagent-driven-development`, `verification-before-completion` |
| **review** → `reviewed` | `review.md`: Spec axis, Standards axis, QA verdict | no open finding, QA GO, review stamped against the current code | `requesting-code-review`, `receiving-code-review` |
| **ship** → `shipped` | `ship.md`: GO, rollback, post-release verification | CI green (`gh pr checks`), changelog has the version, code unchanged since review | `shipping` |
| **promote** → `implemented` | living docs, README traceability table | traceability written | `/upgrade-service-docs` |

What it gives you that a prose workflow cannot:

- **Requirement → test traceability.** `aidlc trace <feature>` prints every story with the tickets that cover it, the tests that reference it and their last result; `--write` puts the table in the spec README.
- **Parallel build without conflicts.** `aidlc next <feature>` returns the tickets whose blockers are done, in batches that share no file; the build skill dispatches a batch at once.
- **Decisions instead of stalls.** The session records `aidlc ruling` (decision, why, cost if wrong) and keeps going; the ledger is the decision record a reviewer reads.
- **Evidence that cannot go stale silently.** Test runs and reviews are keyed to a fingerprint of the code; change one line and the gate asks for a fresh run.
- **Hard stops where they matter.** `gh pr create` waits for the review stage, `gh pr merge` for the ship stage (`hooks/ship-gate.py`).

```bash
python3 scripts/aidlc.py status                  # every spec, its stage, what blocks the next gate
python3 scripts/aidlc.py next refunds            # tickets ready to build, in conflict-free parallel batches
python3 scripts/aidlc.py check refunds --to verified
python3 scripts/aidlc.py trace refunds --write
```

The session runs these itself; the session-start snapshot shows each active spec's stage, its blockers and its next batch.

Measured on the pre-3.3.0 spec format (`evals/headless --suite lifecycle`, 3 real sessions, Claude Code 2.1.319): from one prompt asking for wallet refunds "all the way to a change that is ready to ship", naming no skill, stage or command, every session wrote keyed requirements, closed its blind spec check, planned a task graph, built and verified on a fingerprint, ran a two-axis review with QA, opened a PR, waited for CI that runs the tests, wrote `ship.md` and passed the `shipped` gate — 3/3, every stage, every requirement traced to a passing test.

---

## 🤖 Subagents (`agents/`)

Agents use **family aliases**, so they always run on the latest release of that model family. Rationale and override guidance: [`references/model-guide.md`](references/model-guide.md).

| Agent | Responsibility | Model | Effort |
|---|---|---|---|
| `tea-sdlc:security-engineer-subagent` | Threat model (STRIDE, OWASP), numbered security rules for the spec before implementation | sonnet | high |
| `tea-sdlc:code-reviewer` | Read-only, independent review against spec, contract and standards | sonnet | medium |
| `tea-sdlc:ui-ux-designer-subagent` | Flows, wireframes, component states, accessibility specs | sonnet | medium |
| `tea-sdlc:backend-engineer-subagent` | APIs, business logic, databases, integrations, LLM/RAG/agent features with evals | sonnet | high |
| `tea-sdlc:frontend-engineer-subagent` | Web UI, accessibility, client performance | sonnet | high |
| `tea-sdlc:mobile-engineer-subagent` | Flutter, iOS, Android, React Native, secure storage, offline | sonnet | high |
| `tea-sdlc:platform-engineer-subagent` | AWS CDK/serverless, non-AWS IaC, CI/CD, containers, Kubernetes, observability | sonnet | high |
| `tea-sdlc:data-engineer-subagent` | Data models, migrations, ETL/ELT, warehouses, data quality | sonnet | high |
| `tea-sdlc:qa-subagent` | Final release gate (GO / NO-GO) plus live API smoke, performance, security-smoke and stress checks | sonnet | medium |

The main session dispatches every specialist as a first-level dispatch. Every dispatch follows the nine-field contract in `rules/dispatch-prompt-contract.md`, and every return carries a status, evidence paths and an exit-criteria check (`rules/subagent-return-format.md`).

---

## 📚 Documentation layout

One structure for every agent, command and skill, owned by [`references/documentation-layout.md`](references/documentation-layout.md). Documents are separated by **lifecycle**, not by author:

| Kind | Location | Lifecycle |
|---|---|---|
| Living reference — what the system does now | `docs/*.md` per service; `docs/00-overview … 04-ai-friendly/` at system level | Rewritten to match verified code by `/generate-service-docs` and `/upgrade-service-docs` |
| Change spec — what we are changing and why | `docs/specs/<feature>/` | AIDLC stages `proposed → accepted → planned → building → verified → reviewed → shipped → implemented` |
| Decision record | `docs/adr/NNNN-<slug>.md`, only for a hard-to-reverse, surprising trade-off | Immutable once accepted |
| Workflow state | `docs/specs/<feature>/tickets.md`, `docs/plans/` | Disposable |

```
<service>/docs/
├── README.md  architecture.md  business-logic.md  api-contracts.md  data-model.md
├── events.md  security.md  configuration.md  troubleshooting.md  diagrams/
├── adr/                      NNNN-<slug>.md (main session)
└── specs/<feature>/
    ├── README.md             stage frontmatter (key, branch, status) + traceability (main session, aidlc)
    ├── spec.md               stories RFD-1 …, decisions incl. Security (from security-engineer) and UI, testing seams
    ├── spec-check.md         optional blind spec check: every guess closed (spec-check)
    ├── contracts/            only for contract: external (checked by scripts/check-contract.py)
    ├── measurement.md        measurement-planning (when in scope)
    ├── tickets.md            vertical slices (writing-plans); Status: done set only by aidlc task-done
    ├── ledger.md             aidlc only: advances, task-done, verify, rulings, stamps
    ├── review.md             Spec + Standards axes + QA verdict
    └── ship.md               GO / NO-GO, rollback, post-release verification
```

Project level: `GLOSSARY.md` (domain terms). Legacy specs (`requirements.md`, `plan.md`) still pass their pre-3.3.0 gates. Existing projects keep their established locations; the layout file maps legacy folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, …) and nothing is migrated automatically.

---

## ⌨️ Slash commands (`commands/`)

| Command | Purpose |
|---|---|
| `/generate-service-docs` | Build or normalize the living service and system docs from source code |
| `/upgrade-service-docs` | Promote stage: fold a shipped change into the living docs, write its traceability table and close its spec |
| `/debug-parallel` | Parallel config, diagnostics, code-path and history investigation for multi-service errors |
| `/prove-it` | List every claim just made and run a check that would fail if it were false; narrow or withdraw what the evidence does not support |
| `/prompt-builder` | Design a Claude prompt from a description; a software change gets a prompt that follows the tier: fast path (spec → tdd → implement → test → PR) or the AIDLC stages |
| `/eval-upgrade` | Score, upgrade and A/B-duel Claude Code assets with the bundled tool in `tools/eval-upgrade/` (Node ≥ 20, no dependencies); state is kept in `~/.claude/state/eval-upgrade` |

---

## 🧩 Skills (`skills/`)

| Area | Skills |
|---|---|
| Workflow (AIDLC) | `session-bootstrap`, `brainstorming` (spec), `grilling` (decisions, `GLOSSARY.md`, ADRs), `spec-check` (optional blind spec check), `measurement-planning`, `writing-plans` (tickets), `subagent-driven-development` (parallel build), `executing-plans`, `dispatching-parallel-agents`, `shipping` (ship stage), `goal` |
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
| `pr-review-gate.py` | PreToolUse (Bash) | Blocks `gh pr create` until the review is done: on a branch bound to a full-workflow spec, until the spec passes the `reviewed` gate (keyed to the code fingerprint); otherwise until a review with zero open findings is recorded for `HEAD` via `scripts/mark-pr-review.py`. Also blocks while an active external contract fails the contract gate |
| `ship-gate.py` | PreToolUse (Bash) | Blocks `gh pr merge` of a branch bound to a full-workflow spec until the spec passes the `shipped` gate (GO decision, rollback plan, green CI, code unchanged since review). Off with `TEA_SDLC_SHIP_GATE=off` |
| `contract-gate.py` | PreToolUse (Edit/Write/Bash) | Advisory: when an active spec declares an external contract that fails `scripts/check-contract.py`, blocks the first production-code change of a session once. Off with `TEA_SDLC_CONTRACT_GATE=off` |
| `tdd-gate.py` | PreToolUse (Edit/Write/Bash) + PostToolUse (Bash) | Advisory: records a failing test run per session and blocks the first production-code change that has none, once. A test run is a command segment that starts with a runner (npm/pnpm/yarn/bun, vitest/jest/playwright, pytest/unittest/tox, Gradle/Maven, Go, Cargo, .NET, Flutter, Swift, RSpec and more), so `npm install -D jest` is not one; shell writes are detected by their target (`>`, `1>`, `&>`, `>|`, `tee`, `sed -i`, `perl -i`, inline `open(…,'w')`). Off with `TEA_SDLC_TDD_GATE=off` |
| `autopilot.py` | UserPromptSubmit, PostToolUse (Edit/Write/Bash), Stop, SubagentStart | Prompt router, follow-up notes, the verification gate, and the house rules injected into every subagent (leaf only, return contract, TDD, requirement IDs in test names, stay in your files). Never blocks a tool call; fails silent |
| `session-start` | SessionStart | Injects the `session-bootstrap` skill (≤ 48 KiB) with the plugin root resolved, plus the project snapshot (each active spec's stage, blockers and next batch) |

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

Checks manifests and version, that every bundled file is tracked by git (a personal ignore pattern cannot drop one from the release), agent/skill/command frontmatter (alias-only models, valid effort, YAML), that every bundled path reference resolves, that every hook compiles and every `tea-sdlc:<name>` the autopilot can name is a real skill or command, that no `~/.claude/` path or misplaced `${CLAUDE_PLUGIN_ROOT}` remains, and the SessionStart output contract. Run it and `python3 -m unittest discover -s tests` before every release, then bump `version` in `.claude-plugin/plugin.json` and add a `CHANGELOG.md` entry.

Evaluations ([`evals/README.md`](evals/README.md)):

```bash
python3 evals/routing/run.py                       # 144 router cases, free, also in CI
python3 evals/descriptions/run.py                  # description lint + collision check, free, also in CI
python3 evals/headless/run.py --suite passive,tdd --runs 3 --compare   # real Claude sessions, paid
python3 evals/headless/run.py --suite lifecycle --runs 2               # full mode spec → ship, and lean mode by outcome; paid
```

`.github/workflows/ci.yml` runs the unit tests, `check-setup.py` and the free evals on Python 3.9 and 3.12 for every push and PR; `evals.yml` runs the paid suites weekly or on demand and fails on a regression against `evals/headless/baseline.json`. A change to a skill description, the router or the bootstrap must not lower a suite's score.

`scripts/validate.sh` starts a headless Claude session that validates pending work in a target project with the `validate-feature` skill.

---

## 📁 Repository structure

```
tea-sdlc/
├── .claude-plugin/
│   ├── plugin.json          # Manifest (name, version)
│   └── marketplace.json     # Marketplace entry
├── agents/                  # 9 subagent definitions
├── .github/workflows/       # ci.yml (tests, check-setup, free evals), evals.yml (paid headless suites)
├── commands/                # 6 slash commands
├── evals/                   # routing, description lint, headless passive/tdd/lifecycle suites, baseline
├── hooks/                   # hooks.json, autopilot.py, security-gate.py, pr-review-gate.py, ship-gate.py, tdd-gate.py, contract-gate.py, session-start
├── references/              # Shared guidance (documentation layout, model guide, …)
├── rules/                   # Routing, contracts, review and persistence rules
├── scripts/                 # aidlc.py (lifecycle engine), check-setup.py, check-contract.py, mark-pr-review.py, validate.sh
├── skills/                  # Workflow, quality and domain skills
├── tests/                   # unit tests for hooks, engine and evals
├── CHANGELOG.md
└── README.md
```

---

## 📄 License

MIT © [Tea Nguyen](https://github.com/TeaSui)
