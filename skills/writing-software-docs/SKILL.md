---
name: writing-software-docs
description: Use when the user asks to write, draft or spec out a BRD, PRD, FRD, user stories with acceptance criteria, RFC, ADR, specification or concern report ("write a PRD for…", "spec out this feature", "write up the decision to use X", "do a compatibility analysis"), including when the user describes the artifact without naming the type. This skill is the structure authority for these documents even when the result is published through a document connector (Docs, Notion, Confluence, Google Drive) — load it first for the sections, then publish. Not for code comments, docstrings, READMEs, commit messages, changelogs, chat answers or quick informal notes.
---

# Writing software documents

Only for a named, reusable document; a short write-up gets plain prose (unsure: ask "full <type> or a short write-up?").

## 1. Type

Pick the best fit and say it. Ask one line only when the choice changes the audience (PRD = product/scope decision, FRD = exact behaviour to build; FRD = for humans, Specification = adds machine contracts; RFC = still choosing, ADR = decided). Spanning several types: write the one needed now, offer the next.

## 2. Routing

This skill formats; it never turns trust-boundary work into fast path. If the document covers a trust-boundary item (auth, payments, PII, new endpoint/webhook, new vendor) and `tea-sdlc:security-engineer-subagent` has not run: label it **Working Draft**, add a `Routing / Required Review` section naming the missing gate, never label it Approved or implementation-ready, and save it only on request with `working-draft` in the filename or first heading. Labels: Working Draft → Security-Reviewed (review and any contract gate ran, evidence cited) → Approved (user/team accepted). Never write `security.md` (the Security agent's) or `ui-design.md` here.

## 3. Draft

Ground it in the conversation, code, existing `docs/` and upstream artifacts. Fill every section or mark it N/A with a reason. Mark gaps `[NEEDS INPUT: what, why it matters]` and inferences `[ASSUMED: inference + basis]`; any number, SLA, threshold or limit nobody stated must carry one of them. Collect all markers in a final **Open Questions** section. Number requirements and rules (FR-1, BR-1…). Acceptance criteria are Given/When/Then and cover unhappy paths.

| Type | Sections |
|---|---|
| BRD | Introduction (Purpose, Scope, Definitions — link `glossary.md` if it exists, list only local terms), Business Background, Business Objectives (BO-n), Stakeholders, Functional Requirements (FR-n), Non-functional (NFR-n), Assumptions, Constraints, Risks, Success Metrics |
| PRD | Overview, Problem Statement, Goals, User Personas, User Stories, User Flow, Functional Requirements, Edge Cases, Non-functional Requirements, Metrics, Rollout Plan, Risks |
| FRD | Feature Overview, Business Rules, Inputs, Outputs, Validation Rules (field/required/rule table), Process Flow, Exception Cases (EX-n), Acceptance Criteria (AC-n) |
| User story | `As a <role> I want <capability> So that <benefit>`; AC-n in Given/When/Then, each observable from outside; one capability per story; link each AC to its FR when derived |
| RFC | Header (Author, Status Draft/In review/Accepted/Rejected, Date); Context, Problem, Goals, Non-Goals, Proposed Solution, Alternatives (real options, pros and cons), Risks, Rollout, Open Questions |
| ADR | `# ADR-NNNN: <title>`, Status (Proposed/Accepted/Superseded by ADR-XXXX), Date; Context, Decision, Alternatives considered (one line each with reason), Consequences (including downsides). Immutable once Accepted: supersede with a new ADR |
| Specification | Overview, Scope, Business Flow, User Flow, API Contract, Event Contract, Database Schema, Business Rules, Error Handling, Security, Rollout, Monitoring, Test Cases (TC-n), Open Questions. Contracts exact: field names, types, required, formats. Every HTTP endpoint shows request and both envelopes: `{"data":{…},"meta":{"timestamp":…}}` and `{"error":{"code","message","details":[]}}`; a vendor-forced shape is wrapped at ingress |
| Concern report | Date, Scope; Summary (overall risk, biggest concern); table Concern / Status / Detail with Status `OK` (say how verified), `MISMATCH` (name the field, contract or consumer), `UNKNOWN` (not verified; never guess OK); Recommended actions, riskiest first, each tied to a row |

**Change-spec requirements** (`docs/specs/<feature>/requirements.md`, parsed by `aidlc`): keyed requirements only, no narrative. `<KEY>` is the README `key:`; IDs are never reused. `US-n`/`AC-n`/`FR-n` are for standalone documents only.
```
### KYC-2: Reject unsupported ID image formats
Acceptance:
- Given the customer is on the KYC page, when they upload a .docx file, then the upload is rejected with UNSUPPORTED_FORMAT.
Verify: test
```
`Verify:` is `test`, `check — <command or procedure>` or `manual — <reason>`. Criteria in Given/When/Then or EARS. Open questions are not left as markers at approval: `tea-sdlc:spec-check` turns them into guesses that are resolved or accepted as risk.

## 4. Save

Return it in the conversation unless it is a spec artifact of the current change or the user wants a file or a connector (keep this structure there). New spec folder: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" init <feature> --key <KEY>`, never by hand. Reuse the project's existing location first:

| Type | Path |
|---|---|
| Change-spec requirements | `docs/specs/<feature>/requirements.md` |
| BRD, PRD, FRD, stories | where the user asks; as a spec's `requirements.md`, rewrite as keyed requirements |
| RFC, Specification | `docs/specs/<feature>/design.md` (≤ ~120 lines; machine contracts in `contracts/`) |
| ADR | `docs/adr/NNNN-<decision>.md` |
| Concern report | `docs/specs/<feature>/concern-report.md` |

Slugs are stable kebab-case, no dates or versions; an `implemented` spec gets a new slug. Lifecycle status lives only in the spec README frontmatter. A strategic subagent (Security, UI/UX) uses its own persistence path and returns the saved path, not the document.
