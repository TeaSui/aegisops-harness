---
description: Use when a service or system has no living docs (no docs/ folder), when the user asks to document a service or codebase, or when docs are missing sections a task needs. Builds production-grade, AI-readable living reference docs from the source code. Offer it once before running; it reads the whole service.
argument-hint: "[service-name]"
---

Build or refresh the **living reference docs** of `$ARGUMENTS` from source code. If no service is named, use the current repo as the single service, or every service root under a detected system root, and state the choice. Ask only if no service root can be identified.

Read `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md` first. It owns the service tree (§2), the system tree (§3) and root resolution (§6.1). This command owns only the living files listed there.

## Rules
- Source code is the only source of truth. Confluence/Notion are secondary. Document only what the code does now, using real class names, methods and payload shapes. Never invent APIs, events or flows. Where the code diverges from an open spec or ADR, add a one-line link to it (`See docs/specs/<feature>/`).
- Runs are idempotent:
  - Inspect the existing `docs/` (service and system) first.
  - Update files in place, and create a file only when it is missing.
  - Rename misnamed living files to their canonical names, and merge duplicates into the canonical file.
  - Never create numbered or `-v2`/`-copy` duplicates, or a parallel tree.
  - List anything that is neither a canonical living file nor protected as "unclassified — needs human decision"; never delete it.
- Protected: never move, rename, rewrite or delete these; you may only add links to them from `README.md`:
  - `docs/specs/`, `docs/adr/` and `docs/plans/`;
  - the legacy role folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, `docs/design/`, `docs/domain/`, `docs/decisions/`);
  - the authoritative contract source (`api/`, `openapi/`, `proto/`, …).
- Mermaid for diagrams, `GLOSSARY.md` terms, scannable tables and bullets; state assumptions; no filler.

## 1. Service docs (`<service>/docs/`, layout §2)
Write `README.md`, `architecture.md`, `business-logic.md`, `api-contracts.md`, `data-model.md`, `events.md`, `security.md`, `configuration.md`, `troubleshooting.md`, `diagrams/` and `adr/`.
- `architecture.md` includes the deployment view and quality requirements, plus:
  - **Code conventions**: naming, layering, error handling, logging, DI and module boundaries, each with one real example file;
  - **Test strategy**: frameworks and runner commands, layout, naming, mocking, the unit/integration/e2e split and coverage gaps.
  Derive both from the source and test files, not from lint config.
- `troubleshooting.md` includes **Known concerns / tech debt**: fragile areas, TODO/FIXME clusters, missing tests and risky dependencies, each with a path and evidence. Facts only, no redesigns.
- `api-contracts.md` links the authoritative contract source and never re-types schemas.
- `security.md` describes the current posture and keeps the active security-rule register. Never invent rules; threat models live in specs.
- `README.md` indexes `specs/` (with `status`) and `adr/` (number, title and status, or "none yet").
- `adr/`: create it with a `.gitkeep` if it is missing, and remove the `.gitkeep` once real ADRs exist.
  - Never write, rename or edit an ADR; the main session owns `NNNN-<slug>.md`.
  - Leave legacy decision folders in place and link them from `README.md`.
  - Report decisions you notice in the code as "candidate ADRs"; never invent ADRs.

## 2. System docs (`<system-root>/docs/`, layout §3), only when a system root exists
After all target services: relationships, end-to-end flows, and the master catalogs (APIs, events, topics/queues). Ensure `adr/` exists. `GLOSSARY.md` belongs to the main session: add only missing terms the code clearly evidences, and never redefine an entry.

## Output
- The final folder tree.
- What was created, updated or renamed.
- Candidate ADRs.
- Unclassified items.
- A confirmation that every target service, and the system root when there is one, has `docs/adr/`.
