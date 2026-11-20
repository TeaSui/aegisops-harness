---
description: Use right after a full-workflow change is shipped and merged (spec stage `shipped`), whenever a spec under docs/specs/ is still `shipped` (or, for a spec from before the AIDLC lifecycle, `accepted`) after its code merged, or when the user says the docs are outdated — promotes the change into the living service and system docs, writes the traceability table and moves the spec to `implemented`. Run it yourself at the end of the ship stage; the user does not need to type it.
argument-hint: "[service-name] [feature-slug or short description]"
---

Promote a merged change into the living docs and close its spec: the AIDLC promote stage, `shipped` → `implemented` (`${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` § 1. Stages). Source code is the only source of truth for living docs; specs are inputs, not facts.

## Ownership
- **Change:** `$ARGUMENTS`. If it is missing, infer it from the autopilot note, the current branch, or the specs at `shipped` in `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" status`. Ask only if several remain.
- **Layout:** read `${CLAUDE_PLUGIN_ROOT}/references/documentation-layout.md` first. It owns the trees (§2, §3), the spec folder (§4) and root resolution (§6.1).
- **This command owns** the living files and the lifecycle fields of the spec's `README.md`. It never edits the spec's `requirements.md`, `security.md`, `design.md`, `ui-design.md`, `measurement.md`, `contracts/`, `plan.md`, `ledger.md`, `review.md`, `ship.md` or ADRs.

## Steps
1. **Resolve** the service root, the system root and the spec folder. With no spec (fast path), skip steps 2, 3 and 7 and compare the code changes with the living docs directly.
2. **Confirm the ship.** The spec is at `shipped` and its commits are on the target branch (merge or squash). Run promotion on that branch, never in an implementation worktree.
   - Spec at an earlier stage: finish that stage first (`tea-sdlc:shipping`).
   - Change not merged: stop with `NEEDS_CONTEXT`.
   - Pre-AIDLC spec (no `key:`): QA `GO` or the merge is enough, and steps 3 and 7 are done by hand.
3. **Trace.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" trace <spec> --write`, which writes README `## Traceability`. Compare the actual code changes (classes, endpoints, events, tables, config) with the table and the contract delta. A requirement shown as pending or failing stays pending.
4. **Service docs**, in place, in this order:
   - `api-contracts.md`: link the contract source; never re-type schemas.
   - `events.md`, `business-logic.md`.
   - `architecture.md`: change Code conventions or Test strategy only if a pattern, framework, runner command or test layout changed.
   - `data-model.md`.
   - `security.md`: add the spec's implemented rules to the register as `<feature>/<RULE-ID>` with a link to the spec; retire the rules of any superseded spec.
   - `configuration.md`.
   - `troubleshooting.md`: in Known concerns, add what the change introduced or left pending (from `DONE_WITH_CONCERNS`) and remove what it resolved.
   - `README.md`: the specs index and the ADR index.
5. **System docs**, when a system root exists, in this order: `03-cross-cutting/all-apis-catalog.md`, `all-events-catalog.md`, `all-topics-and-queues.md`, `02-collaboration/end-to-end-flows.md`, `sequence-diagrams.md`, `integration-points.md`, `01-services/<service>.md`. Update `00-overview/service-map.md` only if service boundaries changed.
6. **Style.** Use Mermaid for diagrams and terminology from `glossary.md`. Describe current behavior only; link open specs instead of narrating intent.
7. **Close the spec.**
   - Set README `source_revision` to `<repo>@<sha>` for every affected repo, using a commit that contains the change.
   - Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <spec> implemented`, or `partially-implemented` if the table has pending requirements. Never hand-edit `status:` on an AIDLC spec.
   - If the change supersedes a spec, set the old spec's `superseded_by`.
   - Never rewrite the spec's intent to match what shipped.
8. **ADRs.**
   - Make sure `adr/` exists: create it with a `.gitkeep`, and at the system root too for a cross-service ADR.
   - Confirm that every ADR `design.md` links exists. Report a missing one as a gap; never write it.
   - Refresh the README ADR index (number, title, status). Record implementation status only in the index, never in the ADR.
   - List decisions you notice in the code that have no ADR as candidate ADRs.

## Constraints
- Update in place. Before creating a missing living file, check `git check-ignore -q <path>` and `git worktree list`. If the file is ignored or exists in another checkout, stop and report instead of creating a divergent copy.
- No duplicates or parallel trees. Never move or delete `specs/`, `adr/`, `plans/` or the legacy role folders.
- The living file set stays canonical. Write scannably, state assumptions, no filler.

## Output
1. What changed in the code.
2. The docs updated or created, with full paths and a one-line note each.
3. The spec's old → new stage (the `aidlc advance` output), the traceability table, and the source revisions.
4. The ADR check: `adr/` present, ADRs linked, missing ADRs, candidate ADRs.
5. Gaps that need human review.
