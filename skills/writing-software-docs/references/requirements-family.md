# Requirements Family: BRD, PRD, FRD

These three sit on a spectrum from business intent → product behavior → exact functional detail. Pick by who's asking and how much detail they need.

- **BRD** — "What does the business want?" (BA/BO/PM). Highest level.
- **PRD** — "Why does this product feature exist and how does it work?" (PM/PO). Adds personas, flows, metrics.
- **FRD** — "Exactly how does this function behave?" (BA/Dev). Inputs, validation, exceptions, acceptance.

When unsure between PRD and FRD: if the reader needs to make a product/scope decision, it's a PRD; if they need to build the exact behavior, it's an FRD.

The `BO-n`, `FR-n`, `NFR-n`, `US-n` and `AC-n` IDs below are for standalone documents. A change spec's `requirements.md` uses the keyed format in the next section instead.

---

## Change-spec requirements — `docs/specs/<feature>/requirements.md`

The requirements of one full-workflow change. The lifecycle gates read this file, the plan's tasks cite its IDs, and each test names the ID it proves, so its shape is fixed: the plugin-root `references/aidlc.md` §2 owns it. In short:

- Each requirement is a heading whose first token is its ID: `### <KEY>-<n>: <title>`. `<KEY>` is the spec's `key:` from its `README.md`; numbers are never reused.
- Its acceptance criteria are the bullets under an `Acceptance:` line, one observable outcome per bullet. Write them in Given/When/Then or EARS form ("When <trigger>, the <system> shall <response>"), and cover the unhappy paths.
- A `Verify:` line says how it is proven: `test`, `check — <command or procedure>` or `manual — <reason>`.
- Business rules, new terms and story text may follow in any form. Only the ID headings define requirements; a PRD-style section that matters to the build becomes a requirement or a bullet of one.

```
### KYC-2: Reject unsupported ID image formats
Priority: must
Acceptance:
- Given the customer is on the KYC page, when they upload a .docx file, then the upload is rejected with `UNSUPPORTED_FORMAT` and the accepted formats are shown.
- When an upload is rejected, the KYC service shall keep the customer on the upload step.
Verify: test
```

Open questions do not stay as `[NEEDS INPUT]` markers here at approval: the blind spec check turns each into a guess that is resolved in the spec or accepted as a risk.

---

## BRD — Business Requirements Document

```
# BRD: <title>

## 1. Introduction
### 1.1 Purpose
### 1.2 Scope
### 1.3 Definitions  <!-- if the top-scope glossary.md exists, point to it and list only doc-local terms; do not restate glossary entries (link, do not restate) -->
## 2. Business Background
## 3. Business Objectives
## 4. Stakeholders
## 5. Functional Requirements
## 6. Non-functional Requirements
## 7. Assumptions
## 8. Constraints
## 9. Risks
## 10. Success Metrics
```

**Worked example (excerpts):**

```
## 3. Business Objectives
BO-1: Reduce KYC completion time from current baseline to target. [NEEDS INPUT: baseline and target]
BO-2: Increase first-attempt KYC pass rate. [NEEDS INPUT: current rate and target]

## 5. Functional Requirements
FR-1: The customer can upload an ID card.
       Supported formats: JPG, PNG, PDF. Max size: 10MB.
FR-2: The system extracts ID fields via OCR. [NEEDS INPUT: provider]

## 6. Non-functional Requirements
NFR-1: Upload-to-OCR response time target. [NEEDS INPUT: p95 latency target]
NFR-2: Availability 99.9%. [NEEDS INPUT: stakeholder hasn't set a target]

## 10. Success Metrics
- KYC median completion time. [NEEDS INPUT: target]
- First-attempt pass rate. [NEEDS INPUT: target]
```

---

## PRD — Product Requirements Document

The most common doc at product companies (Google, Meta, Airbnb, Uber). Answers: why does this exist, how does it work, how do we measure success.

```
# PRD: <title>

## 1. Overview
## 2. Problem Statement
## 3. Goals
## 4. User Personas
## 5. User Stories
## 6. User Flow
## 7. Functional Requirements
## 8. Edge Cases
## 9. Non-functional Requirements
## 10. Metrics
## 11. Rollout Plan
## 12. Risks
```

**Worked example (excerpts):**

```
## 2. Problem Statement
Customers abandon KYC because the process is too long and re-asks for
data we already have.

## 3. Goals
Increase KYC completion rate. [NEEDS INPUT: current baseline and target]

## 5. User Stories
As a customer, I want to upload my ID card so that I can continue the
KYC process without re-entering data.

## 8. Edge Cases
- Blurred image → prompt retake, do not call OCR.
- OCR timeout → show "Please try again", preserve uploaded file.
```

---

## FRD — Functional Requirements Document

BA's workhorse for pinning down exact behavior.

```
# FRD: <title>

## 1. Feature Overview
## 2. Business Rules
## 3. Inputs
## 4. Outputs
## 5. Validation Rules
## 6. Process Flow
## 7. Exception Cases
## 8. Acceptance Criteria
```

**Worked example (excerpts):**

```
## 5. Validation Rules
| Field      | Required | Rule                          |
|------------|----------|-------------------------------|
| ID Number  | Yes      | Exactly 12 digits, numeric    |
| ID Image   | Yes      | JPG/PNG/PDF, ≤ 10MB            |

## 7. Exception Cases
EX-1: OCR service timeout → show "Please try again", keep uploaded file,
      do not advance the step.
EX-2: Unsupported format → reject at upload, show accepted formats.

## 8. Acceptance Criteria
AC-1: Given a valid 12-digit ID and a clear image, when the customer
      submits, then OCR is called and the customer advances to the next step.
```
