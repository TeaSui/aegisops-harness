# Code quality reviewer template (per task)

Dispatch only after the spec compliance review passes. Send to `tea-sdlc:code-reviewer` the template `skills/requesting-code-review/code-reviewer.md`, filled with:

```
AXIS: standards
WHAT_WAS_IMPLEMENTED: [from the implementer's report]
PLAN_OR_REQUIREMENTS: T<n> of docs/specs/<feature>/plan.md with its covered requirement IDs
REVIEW_SCOPE: [committed range | pending Git work incl. staged, unstaged, untracked owned files | non-Git copies + hash manifest; owned paths; checked state]
BASE_SHA / HEAD_SHA: [committed range only]
FIRST_ID: Q1
DESCRIPTION: [task summary]
Also check: one responsibility per file with a clear interface; units testable alone; the plan's file structure followed; files this change made large (not pre-existing size); changes stay inside the task's files; tests named with their requirement ID and testing behavior, not mocks.
```

Never request commits just to get a review, and never add "high-severity only" wording: the reviewer reports everything with severity and confidence. Status: any must → BLOCKED; should only → DONE_WITH_CONCERNS; nits or clean → DONE.
