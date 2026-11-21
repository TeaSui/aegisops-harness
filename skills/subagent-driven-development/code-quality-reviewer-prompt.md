# Code quality reviewer template (per ticket)

Dispatch only after the spec compliance review passes. Send to `tea-sdlc:code-reviewer` the template `skills/requesting-code-review/code-reviewer.md`, filled with:

```
AXIS: standards
WHAT_WAS_IMPLEMENTED: [from the implementer's report]
PLAN_OR_REQUIREMENTS: T<n> of docs/specs/<feature>/tickets.md with its covered story IDs and the spec's security decisions
REVIEW_SCOPE: [committed range | pending Git work incl. staged, unstaged, untracked owned files | non-Git copies + hash manifest; owned paths; checked state]
BASE_SHA / HEAD_SHA: [committed range only]
FIRST_ID: Q1
DESCRIPTION: [ticket summary]
Also check: one responsibility per file with a clear interface; units testable alone; files this change made large (not pre-existing size); changes stay inside the ticket's `Files:` when declared; tests named with their story ID, through the spec's Testing Decisions seams, testing external behavior, not mocks.
```

Never request commits just to get a review, and never add "high-severity only" wording: the reviewer reports everything with severity and confidence. Status: any must → BLOCKED; should only → DONE_WITH_CONCERNS; nits or clean → DONE.
