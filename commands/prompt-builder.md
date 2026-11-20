---
description: Use only when the user asks for a prompt to be written (or runs /prompt-builder) — generates an optimal Claude prompt from a description. Software-change requests get a prompt that follows the tea-sdlc flow (fast path spec → adr → tdd → implement → test → create PR, or the full-workflow AIDLC stages spec → plan → build → verify → review → ship → promote); other tasks get a minimal or full XML-structured prompt. Asks clarifying questions when details are missing.
argument-hint: "[description of what you want the prompt to do]"
---

# /prompt-builder

## Objective

Turn a natural-language description of a task into a well-structured Claude prompt. Ask for missing details before generating.

- **Software change** (build, add, modify, fix or refactor code): generate an **SDLC-flow prompt** with a gate between stages. Fast path: `spec → adr → tdd → implement → test → create PR`. Full workflow: the AIDLC stages in `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` (spec with keyed requirements, spec check and one approval → plan graph → build via the frontier → verify → two-axis review → ship → promote).
- **Anything else** (classification, extraction, writing, analysis): choose between **minimal** and **full** based on complexity.

## Arguments

- `$ARGUMENTS` — free-text description of the prompt's purpose.
- If `$ARGUMENTS` is empty: ask the user "What do you want this prompt to do?" and wait.

## Process

### 1. Parse the input

Extract what you can from `$ARGUMENTS`:

| Field | What to look for |
|---|---|
| **Role** | Who the AI is ("act as a", "you are a", domain expert implied) |
| **Task** | The verb — summarize, classify, extract, rewrite, answer |
| **Inputs** | Documents, variables, user text the prompt will receive |
| **Output format** | JSON, markdown, free text, table, code |
| **Constraints** | Tone, length, rules, things to avoid |
| **Examples** | Any sample input/output pairs mentioned |

### 1b. Pick the track

Software change → **SDLC-flow track** (§4a). Otherwise → minimal/full track (§3, §4b). If the user explicitly asks for a generic prompt for a dev task, honor it.

For the SDLC-flow track also extract: **service/repo**, **feature slug** (stable kebab-case, one change — `auth-login-mfa`, no numbers/dates/`-v2`), **spec key** for the full workflow (2-6 capital letters, prefixes every requirement ID, e.g. `ALM`), **acceptance criteria**, **trust boundary** (any item in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` → treat as YES when unsure), **domain count**, and whether an **external contract** changes. An external contract is an interface with consumers outside the changed module: an HTTP/RPC API, an event or message, a shared database schema, or a public library API. Interfaces, methods and classes used only inside the module or service are NOT contracts. The tier (fast path / full workflow) decides how heavy each stage is; never skip a stage, shrink it.

### 2. Decide: enough info?

**Enough info** means you can write a concrete `<role>`, a concrete `<task>`, and at least one `<constraints>` bullet. If any of these are completely missing or vague, ask.

**Ask ONE targeted question per gap** (not a list of 6). Pick the most important missing piece. After the user answers, re-evaluate — ask a second question only if a second gap remains. Stop asking after 3 rounds maximum; fill remaining gaps with sensible defaults and flag them.

Examples of targeted questions:
- "What should Claude output — JSON, markdown, or free text?"
- "Who is the role here — a customer support agent, a code reviewer, a data analyst?"
- "Will the prompt receive a long document, or just a short user query?"

### 3. Choose version (minimal/full track only)

Use **Full** when ANY of these apply:
- Prompt will receive documents or long variable content (>~500 tokens)
- Task has multiple steps or edge cases to handle explicitly
- Output needs a concrete schema (JSON, table, structured format)
- 3+ examples are needed to teach the pattern
- Constraints are complex or counter-intuitive

Use **Minimal** otherwise (simple one-step tasks, short inputs, free-text output).

If the user explicitly requests a version, honor it.

### 4a. SDLC-flow prompt (software changes)

Generate this prompt. Fill every `[...]` from the parsed input; leave `[TODO: ...]` + flag when unknown. Use the `<workflow>` block that matches the tier: **fast path** or **full workflow**, never both. Document locations, owners and lifecycle come only from `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`, and full-workflow stages, gates, file formats and commands only from `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` — do not restate or invent a different tree or stage list. Keep the generated prompt's paths, file names, owners, commands and status values identical to those files and to `/generate-service-docs` and `/upgrade-service-docs`.

```xml
<role>
You are a senior engineer on [service/repo], working through the tea-sdlc flow. You deliver one change end to end and never skip a stage; you may shrink one to match the change's tier.
</role>

<task>
[One imperative sentence: the change to deliver.]
</task>

<context>
- Service/repo: [name, path]
- Doc scope: [service → `[service]/docs/` | system (cross-service) → `<system-root>/docs/`]
- Feature slug: [kebab-case]
- Spec key (full workflow): [2-6 capital letters]
- Acceptance criteria: [list, or "derive from the description and confirm in stage 1"]
- Tier: [fast path | fast path + security pass (lean, the default) | full workflow (full mode or asked for)] — [why, citing the trust-boundary items hit]
- External contract change: [yes — what, and who consumes it | no, internal only]
</context>

<workflow>  <!-- fast path -->
First, invoke the `tea-sdlc:brainstorming` skill on this change (2-3 lines for a fast-path change), then confirm the tier. Do this before reading files or starting stage 1.

Before stage 1, read `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`. Resolve the owning scope root (§6.1) and the project's existing locations for ADRs and living docs (§6.2); reuse them, never create a parallel tree or a numbered/`-v2` duplicate.

Execute in order. Finish a stage and meet its gate before starting the next. Report the stage you are in.

1. SPEC — state the approach and acceptance criteria in 2–3 lines; no spec folder and no approval gate. If the change alters documented behavior, update the affected living file in the same change (layout §6.6).

2. ADR — record decisions that outlive the change.
   - For each significant decision (architecture, data model, new dependency, API style, security posture), write `[service]/docs/adr/NNNN-<decision>.md` (`<system-root>/docs/adr/` when it spans services) with the next free number: context, options, decision, consequences. The main session is the writer. Link it from the service `README.md` ADR index.
   - If no such decision exists, write one line: "No ADR needed: [reason]". An accepted ADR is immutable: supersede it with a new ADR, never rewrite it.
   - Gate: every decision the change depends on has an ADR or an explicit "no ADR needed".

3. TDD — write failing tests first (`tea-sdlc:test-driven-development`).
   - Read the service's `docs/architecture.md` (Code conventions, Test strategy) when present, then 2–3 existing tests to confirm them. Write tests for happy path, edge cases and error conditions from the acceptance criteria, not from the implementation.
   - Run them with the project's own test runner; they MUST fail for the expected reason. Show the failing output.
   - Gate: failing tests exist and fail correctly.

4. IMPLEMENT — minimum code to go green, in this session, no subagent dispatch. Do not add untested behavior or weaken assertions.
   - Gate: the new tests pass.

5. TEST — prove it.
   - Run the full suite (and build, lint, live API validation if a service is running). Fix regressions.
   - Single pre-PR pass per `${CLAUDE_PLUGIN_ROOT}/rules/pre-pr-review.md`.
   - Gate: all checks green with evidence; skipped or unavailable checks are stated explicitly.

6. CREATE PR — hand off.
   - Branch from the default branch and commit in logical steps. Record the pre-PR pass for the final HEAD with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mark-pr-review.py" --reviewer <name> --open-findings 0` (the `gh pr create` gate needs it), then open the PR (`tea-sdlc:finishing-a-development-branch`). The description lists the acceptance criteria with evidence and notes risks and skipped checks.
</workflow>

<workflow>  <!-- full workflow -->
First, invoke the `tea-sdlc:brainstorming` skill on this change (a full design for trust-boundary work), then confirm the tier. Do this before reading files or starting stage 1.

Before stage 1, read `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` (stages, gates, file formats, CLI) and `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md`. Resolve the owning scope root (§6.1) and the project's existing locations for specs, ADRs and contracts (§6.2, §6.4); reuse them, never create a parallel tree or a numbered/`-v2` duplicate.

Below, `aidlc` stands for `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`. Run it yourself. Only `aidlc advance` changes the spec's stage; when a gate lists findings, fix them and run it again. Start with `aidlc status`: if `[slug]` already exists, continue from its current stage.

Execute in order. Finish a stage and pass its gate before starting the next. Report the stage you are in.

1. SPEC (proposed → accepted).
   - `aidlc init [slug] --key [KEY]` in `[service]/docs/specs/`. Fill the README frontmatter (`scope`, `affects`, `contract: none|external`, `security: required`).
   - `requirements.md`: one `### [KEY]-<n>: <title>` heading per requirement, its acceptance criteria as bullets under `Acceptance:` (Given/When/Then or EARS, unhappy paths included), and a `Verify:` line.
   - `security.md` → tea-sdlc:security-engineer-subagent; `ui-design.md` → tea-sdlc:ui-ux-designer-subagent when the UI needs design; `design.md`, `contracts/` and `measurement.md` (via `tea-sdlc:measurement-planning`) → the main session, only the files the change needs. When the context says `External contract change: yes`, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py" [service]/docs/specs/[slug]` until it passes.
   - For each decision that outlives the change, write `[service]/docs/adr/NNNN-<decision>.md` with the next free number and link it from `design.md`; otherwise one line "No ADR needed: [reason]".
   - Run the blind spec check (`tea-sdlc:spec-check`) and close every guess in `spec-check.md`.
   - Present the spec once and ask the user to approve it; if this request explicitly delegated approval, record `accepted_by: <user> (delegated in request)` instead of asking. Then `aidlc advance [slug] accepted`.

2. PLAN (→ planned). `tea-sdlc:writing-plans` writes `plan.md` as a task graph (covers, depends, owner, files, exit), with no shared file between tasks that may run in parallel. Then `aidlc advance [slug] planned`.

3. BUILD (→ building). On a feature branch, `aidlc advance [slug] building`. Then repeat until no task is ready: `aidlc next [slug]`, dispatch the batch in parallel through `tea-sdlc:subagent-driven-development` (each task test-first with `tea-sdlc:test-driven-development`; tests name the requirement ID they prove), and tick each task with `aidlc task-done [slug] T<n> --cmd "<its exit check>"`.
   - Apply the accepted `contracts/` delta to the project's authoritative contract source (layout §6.4); do not re-type schemas in prose. Implementers never rewrite spec, ADR or living-doc files; contradictions are reported as `DONE_WITH_CONCERNS`.
   - A choice the spec does not settle and that is not the user's: decide, record it with `aidlc ruling [slug] --decision … --why … --if-wrong …`, and continue.

4. VERIFY (→ verified), the end of `tea-sdlc:subagent-driven-development`. Run the full suite with `aidlc verify [slug] --cmd "<test command>"` (add `--junit <glob>` when the runner writes JUnit XML), plus build and lint. Fix regressions, then `aidlc advance [slug] verified`.

5. REVIEW (→ reviewed), with `tea-sdlc:requesting-code-review`. Two separate reviews: the Spec axis (the change against `requirements.md`, `design.md`, `contracts/`) and the Standards axis (code quality, security rules, conventions), plus the QA verdict from `tea-sdlc:qa-subagent` (live API validation when a service is running). Findings go to `review.md` without being merged or re-ranked; close each with `fixed:` or `cleared:`, re-running `aidlc verify` after code fixes. Then `aidlc stamp [slug] review` and `aidlc advance [slug] reviewed` (this records the pre-PR pass, so `gh pr create` is allowed).

6. SHIP (→ shipped), with `tea-sdlc:shipping`. Open the PR; its description links the spec and ADRs and includes `aidlc trace [slug]`. Wait for CI, bump the version and `CHANGELOG.md` when the project versions releases, write `ship.md` (decision, version, checks, rollback, post-release verification), then `aidlc advance [slug] shipped`; the merge is blocked until it passes. Merge and deploy only when this request covers delivery.

7. PROMOTE (→ implemented). After the merge, run `upgrade-service-docs [service] [slug]` yourself: it updates the living docs, writes the traceability table, sets `source_revision` and moves the spec to `implemented`. Living docs are owned by `/generate-service-docs` and `/upgrade-service-docs`; do not hand-edit them in the PR.
</workflow>

<constraints>
- Follow the stages in the order given; do not implement before the failing tests exist, and in the full workflow not before the spec is accepted. In the full workflow never edit `status:` or tick a `plan.md` task by hand; `aidlc` does both.
- Never move, rename or delete `specs/`, `adr/`, `plans/` or legacy role folders (`docs/requirements/`, `docs/security/`, `docs/contracts/`, `docs/design/`, `docs/domain/`, `docs/decisions/`); add to them only through the owning stage.
- Reuse existing project locations for docs and contracts before creating new ones.
- Report only what you ran; never claim a skipped check passed.
- If information for a stage is missing, ask one targeted question only when the answer changes the design; otherwise state the assumption and continue.
</constraints>

<output_format>
After each stage, one line: `Stage N <name>: done | blocked — <artifact path or evidence>`. Final message: PR link, acceptance-criteria table (criterion → test → result; in the full workflow the `aidlc trace` matrix), the rulings taken (full workflow), open risks.
</output_format>

<user_query>
[Verbatim $ARGUMENTS]
</user_query>
```

### 4b. Minimal/full prompts (non-software tasks)

#### Minimal version

```xml
<role>You are [role]. You [one-sentence mission].</role>

<instructions>
1. [Step 1]
2. [Step 2]
3. [Step 3]
</instructions>

<constraints>
- [Hard rule]
- [Output format rule]
</constraints>

<examples>
  <example>
    <sample_input>...</sample_input>
    <ideal_output>...</ideal_output>
  </example>
</examples>

<user_query>{{USER_INPUT}}</user_query>
```

#### Full version

```xml
<role>
[One or two sentences. Who Claude is and what it does.]
</role>

<task>
[One imperative sentence: what to produce this turn.]
</task>

<!-- Long variable content goes FIRST for cache efficiency -->
<documents>
  <document index="1">
    <source>filename-or-id</source>
    <document_content>
      {{VAR_1}}
    </document_content>
  </document>
</documents>

<instructions>
1. [Numbered, ordered, one action per step.]
2. [Edge-case handling explicitly here.]
3. [For long-doc tasks: "First, quote relevant passages in <quotes>, then answer in <answer>."]
</instructions>

<constraints>
- [Tell Claude what TO do, not what not to do.]
- [State scope explicitly.]
- [Failure behavior: "If you lack the information, respond with {"error": "insufficient_context"} — do not guess."]
</constraints>

<examples>
  <example>
    <sample_input>...</sample_input>
    <ideal_output>...</ideal_output>
    <why_good>[Specific reasons tied to constraints.]</why_good>
  </example>
</examples>

<output_format>
[Concrete schema. JSON → show the schema. Free text → "Start with a one-sentence verdict, then 2–3 bullet reasons."]
</output_format>

<user_query>
{{USER_INPUT}}
</user_query>
```

### 5. Output

Present:
1. Which track/version was chosen and why (one sentence) — for the SDLC track, include the tier.
2. The filled-in prompt, ready to copy.
3. A short list of **flagged defaults** — any fields you filled in with assumptions the user should review (max 3 bullets).

**Inline the user's input into `<user_query>`.** `$ARGUMENTS` is the concrete request the prompt will actually process — do NOT leave it as `{{USER_INPUT}}`. The placeholder only applies when the user asked you to design a reusable template (e.g., "give me a template I can reuse for different emails"). Default behavior: paste the verbatim `$ARGUMENTS` text into `<user_query>`.

If a field has no good default (e.g., you have no idea what the output schema should be), leave a `[TODO: ...]` placeholder and flag it.

## Decision guide

```
Software change (code)?  ──YES──► SDLC-flow prompt: fast path spec → adr → tdd → implement → test → PR
         │                          full workflow spec → plan → build → verify → review → ship → promote
         │
         NO
         │
Has long documents / variable content?  ──YES──► Full
         │
         NO
         │
Multiple steps or edge cases?  ──YES──► Full
         │
         NO
         │
Structured output schema needed?  ──YES──► Full
         │
         NO
         │
         ▼
       Minimal
```

## Example run

**User:** `/prompt-builder I need a prompt that classifies customer support emails into categories`

**Output:**

> Choosing **Minimal** — single classification step, short input, free-text category output.
>
> ```xml
> <role>You are a customer support triage agent. You classify incoming support emails into the correct category.</role>
>
> <instructions>
> 1. Read the email in <user_query>.
> 2. Assign exactly one category from this list: Billing, Technical, Account Access, General Inquiry, Complaint.
> 3. If the email fits multiple categories, choose the primary issue.
> </instructions>
>
> <constraints>
> - Output the category name only — no explanation unless asked.
> - If the email is spam or irrelevant, output: Spam.
> </constraints>
>
> <examples>
>   <example>
>     <sample_input>Hi, I was charged twice this month for my subscription.</sample_input>
>     <ideal_output>Billing</ideal_output>
>   </example>
> </examples>
>
> <user_query>{{EMAIL_TEXT}}</user_query>
> ```
>
> **Flagged defaults:**
> - Category list is assumed — replace with your actual taxonomy.
> - Output is the category name only; change `<constraints>` if you need a confidence score or explanation.

---

**User:** `/prompt-builder add rate limiting to the login endpoint in auth-service`

**Output:**

> Choosing the **SDLC-flow** track — code change; touches auth (trust boundary), single backend domain → **full workflow** tier.
>
> *(the filled `<role>/<task>/<context>/<workflow>/<constraints>/<output_format>` prompt from §4a with the full-workflow `<workflow>`, slug `auth-login-rate-limit`, key `ALR`, `<user_query>` set to the request above)*
>
> **Flagged defaults:**
> - Slug `auth-login-rate-limit` and key `ALR` are assumed.
> - Acceptance criteria are left to be derived in stage 1 — supply them if you have them.
> - No contract change assumed (existing endpoint, new 429 behavior); say so if the OpenAPI spec must change.
