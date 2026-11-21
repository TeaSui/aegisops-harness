---
name: clarify
description: Use before starting a task when the request leaves open something that changes what gets built (scope, behavior, data, interface, anything expensive to undo), or when the user asks to be asked clarifying questions first. Inspects the project, then asks only the questions whose answers change the work, each with the default that applies if unanswered. Skip for clear or routine requests. For a code change, tea-sdlc:spec already covers this; load clarify when the user asks to be questioned first or the task is not a code change.
---

Task: $ARGUMENTS (default: the task under discussion)

1. Read project instructions, the code involved, specs/ADRs and earlier messages; never ask what they answer.
2. An open point that changes scope, behaviour, data, an interface, a trust-boundary item or anything costly to undo → ask. Anything else → pick a default and list it under "Assumptions".
3. One batch, most consequential first, ≤5 questions, via the runtime's question tool if any. Each: concrete options, one line on what the answer changes, the default if unanswered.
4. Second round only if an answer opens a new question of that kind. Then state remaining assumptions and start. If the user asked only for clarification, restate the task in 3-5 lines and wait.
5. Nothing material open → say so in one line and start.
