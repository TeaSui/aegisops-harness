#!/usr/bin/env python3
"""Generate HOW-IT-WORKS.md, the one-page human map of the plugin, from the plugin's own sources.

  python3 scripts/map.py           write HOW-IT-WORKS.md
  python3 scripts/map.py --check   exit 1 when HOW-IT-WORKS.md is stale (scripts/check-setup.py runs this)

Sources: skills/*/SKILL.md, agents/*.md and commands/*.md frontmatter, hooks/hooks.json, the router tables in
hooks/autopilot.py. PHASES below is the only hand-kept grouping; check-setup fails when a skill is in no phase.
"""
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'HOW-IT-WORKS.md'

# Phase → skills, in lifecycle order (the stages of references/aidlc.md, the order work actually happens in).
PHASES = (
    ('Define', 'what to build and why', (
        'brainstorming', 'grilling', 'clarify', 'goal', 'expert-lens', 'reframe', 'spec-check', 'writing-software-docs',
        'measurement-planning')),
    ('Plan', 'slices and order', ('writing-plans',)),
    ('Build', 'code, test-first', (
        'test-driven-development', 'subagent-driven-development', 'executing-plans', 'dispatching-parallel-agents')),
    ('Verify', 'prove it works', (
        'verification-before-completion', 'systematic-debugging', 'validate-feature', 'grounding-claims', 'find-docs')),
    ('Review', 'a second pair of eyes', ('requesting-code-review', 'receiving-code-review')),
    ('Ship', 'PR, release, learn', ('shipping', 'finishing-a-development-branch', 'incident-to-eval')),
    ('Domain', 'loaded when the stack shows up', (
        'fintech-security', 'fintech-mobile', 'backend-languages', 'database-patterns', 'messaging-patterns',
        'data-pipeline-patterns', 'frontend-react', 'api-contract-testing', 'bdd-cucumber', 'cdk-testing',
        'observability')),
    ('Meta', 'always on', ('session-bootstrap',)),
)

# Hook script → what it does to the session (one line each; the script's docstring has the detail).
GATES = (
    ('session-start', 'SessionStart', 'injects the bootstrap (tier rules, mode, open specs)'),
    ('autopilot.py', 'UserPromptSubmit', 'reads the prompt, names the skills to load, the tier and the mode'),
    ('autopilot.py', 'Stop, SubagentStart, PostToolUse', 'follow-up notes: verify before "done", docs after merge'),
    ('tdd-gate.py', 'Edit / Write', 'first production edit needs a failing test run first (asks once)'),
    ('contract-gate.py', 'Edit / Write / Bash', 'external API contract must pass check-contract.py (advisory)'),
    ('security-gate.py', 'git commit / push', 'blocked while gitleaks finds a secret'),
    ('pr-review-gate.py', 'gh pr create', 'blocked until the pre-PR review is recorded for HEAD with 0 open findings'),
    ('ship-gate.py', 'gh pr merge', 'blocked until the branch\'s spec passes the `shipped` gate (full mode)'),
)

GLOSSARY = (
    ('Trust boundary', 'PII or money, auth/session/permissions, a new public endpoint, a new vendor, secrets or '
                       'security config. Unsure counts as yes.'),
    ('Lean mode', 'default. Everything in the main session, no subagents; a trust boundary gets a security pass.'),
    ('Full mode', '`TEA_SDLC_WORKFLOW=full` or asked for: the AIDLC lifecycle with gates and specialist agents.'),
    ('Fast path', 'TDD + verification + one pre-PR review. No spec files.'),
    ('Security pass', '3-6 lines of assets, threats, controls before the first edit; tests for them; threats in the PR.'),
    ('AIDLC', 'proposed → accepted → planned → building → verified → reviewed → shipped → implemented; '
              '`scripts/aidlc.py advance` moves a stage only when its gate passes.'),
    ('spec.md', 'the to-spec template: Problem, Solution, numbered User Stories, Implementation Decisions '
                '(incl. Security), Testing Decisions, Out of Scope, Further Notes.'),
    ('Story ID', 'user story n of a spec with `key: RFD` is `RFD-n`; tests name it so `aidlc trace` can find them.'),
    ('Ticket', 'one tracer-bullet vertical slice in tickets.md, with Blocked by, Covers and acceptance checkboxes.'),
    ('Seam', 'the public interface tests go through; the fewer the better, agreed in Testing Decisions.'),
    ('Grilling', 'one-question-at-a-time interview; terms go to GLOSSARY.md, hard-to-reverse decisions to ADRs.'),
    ('Gate', 'a hook or `aidlc` check that blocks the next step until its evidence exists.'),
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
    text = re.sub(r'\s*\(tea-sdlc[^)]*\)\s*$', '', description)
    text = re.split(r' — |(?<=[a-z)])\. ', text, maxsplit=1)[0].rstrip('.')
    text = re.sub(r'^Use (when|in|before|after|first|once)\b', lambda m: m.group(0)[4:].capitalize(), text)
    text = text.replace('|', '\\|').replace('<', '&lt;')
    return text if len(text) <= limit else text[:limit].rsplit(' ', 1)[0] + ' …'


def router_names():
    spec = importlib.util.spec_from_file_location('autopilot_map', ROOT / 'hooks' / 'autopilot.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = {name: 'keyword' for name, _ in module.INTENTS}
    names.update({name: 'stack keyword' for name, _ in module.DOMAINS})
    names.update({name: 'every code change' for name in ('brainstorming', 'test-driven-development')})
    names['systematic-debugging'] = 'bug or error'
    names['session-bootstrap'] = 'session start'
    return names


def unphased():
    phased = {s for _, _, skills in PHASES for s in skills}
    present = {p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')}
    return sorted(present - phased), sorted(phased - present)


def render():
    auto = router_names()
    skills = {p.parent.name: frontmatter(p) for p in sorted((ROOT / 'skills').glob('*/SKILL.md'))}
    agents = {p.stem: frontmatter(p) for p in sorted((ROOT / 'agents').glob('*.md'))}
    commands = {p.stem: frontmatter(p) for p in sorted((ROOT / 'commands').glob('*.md'))}
    out = ['# How tea-sdlc works', '',
           '<!-- Generated by scripts/map.py from the plugin sources. Do not edit; run `python3 scripts/map.py`. -->',
           '', 'One page for people. The skills themselves are written for the model: short, imperative, loaded only '
           'when needed. Start here, open a skill only when you want its exact rules.', '',
           '## One request, end to end', '', '```text',
           'you type a request',
           '  │  UserPromptSubmit hook (autopilot.py): skills to load, tier, mode',
           '  ▼',
           'Define   brainstorming ── trust boundary? ── no ──▶ fast path: TDD → verify → one review → PR',
           '  │                          │ yes',
           '  │                lean (default): security pass, still one session, no subagents',
           '  │                full: spec.md (grilling, Security) ── approval',
           '  ▼',
           'Plan     tickets.md: vertical slices                       (full)',
           'Build    TDD at the seams, one ticket at a time            (gate: failing test first)',
           'Verify   aidlc verify: full suite green on this code',
           'Review   spec axis + standards axis, findings closed       (gate: gh pr create)',
           'Ship     PR, CI green, ship.md                             (gate: gh pr merge)',
           '```', '',
           '## Two modes', '',
           '| | Lean (default) | Full (`TEA_SDLC_WORKFLOW=full`, or "full workflow" in the prompt) |',
           '|---|---|---|',
           '| Who works | the main session only | the main session plus specialist agents |',
           '| Trust boundary | security pass, threats listed in the PR | AIDLC lifecycle with a gate at every stage |',
           '| Files per task | none (a handed-over spec is saved as `spec.md`) | `docs/specs/<feature>/` below |',
           '| Typical cost | about $1 per feature | about $6-8 per feature |', '',
           '## Skills by phase', '',
           '| Phase | Skill | Use it for | Loads by itself on |', '|---|---|---|---|']
    for phase, purpose, names in PHASES:
        first = True
        for name in names:
            meta = skills.get(name)
            if meta is None:
                continue
            label = f'**{phase}** · {purpose}' if first else ''
            out.append(f'| {label} | `{name}` | {gist(meta.get("description", ""))} | '
                       f'{auto.get(name, "named by another skill")} |')
            first = False
    out += ['', '## Agents (full mode only)', '', '| Agent | Job |', '|---|---|']
    out += [f'| `tea-sdlc:{name}` ({meta.get("model", "inherit")}) | {gist(meta.get("description", ""), 110)} |'
            for name, meta in agents.items()]
    out += ['', '## Commands (optional shortcuts; the autopilot runs them for you)', '', '| Command | Does |',
            '|---|---|']
    out += [f'| `/{name}` | {gist(meta.get("description", ""), 110)} |' for name, meta in commands.items()]
    out += ['', '## Gates', '', '| Hook | Fires on | Effect |', '|---|---|---|']
    out += [f'| `hooks/{script}` | {event} | {effect} |' for script, event, effect in GATES]
    out += ['', '## Files one full-mode task leaves behind', '', '| File | Read it? | What |', '|---|---|---|',
            '| `docs/specs/<feature>/spec.md` | yes | what and why: stories, decisions, security, seams |',
            '| `docs/specs/<feature>/tickets.md` | when planning | the slices and their order |',
            '| `GLOSSARY.md`, `docs/adr/` | when a term or decision is unclear | domain words; hard-to-reverse choices |',
            '| the pull request | yes | the change, the threats checked, the review |',
            '| `README.md`, `ledger.md`, `review.md`, `ship.md` in the spec folder | no | evidence the gates check |',
            '', '## Words', '', '| Term | Meaning |', '|---|---|']
    out += [f'| {term} | {meaning} |' for term, meaning in GLOSSARY]
    out += ['', 'Exact rules: `rules/workflow-routing.md` (tiers), `references/aidlc.md` (lifecycle formats and gates), '
            '`skills/session-bootstrap/SKILL.md` (what every session starts with).', '']
    return '\n'.join(out)


def main(argv):
    missing, unknown = unphased()
    if missing or unknown:
        print(f'map.py: skills in no phase: {missing}; phases naming missing skills: {unknown}', file=sys.stderr)
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
