#!/usr/bin/env python3
"""Generate HOW-IT-WORKS.md, the one-page human map of the plugin, from the plugin's own sources.

  python3 scripts/map.py           write HOW-IT-WORKS.md
  python3 scripts/map.py --check   exit 1 when HOW-IT-WORKS.md is stale (scripts/check-setup.py runs this)

Sources: skills/*/SKILL.md, agents/*.md and commands/*.md frontmatter. COMMANDS and SUPPORT below are the only
hand-kept grouping; check-setup fails when a skill is in neither.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'HOW-IT-WORKS.md'

# Situation → command → what it loads. The only hand-kept part; check-setup fails when a skill is in no row.
COMMANDS = (
    ('New backend feature or behaviour change (a request or a pasted to-spec spec)', 'aidlc',
     ('spec', 'plan', 'build', 'verify', 'review', 'ship')),
    ('Open decisions; interview me before the spec', 'grilling', ()),
    ('Stage 1: spec.md, security, the one approval', 'spec', ('fintech-security',)),
    ('Approve a spec as it is written now (the one approval)', 'approve', ()),
    ('Stage 2: tickets (vertical slices)', 'plan', ()),
    ('Stage 3: build the tickets test-first', 'build', ('test-driven-development', 'systematic-debugging')),
    ('Stage 4: full suite, trace, placeholders → verified', 'verify', ()),
    ('Stage 5: Spec + Standards review and QA → reviewed', 'review', ()),
    ('Stage 6: PR, CI, ship.md → shipped (merge on request)', 'ship', ()),
    ('Bug fix or small change with no new decision', 'fix',
     ('systematic-debugging', 'test-driven-development', 'verify', 'review', 'ship')),
    ('Review comments arrived', 'receiving-code-review', ('test-driven-development', 'verify')),
    ('Challenge a plan or a belief', 'reframe', ()),
    ('What a top practitioner would do', 'expert-lens', ()),
)
# Commands in commands/ with the situation they serve (their own descriptions follow in the map).
COMMAND_FILES = {
    'prompt-builder': 'Turn a rough idea into an input that meets the AIDLC standard (checked with aidlc lint)',
    'eval-upgrade': 'Score, upgrade or A/B-duel one part of the plugin or a .claude directory',
    'upgrade-service-docs': 'After the merge: promote the spec into the living docs, close it',
    'generate-service-docs': 'A service has no living docs yet',
}
# Support skills: never invoked by name; a stage Reads them when the repository (or the change) calls for them.
SUPPORT = (
    ('test-driven-development', 'build, fix: before any production code'),
    ('systematic-debugging', 'fix; build when a test fails for an unexplained reason or a fix fails twice'),
    ('grounding-claims', 'every stage: before a factual claim'),
    ('find-docs', 'every stage: before relying on a library or cloud-service detail'),
    ('fintech-security', 'spec and fix: when the trust-boundary check says yes'),
    ('backend-languages', 'build.gradle, pom.xml, go.mod, Cargo.toml or a Python web framework'),
    ('database-patterns', 'SQL migrations, ORM entities, DynamoDB or Redis clients'),
    ('messaging-patterns', 'Kafka, RabbitMQ, SQS, SNS or EventBridge clients, an outbox table'),
    ('api-contract-testing', 'OpenAPI, AsyncAPI, proto files or Pact'),
    ('bdd-cucumber', '*.feature files, Cucumber or godog'),
    ('cdk-testing', 'cdk.json'),
    ('observability', 'dd-trace, dd-java-agent or DogStatsD dependencies'),
    ('session-bootstrap', 'injected at every session start by hooks/session-start'),
)

# Hook script → what it does to the session (one line each; the script's docstring has the detail).
GATES = (
    ('session-start', 'SessionStart', 'injects the command list and the stage + next command of every open spec'),
    ('autopilot.py', 'SubagentStart', 'the rules every dispatched subagent follows'),
    ('autopilot.py', 'Stop', 'code changed since the last test run → run the tests (once per change set)'),
    ('tdd-gate.py', 'Edit / Write', 'first production edit needs a failing test run first (asks once)'),
    ('contract-gate.py', 'Edit / Write / Bash', 'external API contract must pass check-contract.py (advisory)'),
    ('question-gate.py', 'AskUserQuestion', 'inside an AegisOps-Harness command: blocked when the input delegated every '
     'decision; otherwise the first question before any Rovo search is sent back'),
    ('evidence-guard.py', 'Edit / Write / Bash', 'the ledger and stored reviewer returns are written by `aidlc` only; '
     '`aidlc approve` needs the user\'s own /aegisops-harness:approve'),
    ('record-returns.py', 'a reviewer agent returns', 'in the review stage: stores the return verbatim in the spec '
     'folder, for the `reviewed` gate to compare review.md with'),
    ('security-gate.py', 'git commit / push (any spelling)', 'blocked while gitleaks finds a secret'),
    ('pr-review-gate.py', 'opening a PR (gh, API call or GitHub MCP)', 'blocked until the pre-PR review is recorded for '
     'HEAD with 0 open findings'),
    ('ship-gate.py', 'merging a PR (gh, API call or GitHub MCP)', 'blocked until the branch\'s spec passes the '
     '`shipped` gate'),
)

GLOSSARY = (
    ('Command', 'the only way AegisOps-Harness starts: `/aegisops-harness:<name>`. Every skill has `disable-model-invocation: true`.'),
    ('AIDLC', 'proposed → accepted → planned → building → verified → reviewed → shipped → implemented; '
              '`scripts/aidlc.py advance` moves a stage only when its gate passes.'),
    ('Trust boundary', 'PII or money, auth/session/permissions, a new public endpoint, a new vendor, secrets or '
                       'security config. Unsure counts as yes.'),
    ('Rovo first', 'a business question goes to files, then Atlassian Rovo, then a recorded assumption; a person only '
                   'for risk, money/regulatory, irreversible or contradictory cases (`references/aidlc.md` §0).'),
    ('spec.md', 'the to-spec template: Problem, Solution, numbered User Stories, Implementation Decisions '
                '(incl. Security), Testing Decisions, Out of Scope, Further Notes (Sources, Assumptions).'),
    ('Story ID', 'user story n of a spec with `key: RFD` is `RFD-n`; a test carries it in its name, and the gate needs '
                 'that test to have run and passed in the pinned run.'),
    ('Pinned command', 'the full-suite command in `.aidlc.json`, read from the default branch: the session that is '
                       'verified does not choose what verifies it.'),
    ('Revert check', 'the suite run with this branch\'s production source put back to its base version; it must fail, '
                     'or no test depends on the change.'),
    ('Approval', 'a ledger event with the hash of spec.md, recorded when the user types `/aegisops-harness:approve`; an '
                 'edit to the spec afterwards needs a new one.'),
    ('Ticket', 'one tracer-bullet vertical slice in tickets.md, with Blocked by, Covers and acceptance checkboxes.'),
    ('Seam', 'the public interface tests go through; the fewer the better, agreed in Testing Decisions.'),
    ('Gate', 'a hook or `aidlc` check that blocks the next step until its evidence exists; every gate up to `shipped` '
             're-checks the gates before it.'),
)


def frontmatter(path):
    text = path.read_text(errors='replace')
    match = re.match(r'---\s*\n(.*?)\n---', text, re.S)
    fields, current = {}, None
    for line in (match.group(1).splitlines() if match else []):
        if line.startswith((' ', '\t')):
            if current:  # continuation of a YAML block scalar (| or >)
                fields[current] = (fields[current] + ' ' + line.strip()).strip()
            continue
        key, sep, value = line.partition(':')
        if sep:
            value = value.strip().strip('"')
            current = key.strip() if value in ('|', '>', '|-', '>-', '') else None
            fields[key.strip()] = '' if current else value
    return fields


def gist(description, limit=120):
    """The trigger part of a description: up to the first ' — ' or sentence end, cut at a word."""
    text = re.sub(r'\s*\(AegisOps-Harness[^)]*\)\s*$', '', description)
    text = re.split(r' — |(?<=[a-z)])\. ', text, maxsplit=1)[0].rstrip('.')
    text = re.sub(r'^Use (when|in|before|after|first|once)\b', lambda m: m.group(0)[4:].capitalize(), text)
    text = text.replace('|', '\\|').replace('<', '&lt;')
    return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + ' …'


def unphased():
    listed = {name for _, cmd, loads in COMMANDS for name in (cmd, *loads)} | {name for name, _ in SUPPORT}
    present = {p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')}
    return sorted(present - listed), sorted(listed - present)


def render():
    skills = {p.parent.name: frontmatter(p) for p in sorted((ROOT / 'skills').glob('*/SKILL.md'))}
    agents = {p.stem: frontmatter(p) for p in sorted((ROOT / 'agents').glob('*.md'))}
    commands = {p.stem: frontmatter(p) for p in sorted((ROOT / 'commands').glob('*.md'))}
    out = ['# How AegisOps-Harness works', '',
           '<!-- Generated by scripts/map.py from the plugin sources. Do not edit; run `python3 scripts/map.py`. -->',
           '', 'AegisOps-Harness starts only from a slash command. No prompt keyword starts anything, and the model cannot load '
           'an AegisOps-Harness skill on its own. Inside a command, each stage is a fixed file and support skills are chosen from '
           'the repository\'s files.', '',
           '## The lifecycle', '', '```text',
           '/aegisops-harness:aidlc <request or pasted spec>     (or each stage on its own)',
           '  spec     spec.md: stories, decisions, Security, seams      gate: your approval of that text (/aegisops-harness:approve)',
           '  plan     tickets.md: vertical slices                        gate: every story covered',
           '  build    TDD at the seams, ticket by ticket                 reminder: failing test before code',
           '  verify   the pinned suite at this code                      gate: red without the change, green with it,',
           '                                                                    a passing test per story (JUnit)',
           '  review   Spec + Standards axes, QA                          gate: review.md = what the reviewers returned',
           '  ship     PR, CI green, ship.md                              gate: a result from CI; then the merge',
           'questions on the way: files → Atlassian Rovo → recorded assumption → (rarely) you',
           '```', '',
           '## What enforces what', '',
           '| Layer | What it is | Stops |', '|---|---|---|',
           '| Prompts | skills, rules, agents | nothing: they advise |',
           '| Hooks and local gates | `hooks/`, `aidlc check` | the default path: a session that forgets or takes the short '
           'way. They read files the session can write, so they are a guard rail, not a control |',
           '| CI on a protected branch | `aidlc ci` as a required status check, plus a required review by a person | a '
           'session that writes its own evidence: it cannot write CI\'s result or the base branch\'s config |', '',
           'Setup for the last row, once per repository: `aidlc config init` (pins the verify command in `.aidlc.json`), '
           'the `aidlc-gate` action in CI, branch protection that requires it (`references/aidlc.md` §4, §5, Trust model).',
           '',
           '## Situation → command → what it loads', '',
           '| Situation | Command | Loads, in order |', '|---|---|---|']
    for situation, cmd, loads in COMMANDS:
        out.append(f'| {situation} | `/aegisops-harness:{cmd}` | {" → ".join(f"`{x}`" for x in loads) or "—"} |')
    out += [f'| {COMMAND_FILES.get(name) or gist(meta.get("description", ""), 90)} | `/aegisops-harness:{name}` | — |'
            for name, meta in commands.items()]
    out += ['', '## Support skills (never invoked by name)', '', '| Skill | Read when |', '|---|---|']
    out += [f'| `{name}` | {when} |' for name, when in SUPPORT if name in skills]
    out += ['', '## Agents', '', '| Agent | Job |', '|---|---|']
    out += [f'| `aegisops-harness:{name}` ({meta.get("model", "inherit")}) | {gist(meta.get("description", ""), 110)} |'
            for name, meta in agents.items()]
    out += ['', '## Gates (on in every session)', '', '| Hook | Fires on | Effect |', '|---|---|---|']
    out += [f'| `hooks/{script}` | {event} | {effect} |' for script, event, effect in GATES]
    out += ['', '## Files one feature leaves behind', '', '| File | Read it? | What |', '|---|---|---|',
            '| `docs/specs/<feature>/spec.md` | yes | what and why: stories, decisions, security, seams, sources |',
            '| `docs/specs/<feature>/tickets.md` | when planning | the slices and their order |',
            '| `GLOSSARY.md`, `docs/adr/` | when a term or decision is unclear | domain words; hard-to-reverse choices |',
            '| the pull request | yes | the change, the threats checked, the review |',
            '| `README.md`, `ledger.md`, `returns/`, `review.md`, `ship.md` in the spec folder | no | evidence the gates '
            'check (`ledger.md` and `returns/` are written by `aidlc` only) |',
            '| `.aidlc.json` at the repository root | once, by a person | the verify command every gate trusts; read from '
            'the default branch |',
            '', '## Words', '', '| Term | Meaning |', '|---|---|']
    out += [f'| {term} | {meaning} |' for term, meaning in GLOSSARY]
    out += ['', 'Exact rules: `rules/workflow-routing.md` (fix or aidlc, trust boundary, stack skills), '
            '`references/aidlc.md` (questions, lifecycle formats and gates), `skills/session-bootstrap/SKILL.md`.', '']
    return '\n'.join(out)


def main(argv):
    missing, unknown = unphased()
    if missing or unknown:
        print(f'map.py: skills in no phase: {missing}; rows naming missing skills: {unknown}', file=sys.stderr)
        return 1
    text = render()
    if '--check' in argv:
        current = OUT.read_text() if OUT.exists() else ''
        if current != text:
            print('HOW-IT-WORKS.md is stale: run python3 scripts/map.py', file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text)
    print(f'wrote {OUT.relative_to(ROOT)} ({len(text.splitlines())} lines)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
