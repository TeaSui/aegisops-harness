---
name: session-bootstrap
description: Injected at session start by the AegisOps-Harness hook. Lists the AegisOps-Harness commands; nothing in AegisOps-Harness starts without one.
disable-model-invocation: true
user-invocable: false
---

# AegisOps-Harness

AegisOps-Harness is the backend engineering lifecycle **spec → plan → build → verify → review → ship**, and it acts only through the commands below. Without one, work as plain Claude Code: never start an AegisOps-Harness workflow or open its skill files yourself, and never pick a workflow from words in the prompt. When a request fits a command, name the command in one line and let the user run it. The gates in hooks stay on in every session: secret scan on commit and push, a failing test before the first production edit, a recorded pre-PR review before a pull request is opened, the ship gate before it is merged, and a spec's ledger and stored reviewer returns are written by `aidlc` only. When a gate blocks, do what it says and retry; never look for another command or tool that gets past it.

| Situation | Command | What runs |
|---|---|---|
| Unsure the input is good enough for the lifecycle | `/aegisops-harness:prompt-builder <rough idea>` | a `/aegisops-harness:aidlc` input with a spec that passes `aidlc lint`, or a `/aegisops-harness:fix` input |
| New backend feature or behaviour change | `/aegisops-harness:aidlc <request or pasted spec>` | spec → plan → build → verify → review → ship, one approval at the spec |
| You already wrote a spec in the to-spec template | `/aegisops-harness:aidlc <pasted spec>` | the same; the spec is saved verbatim, `Status: ready-for-agent` = approved |
| Decisions still open and you want to be interviewed | `/aegisops-harness:grilling <topic>`, then `/aegisops-harness:aidlc` | interview → `GLOSSARY.md`, ADRs |
| The lifecycle stopped for your approval of a spec | `/aegisops-harness:approve <slug>` | records your approval of spec.md as written (an edit needs a new one), then continues |
| Step-by-step control, or one stage again | `/aegisops-harness:spec` · `plan` · `build` · `verify` · `review` · `ship` | that stage only, then it stops |
| Resume after `/clear` or in a new session | `/aegisops-harness:aidlc <slug>` (no argument: status of every spec) | continues from the recorded stage |
| Bug fix or small change with no new decision | `/aegisops-harness:fix <bug or change>` | root cause → failing test → fix → verify → one review → PR |
| Review comments arrived | `/aegisops-harness:receiving-code-review <PR or comments>` | verify each comment → fix test-first → re-verify |
| After the merge | `/aegisops-harness:upgrade-service-docs` | living docs updated, spec closed (`implemented`) |
| A service has no living docs | `/aegisops-harness:generate-service-docs` | `docs/` for the service |
| Challenge a plan, or a top practitioner's view | `/aegisops-harness:reframe` · `/aegisops-harness:expert-lens` | an opinion, no code |

**Inside a command:** follow its file to the end without asking for permission between steps. Support skills (TDD, debugging, stack patterns, security catalogue) are loaded by the stage files by path, chosen from the repository's files (`rules/workflow-routing.md`), never from prompt keywords. Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Paths `rules/…`, `references/…`, `scripts/…`, `skills/…` are under it, and a literal `${CLAUDE_PLUGIN_ROOT}` in a file you Read means it too (write the real path in commands); `docs/…` is in the project.

**Open questions** (business rules, domain terms, existing behaviour): `references/aidlc.md` §0 — files first, then Atlassian Rovo, then a recorded assumption; ask the user only for what only they can decide.

**Subagents.** A subagent on a dispatched subtask keeps to it and ignores this table.

**PRs.** Open, check, merge and answer PRs with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pr.py"` (`create`, `checks`, `merge`, `comments`, `reply`): `gh` for GitHub, the REST API for Bitbucket Cloud. A refused push or rejected credentials is BLOCKED: quote it and name the fix.

**Final reply.** Outcome first (done, partly done, blocked); then key changes, what was verified, files changed, checks run, rulings and assumptions with their sources, risks or user actions.
