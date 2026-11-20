---
description: Use when an error, timeout or wrong result crosses two or more services (or service + infra/config) and the cause is not obvious — runs independent config, diagnostics, code-path and history investigations in parallel, then verifies one root cause and a scoped fix. Run it yourself; the user does not need to type it.
argument-hint: "<error description>"
---

Error: **$ARGUMENTS**

## When to run
Run this only in full mode (`${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`) or when the user asks for a parallel investigation. Otherwise, and for any single-service error, use `tea-sdlc:systematic-debugging` in the main session.

## How to run
- Dispatch only the independent branches below that would help, in parallel, through the Agent tool (the `Task` alias works), following `${CLAUDE_PLUGIN_ROOT}/rules/dispatch-prompt-contract.md`. Keep dependent steps sequential. If agents are unavailable, say so and run the branches yourself.
- Every branch is read-only.
- Reports carry only presence, counts, safe identifiers, filenames or redacted metadata. Never print credentials, env or config values, auth headers, connection strings, PII or request/response bodies.
- Stay on the authorized safe target. Never start services or replay mutating requests.

## Branches
| Branch | Checks | Returns |
|---|---|---|
| Config | required env/config keys (presence and validity), credential-source availability, service-to-service settings (ports, hosts, feature flags) | what is present, missing or invalid, with values redacted |
| Diagnostics | read-only health checks on the authorized target; ports (`lsof -i :<port>` or `ss -tlnp`); availability of required resources | what responds, sanitized results, skipped checks marked |
| Code path | from the error surface back to where data or state first goes wrong | the originating `file:line` with a snippet |
| History | `git log --oneline -20` on the related files; staged, unstaged and untracked changes; shallow or unborn history handled | the commits among those 20 that could explain the error |

## Synthesis
1. Read every report and the evidence it cites.
2. State the root cause in one falsifiable sentence. Cross-check it against all the findings and state what remains uncertain.
3. Finish the routing prerequisites (the security pass or the Security agent, and the contract gate) before fixing. The fix follows the tier.
4. Write a failing test that reproduces the root cause (`tea-sdlc:test-driven-development`), then fix it, citing the finding behind each change.
5. Verify with `tea-sdlc:verification-before-completion`.
