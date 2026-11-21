---
name: grilling
description: Use when the user asks to be grilled or interviewed on a plan or design ("grill me", "interview me"), or before writing a full-workflow spec that the user has not already decided in detail — a relentless one-question-at-a-time interview down the decision tree that records domain terms in GLOSSARY.md and hard-to-reverse decisions as ADRs as they settle. Skip when the user handed over a spec marked ready-for-agent or delegated every choice.
---

# Grilling

Goal: shared understanding before a spec, with the vocabulary and the decisions written down as they settle.

1. **Read first.** Code, `GLOSSARY.md` (or `CONTEXT.md`), `docs/adr/`, existing specs and source pages. Never ask what they answer; when code contradicts what the user says, ask which is right.
2. **One question at a time**, down the decision tree (each answer may open the next branch), most consequential first. Each question carries your recommended answer and what changes with it. Invent concrete edge-case scenarios to force precision at the boundaries.
3. **Language.** A term that conflicts with the glossary, or a fuzzy or overloaded one → propose one canonical term. Resolved → add it to `GLOSSARY.md` at once (term, one-line definition, terms to avoid). Domain only: no implementation.
4. **ADR** (`docs/adr/NNNN-<slug>.md`, next free number: context, decision, alternatives, consequences) only when the decision is hard to reverse, surprising without context and a real trade-off. Otherwise it goes in the spec's Implementation Decisions.
5. **Seams.** Settle where the feature is tested: the highest existing seam, else the fewest new ones (ideally one). They become the spec's Testing Decisions.
6. **Stop** when the remaining open points change nothing a test could observe. Then write the spec (`tea-sdlc:spec` §3) with no further interview.
