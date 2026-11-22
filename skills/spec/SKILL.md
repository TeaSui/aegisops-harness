---
name: spec
description: Stage 1 of the backend lifecycle — turn a request or a pasted to-spec spec into docs/specs/<feature>/spec.md (stories, decisions incl. security, testing seams), get the one approval and advance the spec to accepted.
argument-hint: "[feature request | pasted spec]"
disable-model-invocation: true
---

# Stage 1: spec

`aidlc` = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py"`; run it yourself. Format: `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 (`spec.md`, README frontmatter). Open questions: §0 (files, then Rovo, then a recorded assumption). Input: `$ARGUMENTS`, else the request in the conversation.

## 1. Folder
Stable kebab-case slug; a 2-6 letter key unused by other specs (`aidlc status`). `aidlc init <feature> --key <KEY>` (a folder path when the spec does not belong in the repository's own `docs/specs/`). README frontmatter: `scope`, `affects`, `contract: none|external`, `security: required` (or `not-applicable — <reason>` when the trust-boundary check in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` is all NO).

## 2. spec.md
- **Pasted spec in the to-spec template:** save it verbatim as `spec.md`; change only what the `accepted` gate rejects (say each change in one line). Do not re-derive it into other files and do not re-ask what it decides.
- **Otherwise write it:** read the code, `GLOSSARY.md`, ADRs and living docs, then Rovo (§0) for the business rules, terms and existing decisions the request names. Problem Statement and Solution from the user's side; a long numbered list of user stories (`As a <actor>, I want <feature>, so that <benefit>`) covering every behaviour incl. unhappy paths; Implementation Decisions (modules, interfaces, schema, contracts, architecture; no file paths or code); Testing Decisions (the highest existing seam, else the fewest new ones, ideally one; external behaviour only; prior art); Out of Scope; Further Notes with `Sources:` (Rovo pages and issues used) and `Assumptions:` (what no source settled). Glossary terms throughout; respect ADRs. A story this repository does not deliver → `(Verify: none — <owner>)`.
- New domain term settled → add it to `GLOSSARY.md`. A decision that is hard to reverse, surprising and a real trade-off → an ADR in `docs/adr/`.

## 3. Security
Trust boundary → Read `${CLAUDE_PLUGIN_ROOT}/skills/fintech-security/SKILL.md`, dispatch `aegisops-harness:security-engineer-subagent` on the draft spec, and put its returned assets, threats and numbered controls under `### Security` in Implementation Decisions (a pasted spec's own Security section is kept and extended, not replaced). It runs while you finish the rest.

## 4. Contract
External contract change (HTTP/RPC API, event, shared schema; tighter validation on an existing endpoint is not one) → `contracts/` and `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py" <spec-dir>` until it passes.

## 5. Blind check
Only for a spec you wrote that was not grilled with the user: dispatch one fresh `general-purpose` agent with `${CLAUDE_PLUGIN_ROOT}/skills/spec/checker-prompt.md` (absolute spec folder, first guess number 1). It appends guesses to `spec-check.md`. Close each in spec.md: `— resolved: <where>` (Rovo first for business answers) or `— accepted risk: <why>`. No second run.

## 6. One approval
Present once: summary, stories, decisions incl. security, seams, contract result, assumptions and sources. Skip asking when the input delegated it or the pasted spec says `Status: ready-for-agent`; record `accepted_by: <name> (<date>)`, `<name> (delegated in request)` or `<name> (handed over ready-for-agent)`. Then `aidlc advance <feature> accepted`; fix what the gate lists and rerun (not a new approval unless the fix changes what was approved). Approval never authorizes destructive actions, external publishing or bypassing native controls.

Next: `/aegisops-harness:plan` (inside `/aegisops-harness:aidlc`: continue).
