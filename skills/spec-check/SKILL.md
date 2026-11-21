---
name: spec-check
description: Use before a full-workflow spec is approved when the spec was written by the session and not grilled with the user, once docs/specs/<feature>/spec.md is drafted — dispatches a fresh agent that reads only the spec files and lists every point it would have to guess to build and test the change, then closes each guess in the spec. Not for fast-path work.
---

# Blind spec check

One blind pass per spec: a fresh agent that sees only the spec files lists everything it would have to guess; you close each guess in the spec. Output: `spec-check.md` (format `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `spec-check.md`; when present, the `accepted` gate requires every guess closed). Skip it for a spec grilled with the user or handed over.

## 1. Dispatch

1. `spec.md` (with its Security subsection) and any `contracts/` exist; wait for a running Security dispatch to return.
2. First guess number: 1 for a new `spec-check.md` (the `aidlc init` skeleton has none), else the highest `G<n>` + 1.
3. Dispatch a fresh `general-purpose` subagent (never a fork) with `${CLAUDE_PLUGIN_ROOT}/skills/spec-check/checker-prompt.md`, filled with the absolute spec folder and the first number. Add nothing about the conversation, your reasoning or the code.
4. It appends its guesses to `spec-check.md`, edits nothing else, and returns the count.

## 2. Close every guess

For each open `- [ ] G<n>: …`:
- **Resolved:** change spec.md so it answers it (story, decision, error code, limit), tick the line, append `— resolved: <where>`.
- **Accepted risk:** tick and append `— accepted risk: <why>` when the answer changes nothing a test could see, or something outside the spec settles it (cite it).

A guess needing a product decision gets your most reasonable answer, written into the spec, marked resolved and listed for the user at the approval point (`tea-sdlc:spec` §4). Do not stop to ask per guess. Never delete a guess or reword it.

No second blind run, even after large closing edits: close the guesses directly in the spec. Exception: stories added mid-execution get one pass over the new stories only.

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" check <feature> --to accepted` lists any guess still open. Report one line: guesses found, resolved, accepted as risk.
