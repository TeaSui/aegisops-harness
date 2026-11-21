---
name: build
description: Use in the full workflow once the spec is `planned` (tickets.md passes its gate), to run the build stage in this session — dispatch each ready batch of tickets from `aidlc next` (in parallel when they declare disjoint files), review every ticket, finish tickets only through `aidlc task-done`, then record the full test run with `aidlc verify` and advance the spec to `verified`. Also when resuming saved tickets or a docs/plans/*.md plan after a new session, /clear or compaction, without redoing finished work.
---

# Build stage: build the tickets

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`, `<f>` = spec folder or slug; you run every command. Formats: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `tickets.md` and §2 `ledger.md`. Never claim a dispatch or review that did not happen. Templates in this folder use plugin-relative paths; expand them to absolute paths in each dispatch.

## 1. Enter (or resume)

Resuming: keep the original goal, constraints and decisions; never redo a ticket at `Status: done`. `aidlc status` (or the session-start snapshot) gives the stage and the next-gate blockers; at `building`, go straight to §2.

1. `aidlc status`: spec at `planned`, `building` gate passing; otherwise run the missing stage first (`tea-sdlc:spec`, `tea-sdlc:plan`).
2. On a feature branch, not the default (`git switch -c feat/<slug>` if needed; no need to ask).
3. `aidlc advance <f> building`.

## 2. Batch loop

Until `aidlc next <f> --json` returns no ticket:

- **Batch of one** (a ticket without `Files:`, the common case): build it yourself in this session with `tea-sdlc:test-driven-development` at the spec's seams, unless its `Owner:` names an agent.
- **Wider batch** (tickets declaring disjoint `Files:`): dispatch it in ONE message, one Agent call per ticket. Agent = the ticket's `Owner:`, else the domain agent for its files (`${CLAUDE_PLUGIN_ROOT}/rules/agents.md`).
- **Prompt:** `${CLAUDE_PLUGIN_ROOT}/skills/build/implementer-prompt.md` with the ticket verbatim, the covered stories copied from `spec.md`, the paths of `spec.md` (Implementation and Testing Decisions, `### Security`), `GLOSSARY.md`, cited ADRs and `contracts/`, the matching rulings from `ledger.md`, and the exit command (`Test:`).
- Owned paths = the ticket's `Files:`. Tests are named with the story ID they prove (`RFD-1 rejects over-capture`) so the gate and `aidlc trace` find them. Each acceptance checkbox is ticked when a test shows it.

When an implementer returns, read its status, evidence and exit checks, and confirm with `git status` it changed only its files. Then per task:

1. **Spec compliance:** `${CLAUDE_PLUGIN_ROOT}/skills/build/spec-reviewer-prompt.md` with the ticket and its stories. A ticket you built yourself skips the per-ticket reviews; the review stage covers it.
2. **Quality**, after spec passes: `${CLAUDE_PLUGIN_ROOT}/skills/build/code-quality-reviewer-prompt.md` to `tea-sdlc:code-reviewer`.
3. **Fix loop:** verified findings go back to the implementer; each re-review covers only the fix diff. Max 2 fix rounds per review, max 4 review iterations per task in total. Still failing after 2 rounds → re-dispatch the task once, fresh, one model tier up (table), with the findings and failed approaches. That fails too → stop the ticket: split it in `tickets.md` and rerun `aidlc check <f> --to planned` when it is too big, or take it to the user when the story is unclear or contradictory.
4. **Finish only through the CLI** (needs every criterion ticked; runs the command; on exit 0 sets `Status: done` and logs `task-done`; on failure changes nothing). Never set the status by hand:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" task-done <f> T<n>            # runs Test:, or pass --cmd "<command>"
```

Commit after each ticket or batch converges (implementers never commit; parallel commits race on the index), then the next `aidlc next`.

| Role | Default | After 2 failed fix rounds |
|---|---|---|
| Implementer (domain engineer) | `sonnet`, high | `opus` |
| Implementer already on `opus` | `opus` | `fable` |
| Spec and quality reviewer (`tea-sdlc:code-reviewer`) | `sonnet`, medium | effort high |
| `tea-sdlc:qa-subagent` (review stage) | `sonnet`, medium | effort high |

Override with the Agent call's `model` only when the task differs from the agent's normal job.

## 3. Decide routine questions yourself

`NEEDS_CONTEXT` or an ambiguity → answer from spec.md, ADRs, contracts and code. A routine choice no story or decision fixes (naming, which pattern or library, an error message, test data, an order of operations) → decide, record, continue:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" ruling <f> --task T<n> \
  --decision "<what>" --why "<evidence>" --if-wrong "<cost and how to reverse>"
```

Ask the user only for: changing a story or decision, accepting a security risk, a new vendor or paid dependency, a scope change, anything irreversible in production. List every ruling in the final report.

## 4. Verify and advance

1. No ticket left → bump the release version if a manifest holds it (`package.json`, `pyproject.toml`, `plugin.json`, `VERSION`; semver from the change; skip when release tooling owns it). Do it now: a manifest change after `verify` invalidates the evidence.
2. Run the full suite through the CLI (`--junit` when the runner writes JUnit XML, so the gate sees failing story tests), then advance:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" verify <f> --cmd "<full test suite>" --junit "<junit glob>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <f> verified
```

3. Gate fails → `aidlc check <f> --to verified` names it (open ticket or criterion, `Verify: test` story no test references, failing story test, code changed after `verify`). Fix (code fixes go to the owning agent) and retry.

Then the review stage: `tea-sdlc:review`, then `tea-sdlc:ship`.

## 5. Plans outside a spec (`docs/plans/*.md`)

Continue from the first open `- [ ] Task N:` in dependency order; tick `- [x]` when its exit check passes. Full mode dispatches as in §2; lean mode implements here. Deliver as already authorized (`tea-sdlc:finishing-a-development-branch`). Bound fix and review attempts per `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`.

Use an isolated checkout only when needed and supported; preserve user changes; never init a repository or commit generated files unasked. Missing runtime or gates are reported as concerns or blockers, not replaced by static inspection. Report outcome, gate output and ledger events, rulings, next stage.
