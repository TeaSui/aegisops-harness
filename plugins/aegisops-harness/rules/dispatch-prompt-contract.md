# Dispatch prompt contract

Applies to every `Task` dispatch by the main session.

## Prompt shape
Implementation dispatch: these fields in this order, as XML tags or headings.
1. `role` — one sentence: which agent, doing what.
2. `context` — why the task exists; upstream outputs it relies on; that others edit other files in the same checkout. Load-bearing facts (IDs, amounts, contract paths, hard constraints) first; no conversation history.
3. `inputs` — every file it may read or change (`status="new"` for new ones); optional refs: `spec.md` (stories, decisions), contracts, `GLOSSARY.md` (terms verbatim).
4. `task` — one imperative instruction with explicit scope.
5. `exit_criteria` — each verifiable by running a command and reading its output.
6. `out_of_scope` — do-not-touch list, each with what to do instead (e.g. contract looks wrong → `NEEDS_CONTEXT`).
7. `evidence` — files changed; test output in a file (path + command); persisted docs.
8. `bailout` — ambiguity the inputs cannot resolve → `NEEDS_CONTEXT`; 2 failed fix attempts on one issue → `BLOCKED` (no third); needs out-of-scope files → `BLOCKED` with a scope-change request.
9. `return_format` — status, evidence paths, one met/not-met line per exit criterion, per `rules/subagent-return-format.md`. Its presence tells the subagent it got a contract dispatch.

Add `delegation` ("do not dispatch; return the dispatch plan") if the agent could dispatch. Review/advisory dispatches (review, QA, threat model): `role`, `context`, `task`, `return_format`, others only with content.

Non-fork subagents inherit neither conversation nor skills: make task context self-contained, but don't copy global rules (the SubagentStart hook injects them). Security precedence: the spec's security decisions (legacy: `security.md`), else the agent's embedded checklist.

## Model
Agent frontmatter sets model and effort; override only when the task differs: implementers → `opus` for ambiguous bugs, cross-cutting refactors or when `high` still fails; aegisops-harness:code-reviewer → `high` effort (or `opus`) for large or trust-boundary diffs; security → `opus`/`fable` for novel auth, crypto or payment designs.

## Before dispatching
- Verify every input path with Read/Glob; only `status="new"` may be missing. A fabricated input path is as bad as fabricated evidence.
- Worktrees: cited instruction files (CLAUDE.md, `.claude/rules/*.md`, docs) may be absent if ignored or uncommitted; then cite the main checkout's absolute paths.

## Parallel dispatch
All independent `Task` calls in one message, non-overlapping file ownership; never across a dependency edge (contract before its implementation).

## Re-dispatch
On `NEEDS_CONTEXT`, `BLOCKED` or rejection: read the return, diagnose (context, scope, spec, tool/environment), amend or split; never resend an identical prompt. Max 2 fix rounds per review, then one re-dispatch one model tier up, then split or ask the user.
