# Implementer prompt template

One Agent call per task of the batch, to the task's `owner` (`general-purpose` only when no domain agent fits). Fill every `[…]`.

```
description: "Implement T<n>: [title]"
prompt: |
  You are [owner] implementing T<n>: [title] of spec docs/specs/<feature>/. Work from [directory].

  ## Task (verbatim from plan.md)
  [full task block: title, covers, depends, owner, files, exit]

  ## Requirements covered
  [per ID: heading + acceptance bullets copied from requirements.md]

  ## Context
  [where it fits; finished tasks it builds on; relevant design.md parts]
  Read: design.md, contracts/ (if any), the security.md rules that apply to your files, the files you own.
  Rulings already made: [ledger.md lines touching this task, or "none"]

  ## Ownership
  Change only: [task files; (new) = create]. Need another file → return BLOCKED with the scope change. Do not commit.

  ## Exit criteria
  - [one line per acceptance criterion]
  - `[exit test command]` passes (the main session reruns it with aidlc task-done)

  ## Rules
  - Build exactly the task and its criteria; follow the plan's file structure and existing patterns; no restructuring beyond the task. A file growing past the plan's intent → DONE_WITH_CONCERNS, do not split it yourself.
  - Routine choice the spec leaves open (naming, which existing pattern) → take what the code points to and report it under Choices. NEEDS_CONTEXT only when the answer changes behavior a requirement describes; BLOCKED when it needs an architectural decision or restructuring the plan did not foresee. Bad work is worse than none.
  - Before reporting: every criterion has an ID-named test that checks behavior, not a mock; only your files changed (git status).

  ## Return
  1. Status
  2. Per requirement ID: proving test names (file:line)
  3. Exit command, exit code, log path
  4. Files changed
  5. Each exit criterion: met | not met — reason
  6. Choices: what and why (recorded as rulings)
  7. Concerns / what is needed / what was tried
```
