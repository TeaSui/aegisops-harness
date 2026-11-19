---
name: measurement-planning
description: Use when a feature must be measurable or the user asks for a North Star, funnel, analytics event taxonomy, experiment design or go-to-market plan. Produces measurement.md as a specification (no code, no publishing, no fabricated numbers).
---

# Measurement planning

Writes `docs/specs/<feature>/measurement.md` (layout `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md` §4). The integrating session is its single writer.

Make the feature *measurable* before it is built, and design the next experiment after launch. Produce specifications only: no instrumentation code, no publishing.

**Hard rules**
1. **No routing bypass.** Instrumentation carrying user identifiers, a new analytics/experimentation vendor, or a pricing/auth/payments experiment is a **trust boundary** that re-enters `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` (Security before implementation, the integrating session ratifies the event contract). List these under "Re-enters Routing" with an owner; never label them non-blocking.
2. **Measure first or say "I don't know".** You have no metric-query tool. Never fabricate numbers; request the export/dashboard or mark "to be measured" (`${CLAUDE_PLUGIN_ROOT}/rules/reduce-hallucinations.md`).
3. **Consent and PII are hard gates.** No raw PII in event payloads (use opaque salted IDs). Mark every property `PII: yes/no` and `consent-gated: yes/no`; any PII or undefined consent gating → escalate to Security.
4. **Experiment validity.** Each experiment: hypothesis, variants, ONE primary metric, MDE, sample size & duration estimate, guardrail metrics, SRM check, pre-registered analysis, no peeking (sequential testing if early looks are needed), stop/ship criteria, named feature-flag/assignment dependency.
5. **Honest funnels.** Report drop-offs truthfully; cut vanity metrics.

**Ownership lines:** the requirements' value statement (`requirements.md`) is the metric of record — the North Star refines it, never overrides it. The event taxonomy is proposed here and ratified into the contract (`design.md` / `contracts/`) by the integrating session. data-engineer-subagent owns ingestion/storage of the events. Platform owns system telemetry (APM, latency, errors); this skill covers product analytics (activation, retention, funnel, referral). Analytics events are distinct from domain events in `docs/events.md`.

**`measurement.md` contents:**
1. North Star & funnel (activation moment, ordered stages, blind stages marked)
2. Input metrics and reconciliation with the requirements' success metric
3. Event taxonomy — PROPOSED (event · properties · PII? · consent-gated? · fires client/server)
4. Experiment backlog, prioritized by ICE/RICE, each with the rule-4 fields
5. GTM plan: positioning, audience, channels, copy drafts (text only — never send or publish)
6. Re-enters Routing (trust-boundary/implementation items + owner)
7. Open questions / assumptions

For rigorous experiment design (power/MDE math, sequential testing, multi-variant interactions) use a general-purpose subagent (full workflow) or do it in-session; choose the model per `${CLAUDE_PLUGIN_ROOT}/references/model-guide.md`.
