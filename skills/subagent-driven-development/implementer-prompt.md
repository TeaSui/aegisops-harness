# Implementer prompt template

One Agent call per ticket of the batch, to the ticket's `Owner:` or the domain agent for its files (`general-purpose` only when none fits). Fill every `[…]`.

```
description: "Implement T<n>: [title]"
prompt: |
  You are [owner] implementing T<n>: [title] of spec docs/specs/<feature>/. Work from [directory].

  ## Ticket (verbatim from tickets.md)
  [full ticket: title, Blocked by, Covers, What to build, criteria, Test, Files]

  ## Stories covered
  [per ID: the story text copied from spec.md]

  ## Context
  [where it fits; finished tickets it builds on]
  Read: spec.md Implementation Decisions (incl. ### Security) and Testing Decisions (the seams), GLOSSARY.md, cited ADRs, contracts/ (if any), the files you own.
  Rulings already made: [ledger.md lines touching this task, or "none"]

  ## Ownership
  Change only: [ticket Files:]. Need another file → return BLOCKED with the scope change. Do not commit.
  Never edit docs/specs/** (spec.md, contracts/, tickets.md, ledger.md, review.md, README.md belong to the main session); a contract that looks wrong or a failing contract gate → NEEDS_CONTEXT. Never revert, reset or delete work you did not write.
  Out of scope: [what this ticket must not touch or decide; spec Out of Scope]
  Bailout: [when to stop and return BLOCKED instead of pressing on]; 2 failed fix attempts on the same issue → BLOCKED, no third.

  ## Exit criteria
  - [one line per ticket criterion]
  - `[exit test command]` passes (the main session reruns it with aidlc task-done)

  ## Rules
  - TDD at the spec's seams only: write the story-ID-named test against the public interface, run it, show it failing for the expected reason, then the code (RED-GREEN-REFACTOR). No tests of internals.
  - Build exactly the ticket and its criteria; follow existing patterns and glossary terms; no restructuring beyond the ticket. A file growing past the ticket's intent → DONE_WITH_CONCERNS, do not split it yourself.
  - Routine choice the spec leaves open (naming, which existing pattern) → take what the code points to and report it under Choices. NEEDS_CONTEXT only when the answer changes behavior a story describes; BLOCKED when it needs an architectural decision or restructuring the spec did not foresee. Bad work is worse than none.
  - Before reporting: every criterion has an ID-named test that checks behavior, not a mock; only your files changed (git status).

  ## Return
  1. Status
  2. Per story ID: proving test names (file:line)
  3. Exit command, exit code, log path
  4. Files changed
  5. Each ticket criterion: met | not met — reason (the main session ticks it in tickets.md)
  6. Choices: what and why (recorded as rulings)
  7. Concerns / what is needed / what was tried
```
