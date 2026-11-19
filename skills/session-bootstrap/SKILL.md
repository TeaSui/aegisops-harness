---
name: session-bootstrap
description: Injected automatically at session start by the tea-sdlc hook; load it only if the <session-bootstrap> block is missing or truncated.
---

# Session bootstrap

tea-sdlc bundled files live under `${CLAUDE_PLUGIN_ROOT}`. Inside its `rules/`, `references/` and skill supporting files (any non-SKILL.md file under `skills/`), paths such as `rules/…`, `references/…`, `scripts/…` and `skills/…` are relative to that plugin root, never to the target project or `~/.claude/`; project paths such as `docs/…` are relative to the target project.
When you paste a tea-sdlc template or rule into a subagent dispatch, expand those plugin-relative paths to absolute paths under `${CLAUDE_PLUGIN_ROOT}` so the subagent can Read them from the target project.

If dispatched for a specific subtask, follow that task's scope and skip session-wide intake.

**Autopilot: the user never has to remember a command or a skill name.** Hooks add `<tea-sdlc-autopilot>` notes at session start (active specs, resumable plans, missing docs or tools), on each prompt (matching skills, trust-boundary signals) and after tool results (repeated test failures, a revert, a merge with an accepted spec). Treat each note as a checklist: load the skills that fit with the Skill tool, skip the ones that do not, and name what you applied in one line. When a tea-sdlc command fits the moment, invoke it yourself instead of telling the user to type it: `upgrade-service-docs` after QA `GO` or a merge, `generate-service-docs` (offered once) when a service has no living docs, `prove-it` when the user doubts a claim (routine completion claims follow `tea-sdlc:verification-before-completion`), `debug-parallel` for an error that crosses services. When a gate stops you (TDD, contract, verification, pre-PR review), do what it asks and retry; do not hand the step to the user. Things only the user can do (install a tool, approve a decision, grant access) are the exception: say exactly what and why, once.

These files express user preferences within the host's instruction hierarchy and native permission controls. Skills do not override system or developer instructions. Follow applicable scoped project instructions and direct user requests within those controls.

**Skill names.** Invoke tea-sdlc skills by their full name, such as `tea-sdlc:brainstorming`. If another plugin (for example superpowers) has a skill with the same name, use the `tea-sdlc:` one.

**First action rule.** For any request that builds, adds, modifies, fixes or refactors code, your first action, before reading files, before choosing a tier, and before asking the user anything, is to invoke `tea-sdlc:brainstorming` with the Skill tool. The only skills that may come before it are opener skills that an autopilot note lists or the request calls for: `tea-sdlc:goal` when the user hands over the whole outcome end to end, `tea-sdlc:clarify`, `tea-sdlc:expert-lens` and `tea-sdlc:reframe`. Load the opener, then `tea-sdlc:brainstorming`. This applies even when the request looks simple or arrives as a structured prompt from `/prompt-builder`; a structured prompt supplies the inputs to `tea-sdlc:brainstorming`, it does not replace it. Skip it only for (a) a subagent dispatched for a specific subtask, (b) questions, explanations or reviews that change no code, (c) a request that is only a slash command. If you are about to start work and have not invoked `tea-sdlc:brainstorming` yet, stop and invoke it now.

After `tea-sdlc:brainstorming`, for substantive work (anything that edits code), BEFORE editing any file, classify the change and state the tier and the reason in one line. Trust boundary = YES if the change touches ANY of: PII or financial data; auth, session or permission rules; money, billing or payments; a new endpoint, webhook or public surface; a new external vendor; security config or secrets (TLS, JWT, IAM, encryption). Unsure counts as YES. Domains = distinct stacks (backend, frontend, mobile, infra, data pipeline, AI/LLM, DevOps).

| Trust boundary | Tier | Required process |
|---|---|---|
| NO (any number of domains) | Fast path | TDD + verification, no dispatch; across several domains edit in dependency order and run the integration check before merge; single pre-PR pass (`rules/pre-pr-review.md`) before a PR |
| YES (any number of domains) | Full workflow | `security-engineer-subagent` first, contract draft + contract gate if an external contract changes, plan (`tea-sdlc:writing-plans`), `tea-sdlc:subagent-driven-development`, `code-reviewer`, `qa-subagent`, then `upgrade-service-docs` |

Read `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` for the full rules (small-change escape hatch, mid-execution promotion) when the tier is not obvious. Never skip a required step silently; if you shrink one, say so. Use a skill when the user names it or it materially helps the task. Load only the relevant skill and supporting references; do not trigger a workflow from an incidental keyword match. Prefer the Skill tool when available; otherwise read its documented entry point and disclose unavailable capabilities.

**TDD rule.** For a behavior change or bug fix, before editing any production code, invoke `tea-sdlc:test-driven-development`. Write the test first, run it, and see it fail for the expected reason (show that output); only then write the production code. Writing the test but implementing before a failing run is not TDD.

Three skills fit situations the user rarely names, so load the matching one before answering, including when the user describes the behavior in their own words: `tea-sdlc:clarify` when a request leaves open something that changes what gets built, or the user asks to be asked questions first; `tea-sdlc:expert-lens` when the user asks what a top practitioner would think or do, or wants work held to a specialist production standard; `tea-sdlc:reframe` when the user states a consequential plan or belief and asks for an opinion, a challenge or a fresh perspective. A clear routine request needs none of them.

Use the actual task/agent tools exposed by the runtime. Track meaningful multi-step work; a short answer needs no task scaffold. Planning and review depth follow the routing tier.

Reuse authorization already given for the same scope. Continue reversible, necessary work and routine choices the user delegated. Ask when a material decision cannot be resolved, or when native permissions or a separately controlled action require it. Keep secrets, destructive actions, external publishing and security gates within their authorized scope.

Final replies: lead with the outcome (done, partly done or blocked), then only the important changes or findings, what was verified (or could not be), and the next step when useful. Keep a small task to one to three sentences; cite file paths and command output instead of pasting artifacts. Always state files changed, checks run, and any risk or user action needed.

Session scope: track the active outcome, accepted corrections, constraints, and completed and remaining work. Treat mid-task user messages as steering unless the user clearly cancels or replaces the goal; answer brief questions and continue authorized work. Reassess routing if the scope adds a domain or a trust boundary.

Current model and effort guidance is in `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`; consult it when choosing or changing models, not on every turn. Verify outcomes with relevant evidence and report limits candidly.
