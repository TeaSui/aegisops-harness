# Documentation layout

Owns where project docs live, who writes each file and the doc lifecycle; on conflict this file wins. Doc paths are target-project paths relative to the owning scope root (§6.1).

## 1. Separate by lifecycle

- Living reference, rewritten to match verified code: `docs/*.md`, fixed set (§2, §3).
- Change spec, edited while active, frozen once `implemented`: `docs/specs/<feature>/`.
- Decision record, immutable (superseded, never rewritten): `docs/adr/NNNN-<decision>.md`.
- Workflow state, disposable (`ledger.md` append-only): `plan.md`, `ledger.md`, `docs/plans/`.

No role-based trees (`docs/requirements/`, `docs/security/`, `docs/contracts/`, `docs/design/`, `docs/domain/`) for new work; projects that have them keep them (§6.2, §8).

## 2. Service scope — `<service>/docs/`

Living files are written only by `/generate-service-docs` (build/normalize) and `/upgrade-service-docs` (promote); workflow agents read them.

```
<service>/docs/
├── README.md            # purpose, ownership, reading order, index of specs/ and adr/
├── architecture.md      # C4 container/component, deployment, NFR/SLO, conventions, test strategy
├── business-logic.md    # domain flows, real class/method names
├── api-contracts.md     # summary + error codes; links the contract source (§6.4)
├── data-model.md        # entities, fields, relationships, invariants
├── events.md            # name, payload, producer, consumer
├── security.md          # posture + active security-rule register (§5 step 5)
├── configuration.md     # config keys, flags, env vars
├── troubleshooting.md   # failure modes, dashboards, playbook, tech debt
├── diagrams/            # Mermaid sources
├── adr/                 # owner: integrating session
├── specs/<feature>/     # change specs (§4); never touched by normalization
└── plans/               # optional; never touched by normalization
```

Living files describe only what the code does now (intent and gaps go in specs). A single repo with no system root uses this layout at the repo root, plus `glossary.md`.

## 3. System scope — `<system-root>/docs/` (multi-service)

Same owners as §2.

```
<system-root>/docs/
├── README.md
├── 00-overview/         system-overview.md (C4 context, style, principles), service-map.md
├── 01-services/         README.md, <service-name>.md (role + contract summary; links into <service>/docs/)
├── 02-collaboration/    end-to-end-flows.md, sequence-diagrams.md, integration-points.md
├── 03-cross-cutting/    all-apis-catalog.md, all-events-catalog.md, all-topics-and-queues.md, shared-concepts.md
├── 04-ai-friendly/      how-to-add-new-service.md, how-to-safely-modify-a-flow.md, key-files-and-entrypoints.md, common-debugging-playbooks.md
├── glossary.md          # owner: integrating session
├── adr/                 # never touched by normalization
├── specs/<feature>/     # cross-service changes; never touched by normalization
└── plans/               # optional; never touched by normalization
```

## 4. Change spec — `docs/specs/<feature>/`

`<feature>`: stable kebab-case slug for **one change** (`auth-login`, later `auth-login-mfa`); no numbers, dates or `-v2`. Reuse the folder only while active; afterwards a new slug links back. Create with `scripts/aidlc.py init`.

The integrating (main) session writes every file except: `ui-design.md` (tea-sdlc:ui-ux-designer-subagent), `security.md` (tea-sdlc:security-engineer-subagent), `spec-check.md` (blind checker, skill `spec-check`; the session closes guesses), `ledger.md` (`aidlc` only, append-only). `aidlc advance` edits README `status`/`updated`/`branch`; `[x]` in `plan.md` only via `aidlc task-done`; `aidlc stamp review` writes review.md `fingerprint:`.

| File | Content | When |
|---|---|---|
| `README.md` | frontmatter, one-paragraph summary, file index, `## Traceability` | always |
| `requirements.md` | `### <KEY>-<n>:` per requirement, `Acceptance:` (Given/When/Then or EARS), `Verify:`; business rules, `New terms` | full workflow |
| `spec-check.md` | guesses a spec-only reader would make, each resolved or accepted risk | full workflow |
| `ui-design.md` | flows, wireframes, all component states, responsive + a11y rules | UI needing design |
| `security.md` | threat table (assets, boundaries, STRIDE, OWASP) + numbered rules (`AUTH-01`…) with severity, provenance | trust boundary, unless `security: not-applicable — <reason>` |
| `design.md`, `contracts/` | design, contract/data-model delta, rollout, ADR links (≤ ~120 lines); machine-readable deltas (OpenAPI, AsyncAPI, JSON Schema, proto) | contract or architecture change |
| `measurement.md` | metrics, funnel, analytics event taxonomy, experiments, consent (skill `measurement-planning`) | must be measurable |
| `concern-report.md` | existing vs required compatibility | optional |
| `plan.md` | task graph (skill `writing-plans`); exempt from freezing | full workflow |
| `ledger.md` | transitions, task completions, rulings, test runs, review stamps | from `accepted` |
| `review.md` / `ship.md` | finding lines / GO-NO-GO, version, checks, rollback, post-release verification (skill `shipping`) | before `reviewed` / `shipped` |

README frontmatter is the only lifecycle metadata in the folder:

```yaml
---
status: proposed        # stage or side state; set only by `aidlc advance`
key: RFD                # 2-6 capital letters, unique per repository; prefixes every requirement ID
branch: feat/<slug>     # written by `aidlc advance building`
security: required      # or: not-applicable — <reason> (escape hatch only)
scope: <service> | system
affects: [<service-or-module>, ...]
accepted_by: <name> (<date>)        # explicit approval only, or `<name> (delegated in request)`
source_revision: [<repo>@<sha>, ...] # set on promotion; one per affected repo
superseded_by: <slug>
contract: external                  # none only if no consumer outside the module; omitted = auto-detect from contracts/
contract_source: <path>             # optional: OpenAPI file for the compatibility check
breaking: approved                  # optional: breaking change explicitly approved
updated: YYYY-MM-DD
---
```

`writing-software-docs` labels (`Working Draft` / `Agent-Reviewed` / `Approved`) are review provenance, not lifecycle status.

## 5. Lifecycle

Only `aidlc advance` changes `status:`; never edit it by hand.
1. **Propose.** `aidlc init`; strategic agents write their own files.
2. **Accept.** Only explicit user/team approval, recorded in `accepted_by`. Implementers use `accepted`+ specs (`proposed` only if the dispatch says so).
3. **Decide.** A decision that outlives the change → ADR, linked from the spec. A smaller build-time decision → ruling in `ledger.md`.
4. **Implement.** Implementers apply the accepted `contracts/` delta to the authoritative contract source (§6.4). They never rewrite strategic files; contradictions found in code → `DONE_WITH_CONCERNS`.
5. **Promote.** After merge, `/upgrade-service-docs <service> <feature>` folds verified behaviour into living files, appends active security rules to the living register as `<feature>/AUTH-01`, writes `## Traceability`, sets `source_revision` (must contain the change: `git merge-base --is-ancestor`), advances to `implemented` or `partially-implemented`. Never rewrite intent to match what shipped. Not merged yet → keep status, report it.
6. **Supersede.** New slug; old README gets `superseded_by`; its rules are retired in the register.

## 6. Resolution rules

1. **Owning scope.** Service root for single-service work; system root = nearest ancestor with `docs/00-overview/`, else with ≥ 2 service roots. Only authorized scopes. Unversioned system root over separate repos → say so (cross-service specs cannot ride a branch).
2. **Reuse beats default.** Write to an existing equivalent location (`docs/security/`, `docs/decisions/`, `openapi/`, module READMEs, …) and return that path. Never migrate, rename or duplicate docs unless asked.
3. **One writer per file** (§2–§4); everyone else reads and cites. External contract → `scripts/check-contract.py` passes on `contracts/` before implementation.
4. **Authoritative contract source.** Contract-first: the schema folder the build consumes (`api/`, `openapi/`, `proto/`). Code-first (springdoc, NestJS, FastAPI): the code, with `api-contracts.md` linking the generated spec. Prose links, never re-types, schemas.
5. **Glossary.** Top-scope `glossary.md` (system root, or repo root for single repos). Terms proposed in `requirements.md`, ratified into `glossary.md`. Per-service entities in `data-model.md`; cross-service in `03-cross-cutting/shared-concepts.md`.
6. **Fast path** creates no spec folder; if it changes documented behaviour, update the living file in the same change.
7. **Docs are tracked.** If `git check-ignore -q docs/specs/x.md` succeeds (often a personal `core.excludesFile`), add `!/docs/` and `!/docs/**` to the repo `.gitignore`. `scripts/check-setup.py` warns about this.

## 7. Staleness

Applies to living files and active specs. `implemented`, `partially-implemented` (implemented items), `superseded` and `abandoned` specs are history, never refreshed; read living files for current behaviour.

## 8. Legacy path mapping

`docs/requirements/<f>.md` → `specs/<f>/requirements.md`; `docs/security/{threat-model,rules,stride}-*.md` → `specs/<f>/security.md` + living register; `docs/contracts/*.yaml` → `specs/<f>/contracts/` (proposed) or the authoritative source (implemented); ADRs under `docs/contracts/` → `docs/adr/`; `docs/design/<f>.md` → `specs/<f>/ui-design.md`; `docs/domain/*` → top-scope `glossary.md`, `data-model.md`, `shared-concepts.md`; a one-change `docs/plans/YYYY-MM-DD-*.md` → `specs/<f>/plan.md`; contracts in module READMEs → `api-contracts.md` + authoritative source (README keeps a pointer).
