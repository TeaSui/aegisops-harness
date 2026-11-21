---
description: Use only when the user asks for a prompt to be written (or runs /prompt-builder) — generates an optimal Claude prompt from a description. Software-change requests get a prompt that follows the tea-sdlc flow (fast path spec → adr → tdd → implement → test → create PR, or the full-workflow AIDLC stages spec → plan → build → verify → review → ship → promote); other tasks get a minimal or full XML-structured prompt. Asks clarifying questions when details are missing.
argument-hint: "[description of what you want the prompt to do]"
---

# /prompt-builder

Turn `$ARGUMENTS` into a ready-to-copy Claude prompt. If `$ARGUMENTS` is empty, ask "What do you want this prompt to do?" and wait.

## 1. Parse and pick the track
- Extract the role, task, inputs, output format, constraints and any examples.
- **Software change** (build, add, modify, fix or refactor code) → the **SDLC-flow** track (§2), unless the user explicitly asks for a generic prompt. Also extract:
  - the service/repo;
  - a feature slug: stable kebab-case, one change, no numbers, dates or `-v2`;
  - a spec key for the full workflow: 2-6 capital letters;
  - the acceptance criteria;
  - the trust boundary: any of the six items in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`, YES when unsure;
  - the domain count;
  - whether an external contract changes: an HTTP/RPC API, event, shared DB schema or public library API with consumers outside the module. Module-internal interfaces are not contracts.
- **Anything else** → the minimal or full track (§3).
- Enough information means a concrete role, a concrete task and at least one constraint. For each gap, ask ONE targeted question, the most important one first, and re-evaluate after each answer. After at most 3 rounds, fill the rest with defaults and flag them.

## 2. SDLC-flow prompt
Pick the tier with the routing rule:

| Trust boundary | lean mode (the default) | full mode (`TEA_SDLC_WORKFLOW=full`, asked for, or a spec past `proposed` on the branch) |
|---|---|---|
| no | fast path | fast path |
| yes | fast path + security pass | full workflow |

The tier makes a stage lighter; it never removes one. Emit only the tier's `<workflow>`. Paths, owners, commands and statuses must match `documentation-layout.md`, `aidlc.md` and the service-docs commands; never invent another tree or stage list. Fill every `[...]`; leave `[TODO: ...]` for anything unknown and flag it.

```xml
<role>You are a senior engineer on [service/repo], working through the tea-sdlc flow. You deliver one change end to end and never skip a stage; you may shrink one to match the tier.</role>

<task>[One imperative sentence.]</task>

<context>
- Service/repo: [name, path]
- Doc scope: [service → `[service]/docs/` | system → `<system-root>/docs/`]
- Feature slug: [kebab-case]
- Spec key (full workflow): [KEY]
- Acceptance criteria (full workflow: user stories): [list | "derive in stage 1 and confirm"]
- Tier: [fast path | fast path + security pass (lean, the default) | full workflow (full mode or asked for)] — [why, citing the trust-boundary items hit]
- External contract change: [yes — what, who consumes it | no, internal only]
</context>

<workflow> <!-- fast path / fast path + security pass -->
First invoke `tea-sdlc:spec` (2-3 lines), then confirm the tier. Resolve the owning scope root and the existing ADR and living-doc locations per `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`, and reuse them. Never create a parallel tree or a `-v2` duplicate. Run the stages in order; meet each gate before the next and report the current stage. Do not dispatch subagents.
1. SPEC: the approach and acceptance criteria in 2-3 lines; no spec folder, no approval. If documented behavior changes, update the affected living file in the same change. Security pass: before the first edit, write 3-6 lines (assets, the applicable STRIDE/OWASP threats, the controls kept or added) using `tea-sdlc:fintech-security`.
2. ADR: for each decision that is hard to reverse, surprising without context and a real trade-off, write `[service]/docs/adr/NNNN-<slug>.md` (`<system-root>/docs/adr/` when it spans services) with the next free number (context, options, decision, consequences), and link it from the README ADR index. If there is none, write "No ADR needed: [reason]". Accepted ADRs are immutable; supersede them instead. Gate: every decision has an ADR or that line.
3. TDD (`tea-sdlc:test-driven-development`): read `docs/architecture.md` (Code conventions, Test strategy) and 2-3 existing tests. Write tests from the acceptance criteria: happy path, edge cases and errors; with a security pass, also authorization denied, input rejected, no PII in logs, and idempotent money movement. Run them and show them failing for the expected reason. Gate: that output.
4. IMPLEMENT: the minimum code to go green, in this session. Never add untested behavior or weaken assertions. Gate: the new tests pass.
5. TEST: the full suite, build and lint, plus a live API check if a service is running; fix regressions. If an external contract changed, run the contract gate (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py"`) on the drafted contract. Then the single pre-PR pass in `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md`, covering security explicitly when there was a security pass. Gate: green with evidence, and skipped checks stated.
6. CREATE PR: branch from the default branch and commit in logical steps. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <name> --open-findings 0` for the final HEAD, then open the PR with `tea-sdlc:finishing-a-development-branch`. The description lists the acceptance criteria with evidence, the risks and the skipped checks; with a security pass, also the threats checked and those left to the human reviewer.
</workflow>

<workflow> <!-- full workflow -->
First invoke `tea-sdlc:spec` (a full design), then confirm the tier. Resolve the scope root and the existing spec, ADR and contract locations per `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`, and reuse them. For each stage, read only its section of `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md`. `aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run it yourself. Only `aidlc advance` changes the stage; when a gate lists findings, fix them and rerun. Start with `aidlc status` and resume `[slug]` if it already exists. Report the current stage.
1. SPEC (→ accepted):
   - `aidlc init [slug] --key [KEY]` in `[service]/docs/specs/`; set the README `scope`, `affects`, `contract: none|external` and `security: required`.
   - Write `spec.md` with the template in `aidlc.md` §2: Problem Statement, Solution, User Stories (numbered; story n is `[KEY]-n`; optional `(Verify: check|manual|none — …)`), Implementation Decisions (architecture, contracts, UI, `### Security`; no file paths or code), Testing Decisions (the agreed seams, ideally one; external behaviour only; prior art), Out of Scope, Further Notes.
   - `tea-sdlc:security-engineer-subagent` reviews the draft and returns the `### Security` subsection (assets, threats, controls as numbered rules); paste it under Implementation Decisions. `tea-sdlc:ui-ux-designer-subagent` returns the UI decisions when the UI needs design. Write `contracts/` (`contract: external` only), `measurement.md` (`tea-sdlc:measurement-planning`) and new domain terms in `GLOSSARY.md` yourself, only where needed.
   - If an external contract changes, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py" [service]/docs/specs/[slug]` until it passes.
   - Write ADRs as in the fast path, linked from Implementation Decisions.
   - Grill open decisions with the user (`tea-sdlc:grilling`); if that did not happen, run one blind spec check (`tea-sdlc:spec-check`) and close every guess in the spec directly; there is no second check.
   - Get the user's approval once; if the request explicitly delegated it, record `accepted_by: <user> (delegated in request)`. Then `aidlc advance [slug] accepted`.
2. PLAN (→ planned): `tea-sdlc:plan` writes `tickets.md` as tracer-bullet vertical slices (`## T<n>`, `Blocked by`, `Covers`, `Status: ready-for-agent`, What to build, acceptance checkboxes, `Test:`, `Files:` for parallel tickets). Every story is covered (except `Verify: none`), and no file is shared by tickets that may run in parallel. Then `aidlc advance [slug] planned`.
3. BUILD (→ building):
   - On a feature branch, `aidlc advance [slug] building`.
   - Loop until no ticket is ready: `aidlc next [slug]`; dispatch each batch in parallel via `tea-sdlc:build` (test-first through the agreed seams, tests named by story ID; the implementer ticks the acceptance checkboxes); close each with `aidlc task-done [slug] T<n> --cmd "<exit check>"`.
   - Apply the accepted `contracts/` delta to the authoritative contract source. Implementers never rewrite spec, ADR or living-doc files.
   - Record each unsettled, non-user decision with `aidlc ruling [slug] --decision … --why … --if-wrong …`.
4. VERIFY (→ verified): `aidlc verify [slug] --cmd "<test command>"` (add `--junit <glob>` when the runner writes JUnit XML), plus build and lint. Then `aidlc advance [slug] verified`.
5. REVIEW (→ reviewed), with `tea-sdlc:review`:
   - Run the Spec axis and the Standards axis once each, plus the `tea-sdlc:qa-subagent` verdict (live API checks when a service is running).
   - Put finding lines only in `review.md`, never merged or re-ranked. Close each with `fixed:` or `cleared:`, and rerun `aidlc verify` after code fixes.
   - Allow at most one diff-only re-review of the fixes (one reviewer, both axes); never a second full round.
   - Then `aidlc stamp [slug] review` and `aidlc advance [slug] reviewed`, which records the pre-PR pass.
6. SHIP (→ shipped), with `tea-sdlc:ship`:
   - Open the PR, linking the spec and ADRs and including `aidlc trace [slug]`.
   - Wait for green CI. Bump the version and `CHANGELOG.md` when the project versions releases.
   - Write `ship.md` with only its required sections (decision, version, Checks, Rollback, Post-release verification), then `aidlc advance [slug] shipped`.
   - Merge and deploy only if this request covers delivery.
7. PROMOTE (→ implemented): after the merge, run `upgrade-service-docs [service] [slug]` yourself. Never hand-edit the living docs in the PR.
</workflow>

<constraints>
- Stages run in order. No implementation before the tests fail, and in the full workflow none before the spec is accepted. Never hand-edit README `status:` or a ticket's `Status: done`; `aidlc` sets both.
- Never move, rename or delete `specs/`, `adr/`, `plans/` or the legacy role folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, `docs/design/`, `docs/domain/`, `docs/decisions/`).
- Reuse the existing doc and contract locations.
- Report only what you ran; a skipped check is never a pass.
- Missing information: ask one question only when the answer changes the design; otherwise state the assumption and continue.
</constraints>

<output_format>
After each stage, one line: `Stage N <name>: done | blocked — <artifact path or evidence>`. Final message: the PR link; the criterion → test → result table (in the full workflow, the `aidlc trace` matrix); the rulings (full workflow); open risks.
</output_format>

<user_query>[verbatim $ARGUMENTS]</user_query>
```

## 3. Minimal or full prompt (non-software)
Use **Full** when any of these hold: long or variable input (over ~500 tokens), multiple steps or explicit edge cases, a structured output schema, 3 or more examples needed, or counter-intuitive constraints. Otherwise use **Minimal**. If the user names a version, use it.

- **Minimal:** `<role>` (who, plus a one-sentence mission), `<instructions>` (numbered steps), `<constraints>` (hard rules and the output format), optional `<examples>` (`<example><sample_input>…</sample_input><ideal_output>…</ideal_output></example>`), then `<user_query>`.
- **Full:** `<role>`, `<task>`, `<documents>` first for cache efficiency (`<document index="n"><source>…</source><document_content>{{VAR}}</document_content></document>`), `<instructions>` (numbered, explicit edge cases; for long documents, quote passages in `<quotes>` before `<answer>`), `<constraints>` (positive phrasing, scope, a failure value such as `{"error": "insufficient_context"}` instead of guessing), `<examples>` with `<why_good>`, `<output_format>` (a concrete schema), `<user_query>`.

## 4. Output
1. One sentence on the track and version chosen and why; for the SDLC track, the tier.
2. The filled prompt, ready to copy. Put the verbatim `$ARGUMENTS` in `<user_query>`; use `{{USER_INPUT}}` only when the user asked for a reusable template.
3. Up to 3 flagged defaults the user should review. Use `[TODO: ...]` where no sensible default exists.
