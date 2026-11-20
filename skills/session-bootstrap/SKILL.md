---
name: session-bootstrap
description: Injected automatically at session start by the tea-sdlc hook; load it only if the <session-bootstrap> block is missing or truncated.
---

# tea-sdlc

Paths `rules/…`, `references/…`, `scripts/…`, `skills/…` are under `${CLAUDE_PLUGIN_ROOT}` (expand them in subagent dispatches); `docs/…` is in the project. A subagent on a dispatched subtask keeps to it and skips this intake.

**Skill names.** Use `tea-sdlc:<skill>`; it wins over a same-named skill from another plugin.

**Autopilot.** Treat `<tea-sdlc-autopilot>` notes as a checklist: load what fits, name it in one line. Run commands yourself: `upgrade-service-docs` after QA GO or a merge, `generate-service-docs` (offer once) for a service without living docs, `prove-it` when the user doubts a claim, `debug-parallel` for a cross-service error. A blocking gate (TDD, contract, verification, pre-PR): do what it says, retry. Ask the user only for what only they can do.

**First action.** For any request that builds, adds, modifies, fixes or refactors code, invoke `tea-sdlc:brainstorming` before reading files, choosing a tier or asking anything, even if simple or from `/prompt-builder`. Only openers may precede it: `tea-sdlc:goal` (whole outcome handed over), `tea-sdlc:clarify`, `tea-sdlc:expert-lens`, `tea-sdlc:reframe`. Skip only for (a) a subagent on a specific subtask, (b) questions, explanations or reviews that change no code, (c) a bare slash command.

**Tier.** Before the first edit, state tier and reason in one line. Trust boundary = YES if it touches any of: PII or financial data; auth, session or permissions; money, billing, payments; a new endpoint, webhook or public surface; a new external vendor; security config or secrets (TLS, JWT, IAM, encryption). Unsure = YES. Mode is lean unless `TEA_SDLC_WORKFLOW=full`, the user asks for the full workflow, or a spec on this branch is in progress.

| Trust boundary | Process |
|---|---|
| NO | Fast path: TDD + verification here, no dispatch; several stacks → dependency order, integration check before merge; one pre-PR pass (`rules/pre-pr-review.md`) |
| YES, lean | Fast path + security pass: 3-6 lines of assets, threats, controls before the first edit (`tea-sdlc:fintech-security`), tests for them, threats in the PR description; no subagents |
| YES, full | AIDLC (`references/aidlc.md`, current stage's section): `tea-sdlc:brainstorming` → accepted; `tea-sdlc:writing-plans` → planned; branch → building; `tea-sdlc:subagent-driven-development` → verified; `tea-sdlc:requesting-code-review` → reviewed; `tea-sdlc:shipping` → shipped; `upgrade-service-docs` → implemented. Only `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <feature> <stage>` moves a stage; run it yourself |

Unclear: `rules/workflow-routing.md`. Never skip a required step silently. Re-route if scope adds a stack or trust boundary.

**PRs.** Run `gh pr create` and decide from what `gh` answers, never from the remote URL. "Ready to ship" includes an open PR.

**TDD.** Behaviour change or bug fix: invoke `tea-sdlc:test-driven-development` first; show the new test failing for the expected reason before production code.

**Situational** (also when described): `tea-sdlc:clarify` if an open point changes what gets built or the user wants questions first; `tea-sdlc:expert-lens` for what a top practitioner would do; `tea-sdlc:reframe` when asked to challenge a consequential plan or belief.

**Autonomy.** Reuse authorization for the same scope; continue reversible, necessary work and delegated routine choices; ask only for unresolvable material decisions or when permissions require. Secrets, destructive actions, publishing and security gates stay in authorized scope. Mid-task messages steer unless they cancel the goal.

**Final reply.** Outcome first (done, partly done, blocked); then key changes, what was verified or not, files changed, checks run, risks or user actions. Small task: 1-3 sentences. Cite paths and output.

Model choice: `references/model-guide.md`, only when choosing models.
