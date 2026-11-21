---
name: aidlc
description: Run the whole backend lifecycle for one feature — spec, plan, build, verify, review, ship — from a request or a pasted to-spec spec, or resume a spec by its slug. No argument shows every spec's stage and the next command.
argument-hint: "[feature request | pasted spec | spec slug]"
disable-model-invocation: true
---

# /tea-sdlc:aidlc

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run every command yourself. Input: `$ARGUMENTS`.

- **Empty:** `aidlc status`; print one row per spec (stage, first blockers, next command from the table below) and stop.
- **A spec slug** that `aidlc status` knows: resume at its stage.
- **Anything else:** a new feature; start at `spec`.

## Run the stages

Read the stage's file and follow it to its end, then go straight to the next row. No pause and no question between stages.

| Spec stage | Read and follow | Ends at |
|---|---|---|
| none, `proposed` | `${CLAUDE_PLUGIN_ROOT}/skills/spec/SKILL.md` | `accepted` |
| `accepted` | `${CLAUDE_PLUGIN_ROOT}/skills/plan/SKILL.md` | `planned` |
| `planned`, `building` with open tickets | `${CLAUDE_PLUGIN_ROOT}/skills/build/SKILL.md` | every ticket `Status: done` |
| `building`, every ticket done | `${CLAUDE_PLUGIN_ROOT}/skills/verify/SKILL.md` | `verified` |
| `verified` | `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` | `reviewed` |
| `reviewed` | `${CLAUDE_PLUGIN_ROOT}/skills/ship/SKILL.md` | PR open, CI green, `shipped` |

## Stops

1. **The one approval** at the end of `spec`, skipped when the input delegates it ("don't ask", "end to end") or is a pasted spec marked `Status: ready-for-agent`.
2. **A blocking user decision** per `references/aidlc.md` §0 step 4 (security or compliance risk, money or regulatory behaviour with no source, an irreversible or production action, contradictory sources). Ask once, batched, with your recommendation; continue the rest while you wait only when it is independent.
3. **Merge and deploy** need words for it in the input ("merge", "release", "deploy"); otherwise stop with the PR open and `shipped`, and give `/tea-sdlc:ship merge` as the next command.

A gate that fails is not a stop: fix what it names and rerun.

## Report

Stage reached, PR link, `aidlc trace <f>` summary, rulings (`ledger.md`), assumptions with their sources (Rovo pages and issues, or "no source"), open risks, next command.
