---
name: expert-lens
description: Hold a task or decision to a named top practitioner's production standard (/tea-sdlc:expert-lens) — what they would notice that a competent generalist misses, do first, refuse to do, and where they disagree with the plan. An opinion, no code.
disable-model-invocation: true
---

Target: $ARGUMENTS (default: the task or decision under discussion)

Name a specific practitioner ("a payments engineer who has run ledger migrations", not "a senior engineer"). Read the relevant code, documents or data first.

1. **Would notice:** 2-3 things a competent generalist misses, each with evidence (`path:line`, output) or marked inference.
2. **Would do first:** one action, and why before the obvious one.
3. **Would refuse:** the tempting move and its cost.
4. **Disagrees with the plan:** where, or "no disagreement".

Omit what a generalist would say. If the current approach already matches, say so in one line and stop. No code: a change it calls for goes to `/tea-sdlc:fix` or `/tea-sdlc:aidlc`, named in one line.
