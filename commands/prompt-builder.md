---
description: Turn a rough description into an input that meets the AIDLC standard — a /aegisops-harness:aidlc prompt carrying a spec in the to-spec template, checked with aidlc lint, or a /aegisops-harness:fix prompt for a bug — or, for non-software work, a structured Claude prompt.
argument-hint: "[what you want built, fixed or prompted]"
disable-model-invocation: true
---

# /aegisops-harness:prompt-builder

Turn `$ARGUMENTS` into one ready-to-paste input. Empty → ask "What do you want built, fixed or prompted?" and wait. You write a prompt here; you change no code and create no spec folder.

## 1. Pick the track
- **Feature or behaviour change** in a backend service → §2, output starts with `/aegisops-harness:aidlc`.
- **Bug fix or small change with no new decision** (`${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md`, "/aegisops-harness:fix or /aegisops-harness:aidlc") → §3, output starts with `/aegisops-harness:fix`.
- **Anything else** → §4.

## 2. Feature: `/aegisops-harness:aidlc` + spec.md
1. **Gather** in the order of `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §0: the repository (code, tests, `GLOSSARY.md`, ADRs, `docs/`), then Atlassian Rovo (`search`, then `fetch` / `getConfluencePage` / `getJiraIssue`) for the business rules, terms, limits and decisions the description names. Ask the user only what neither answers and a test would observe: one question at a time with your recommended answer, at most 3 rounds; then take defaults and list them.
2. **Write the spec** in the template of `${CLAUDE_PLUGIN_ROOT}/references/aidlc.md` §2 `spec.md`:
   - Markdown structure kept exactly: `# <title>`, `## <section>` headings, stories numbered `1.` … `n.` in one list (a paste that loses them fails the gate);
   - `Status: ready-for-agent` only when nothing material is left open and the user agreed to hand it over; otherwise omit the line (the spec stage then asks for the one approval). "I approve your assumptions" approves the ones listed, not later decisions: say "do not ask" for those;
   - Problem Statement and Solution from the user's side;
   - a long numbered list of user stories (`As a <actor>, I want <feature>, so that <benefit>`) covering every behaviour, unhappy paths included; a story another service delivers ends `(Verify: none — <owner>)`;
   - Implementation Decisions: modules, interfaces, schema, contracts, error codes, configuration defaults; no file paths or code. A trust boundary (the six-item check in `rules/workflow-routing.md`) → a `### Security` subsection: assets, threats (STRIDE / OWASP), controls, and the three things a security review otherwise has to ask about: the compliance regime (`Compliance: POPIA + SARB`, from the customers' country, `docs/security.md` or Rovo), how each national ID or other Level 1 field appears in events and logs (profile ID or masked, never raw), and each external dependency the change calls (endpoint or contract, or "connector with the path in config, confirmed before release");
   - each story another system delivers (mobile screens, popups, analytics events sent by the app) ends `(Verify: none — <owner>)`;
   - Testing Decisions: the seam (the highest existing one, ideally one), external behaviour only, the good tests, prior art in this repository;
   - Out of Scope; Further Notes with `Sources:` (each Rovo page or issue used, with its link) and `Assumptions:` (each default taken).
   Use glossary terms; respect ADRs.
3. **Check it** — write the spec to a scratch file outside the repository and run:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" lint <file> --key <KEY>            # add --no-security when the check is all NO
   ```
   Fix every FAIL and rerun until it exits 0; settle every WARN about the compliance regime or a national ID too. Quote its last line.
4. **Delivery words:** add "merge when CI is green" (or "deploy") only if the user asked for it; otherwise the run stops with the PR open.

Output:
```text
/aegisops-harness:aidlc <one line: the outcome; when the user delegates every choice: "End to end, do not ask: take your recommended default for any open decision, record it, and list it in the final report.">

<the spec>
```

## 3. Bug: `/aegisops-harness:fix`
Gather as in §2.1, then output one block:
```text
/aegisops-harness:fix <one sentence: what is wrong>
Reproduce: <steps, request or failing test>
Expected: <behaviour, with its source (spec, Rovo page, issue)>
Actual: <behaviour, log line or error, no secrets or PII>
Scope: <service, module>; out of scope: <what not to touch>
```

## 4. Other prompts
**Full** when the input is long or variable (> ~500 tokens), there are several steps or explicit edge cases, a structured output schema, ≥ 3 examples, or counter-intuitive constraints; otherwise **Minimal**.
- **Minimal:** `<role>`, `<instructions>` (numbered), `<constraints>` (hard rules, output format), optional `<examples>`, `<user_query>`.
- **Full:** `<role>`, `<task>`, `<documents>` first (`<document index="n"><source>…</source><document_content>{{VAR}}</document_content></document>`), `<instructions>` with edge cases (long documents: quotes before the answer), `<constraints>` (positive phrasing, a failure value such as `{"error": "insufficient_context"}`), `<examples>` with `<why_good>`, `<output_format>` (a schema), `<user_query>`.

## 5. Reply
1. One line: the track and why.
2. The input, ready to paste, in one code block.
3. For §2: the `aidlc lint` result line, the sources used, and up to 3 defaults to review.
