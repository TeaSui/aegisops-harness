---
name: measurement-planning
description: Use when a feature must be measurable or the user asks for a North Star, funnel, analytics event taxonomy, experiment design or go-to-market plan. Produces measurement.md as a specification (no code, no publishing, no fabricated numbers).
---

# Measurement planning

Write `docs/specs/<feature>/measurement.md` (the main session is its only writer). Specification only: no instrumentation code, nothing sent or published.

**Hard rules**
1. Instrumentation carrying user identifiers, a new analytics or experimentation vendor, or a pricing/auth/payments experiment is a trust boundary: list it under "Re-enters routing" with an owner; never mark it non-blocking.
2. No metric-query tool: never invent a number; request the export or write "to be measured".
3. No raw PII in events (opaque salted IDs). Mark each property `PII: yes/no` and `consent-gated: yes/no`; any PII or undefined consent → Security.
4. Each experiment: hypothesis, variants, one primary metric, MDE, sample size and duration, guardrails, SRM check, pre-registered analysis, no peeking (sequential testing if early looks are needed), stop/ship criteria, flag/assignment dependency.
5. Report drop-offs honestly; drop vanity metrics.

**Ownership.** The value statement in `spec.md` (Problem Statement, Solution) is the metric of record; the North Star refines, never overrides it. The event taxonomy is proposed here and ratified into `spec.md` Implementation Decisions/`contracts/` by the main session. `tea-sdlc:data-engineer-subagent` owns ingestion and storage. System telemetry belongs to platform; analytics events are distinct from domain events in `docs/events.md`.

**Sections:** 1 North Star and funnel (activation moment, ordered stages, blind stages marked) · 2 input metrics reconciled with the requirements' success metric · 3 event taxonomy, PROPOSED (event, properties, PII, consent-gated, client/server) · 4 experiment backlog by ICE/RICE with rule-4 fields · 5 GTM: positioning, audience, channels, copy drafts (text only) · 6 Re-enters routing (item, owner) · 7 open questions and assumptions.
