---
name: grounding-claims
description: Use when about to assert a codebase, git-history, command-output or subagent-evidence fact not seen in this session's tool output — cite file:line or output, or say "I don't know". For library/API documentation lookups use find-docs.
---

# Grounding claims

A fabricated path, symbol, flag, API, SHA or result is a defect. No claim without a source you can cite; "I don't know" or "let me check" is a valid answer. Reuse inspected evidence while its state is unchanged.

| Claim | Source | Cite |
|---|---|---|
| File exists / contains X | Read, Glob | `path:line` |
| Function behaviour, callers | Read, Grep | `path:start-end`, one `path:line` per hit |
| Library API | `tea-sdlc:find-docs` (version-matched) | source + version |
| CLI flag | `--help`, code | output |
| Env var / config key | grep the loader | `path:line` |
| Commit, PR, "recent" changes | `git log`, `git show`, `gh` | SHA + title |
| Test / build passes | run it | exit code + log path |
| Subagent evidence | Read the cited path; missing = BLOCKED | `path` |
| Memory from a prior session | re-check it exists now | `path:line` |

Stop and verify when about to write a name, path, flag or SHA not seen in this session's tool output, or "typically / usually / should be / probably" about a checkable fact. Summaries are claims. If verifying costs more than the claim is worth, drop the claim. Speculation is fine only where the user asked for brainstorming. Success claims also follow `tea-sdlc:verification-before-completion`.
