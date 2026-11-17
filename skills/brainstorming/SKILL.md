---
name: brainstorming
description: You MUST use this first, before any other action, whenever a request builds, adds, modifies, fixes or refactors code. Clarifies the outcome, constraints and acceptance evidence, compares approaches when the tradeoff matters, and sets the depth for the rest of the workflow. Scales from three lines (routine fix) to a full design (trust-boundary or new system).
---

# Design clarification

This skill always runs first for code-changing work. It scales with the change; it never becomes a reason to stop.

| Change | Depth |
|---|---|
| Routine fix, one domain, no trust boundary | 2-3 lines: outcome, acceptance evidence, approach. Then continue immediately. |
| Feature or behavior change | Add constraints and 2-3 approaches only if the tradeoff is real; recommend one. |
| Trust boundary (money, auth, PII, new surface, secrets) or new system | Full design below; Security and contract steps follow the routing tier. |

If the request already carries goals, acceptance criteria and a tier (for example a `/prompt-builder` prompt), confirm them in one line, state any assumption you make, and continue. If you cannot ask the user (non-interactive run) or they delegated the choices, answer your own questions with the most reasonable assumption, say what you assumed, and proceed.

Read the applicable project context, then identify the outcome, constraints, acceptance evidence and material unknowns. Consult available sources before asking for information they already contain. Ask a concise question only when the answer changes the design; routine decisions can use a stated reasonable assumption.

Compare two or three approaches when the tradeoff matters. Recommend one with its costs, risks and validation. Preserve existing domain conventions and security controls. A configuration change may need a few sentences; a new system needs interfaces, ownership, data flow and failure behavior.

Present the concrete design. Reuse the user's authorization for the same scope; if they delegated implementation/design choices, proceed without repeated section-by-section, spec and execution confirmations. Obtain missing material decisions and separately required permissions before dependent work. This never authorizes destructive actions, external publishing or bypassing native controls beyond the user's scope.

For full-workflow/orchestrator work, record the design/coordination outline in the authorized project location. Obtain Security rules and any needed TechLead contract before the implementation plan; then use writing-plans. Do not invent artifacts or commit/scaffold an existing repository solely because a template says to. The routing rule controls required specialists and quality gates.

Make components understandable and independently testable. Use a design challenger for significant architecture decisions where available; keep review iterations bounded and record unresolved concerns. Use visuals when they help explain an actual visual decision, not as a mandatory intake ceremony.
