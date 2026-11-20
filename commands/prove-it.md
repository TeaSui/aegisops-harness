---
description: Use when the user doubts or challenges a claim ("are you sure?", "double-check", "prove it") or asks for fresh re-verification — re-runs, for each claim, a check that would fail if it were false and narrows or withdraws what the evidence does not support. Routine completion claims use verification-before-completion.
argument-hint: "[optional: specific claim or task to verify]"
---

Re-verify every claim in the current task (completion, status or factual), including the ones made in passing. Use fresh evidence; never reuse an earlier run.

## Limits
- Stay on the authorized safe target, and use only commands the project supports.
- Never install dependencies, start services or send mutating requests just to prove a claim. When a check cannot run, mark the claim UNVERIFIED.
- Redact credentials, PII, env values, auth headers and raw payloads.

## Evidence per claim
| Claim | Check | False if |
|---|---|---|
| Tests pass | the project's test command | any failure, or the run does not exercise the changed code |
| Build succeeds | the project's build command | non-zero exit, or the changed module is not built |
| Lint clean | the project's lint command | any error in the changed scope |
| Bug fixed | the original reproduction | the symptom still reproduces |
| Feature works | an acceptance test or a read-only request | the response differs from the acceptance criterion |
| Root cause is X | a reproduction where only X changes | the failure persists without X |
| Code fact | a search plus `path:line` | the search finds a counter-example |
| External fact | the installed `--help` or source, or primary docs, quoted | the source says otherwise or cannot be found |

## Rules
- For each check, ask: would it have failed if the claim were false? If not, replace the check or narrow the claim.
- For "bug fixed", cite the failing run you observed before the fix. If you never observed one, the claim is "passes now; pre-fix failure not observed".

## Report each claim
```
claim: "tests pass"
check: npm test
output: 47 passed, 0 failed (exit 0)
would fail if false: yes — auth.test.ts covers the changed branch
result: VERIFIED
```

`result` is one of: `VERIFIED` · `NARROWED: <the smaller supported claim>` · `REFUTED` · `UNVERIFIED: <reason>`.

For every non-VERIFIED result, restate what is known and what is open; never defend the original wording.

$ARGUMENTS
