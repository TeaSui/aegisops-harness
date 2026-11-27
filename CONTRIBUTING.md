# Contributing to AegisOps-Harness

Maintainer guide for editing this plugin's instruction artifacts. It is not loaded into agent sessions.

## Single Source of Truth (No Harmful Duplication)

**Scope:** Authoring or editing any instruction / reference artifact — skills, `docs/`, rule files, READMEs, ADRs, agent definitions. Governs when you may restate content that already lives in another file.

## The litmus test (primary criterion)

Before copying or restating content from another file, ask:

> **"If the source file changes, must I edit this copy to keep it correct?"**
> - **Yes → harmful duplication.** Do not copy. Point to the source instead.
> - **No → acceptable.** A pointer, cross-reference, or illustrative naming is fine.

This test **outranks the "it's just a curated subset" justification.** A curated subset of a rule/doc body still fails the test — when the source changes, the subset goes stale. "Curated subset" is not a license to duplicate; the sync-burden test is the deciding line. Decide with the litmus test first; reach for "curated subset" only to describe content that already passes it.

## Acceptable inline

- **Pointers / cross-references:** "`X` applies — see `path/to/source`." Editing the source never breaks the pointer.
- **Illustrative naming with no completeness contract:** list a few item *names* followed by "…and the rest", explicitly delegating authority to the source (and any enforcing tool). No "this is the full list" promise → no sync burden.
- **Domain specialization that ADDS value:** instantiate an abstract rule for the local context (e.g. name which decisions are the high-risk ambiguity points here, or which concrete source types to cite). This carries information the source does not.

## Harmful (do not do)

- Verbatim or near-verbatim copies of a rule/doc body in a second file.
- Restating a checklist a **tool already enforces** (e.g. duplicating lint rules a linter checks). Point to the tool; do not hand-maintain a parallel list that silently drifts from it.
- "Standalone for portability" copies of content that is itself always loaded/available in the relevant context — that pays a real maintenance cost for a portability benefit you don't need. Drop the copy; keep the pointer.

## When a duplicate is genuinely unavoidable

Rare. If you must restate, add a provenance marker so drift is detectable: `synced from <source> as of <SHA>`.

## Interaction with existing rules

- **`strategic-output-persistence.md`** — its staleness check is the same concern for `docs/`; this rule is the upstream "don't create the duplicate in the first place".
- **`reduce-hallucinations.md`** — a stale duplicate is a future false claim (it asserts what the source no longer says). Removing the duplicate removes the drift before it can mislead.

## Reachability

`rules/` and `references/` are never auto-loaded. Every file in them must be named from the session bootstrap, a skill or command, an agent, or a hook message (as `${CLAUDE_PLUGIN_ROOT}/…` in agents, commands and `SKILL.md`; plugin-root-relative inside `rules/` and `references/`). Prefer one hop; a `rules/` stub that only points to a reference is a smell. `python3 scripts/check-setup.py` verifies that every `aegisops-harness:<name>` and bundled path resolves.

## This repository runs its own lifecycle

A change to the engine, a hook, a stage skill or the evals goes through the plugin itself, loaded from the checkout (`claude --plugin-dir plugins/aegisops-harness`): `/aegisops-harness:aidlc <request>`, with the spec in `docs/specs/<slug>/`. `.aidlc.json` pins the verify command (`tests/junit_runner.py`, which writes the JUnit report the gates read), and CI runs `aidlc ci` on every pull request (`lifecycle gate`).

- **Tests name the story they prove** (`test_rfd_1_…`): the gate needs a passing test per story in the pinned run, and the revert check needs the suite to fail without the production change. A gap found by a proof, an eval run or a review becomes a failing test first.
- **A new gate says what it cannot stop.** A check that reads files the session can write is a guard rail; write that in its docstring and keep `references/aidlc.md` "Trust model" true.
- **An eval case ships with its proof.** A hidden check must fail on the fixture as shipped, pass on a reference solution and fail on the wrong solutions you expect (`tests/test_eval_cases.py`). Scores are read with their interval (`evals/README.md`).
- **The formats are frozen at schema 1** (`references/aidlc.md` "Compatibility"): add optional fields and event kinds; anything that changes what an existing file means is schema 2 and a major version.
