---
name: goal
description: Execute an explicitly delegated end-to-end outcome autonomously, including recon, implementation, verification and delivery. Use for /goal or requests to handle the whole task independently; ordinary factual questions do not need this workflow.
---

# Autonomous outcome delivery

- Recon first (project instructions, existing changes, code, test commands); derive goal, scope and measurable success criteria; ask only for a material constraint you cannot resolve. Preserve the user's work.
- Code change: invoke `tea-sdlc:spec` next; it classifies the tier and records spec approval as delegated when the user handed over the outcome without check-ins. Autonomy removes no Security, contract, QA or permission gate.
- Substantial or long work: keep `.goal/state.md` (or the plan) with goal, acceptance evidence, tasks and status, decisions, blockers; update at checkpoints, reread after resume or compaction, never rebuild it from memory, never stage `.goal/`. Skip it for tiny fixes.
- Continue reversible work and routine choices without re-asking for approvals the request already covers. Destructive operations, permission prompts and external releases stay within their own authorization.
- Bound loops per `${CLAUDE_PLUGIN_ROOT}/rules/review-loop-limits.md`; keep independent tasks moving while a dependency is blocked.
- Before finishing, check every success criterion against real evidence; label missing or degraded gates, never call them passed.
- Deliver as authorized (merge/PR per the delivery skill) instead of ending with an offer to continue. Report outcome, key changes, checks and limits; link artifacts.
