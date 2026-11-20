---
name: subagent-driven-development
description: Use in the full workflow once the spec is `planned` (plan.md passes its gate), to run the build stage in this session — dispatch each ready batch from `aidlc next` in parallel to specialist subagents, review every task, tick tasks only through `aidlc task-done`, then record the full test run with `aidlc verify` and advance the spec to `verified`.
---

# Build stage: execute the plan with specialists

Stage machine, gates and artifact formats: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. Below, `aidlc <command>` is short for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" <command>`, and `<f>` is the spec folder or its slug. You run every command yourself; the user never types one.

Use the Agent tool the runtime provides; never claim a dispatch or an independent review happened when it did not. The templates' `rules/…`, `references/…` and `skills/…` paths are relative to `${CLAUDE_PLUGIN_ROOT}`; expand them to absolute paths in each dispatch.

## 1. Enter the build stage

1. `aidlc status` shows the spec at `planned` with its `building` gate passing. If not, run the stage that is missing first (`tea-sdlc:writing-plans` for the plan).
2. Be on a feature branch, not the default branch (`git switch -c feat/<slug>` when needed; a routine choice, no need to ask).
3. Advance:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> building
```

## 2. The batch loop

Repeat until `aidlc next <f>` returns no task:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" next <f> --json
```

**Dispatch the whole batch in one message**, one Agent call per task (`tea-sdlc:dispatching-parallel-agents` for the mechanics). Tasks in one batch share no file, so they run concurrently. Per task:

- **Agent:** the task's `owner` from `${CLAUDE_PLUGIN_ROOT}/rules/agents.md`; `owner: main` means you do the task yourself in this session.
- **Prompt:** `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/implementer-prompt.md`, filled with the task block from `plan.md` verbatim, the requirement IDs it covers with their acceptance criteria copied from `requirements.md`, the paths of `design.md`, `contracts/` and `security.md`, and the exit test command (translate the task's `exit:` into the command that proves it, for example `npm test -- refunds/model`).
- **Ownership:** the task's `files` are the only paths it may change. Tell the implementer others work in the same checkout at the same time.
- **Test names:** each test carries the requirement ID it proves, for example `RFD-1 rejects over-capture`, so the `verified` gate and `aidlc trace` find it.

When an implementer returns, read its status, evidence and exit checks (`${CLAUDE_PLUGIN_ROOT}/rules/subagent-return-format.md`) and confirm with `git status` that it changed only its task's files. Then, per task:

1. **Spec compliance review:** `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/spec-reviewer-prompt.md`, with the task's requirements and acceptance criteria.
2. **Quality review** once the spec review passes: `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/code-quality-reviewer-prompt.md`, dispatched to `tea-sdlc:code-reviewer`.
3. **Fix loop**, bounded by `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`: send verified findings back to the implementer; the re-review covers the fix diff. If findings remain after two fix rounds, re-dispatch the task fresh with the implementer one model tier up (table below) and the reviewers' findings in its context. If that attempt also fails, stop the task: split it in `plan.md` (then `aidlc check <f> --to planned`) when it is too large, or bring it to the user when the requirement itself is unclear or contradictory.
4. **Finish the task** only through the CLI. It runs the command, and on exit 0 ticks the task in `plan.md` and logs `task-done`; on failure it changes nothing. Never tick `plan.md` by hand.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" task-done <f> T<n> --cmd "<the task's exit test command>"
```

Commit after each batch converges (implementers do not commit; parallel commits race on the index). Then ask `aidlc next` for the following batch.

### Models per role

Defaults come from each agent's frontmatter (`${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`). Override with the Agent call's `model` only when the task differs from the normal job.

| Role | Default | Third attempt (after two failed fix rounds) |
|---|---|---|
| Implementer (domain engineer) | `sonnet`, effort high | `opus` |
| Implementer already on `opus` | `opus` | `fable` |
| Spec compliance reviewer | `tea-sdlc:code-reviewer` (`opus`, medium) | effort high |
| Quality reviewer | `tea-sdlc:code-reviewer` (`opus`, medium) | effort high |
| QA (`tea-sdlc:qa-subagent`, review stage) | `sonnet`, medium | effort high |

## 3. Decide routine questions yourself

When an implementer returns `NEEDS_CONTEXT`, or you meet an ambiguity, answer it from the spec, design, contracts and existing code. When they leave a routine choice open (naming, which existing pattern or library to follow, an error message, test data, an order of operations that no requirement fixes), decide it, record it and continue:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" ruling <f> --task T<n> \
  --decision "<what you decided>" --why "<the evidence>" --if-wrong "<the cost and how to reverse it>"
```

Ask the user only for decisions that are theirs: changing a requirement or acceptance criterion, accepting a security risk, a new vendor or paid dependency, a scope change, or anything irreversible in production. List every ruling of the run in your final report.

## 4. Verify and advance

When no task is left, bump the release version if the project keeps one in a manifest (`package.json`, `pyproject.toml`, `plugin.json`, a `VERSION` file; semver from the change, see tea-sdlc:shipping §3). The version is part of what you test: a manifest change after `verify` invalidates the evidence. Skip it when release tooling owns the version. Then run the whole suite through the CLI. Pass `--junit` when the runner can write JUnit XML (it lets the gate see which requirement tests failed); omit it otherwise.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full test suite>" --junit "<junit glob>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> verified
```

If the gate fails, `aidlc check <f> --to verified` lists why: an unticked task, a `Verify: test` requirement no test references, a failing requirement test, or code changed after the `verify` run (the fingerprint differs; run `verify` again). Fix it, dispatching to the owning agent when the fix is code, and retry.

Then continue with the review stage yourself: `tea-sdlc:requesting-code-review`, then `tea-sdlc:shipping`.

## Boundaries

- Use an isolated checkout only when needed and supported. Preserve user changes; do not initialize a repository or commit generated files the user did not authorize.
- Missing runtime or independent gates are reported as concerns or blockers; static inspection does not replace them.
- Report the outcome, evidence (gate output, ledger events), the rulings made and the next stage.
