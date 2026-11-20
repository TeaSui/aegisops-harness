---
name: subagent-driven-development
description: Use in the full workflow once the spec is `planned` (plan.md passes its gate), to run the build stage in this session — dispatch each ready batch from `aidlc next` in parallel to specialist subagents, review every task, tick tasks only through `aidlc task-done`, then record the full test run with `aidlc verify` and advance the spec to `verified`.
---

# Build stage: execute the plan with specialists

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`, `<f>` = spec folder or slug; you run every command. Formats: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `plan.md` and §2 `ledger.md`. Never claim a dispatch or review that did not happen. Templates in this folder use plugin-relative paths; expand them to absolute paths in each dispatch.

## 1. Enter

1. `aidlc status`: spec at `planned`, `building` gate passing; otherwise run the missing stage first (`tea-sdlc:writing-plans`).
2. On a feature branch, not the default (`git switch -c feat/<slug>` if needed; no need to ask).
3. `aidlc advance <f> building`.

## 2. Batch loop

Until `aidlc next <f> --json` returns no task, dispatch the whole batch in ONE message, one Agent call per task (tasks in a batch share no file):

- **Agent:** the task's `owner` (`tea-sdlc:<agent>`); `owner: main` → do it yourself.
- **Prompt:** `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/implementer-prompt.md` with the task block verbatim, the covered requirement IDs with their acceptance criteria copied from `requirements.md`, paths of `design.md`, `contracts/`, `security.md`, the matching rulings from `ledger.md`, and the exit test command (the task's `exit:` turned into a command, e.g. `npm test -- refunds/model`).
- Owned paths = the task's `files`. Tests are named with the requirement ID they prove (`RFD-1 rejects over-capture`) so the gate and `aidlc trace` find them.

When an implementer returns, read its status, evidence and exit checks, and confirm with `git status` it changed only its files. Then per task:

1. **Spec compliance:** `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/spec-reviewer-prompt.md` with the task's requirements.
2. **Quality**, after spec passes: `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/code-quality-reviewer-prompt.md` to `tea-sdlc:code-reviewer`.
3. **Fix loop:** verified findings go back to the implementer; each re-review covers only the fix diff. Max 2 fix rounds per review, max 4 review iterations per task in total. Still failing after 2 rounds → re-dispatch the task once, fresh, one model tier up (table), with the findings and failed approaches. That fails too → stop the task: split it in `plan.md` and rerun `aidlc check <f> --to planned` when it is too big, or take it to the user when the requirement is unclear or contradictory.
4. **Finish only through the CLI** (runs the command; on exit 0 ticks `plan.md` and logs `task-done`; on failure changes nothing). Never tick by hand:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" task-done <f> T<n> --cmd "<the task's exit test command>"
```

Commit after each batch converges (implementers never commit; parallel commits race on the index), then the next `aidlc next`.

| Role | Default | After 2 failed fix rounds |
|---|---|---|
| Implementer (domain engineer) | `sonnet`, high | `opus` |
| Implementer already on `opus` | `opus` | `fable` |
| Spec and quality reviewer (`tea-sdlc:code-reviewer`) | `sonnet`, medium | effort high |
| `tea-sdlc:qa-subagent` (review stage) | `sonnet`, medium | effort high |

Override with the Agent call's `model` only when the task differs from the agent's normal job.

## 3. Decide routine questions yourself

`NEEDS_CONTEXT` or an ambiguity → answer from spec, design, contracts and code. A routine choice no requirement fixes (naming, which pattern or library, an error message, test data, an order of operations) → decide, record, continue:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" ruling <f> --task T<n> \
  --decision "<what>" --why "<evidence>" --if-wrong "<cost and how to reverse>"
```

Ask the user only for: changing a requirement or acceptance criterion, accepting a security risk, a new vendor or paid dependency, a scope change, anything irreversible in production. List every ruling in the final report.

## 4. Verify and advance

1. No task left → bump the release version if a manifest holds it (`package.json`, `pyproject.toml`, `plugin.json`, `VERSION`; semver from the change; skip when release tooling owns it). Do it now: a manifest change after `verify` invalidates the evidence.
2. Run the full suite through the CLI (`--junit` when the runner writes JUnit XML, so the gate sees failing requirement tests), then advance:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full test suite>" --junit "<junit glob>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> verified
```

3. Gate fails → `aidlc check <f> --to verified` names it (unticked task, `Verify: test` requirement no test references, failing requirement test, code changed after `verify`). Fix (code fixes go to the owning agent) and retry.

Then the review stage: `tea-sdlc:requesting-code-review`, then `tea-sdlc:shipping`.

Use an isolated checkout only when needed and supported; preserve user changes; never init a repository or commit generated files unasked. Missing runtime or gates are reported as concerns or blockers, not replaced by static inspection. Report outcome, gate output and ledger events, rulings, next stage.
