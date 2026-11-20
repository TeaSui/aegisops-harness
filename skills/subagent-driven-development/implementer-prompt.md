# Implementer Subagent Prompt Template

Use this template to dispatch one task from `plan.md` (one batch from `aidlc next` = one message with one dispatch per task).

Dispatch to the task's `owner` from the registry in `rules/agents.md`
(tea-sdlc:backend-engineer-subagent, tea-sdlc:frontend-engineer-subagent, tea-sdlc:mobile-engineer-subagent, etc.); fall back to
`general-purpose` only when no domain agent fits. This template satisfies
`rules/dispatch-prompt-contract.md` via markdown headings (fields, not tags, are the contract). Adapt it to the
selected model/effort using `references/model-guide.md`. Keep task, security and contract constraints and the
evidence requirements regardless of model. Formats of `plan.md`, `requirements.md` and the ledger:
`references/aidlc.md`.

```
Agent tool (the task's owner per rules/agents.md):
  description: "Implement T<n>: [task title]"
  prompt: |
    You are the [owner] implementing T<n>: [task title] of spec docs/specs/<feature>/.

    ## Task (verbatim from plan.md)

    [The full task block: title, covers, depends, owner, files, exit]

    ## Requirements this task covers

    [For each covered ID, the heading and its acceptance criteria copied from requirements.md, e.g.
     RFD-1: Refund a captured payment
     - Given a captured payment, when a refund for the full amount is requested, then ...
     - Given a refund request above the captured amount, then it is rejected with REFUND_EXCEEDS_CAPTURE.]

    ## Context

    [Where this fits, what finished tasks it builds on, the relevant parts of design.md]
    Inputs to read: docs/specs/<feature>/design.md, docs/specs/<feature>/contracts/ (if any),
    docs/specs/<feature>/security.md (each rule that applies to your files), the files you own.
    Rulings already made for this spec (from ledger.md): [paste the ones that touch this task, or "none"]

    ## Ownership and constraints

    You may change only these paths: [the task's files, (new) marking files to create].
    Other agents are implementing other tasks in the same checkout right now. Preserve their edits and the
    user's; never revert, reset or delete work you did not write.
    Do not edit docs/specs/** (contracts/, plan.md, ledger.md, review.md, README.md belong to the main session).
    If a contract looks wrong or the contract gate fails, return NEEDS_CONTEXT with the finding instead.
    If the task needs a file outside your list, return BLOCKED with the scope change you need.
    Do not commit; the main session commits after the batch.

    ## Exit criteria

    - [One line per acceptance criterion this task must satisfy]
    - Exit test command passes: `[the command the main session will run with aidlc task-done]`

    ## Your job

    1. Follow TDD for behavior changes: write the test, run it, see it fail for the expected reason, then
       write the code. Use structural checks for prose/config.
    2. Name every test with the requirement ID it proves, followed by what it checks, e.g.
       `RFD-1 rejects over-capture` (test name, describe/it string or @DisplayName, as the framework allows).
       The trace gate finds tests by these IDs; a test without one does not count for the requirement.
    3. Implement exactly what the task and its acceptance criteria say; nothing more.
    4. Run the exit test command and keep its output in a log file.
    5. Self-review (below), then report.

    Work from: [directory]

    While you work: investigate unexpected behavior within scope. When the spec leaves a routine choice open
    (naming, which existing pattern to follow), choose the option the existing code points to and report it
    under "Choices made". Return NEEDS_CONTEXT only for a question whose answer changes behavior a requirement
    describes.

    ## Code organization

    - Follow the file structure the plan defines; each file has one clear responsibility.
    - If a new file grows beyond the plan's intent, report DONE_WITH_CONCERNS rather than splitting it on your own.
    - In existing code, follow established patterns; improve what you touch, do not restructure beyond the task.

    ## When the task is too hard

    Returning BLOCKED or NEEDS_CONTEXT is fine; bad work is worse than no work. Report what you are stuck on,
    what you tried and what help you need when the task needs an architectural decision with several valid
    answers, code beyond what you can find, or restructuring the plan did not anticipate.

    ## Self-review before reporting

    - Every acceptance criterion above has a test named with its requirement ID, and the test checks behavior,
      not a mock.
    - Nothing beyond the task was built; existing patterns were followed.
    - Only your listed files changed (`git status`).
    Fix what you find before reporting.

    ## Return (rules/subagent-return-format.md; any shape)

    1. Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
    2. Requirement IDs covered, and for each the test names that prove it (file:line)
    3. Exit test command, its exit code and the log path
    4. Files changed (must be within the owned list)
    5. One line per exit criterion: met | not met — reason
    6. Choices made that the spec did not fix (what, why), so the main session can record them as rulings
    7. Concerns (DONE_WITH_CONCERNS), what is needed (NEEDS_CONTEXT), or what was tried and the blocker (BLOCKED)
```
