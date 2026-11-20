# Dispatch Prompt Contract

**Scope:** every `Task` dispatch. Only the main session dispatches, and only in the Full workflow (implementer dispatches after the contract gate, per `rules/workflow-routing.md`); the Fast path never dispatches. Leaf subagents (backend, frontend, mobile, platform, data, UI/UX, security, QA, tea-sdlc:code-reviewer) read this shape on input and return per `rules/subagent-return-format.md`; they do not dispatch.

**Detection signal:** a subagent knows it received a contract dispatch when its prompt has a return-format section (`<return_format>` tag or heading) referencing `rules/subagent-return-format.md`. Without it, the subagent answers in whatever shape fits the prompt.

Related rules (cite, do not restate): `rules/review-loop-limits.md`, `rules/strategic-output-persistence.md`, `skills/dispatching-parallel-agents/SKILL.md`. Security precedence: the `security.md` rules of the change; each implementation agent's embedded security checklist applies when Security is skipped.

## Required prompt shape

Every **implementation dispatch** carries the nine fields below, in this order. XML tags are the recommended serialization; markdown headings carrying the same fields are compliant.

**Review / advisory dispatches** (spec review, code-quality review, QA, threat model) use a lighter minimum: `role`, `context`, `task` and `return_format`. Add `inputs`, `exit_criteria` or `out_of_scope` only when they carry real content.

**Model and context:** choose model and effort with `references/model-guide.md`. Non-fork subagents do not inherit the parent conversation or its invoked skills, so make task-specific context self-contained without copying global rules.

```xml
<role>
One sentence naming who the subagent is for this task (e.g. "You are the tea-sdlc:backend-engineer-subagent implementing /login per the accepted contract").
</role>

<context>
- Why this task exists (the parent's goal, not the whole project)
- Upstream outputs it depends on (Security rules, accepted contract, requirements)
- Dispatched by the main session; other agents may be editing other files in the same checkout
Put load-bearing facts (IDs, amounts, contract paths, hard constraints) at the top. Do not paste
conversation history; trim upstream tool output to the relevant fields.
</context>

<inputs>
  <file path="..."/>                    <!-- every file the subagent may read or modify; status="new" for files it will create -->
  <!-- Paths follow references/documentation-layout.md; reuse the project's existing equivalents -->
  <contract ref="docs/specs/<feature>/contracts/... | docs/specs/<feature>/design.md"/>  <!-- optional -->
  <security_rules ref="docs/specs/<feature>/security.md"/>    <!-- optional; trust-boundary work -->
  <requirements ref="docs/specs/<feature>/requirements.md"/>  <!-- optional -->
  <domain_model ref="glossary.md"/>       <!-- optional; use its terms verbatim -->
</inputs>

<task>
One imperative instruction with explicit scope.
</task>

<exit_criteria>
- Each criterion is verifiable by running a command and reading its output
  (e.g. "`go test ./pkg/auth/...` passes", "`redocly lint api/openapi.yaml` is clean").
</exit_criteria>

<out_of_scope>
Explicit "do NOT touch" list, each paired with what to do instead
(e.g. "Do NOT modify the accepted contract; if it looks wrong, return NEEDS_CONTEXT").
</out_of_scope>

<evidence>
Files created/modified; test output written to a file (path + command); persisted docs
(per rules/strategic-output-persistence.md). Only actual command output counts.
</evidence>

<bailout>
- Ambiguity the inputs cannot resolve → return NEEDS_CONTEXT
- 2 failed fix attempts on the same issue → return BLOCKED (do NOT start a third)
- Task requires touching out_of_scope files → return BLOCKED with a scope-change request
Review loop limits: rules/review-loop-limits.md.
</bailout>

<return_format>
Include (any shape): 1. status DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED;
2. evidence paths the dispatcher can Read; 3. one line per exit criterion: met | not met — reason.
Full conventions: rules/subagent-return-format.md.
</return_format>

<delegation>
<!-- include when the dispatched agent could itself try to dispatch -->
You are dispatched by the main session. Do not dispatch further agents; if the task needs more agents, return the dispatch plan and stop.
</delegation>
```

## Before dispatching

- **Inputs exist.** Verify every `<file>` and `ref` path with Read or Glob; only paths marked `status="new"` may be missing. A fabricated input path is a defect of the same severity as a fabricated evidence path (`rules/reduce-hallucinations.md`).
- **Worktrees and other checkouts.** Check that each instruction file the prompt cites (CLAUDE.md, `.claude/rules/*.md`, docs) exists there and is non-empty: ignored or uncommitted files are absent from worktrees. If not, cite the main checkout's absolute paths and say why.

## Parallel dispatch

1. Send all N independent `Task` calls in a **single assistant message**.
2. Give each subagent non-overlapping file ownership and tell it other agents may be working in the same checkout.
3. Resolve dependencies first (UI/UX before frontend, contract before backend and frontend); never parallelize across a dependency edge.

## Re-dispatch

On `NEEDS_CONTEXT`, `BLOCKED` or a reviewer rejection: read the actual return, diagnose the cause (missing context, wrong scope, ambiguous spec, tool or environment), amend the prompt or split the task, and never resend an identical prompt. Limits: `rules/review-loop-limits.md`; at the limit, escalate.

## Example (filled fields only)

```xml
<role>You are the tea-sdlc:backend-engineer-subagent implementing POST /login per the accepted contract and Security rules.</role>
<context>Security rules AUTH-01..07 (docs/specs/auth-login/security.md); contract passed the contract gate. tea-sdlc:frontend-engineer-subagent runs in parallel on the same contract.</context>
<inputs><file path="pkg/auth/login.go"/><file path="pkg/auth/login_test.go"/><contract ref="docs/specs/auth-login/contracts/auth-login.yaml"/><security_rules ref="docs/specs/auth-login/security.md"/></inputs>
<task>Implement POST /login per the contract; validate inputs per AUTH-01..04; issue JWT per AUTH-05..07.</task>
<exit_criteria>- `go test -cover ./pkg/auth/...` passes with ≥80% coverage
- `golangci-lint run ./pkg/auth/...` clean</exit_criteria>
<out_of_scope>- Do NOT change the contract file (main session owns it) or database migrations</out_of_scope>
<evidence>- `go test -v -cover ./pkg/auth/... > /tmp/auth-test.log`; cite the log path</evidence>
<bailout>- NEEDS_CONTEXT if AUTH-03 is ambiguous about per-IP vs per-account rate limiting</bailout>
<return_format>Status, evidence paths, one met/not-met line per exit criterion (rules/subagent-return-format.md).</return_format>
```
