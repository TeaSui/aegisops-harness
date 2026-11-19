---
name: spec-check
description: Use before a full-workflow spec is approved, once docs/specs/<feature>/ holds its requirements and any design, contracts and security rules, and again after the spec changes a lot — dispatches a fresh agent that reads only the spec files and lists every point it would have to guess to build and test the change, then closes each guess in the spec. Not for fast-path work.
---

# Blind spec check

The author of a spec fills its gaps from memory without noticing. A reader who has only the files cannot. This skill gives the spec to such a reader and turns every guess it would make into a question the spec must answer before approval. The result is `spec-check.md` in the spec folder; its format and the `accepted` gate that reads it are in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §1-§2.

## 1. Dispatch the checker

1. Make sure the spec files are written: `README.md`, `requirements.md`, and whichever of `design.md`, `contracts/`, `security.md`, `ui-design.md` the change has. Wait for a running Security or UI/UX dispatch to return first.
2. Find the next guess number: 1 for a new `spec-check.md` (the skeleton from `aidlc init` has no guesses), otherwise one more than the highest `G<n>` already in the file.
3. Dispatch a fresh `general-purpose` subagent with the prompt in `${CLAUDE_PLUGIN_ROOT}/skills/spec-check/checker-prompt.md`, filled with the absolute spec folder path and the first guess number. Do not use a fork, and add nothing about the conversation, your reasoning or the code: the check is only useful while the checker is blind.
4. The checker appends its guesses to `spec-check.md` and returns their count. It edits no other file.

## 2. Close every guess

Read `spec-check.md` and close each open line `- [ ] G<n>: …` in one of two ways:

- **Resolved.** Change the spec so it answers the question (usually an acceptance bullet, a business rule, an error code or a limit), then tick the line and add `— resolved: <where>`, for example `— resolved: RFD-3 acceptance, third bullet`.
- **Accepted risk.** Tick the line and add `— accepted risk: <why it may stay open>` when the answer changes no behavior a test could see, or something outside the spec already settles it (cite it).

A guess that needs a product decision gets your most reasonable answer, written into the spec and marked resolved; list it for the user at the one approval point (`tea-sdlc:brainstorming` §4). Do not stop to ask about each guess. Never delete a guess or reword it to make it easier.

## 3. Check again when the spec moved

When closing the guesses added requirements or rewrote behavior, run §1 once more with a new fresh agent; it appends from the next number. Stop after that second run and accept or resolve what remains (bounds in `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`).

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" check <feature> --to accepted` lists any guess still open. Report the counts in one line: guesses found, resolved, accepted as risk.
