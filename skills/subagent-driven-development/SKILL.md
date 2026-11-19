---
name: subagent-driven-development
description: Use in the full workflow once the implementation plan exists, to execute it in this session with specialist subagents — owned files, dependency ordering, parallel independent tasks and evidence-based reviews.
---

# Execute with specialists

Read the accepted plan and applicable canonical Security/contracts. Resolve dependencies before dispatch. Use the actual Agent/Task tools available in the runtime; never claim a dispatch or independent review occurred when unavailable. Model/effort choices follow `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`.

Each task uses three templates from this skill's folder, in order:
1. `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/implementer-prompt.md`, dispatched to the task's domain agent per `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` (the owner named in the plan).
2. `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/spec-reviewer-prompt.md`, once the implementer returns.
3. `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/code-quality-reviewer-prompt.md`, dispatched to agent `code-reviewer` after the spec review passes.

The templates' `rules/…`, `references/…` and `skills/…` paths are relative to `${CLAUDE_PLUGIN_ROOT}`; expand them to absolute paths in the dispatch.

For each substantial task:
1. Supply goal, role, task-specific context, real inputs, file ownership, exclusions, exit criteria, evidence and bailout via `${CLAUDE_PLUGIN_ROOT}/rules/dispatch-prompt-contract.md`.
2. Tell implementers they are not alone in the checkout: accommodate others' edits and never revert their work.
3. Dispatch independent tasks concurrently only with non-overlapping ownership and resolved prerequisites. Sequence shared-file changes, Security/contract dependencies and integration.
4. Implementers run meaningful tests for behavior/code changes and preserve the project's conventions. Reversible prose/config edits need appropriate structural/runtime checks, not tests that merely mirror their text.
5. Read returned status, evidence and exit checks per `${CLAUDE_PLUGIN_ROOT}/rules/subagent-return-format.md`. Resolve material concerns before using dependent results.
6. Review specification compliance, then code quality (templates 2 and 3) for substantive implementation. The routing tier controls formal review requirements; a leaf's self-review does not replace a required independent gate.
7. Address verified findings, rerun relevant checks, and tick the task `- [x]` in `plan.md` when its exit criteria are met. Review bounds: `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`; change approach or escalate when the cap is hit.

After tasks converge:
1. Run the integration checks.
2. Run the pre-PR pass in `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md` (dispatch `code-reviewer` on the whole diff), commit the reviewed changes, then record the pass for that HEAD with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer code-reviewer --open-findings <n>`. The `gh pr create` gate needs 0 open findings.
3. Dispatch `qa-subagent` for the QA gate, including live API validation when a service is running.
4. After QA `GO` or a merge, run `upgrade-service-docs` yourself to promote the spec into the living docs.

Record missing runtime/independent gates as concerns or blockers; static inspection is not their substitute.

Use an isolated checkout only when needed and supported. No dependency on an absent using-git-worktrees skill is required. Do not initialize a repository or commit generated planning files without authorization. Preserve user changes and obtain separately required native permissions. Continue work already authorized; ask only for decisions/constraints that materially block it.

For repository delivery, use `tea-sdlc:finishing-a-development-branch` if applicable and execute the already-authorized delivery choice. Report outcome, evidence, material limits and concrete next action.
