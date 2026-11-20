---
name: expert-lens
description: Use when the user asks what an expert or top practitioner in a field would think or do, asks how the best people handle something, or wants an approach held to a specialist production standard (payments, security, data, infrastructure and similar). Reports what that practitioner would notice that a competent generalist misses, do first and refuse to do. Skip for routine explanations and edits.
---

Target: $ARGUMENTS (default: the task or decision under discussion)

Name a specific practitioner ("a payments engineer who has run ledger migrations", not "a senior engineer"). Read the relevant code, documents or data first.

1. **Would notice:** 2-3 things a competent generalist misses, each with evidence (`path:line`, output) or marked inference.
2. **Would do first:** one action, and why before the obvious one.
3. **Would refuse:** the tempting move and its cost.
4. **Disagrees with the plan:** where, or "no disagreement".

Omit what a generalist would say. If the current approach already matches, say so in one line and stop. If action was requested too, do item 2 within the authorized scope and tier; otherwise stop.
