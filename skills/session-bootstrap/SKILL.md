---
name: session-bootstrap
description: Establish user workflow preferences at session start; use relevant skills without loading unrelated procedures.
---

# Session bootstrap

tea-sdlc bundled files live under `${CLAUDE_PLUGIN_ROOT}`. Inside its `rules/` and `references/` files, paths such as `rules/…`, `references/…`, `skills/…` and `templates/…` are relative to that plugin root, never to the target project or `~/.claude/`; project paths such as `docs/…` are relative to the target project.
When you paste a tea-sdlc template or rule into a subagent dispatch, expand those plugin-relative paths to absolute paths under `${CLAUDE_PLUGIN_ROOT}` so the subagent can Read them from the target project.

If dispatched for a specific subtask, follow that task's scope and skip session-wide intake.

These files express user preferences within the host's instruction hierarchy and native permission controls. Skills do not override system or developer instructions. Follow applicable scoped project instructions and direct user requests within those controls.

**First action rule.** For any request that builds, adds, modifies, fixes or refactors code, your FIRST action, before reading files, before choosing a tier, and before asking the user anything, is to invoke the `brainstorming` skill with the Skill tool. This applies even when the request looks simple or arrives as a structured prompt from `/prompt-builder`; a structured prompt supplies the inputs to brainstorming, it does not replace it. Skip it only for (a) a subagent dispatched for a specific subtask, (b) questions, explanations or reviews that change no code, (c) a request that is only a slash command. If you are about to start work and have not invoked `brainstorming` yet, stop and invoke it now.

After brainstorming, for substantive work (anything that edits code), BEFORE editing any file, classify the change and state the tier and the reason in one line. Trust boundary = YES if the change touches ANY of: PII or financial data; auth, session or permission rules; money, billing or payments; a new endpoint, webhook or public surface; a new external vendor; security config or secrets (TLS, JWT, IAM, encryption). Unsure counts as YES. Domains = distinct stacks (backend, frontend, mobile, infra, data pipeline, AI/LLM, DevOps).

| Trust boundary | Domains | Tier | Required process |
|---|---|---|---|
| NO | 1 | Fast path | TDD + verification, no dispatch |
| NO | 2+ | Coordinated fast path | `writing-plans` plan, then dispatch domain leaf agents, integration check |
| YES | 1 | Full workflow | Security subagent first, TechLead (contract-mode) if a contract changes, plan, `subagent-driven-development`, QA, then `/upgrade-service-docs` |
| YES | 2+ | Orchestrator | Load skill `orchestrating-multi-domain-work`; Security, TechLead, plan, implement, code review, QA |

Read `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` for the full rules (small-change escape hatch, mid-execution promotion) when the tier is not obvious. Never skip a required step silently; if you shrink one, say so. Use a skill when the user names it or it materially helps the task. Load only the relevant skill and supporting references; do not trigger a workflow from a remote keyword match. Prefer the Skill tool when available; otherwise read its documented entry point and disclose unavailable capabilities.

**TDD rule.** For a behavior change or bug fix, before editing any production code, invoke the `test-driven-development` skill. Write the test first, run it, and see it fail for the expected reason (show that output); only then write the production code. Writing the test but implementing before a failing run is not TDD.

Three skills fit situations the user rarely names, so load the matching one before answering, including when the user describes the behavior in their own words: `clarify` when a request leaves open something that changes what gets built, or the user asks to be asked questions first; `expert-lens` when the user asks what a top practitioner would think or do, or wants work held to a specialist production standard; `reframe` when the user states a consequential plan or belief and asks for an opinion, a challenge or a fresh perspective. A clear routine request needs none of them.

Use the actual task/agent tools exposed by the runtime. Track meaningful multi-step work; a short answer needs no task scaffold. Planning and review depth follow the routing tier.

Reuse authorization already given for the same scope. Continue reversible, necessary work and routine choices the user delegated. Ask when a material decision cannot be resolved, or when native permissions or a separately controlled action require it. Keep secrets, destructive actions, external publishing and security gates within their authorized scope.

Final replies: lead with the outcome (done, partly done or blocked), then only the important changes or findings, what was verified (or could not be), and the next step when useful. Keep a small task to one to three sentences; cite file paths and command output instead of pasting artifacts. Always state files changed, checks run, and any risk or user action needed.

Session scope: track the active outcome, accepted corrections, constraints, and completed and remaining work. Treat mid-task user messages as steering unless the user clearly cancels or replaces the goal; answer brief questions and continue authorized work. Reassess routing if the scope adds a domain or a trust boundary.

Current model and effort guidance is in `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`; consult it when choosing or changing models, not on every turn. Verify outcomes with relevant evidence and report limits candidly.
