#!/usr/bin/env python3
"""AIDLC lifecycle engine: the stages, artifacts and gates of references/aidlc.md (stdlib only, Python 3.9+).

CLI: python3 scripts/aidlc.py <command> [--json] [--repo DIR]   exit 0 pass, 1 gate findings, 2 usage or input error
  status [--fast]                          every spec: stage, next stage, whether its gate passes, blockers
  check SPEC [--to STAGE]                  run a gate (default: the next stage's), also for a stage already reached
  advance SPEC STAGE [--back] [--reason T] move forward one stage when its gate passes; --back --reason moves back;
                                           abandoned (--reason), superseded (README superseded_by:), partially-implemented
  next SPEC                                ready tasks in conflict-free parallel batches
  task-done SPEC T<n> [--cmd CMD]          run CMD (default: the task's `test:` field); on exit 0 tick it and log it
  verify SPEC --cmd CMD [--junit GLOB]     run the tests; log exit code, code fingerprint and JUnit totals
  ruling SPEC --decision T --why T --if-wrong T [--task T<n>]
  stamp SPEC review                        write the code fingerprint into review.md and log it
  trace SPEC [--write]                     requirement -> tasks -> tests -> result; --write fills README ## Traceability
  init SPEC --key KEY                      create the spec folder with skeletons
  lint FILE [--key KEY] [--no-security]    check a standalone spec.md (a drafted prompt) against the spec rules
SPEC is a folder path (contains '/') or a slug found under any docs/specs/ folder (init: <repo>/docs/specs/<slug>).
--repo may be any folder of the repository (normalized to the git top level). task-done and verify accept
--timeout SECONDS (default 1800). JSON: `exit` is always the CLI exit code; `command_exit` is the run command's.
Writers of tickets.md (or plan.md), README.md and ledger.md hold an exclusive flock on the spec folder (no-op without fcntl).

Python API (load with importlib.util.spec_from_file_location; hooks call it; names and signatures are stable):
  find_spec(repo, ref) -> Path | None          spec folder for a path or slug; None when missing or ambiguous
  load_spec(path) -> dict                      path, slug, repo, stage, readme (frontmatter), requirements, guesses,
                                               tasks, ledger, review, ship (None when the file is missing),
                                               errors [(level, message)] from parsing
  stage(path) -> str                           README status: (default proposed)
  check(path, target=None) -> [(level, msg)]   level FAIL | WARN | OK; target defaults to the next stage
  fingerprint(repo, rev=None) -> str | None    SHA-256 over sorted (path, git blob ID) of every non-ignored file except
                                               docs/**, **/docs/specs/**, *.md, CHANGELOG*, LICENSE*; rev = a commit
                                               (None when unknown or outside git). A clean tree equals 'HEAD'.
  code_dirty(repo) -> bool                     the working tree's code differs from HEAD
  evidence_findings(path, rev=None) -> [...]   latest verify green and current; review stamp == verified code;
                                               with rev, that commit holds the verified code
  active_specs(repo) -> [Path]                 specs whose status is proposed..shipped
  specs_for_branch(repo, branch) -> [Path]     specs of ANY status whose README branch: is `branch`
  status(repo, fast=False) -> [dict]           path (repo-relative), slug, stage, next, passes (None = not evaluated),
                                               blockers [str], legacy (no key:, not evaluated); fast=True runs no gh
                                               and no contract gate, only cheap git (session-start snapshot)
  next_batches(path) -> [[task dict]]          the frontier; tasks in one batch share no file
Environment: AIDLC_GH = the gh executable for the shipped gate's CI check (tests point it at a fake).
"""
import argparse
import contextlib
import datetime
import glob as globlib
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from functools import cached_property

try:
    import fcntl
except ImportError:  # Windows: spec locking degrades to a no-op
    fcntl = None

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tdd = _load('aidlc_tdd_gate', HERE.parent / 'hooks' / 'tdd-gate.py')
_contract = _load('aidlc_check_contract', HERE / 'check-contract.py')

CODE_EXT = tuple(_tdd.CODE_EXT) + ('.feature', '.sql', '.proto', '.graphql')  # test files for traceability
TEST_PATH = _tdd.TEST_PATH
# The code fingerprint covers every non-ignored file EXCEPT these (docs, specs, changelogs, licences).
NOT_CODE = re.compile(r'^docs/|(^|/)docs/specs/|\.md$|(^|/)(CHANGELOG|LICENSE)[^/]*$', re.I)
SPEC_README = re.compile(r'(^|/)docs/specs/([^/]+)/README\.md$')
FP_MIN = 12  # a recorded fingerprint prefix shorter than this never matches
STAGES = ('proposed', 'accepted', 'planned', 'building', 'verified', 'reviewed', 'shipped', 'implemented')
ACTIVE = STAGES[:-1]
SIDE = ('partially-implemented', 'superseded', 'abandoned')
KEY = re.compile(r'^[A-Z]{2,6}$')
REQ_ID = re.compile(r'^([A-Z][A-Z0-9]*)-(\d+)$')
TASK_ID = re.compile(r'^T\d+$')
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
HEADING = re.compile(r'^(#{1,6})\s+(.*?)\s*$')
CHECKBOX = re.compile(r'^([-*+])\s+\[([ xX])\]\s+(.*)$')
FIELD = re.compile(r'^\s+[-*+]\s+([A-Za-z][\w-]*)\s*:\s*(.*)$')
REQ_FIELD = re.compile(r'^[*_]*(acceptance|verify|priority)[*_]*\s*:[*_]*\s*(.*)$', re.I)
BULLET = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(.*\S)')
DASH = r'\s*(?:—|–|--|-|:)?\s*'
VERIFY = re.compile(r'^(test|check|manual|none)\b' + DASH + r'(.*)$', re.I)
STORY = re.compile(r'^(\d+)[.)]\s+(.*\S)')
STORY_VERIFY = re.compile(r'\s*[\[(]?\bverify\s*:\s*([^\])]*?)[\])]?\s*$', re.I)
SPEC_SECTIONS = ('problem statement', 'solution', 'user stories', 'implementation decisions', 'testing decisions',
                 'out of scope')
SECURITY_DECISION = re.compile(r'^\s*(?:#{3,6}\s+|[-*+]\s+\*\*|\*\*)security\b', re.I)
TICKET_FIELD = re.compile(r'^[*_]*(blocked[ -]by|covers|status|test|files|owner|what to build|exit)[*_]*\s*:[*_]*\s*(.*)$',
                          re.I)
NOT_APPLICABLE = re.compile(r'^not-applicable\b' + DASH + r'(.*)$', re.I)
LEDGER_LINE = re.compile(r'^[-*]\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+([\w-]+)\s*(.*)$')
JUNIT = re.compile(r'\bjunit=(?:(\d+) passed, (\d+) failed|(unreadable|missing))')
KV = re.compile(r'([\w-]+)=("(?:[^"\\]|\\.)*"|\S+)')
RULING = re.compile(r'^(?:(T\d+):\s+)?(.*?)\s+—\s+why:\s+(.*?)\s+—\s+if wrong:\s+(.*)$')
ADVANCE = re.compile(r'^([\w-]+)\s*(?:→|->)\s*([\w-]+)\s*(.*)$')
PLAIN_FINDING = re.compile(r'^\s*[-*+]\s+(?!\[[ xX]\])[*_`]*([A-Z]+\d+)\b')
FINDING = re.compile(r'^([A-Z]+\d+)\b\s*(?:\(([^)]*)\))?\s*:?\s*(.*)$')
GH_STATES = ('pass', 'fail', 'pending', 'skipping', 'cancel')
TAIL_BYTES = 2048
DEFAULT_TIMEOUT = 1800


class UsageError(Exception):
    """Exit 2: bad arguments or input that is not a gate finding."""


def fail(message):
    return ('FAIL', message)


def warn(message):
    return ('WARN', message)


def failed(findings):
    return any(level == 'FAIL' for level, _ in findings)


def today():
    return datetime.date.today().isoformat()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ---------------------------------------------------------------------------------------------------- text helpers

def read_text(path, label):
    """(text, None) or (None, finding message); a missing file gives (None, None)."""
    try:
        data = pathlib.Path(path).read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as err:
        return None, f'{label}: unreadable ({err.strerror or err})'
    try:
        return data.decode('utf-8').replace('\r\n', '\n'), None
    except UnicodeDecodeError as err:
        line = data[:err.start].count(b'\n') + 1
        return None, f'{label}:{line}: not UTF-8 text'


def read_for_edit(path):
    """(text with \\n line ends, the file's own line end) so a rewrite keeps CRLF files CRLF."""
    text = path.read_bytes().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' if '\r\n' in text else '\n')


def write_atomic(path, text, newline='\n'):
    temp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp.write_bytes(text.replace('\n', newline).encode('utf-8'))
    os.replace(temp, path)


def strip_noise(text, fences=True):
    """Lines with HTML comments (and fenced code blocks) blanked; line numbers are kept."""
    text = re.sub(r'<!--.*?-->', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)
    lines, inside = text.split('\n'), False
    if not fences:
        return lines
    out = []
    for line in lines:
        if re.match(r'^\s*(```|~~~)', line):
            inside = not inside
            out.append('')
        else:
            out.append('' if inside else line)
    return out


def parse_frontmatter(text):
    """(meta, body_start_index); meta is None when the text has no closed --- block. Values drop ` # comments`."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return None, 0
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        return None, 0
    meta = {}
    for line in lines[1:end]:
        if not line.strip() or line[0] in ' \t#' or ':' not in line:
            continue
        key, _, value = line.partition(':')
        value = re.split(r'(?:^|\s)#', value, maxsplit=1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, end + 1


def set_frontmatter(path, updates):
    """Set `key: value` lines in a file's frontmatter (created when missing); inline comments are kept."""
    text, newline = read_for_edit(path)
    lines, end = text.split('\n'), None
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == '---'), None)
    if end is None:
        lines, end = ['---', '---'] + lines, 1
    for key, value in updates.items():
        for i in range(1, end):
            if re.match(rf'^{re.escape(key)}\s*:', lines[i]):
                comment = re.search(r'\s+#.*$', lines[i].partition(':')[2])
                lines[i] = f'{key}: {value}'.rstrip() + (comment.group(0) if comment else '')
                break
        else:
            lines.insert(end, f'{key}: {value}'.rstrip())
            end += 1
    write_atomic(path, '\n'.join(lines), newline)


def section_ranges(lines, start=0):
    """{lower-case level-2 heading: (heading index, end index)}."""
    found, current = {}, None
    for i in range(start, len(lines)):
        match = re.match(r'^##\s+(.+?)\s*#*\s*$', lines[i])
        if match:
            if current:
                found[current[0]] = (current[1], i)
            current = (' '.join(match.group(1).lower().split()), i)
    if current:
        found[current[0]] = (current[1], len(lines))
    return found


def id_pattern(req_id):
    """RFD-1 as an exact upper-case token, or rfd_1 / RFD_1 inside an identifier that starts with `test`
    (test_rfd_1_rejects). Never RFD-10, XRFD-1, rfd-1 in prose, or order_1 for ORDER-1."""
    prefix, number = req_id.rsplit('-', 1)
    token = rf'(?<![A-Za-z0-9_]){re.escape(prefix)}-{number}(?![0-9])'
    test_identifier = rf'(?<![A-Za-z0-9_])(?i:test[A-Za-z0-9_]*?_{re.escape(prefix)}_{number})(?![0-9])'
    return re.compile(f'{token}|{test_identifier}')


# -------------------------------------------------------------------------------------------------------- parsers

def parse_requirements(text, label):
    """Requirement candidates: headings whose first token is an ID; criteria under Acceptance:, Verify: kind."""
    reqs, findings, current, in_acceptance = [], [], None, False
    for n, line in enumerate(strip_noise(text), 1):
        heading = HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if current and level <= current['level']:
                current = None
            token = (title.split() or [''])[0]
            match = REQ_ID.match(token.rstrip(':.'))
            if match:
                current = {'id': match.group(0), 'prefix': match.group(1), 'line': n, 'level': level,
                           'title': title[len(token):].strip(' :—-'), 'criteria': [], 'verify': 'test',
                           'verify_detail': '', 'verify_line': None, 'priority': None}
                reqs.append(current)
                in_acceptance = False
            continue
        if current is None:
            continue
        field = REQ_FIELD.match(line.strip())
        if field:
            name, value = field.group(1).lower(), field.group(2).strip()
            in_acceptance = name == 'acceptance'
            if in_acceptance and value:
                current['criteria'].append(value)
            elif name == 'priority':
                current['priority'] = value
            elif name == 'verify':
                current['verify_line'] = n
                findings += _set_verify(current, value, f'{label}:{n}')
            continue
        if in_acceptance:
            bullet = BULLET.match(line)
            if bullet:
                current['criteria'].append(bullet.group(1))
            elif line.strip() and line[0] in ' \t' and current['criteria']:
                current['criteria'][-1] += ' ' + line.strip()
            elif line.strip():
                in_acceptance = False
    for req in reqs:
        del req['level']
    return reqs, findings


def _set_verify(req, value, where):
    match = VERIFY.match(value)
    if not match:
        return [fail(f'{where}: {req["id"]} Verify: {value!r} is not test, check — <command>, manual — <reason> '
                     'or none — <reason>')]
    req['verify'], req['verify_detail'] = match.group(1).lower(), match.group(2).strip()
    if req['verify'] != 'test' and not req['verify_detail']:
        return [fail(f'{where}: {req["id"]} Verify: {req["verify"]} needs "— <command, procedure or reason>"')]
    return []


def requirement_findings(reqs, key, label):
    """Gate checks on parsed requirements for README key `key` (foreign IDs fail only if they look like requirements)."""
    findings, seen = [], {}
    for req in reqs:
        looks_like = req['criteria'] or req['verify_line']
        if key and req['prefix'] != key:
            if looks_like:
                findings.append(fail(f'{label}:{req["line"]}: {req["id"]} is not {key}-<n> (README key: {key})'))
            continue
        if not key and not looks_like:
            continue
        if req['id'] in seen:
            findings.append(fail(f'{label}:{req["line"]}: duplicate requirement {req["id"]} (also line {seen[req["id"]]})'))
        seen.setdefault(req['id'], req['line'])
        if not req['criteria']:
            findings.append(fail(f'{label}:{req["line"]}: {req["id"]} has no acceptance criterion '
                                 '(bullets under "Acceptance:")'))
    if not seen:
        findings.append(fail(f'{label}: defines no requirement (a heading "### {key or "KEY"}-1: <title>")'))
    return findings


def select_requirements(reqs, key):
    chosen, seen = [], set()
    for req in reqs:
        if (req['prefix'] == key if key else (req['criteria'] or req['verify_line'])) and req['id'] not in seen:
            seen.add(req['id'])
            chosen.append(req)
    return chosen


def parse_spec(text, label, key):
    """(stories, findings) for spec.md (the spec template): every template section present and filled; each
    top-level numbered item under ## User Stories is requirement <key>-<n>. An item may end with
    `(Verify: check — <command>)`, `(Verify: manual — <reason>)` or `(Verify: none — <reason>)` (not delivered here)."""
    lines, findings = strip_noise(text), []
    ranges = section_ranges(lines)
    items, current = [], None
    start, end = ranges.get('user stories', (0, 0))
    for i in range(start + 1, end):
        line = lines[i]
        match = STORY.match(line)
        if match:
            current = {'number': int(match.group(1)), 'text': match.group(2), 'line': i + 1}
            items.append(current)
        elif current and line.strip() and line[0] in ' \t':
            current['text'] += ' ' + line.strip()
        elif line.strip():
            current = None
    stories, seen = [], {}
    for item in items:
        rid = f'{key}-{item["number"]}'
        story = {'id': rid, 'prefix': key, 'line': item['line'], 'title': item['text'], 'criteria': [item['text']],
                 'verify': 'test', 'verify_detail': '', 'verify_line': None, 'priority': None}
        tag = STORY_VERIFY.search(item['text'])
        if tag:
            story['title'] = story['criteria'][0] = item['text'][:tag.start()].rstrip()
            story['verify_line'] = item['line']
            findings += _set_verify(story, tag.group(1).strip(), f'{label}:{item["line"]}')
        if rid in seen:
            findings.append(fail(f'{label}:{item["line"]}: duplicate user story {item["number"]} (also line {seen[rid]})'))
            continue
        seen[rid] = item['line']
        stories.append(story)
    return stories, findings


def spec_findings(text, label, stories):
    """The accepted gate on spec.md: every template section present and filled, at least one story."""
    lines, findings = strip_noise(text), []
    ranges = section_ranges(lines)
    for name in SPEC_SECTIONS:
        if name not in ranges:
            findings.append(fail(f'{label}: no "## {name.title()}" section (spec template)'))
            continue
        start, end = ranges[name]
        if not any(x.strip() and not x.lstrip().startswith('#') for x in lines[start + 1:end]):
            findings.append(fail(f'{label}:{start + 1}: "## {name.title()}" is empty'))
    if 'user stories' in ranges and not stories:
        findings.append(fail(f'{label}: "## User Stories" has no numbered story ("1. As a <actor>, I want …")'))
    return findings


def spec_security(text):
    """spec.md records security decisions: a `### Security` heading or a **Security** bullet in Implementation
    Decisions."""
    lines = strip_noise(text)
    start, end = section_ranges(lines).get('implementation decisions', (0, 0))
    return any(SECURITY_DECISION.match(x) for x in lines[start + 1:end])


def parse_spec_check(text, label):
    """(guesses, findings); a guess is any checkbox line, closed ones must say resolved: or accepted risk:."""
    guesses, findings = [], []
    for n, line in enumerate(strip_noise(text), 1):
        match = CHECKBOX.match(line.strip())
        if not match:
            continue
        body = match.group(3).strip()
        gid = re.match(r'^(G\d+)\b', body)
        guess = {'id': gid.group(1) if gid else None, 'open': match.group(2) == ' ', 'text': body, 'line': n}
        if not guess['open'] and not re.search(r'\b(resolved|accepted risk)\s*:', body, re.I):
            findings.append(fail(f'{label}:{n}: closed guess {guess["id"] or "(no ID)"} says neither "resolved:" '
                                 'nor "accepted risk:"'))
        guesses.append(guess)
    return guesses, findings


def spec_check_ran(text):
    """A check is recorded by at least one guess line or a `Checked:` line (the checker found nothing)."""
    return any(CHECKBOX.match(x.strip()) or re.match(r'^\s*checked\s*:', x, re.I) for x in strip_noise(text))


def parse_plan(text, label):
    """(tasks, findings): top-level `- [ ] T<n>: title` lines with indented `- field: value` bullets."""
    tasks, findings, current = [], [], None
    for n, line in enumerate(strip_noise(text), 1):
        box = CHECKBOX.match(line)
        if box:
            body = box.group(3).strip()
            token = (body.split() or [''])[0].rstrip(':.')
            current = None
            if TASK_ID.match(token):
                current = {'id': token, 'title': body[len(token):].strip(' :.—-'), 'done': box.group(2) != ' ',
                           'line': n, 'fields': {}}
                tasks.append(current)
            elif re.match(r'^T\S*\d', token):
                findings.append(fail(f'{label}:{n}: task ID {token!r} must be T<n>'))
            continue
        if current is None:
            continue
        field = FIELD.match(line)
        if field:
            current['fields'].setdefault(field.group(1).lower(), field.group(2).strip())
        elif line.strip() and line[0] not in ' \t':
            current = None
    return [_task(task) for task in tasks], findings


def parse_tickets(text, label):
    """(tickets, findings) for tickets.md: `## T<n>: <title>` sections with `Blocked by:`, `Covers:`, `Status:`
    (ready-for-agent | done), `What to build:`, acceptance checkboxes and optional `Test:`, `Files:`, `Owner:`."""
    tickets, findings, current = [], [], None
    for n, line in enumerate(strip_noise(text), 1):
        heading = HEADING.match(line)
        if heading:
            current = None
            if len(heading.group(1)) == 2:
                title = heading.group(2)
                token = (title.split() or [''])[0].rstrip(':.')
                if TASK_ID.match(token):
                    current = {'id': token, 'title': title[len(token):].strip(' :.—-'), 'line': n, 'fields': {},
                               'criteria': [], 'status_line': None}
                    tickets.append(current)
                elif re.match(r'^T\S*\d', token):
                    findings.append(fail(f'{label}:{n}: ticket ID {token!r} must be T<n>'))
            continue
        if current is None:
            continue
        box = CHECKBOX.match(line.strip())
        if box:
            current['criteria'].append({'done': box.group(2) != ' ', 'text': box.group(3).strip(), 'line': n})
            continue
        field = TICKET_FIELD.match(line.strip())
        if field:
            name = {'blocked by': 'depends', 'blocked-by': 'depends', 'what to build': 'what'}.get(
                field.group(1).lower(), field.group(1).lower())
            current['fields'].setdefault(name, field.group(2).strip())
            if name == 'status' and current['status_line'] is None:
                current['status_line'] = n
    result = []
    for raw in tickets:
        status = raw['fields'].get('status', 'ready-for-agent').strip().lower()
        criteria = raw.pop('criteria')
        status_line = raw.pop('status_line')
        raw['done'] = status.startswith('done')
        raw['fields'].setdefault('owner', 'main')
        if not raw['fields'].get('exit'):
            raw['fields']['exit'] = '; '.join(c['text'] for c in criteria)
        what = raw['fields'].pop('what', '')
        ticket = _task(raw)
        ticket.update(criteria=criteria, status_line=status_line, what=what, ticket=True)
        result.append(ticket)
    return result, findings


def _task(raw):
    fields = raw.pop('fields')
    covers = fields.get('covers')
    none = re.match(r'^none\b' + DASH + r'(.*)$', covers or '', re.I)
    files, new = [], []
    for part in (fields.get('files') or '').split(','):
        is_new = bool(re.search(r'\(new\)\s*$', part))
        part = re.sub(r'\(new\)\s*$', '', part).strip().strip('`\'"').strip()
        if part and part.lower() != 'none':
            part = re.sub(r'^\./', '', part)
            files.append(part + '**' if part.endswith('/') else part)
            if is_new:
                new.append(files[-1])
    raw.update({'covers': [] if none or covers is None else _covers(covers),
                'covers_given': covers is not None, 'covers_none': none.group(1).strip() if none else None,
                'depends': re.findall(r'\bT\d+\b', fields.get('depends') or ''),
                'owner': fields.get('owner', ''), 'files': files, 'new_files': new,
                'exit': fields.get('exit', ''), 'test': fields.get('test', '')})
    return raw


def _covers(value):
    """Requirement IDs in a covers list; `RFD-3..RFD-6` and `RFD-3..6` are inclusive ranges."""
    ids = []
    for prefix, first, second in re.findall(r'\b([A-Z][A-Z0-9]*)-(\d+)(?:\s*(?:\.\.|–|—)\s*(?:\1-)?(\d+))?\b', value):
        last = int(second) if second else int(first)
        ids += [f'{prefix}-{n}' for n in range(int(first), max(int(first), last) + 1)]
    return list(dict.fromkeys(ids))


def parse_ledger(text, label):
    """(events, findings): one `- <UTC time> <event> …` line per event."""
    events, findings = [], []
    for n, line in enumerate(text.split('\n'), 1):
        if not re.match(r'^[-*]\s', line):
            continue
        match = LEDGER_LINE.match(line.rstrip())
        if not match:
            findings.append(fail(f'{label}:{n}: not a ledger event ("- <UTC time> <event> …")'))
            continue
        ts, kind, rest = match.groups()
        event, problem = _event(kind, rest)
        if problem:
            findings.append((problem[0], f'{label}:{n}: {problem[1]}'))
        if event is not None:
            event.update(kind=kind, ts=ts, line=n)
            events.append(event)
    return events, findings


def _kv(rest):
    data = {}
    junit = JUNIT.search(rest)
    if junit:
        data['junit'] = ({'passed': int(junit.group(1)), 'failed': int(junit.group(2))} if junit.group(1)
                         else junit.group(3))
        rest = rest[:junit.start()] + rest[junit.end():]
    for key, value in KV.findall(rest):
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value[1:-1]
        data[key.replace('-', '_')] = value
    return data


def _event(kind, rest):
    if kind == 'ruling':
        match = RULING.match(rest)
        if not match:
            return None, fail('ruling needs "<decision> — why: <why> — if wrong: <cost>"')
        return dict(zip(('task', 'decision', 'why', 'if_wrong'), match.groups())), None
    if kind == 'advance':
        match = ADVANCE.match(rest)
        if not match:
            return None, fail('advance needs "<from>→<to>"')
        data = _kv(match.group(3))
        return {'from': match.group(1), 'to': match.group(2), 'back': bool(re.match(r'back\b', match.group(3))),
                'reason': data.get('reason')}, None
    if kind not in ('task-done', 'verify', 'stamp'):
        return {'text': rest}, warn(f'unknown ledger event {kind!r}')
    head = rest.split(None, 1)
    event = {}
    if kind == 'task-done':
        if not head or not TASK_ID.match(head[0]):
            return None, fail('task-done needs a task ID')
        event['task'], rest = head[0], (head[1] if len(head) > 1 else '')
    if kind == 'stamp':
        if not head or head[0] != 'review':
            return None, fail('stamp needs "review"')
        rest = head[1] if len(head) > 1 else ''
    data = _kv(rest)
    event.update(data)
    event['fingerprint'] = str(data.get('fingerprint', '')).rstrip('…')
    if not re.match(r'^[0-9a-f]+$', event['fingerprint']):
        return None, fail(f'{kind} needs fingerprint=<hex>')
    if kind != 'stamp':
        try:
            event['exit'] = int(data.get('exit'))
        except (TypeError, ValueError):
            return None, fail(f'{kind} needs exit=<code>')
    if kind == 'verify':
        event['before'] = str(data.get('before', '')).rstrip('…')
        event.setdefault('junit', None)
        for name in ('req_pass', 'req_fail'):
            event[name] = [x for x in str(data.get(name, '')).split(',') if x]
    return event, None


def parse_review(text, label):
    meta, start = parse_frontmatter(text)
    lines = strip_noise(text)
    review = {'fingerprint': (meta or {}).get('fingerprint', '').rstrip('…'), 'reviewers': (meta or {}).get('reviewers', ''),
              'axes': {}, 'findings': [], 'qa': None, 'qa_line': None}
    problems = []
    for name, (head, end) in section_ranges(lines, start).items():
        if name not in ('spec', 'standards', 'qa'):
            continue
        review['axes'][name] = {'line': head + 1, 'empty': not any(x.strip() for x in lines[head + 1:end])}
        for i in range(head + 1, end):
            if name == 'qa':
                verdict = re.match(r'^\s*(?:[-*+]\s+)?[*_]*verdict[*_]*\s*:[*_]*\s*(.*)$', lines[i], re.I)
                if verdict and review['qa'] is None:
                    review['qa'], review['qa_line'] = verdict.group(1).strip(), i + 1
                continue
            plain = PLAIN_FINDING.match(lines[i])
            if plain:
                problems.append(fail(f'{label}:{i + 1}: {plain.group(1)} is a finding but not a checkbox '
                                     f'("- [ ] {plain.group(1)} (must): …"): an untracked finding counts as open'))
            box = CHECKBOX.match(lines[i].strip())
            if box:
                match = FINDING.match(box.group(3).strip())
                review['findings'].append({
                    'axis': name, 'id': match.group(1) if match else None, 'open': box.group(2) == ' ',
                    'severity': (match.group(2) or '').strip().lower() if match else '', 'text': box.group(3).strip(),
                    'line': i + 1})
    return review, problems


def review_findings(review, label, qa_waived=False):
    """Structure checks of review.md: both axes, a QA verdict (unless waived), every finding closed with evidence."""
    findings = []
    axes = [('spec', 'Spec'), ('standards', 'Standards')] + ([] if qa_waived else [('qa', 'QA')])
    for axis, title in axes:
        if axis not in review['axes']:
            findings.append(fail(f'{label}: no "## {title}" section'))
        elif review['axes'][axis]['empty']:
            findings.append(fail(f'{label}:{review["axes"][axis]["line"]}: ## {title} is empty '
                                 '(list findings or write "No findings.")'))
    for item in review['findings']:
        where, name = f'{label}:{item["line"]}', item['id'] or 'finding'
        if item['open']:
            findings.append(fail(f'{where}: open finding {name}: {item["text"][:100]}'))
        elif not re.search(r'\b(fixed|cleared)\s*:', item['text'], re.I):
            findings.append(fail(f'{where}: {name} is closed but says neither "fixed:" nor "cleared:"'))
        if item['severity'] not in ('must', 'should', 'nit'):
            findings.append(warn(f'{where}: {name} has no severity (must, should or nit)'))
    if not qa_waived and 'qa' in review['axes'] and not review['axes']['qa']['empty']:
        findings += _qa_findings(review, label)
    return findings


def _qa_findings(review, label):
    verdict = review['qa']
    if verdict is None:
        return [fail(f'{label}: ## QA has no "Verdict:" line (GO, CONDITIONAL GO — <conditions> or NO-GO — <reason>)')]
    where = f'{label}:{review["qa_line"]}'
    if re.match(r'^NO-GO\b', verdict, re.I):
        return [fail(f'{where}: QA verdict is NO-GO')]
    conditional = re.match(r'^CONDITIONAL GO\b' + DASH + r'(.*)$', verdict, re.I)
    if conditional:
        return [] if conditional.group(1).strip() else [fail(f'{where}: CONDITIONAL GO needs "— <conditions>"')]
    if re.match(r'^GO\b', verdict, re.I):
        return []
    return [fail(f'{where}: QA verdict {verdict!r} is not GO, CONDITIONAL GO or NO-GO')]


def parse_ship(text, label):
    meta, start = parse_frontmatter(text)
    raw, lines = strip_noise(text, fences=False), strip_noise(text)
    ship = {'decision': (meta or {}).get('decision', ''), 'version': (meta or {}).get('version', ''),
            'frontmatter': meta is not None, 'sections': {}, 'ci': None, 'ci_line': None}
    for name, (head, end) in section_ranges(lines, start).items():
        ship['sections'][name] = any(x.strip() for x in raw[head + 1:end])
        if name == 'checks':
            for i in range(head + 1, end):
                match = re.match(r'^\s*(?:[-*+]\s+)?[*_]*CI[*_]*\s*:\s*(.*)$', raw[i])
                if match and ship['ci'] is None:
                    ship['ci'], ship['ci_line'] = match.group(1).strip(), i + 1
    return ship, []


def ship_findings(ship, label):
    """Structure checks of ship.md (CI, changelog and fingerprint are checked by the gate)."""
    findings = []
    if not ship['frontmatter']:
        findings.append(fail(f'{label}:1: no frontmatter (decision: GO, version: …)'))
    if ship['decision'] != 'GO':
        findings.append(fail(f'{label}: decision is {ship["decision"] or "missing"!s}, not GO'))
    for title in ('Rollback', 'Post-release verification'):
        if not ship['sections'].get(title.lower()):
            findings.append(fail(f'{label}: "## {title}" is missing or empty'))
    return findings


def says_green(value):
    value = (value or '').lower()
    return bool(re.search(r'\b(green|pass(ed|es|ing)?)\b', value)) and \
        not re.search(r'\b(not|no|red|fail\w*|pending|cancel\w*)\b', value)


# --------------------------------------------------------------------------------------------- plan graph and globs

def _glob_regex(pattern):
    out, i = '', 0
    while i < len(pattern):
        if pattern.startswith('**/', i):
            out, i = out + '(?:.*/)?', i + 3
        elif pattern.startswith('**', i):
            out, i = out + '.*', i + 2
        else:
            out += {'*': '[^/]*', '?': '[^/]'}.get(pattern[i], re.escape(pattern[i]))
            i += 1
    return re.compile(out + r'\Z')


def overlaps(a, b):
    """Whether two plan `files` entries can name the same file (two globs: conservative, by literal prefix)."""
    if a == b or b.startswith(a.rstrip('/') + '/') or a.startswith(b.rstrip('/') + '/'):
        return True
    glob_a, glob_b = ('*' in a or '?' in a), ('*' in b or '?' in b)
    if glob_a and glob_b:
        pa, pb = re.split(r'[*?]', a, maxsplit=1)[0], re.split(r'[*?]', b, maxsplit=1)[0]
        return pa.startswith(pb) or pb.startswith(pa)
    if glob_a or glob_b:
        pattern, path = (a, b) if glob_a else (b, a)
        return bool(_glob_regex(pattern).match(path))
    return False


def _graph(tasks):
    ids = {t['id'] for t in tasks}
    graph = {}
    for task in tasks:
        graph.setdefault(task['id'], [d for d in task['depends'] if d in ids])
    return graph


def _cycles(graph):
    state, stack, found = {}, [], []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for dep in graph[node]:
            if state.get(dep) == 1:
                cycle = stack[stack.index(dep):] + [dep]
                if not any(set(cycle) == set(c) for c in found):
                    found.append(cycle)
            elif dep not in state:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in graph:
        if node not in state:
            visit(node)
    return found


def _ancestors(graph):
    result = {}
    for node in graph:
        seen, todo = set(), list(graph[node])
        while todo:
            dep = todo.pop()
            if dep not in seen:
                seen.add(dep)
                todo.extend(graph.get(dep, []))
        result[node] = seen
    return result


def plan_findings(tasks, req_ids, label):
    """The planned gate on parsed tasks; req_ids None skips the coverage checks."""
    findings, seen = [], {}
    if not tasks:
        if label.endswith('plan.md'):
            return [fail(f'{label}: defines no task ("- [ ] T1: <title>" with indented fields)')]
        return [fail(f'{label}: defines no ticket ("## T1: <title>" with Blocked by:, Covers:, criteria)')]
    for task in tasks:
        where, tid = f'{label}:{task["line"]}', task['id']
        if tid in seen:
            findings.append(fail(f'{where}: duplicate task {tid} (also line {seen[tid]})'))
        seen.setdefault(tid, task['line'])
        if not task.get('ticket'):  # legacy plan.md: every task names its owner and files
            if not task['owner']:
                findings.append(fail(f'{where}: {tid} has no owner'))
            if not task['files']:
                findings.append(fail(f'{where}: {tid} has no files'))
        if not task['covers_given']:
            findings.append(fail(f'{where}: {tid} covers nothing (add "covers: <IDs>" or "covers: none — <reason>")'))
        elif task['covers_none'] == '':
            findings.append(fail(f'{where}: {tid} "covers: none" needs a reason'))
        elif task['covers_none'] is None and not task['covers']:
            findings.append(fail(f'{where}: {tid} covers lists no requirement ID'))
        for rid in task['covers']:
            if req_ids is not None and rid not in req_ids:
                findings.append(fail(f'{where}: {tid} covers unknown requirement {rid}'))
        for dep in task['depends']:
            if dep not in seen and dep not in {t['id'] for t in tasks}:
                findings.append(fail(f'{where}: {tid} depends on unknown {dep}'))
    covered = {rid for task in tasks for rid in task['covers']}
    for rid in req_ids or []:
        if rid not in covered:
            findings.append(fail(f'{label}: requirement {rid} is not covered by any task'))
    graph = _graph(tasks)
    for cycle in _cycles(graph):
        findings.append(fail(f'{label}: dependency cycle {" → ".join(cycle)}'))
    findings += _conflicts(tasks, graph, label)
    return findings


def _conflicts(tasks, graph, label):
    findings, ancestors = [], _ancestors(graph)
    unique, seen = [], set()
    for task in tasks:  # a duplicate ID is reported elsewhere; compare its first definition only
        if task['id'] not in seen:
            seen.add(task['id'])
            unique.append(task)
    for i, first in enumerate(unique):
        for second in unique[i + 1:]:
            if first['id'] in ancestors[second['id']] or second['id'] in ancestors[first['id']]:
                continue
            shared = sorted({f'{a}' if a == b else f'{a} ~ {b}'
                             for a in first['files'] for b in second['files'] if overlaps(a, b)})
            if shared:
                findings.append(fail(f'{label}:{second["line"]}: {first["id"]} and {second["id"]} may run at the same '
                                     f'time but share {", ".join(shared)} (add a dependency or split the files)'))
    return findings


def batches(tasks):
    """Open tasks whose dependencies are done, greedily grouped so that a batch shares no file."""
    done = {t['id'] for t in tasks if t['done']}
    ready = [t for t in tasks if not t['done'] and all(d in done for d in t['depends'])]
    groups = []
    for task in ready:
        if not task['files']:  # no declared files: nothing proves it conflict-free, so it runs alone
            groups.append([task])
            continue
        for group in groups:
            if all(other['files'] for other in group) and not any(
                    overlaps(a, b) for other in group for a in other['files'] for b in task['files']):
                group.append(task)
                break
        else:
            groups.append([task])
    return groups


# ------------------------------------------------------------------------------------------------ repository and spec

def repo_root(path):
    path = pathlib.Path(path).resolve()
    probe = path
    while not probe.is_dir() and probe != probe.parent:
        probe = probe.parent
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=probe, capture_output=True, text=True,
                             timeout=30)
        if top.returncode == 0 and top.stdout.strip():
            return pathlib.Path(top.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    if path.parent.name == 'specs' and path.parent.parent.name == 'docs':
        return path.parents[2]
    return probe


def blob_id(path):
    """The git blob ID of a file (a symlink hashes its target path, as git does), or None when unreadable."""
    try:
        data = os.readlink(path).encode('utf-8', 'surrogateescape') if os.path.islink(path) else path.read_bytes()
    except OSError:
        return None
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _digest(entries):
    digest = hashlib.sha256()
    for path in sorted(entries):
        digest.update(f'{path}\0{entries[path]}\n'.encode('utf-8', 'surrogateescape'))
    return digest.hexdigest()


class Repo:
    """A repository root with cached file listing, fingerprint and test-file contents.

    fast=True (status for the session-start snapshot) skips gh and the contract gate; only cheap git runs."""

    def __init__(self, root, fast=False):
        self.root = pathlib.Path(root).resolve()
        self.fast = fast

    def git(self, *args, stdin=None):
        try:
            return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True, timeout=30,
                                  encoding='utf-8', errors='surrogateescape', input=stdin)
        except (OSError, subprocess.SubprocessError):
            return None

    def _z(self, *args):
        """NUL-separated git output as a list, or None when git fails."""
        result = self.git(*args)
        if result is None or result.returncode != 0:
            return None
        return [x for x in result.stdout.split('\0') if x]

    @cached_property
    def is_git(self):
        result = self.git('rev-parse', '--is-inside-work-tree')
        return result is not None and result.returncode == 0 and result.stdout.strip() == 'true'

    def rel(self, path):
        try:
            return pathlib.Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    @cached_property
    def files(self):
        """Every tracked or untracked, not ignored file (repo-relative); a folder walk outside git."""
        listing = self._z('ls-files', '-z', '--cached', '--others', '--exclude-standard') if self.is_git else None
        if listing is not None:
            return sorted(set(listing))
        found = []
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not _tdd.SKIP_DIRS.search(d + '/'))
            found += [self.rel(os.path.join(folder, name)) for name in names]
        return sorted(found)

    # -- code fingerprint: sha256 over sorted (path, git blob ID) of every file not matched by NOT_CODE ------------
    def _hash_paths(self, paths):
        """{path: blob ID} for files whose content git has not recorded (modified or untracked)."""
        ids, batch = {}, [p for p in paths if '\n' not in p]
        result = self.git('hash-object', '--stdin-paths', stdin=''.join(f'{p}\n' for p in batch)) if batch else None
        hashed = result.stdout.split() if result is not None and result.returncode == 0 else []
        if len(hashed) == len(batch):
            ids.update(zip(batch, hashed))
        for path in paths:
            if path not in ids:
                ids[path] = blob_id(self.root / path)
        return {p: v for p, v in ids.items() if v}

    def _working_entries(self):
        if not self.is_git:
            return {rel: blob_id(self.root / rel) for rel in self.files if not NOT_CODE.search(rel)}
        staged = self._z('ls-files', '-s', '-z') or []
        entries, todo = {}, set()
        for line in staged:
            meta, _, path = line.partition('\t')
            mode, sha, stage = (meta.split() + ['', '', ''])[:3]
            if NOT_CODE.search(path):
                continue
            entries[path] = sha
            if stage != '0':  # merge conflict: hash what is on disk
                todo.add(path)
        changed = (self._z('ls-files', '-m', '-z') or []) + (self._z('ls-files', '-o', '--exclude-standard', '-z') or [])
        todo |= {p for p in changed if not NOT_CODE.search(p)}
        for path in todo:
            target = self.root / path
            if os.path.isdir(target) and not os.path.islink(target):
                continue  # a submodule keeps its recorded commit
            entries.pop(path, None)  # deleted files leave the fingerprint
        present = sorted(p for p in todo if os.path.lexists(self.root / p) and not
                         (os.path.isdir(self.root / p) and not os.path.islink(self.root / p)))
        entries.update(self._hash_paths(present))
        return entries

    @cached_property
    def fingerprint(self):
        return _digest(self._working_entries())

    def fingerprint_at(self, rev):
        """Fingerprint of a commit (same exclusions); None outside git or for an unknown revision."""
        if not self.is_git or not rev or str(rev).startswith('-'):
            return None
        resolved = self.git('rev-parse', '--verify', '--quiet', f'{rev}^{{commit}}')
        if resolved is None or resolved.returncode != 0:
            return None
        tree = self._z('ls-tree', '-r', '-z', '--full-tree', resolved.stdout.strip())
        if tree is None:
            return None
        entries = {}
        for line in tree:
            meta, _, path = line.partition('\t')
            if not NOT_CODE.search(path):
                entries[path] = meta.split()[2]
        return _digest(entries)

    @cached_property
    def code_dirty(self):
        """Whether the working tree's code differs from HEAD (staged, unstaged or untracked)."""
        if not self.is_git:
            return False
        head = self.fingerprint_at('HEAD')
        return self.fingerprint != head if head is not None else bool(self._working_entries())

    # -- tests and specs ---------------------------------------------------------------------------------------
    @cached_property
    def test_texts(self):
        texts = {}
        for rel in self.files:
            if rel.endswith(CODE_EXT) and (TEST_PATH.search(rel) or rel.endswith('.feature')) \
                    and not re.search(r'(^|/)docs/specs/', rel):
                try:
                    texts[rel] = (self.root / rel).read_text(encoding='utf-8', errors='replace')
                except OSError:
                    pass
        return texts

    def tests_referencing(self, req_id):
        pattern = id_pattern(req_id)
        return [rel for rel, text in self.test_texts.items() if pattern.search(text)]

    def branch(self):
        result = self.git('symbolic-ref', '--quiet', '--short', 'HEAD')
        return result.stdout.strip() if result is not None and result.returncode == 0 else None

    def default_branches(self):
        origin = self.git('symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD')
        if origin is not None and origin.returncode == 0 and origin.stdout.strip():
            return {origin.stdout.strip().split('/', 1)[-1]}
        configured = self.git('config', 'init.defaultBranch')
        extra = {configured.stdout.strip()} if configured is not None and configured.stdout.strip() else set()
        return {'main', 'master'} | extra

    @cached_property
    def spec_dirs_cached(self):
        dirs = {(self.root / rel).parent for rel in self.files if SPEC_README.search(rel)}
        return sorted((d for d in dirs if (d / 'README.md').is_file()), key=lambda d: self.rel(d))

    def spec_dirs(self):
        """Spec folders (with a README.md) under any `docs/specs/` in the repository, ignored files excluded."""
        return list(self.spec_dirs_cached)


class Spec:
    """One spec folder; every artifact is parsed once, on first use."""

    def __init__(self, path, repo=None):
        self.dir = pathlib.Path(path).resolve()
        self.repo = repo if repo is not None else Repo(repo_root(self.dir))
        self.slug = self.dir.name

    def label(self, name):
        return self.repo.rel(self.dir / name)

    def _parse(self, name, parser):
        """(data, findings); data is None when the file is missing or unreadable."""
        text, error = read_text(self.dir / name, self.label(name))
        if text is None:
            return None, [fail(error)] if error else []
        try:
            return parser(text, self.label(name))
        except Exception as err:  # a parser bug must surface as a finding, never as a traceback
            return None, [fail(f'{self.label(name)}: cannot be parsed ({err.__class__.__name__}: {err})')]

    def missing(self, name):
        return [] if (self.dir / name).is_file() else [fail(f'{self.label(name)}: missing')]

    @cached_property
    def readme(self):
        label = self.label('README.md')
        text, error = read_text(self.dir / 'README.md', label)
        if text is None:
            return {}, '', [fail(error or f'{label}: missing')]
        meta, _ = parse_frontmatter(text)
        if meta is None:
            return {}, text, [fail(f'{label}:1: no frontmatter (--- block with status:, key:, …)')]
        status = meta.get('status') or 'proposed'
        if status not in STAGES + SIDE:
            return meta, text, [fail(f'{label}: status: {status} is not an AIDLC stage')]
        return meta, text, []

    @property
    def meta(self):
        return self.readme[0]

    @property
    def stage(self):
        return self.meta.get('status') or 'proposed'

    @property
    def key(self):
        key = self.meta.get('key', '')
        return key if KEY.match(key) else ''

    @property
    def legacy_spec(self):
        """requirements.md (+ spec-check.md, security.md) instead of spec.md: specs written before 3.3.0."""
        return not (self.dir / 'spec.md').is_file() and (self.dir / 'requirements.md').is_file()

    @property
    def spec_name(self):
        return 'requirements.md' if self.legacy_spec else 'spec.md'

    @property
    def plan_name(self):
        if (self.dir / 'tickets.md').is_file():
            return 'tickets.md'
        return 'plan.md' if (self.dir / 'plan.md').is_file() or self.legacy_spec else 'tickets.md'

    @cached_property
    def parsed_requirements(self):
        if self.legacy_spec:
            return self._parse('requirements.md', parse_requirements)
        return self._parse('spec.md', lambda text, label: parse_spec(text, label, self.key or 'KEY'))

    @cached_property
    def requirements(self):
        """(requirements of this spec's key or None, parse findings + requirement_findings)."""
        reqs, findings = self.parsed_requirements
        if reqs is None:
            return None, findings or self.missing(self.spec_name)
        if not self.legacy_spec:
            text, _ = read_text(self.dir / 'spec.md', self.label('spec.md'))
            return reqs, findings + spec_findings(text or '', self.label('spec.md'), reqs)
        return (select_requirements(reqs, self.key),
                findings + requirement_findings(reqs, self.key, self.label('requirements.md')))

    @cached_property
    def guesses(self):
        return self._parse('spec-check.md', parse_spec_check)

    @cached_property
    def tasks(self):
        return self._parse(self.plan_name, parse_tickets if self.plan_name == 'tickets.md' else parse_plan)

    @cached_property
    def ledger(self):
        events, findings = self._parse('ledger.md', parse_ledger)
        return events or [], findings

    @cached_property
    def review(self):
        return self._parse('review.md', parse_review)

    @cached_property
    def ship(self):
        return self._parse('ship.md', parse_ship)

    def last(self, kind):
        return next((e for e in reversed(self.ledger[0]) if e['kind'] == kind), None)


def fp_matches(recorded, current):
    """A recorded fingerprint (or a prefix of at least FP_MIN hex characters) matches the current one."""
    return bool(recorded and current) and len(recorded) >= FP_MIN and current.startswith(recorded)


def short(fp):
    return (fp or '')[:12] or 'none'


# ----------------------------------------------------------------------------------------------------------- gates

def gate_accepted(spec):
    readme, findings = spec.label('README.md'), []
    key = spec.meta.get('key', '')
    if not KEY.match(key):
        findings.append(fail(f'{readme}: key: {key!r} must be 2-6 capital letters (prefix of every requirement ID)'))
    else:
        for other in spec.repo.spec_dirs():
            if other != spec.dir and Spec(other, spec.repo).meta.get('key') == key:
                findings.append(fail(f'{readme}: key {key} is also used by {spec.repo.rel(other)}'))
    findings += spec.requirements[1]
    guesses, problems = spec.guesses
    if guesses is not None or problems or spec.legacy_spec:  # spec.md: the blind check is optional
        findings += problems if guesses is not None or problems else spec.missing('spec-check.md')
    text, _ = read_text(spec.dir / 'spec-check.md', spec.label('spec-check.md'))
    if text is not None and not spec_check_ran(text):
        findings.append(fail(f'{spec.label("spec-check.md")}: the blind spec check has not run '
                             '(no guess lines and no "Checked:" line)'))
    for guess in guesses or []:
        if guess['open']:
            findings.append(fail(f'{spec.label("spec-check.md")}:{guess["line"]}: open guess {guess["id"] or ""}: '
                                 f'{guess["text"][:100]}'))
    findings += _security(spec)
    if spec.repo.fast:
        return findings + [warn('contract gate not run (fast status)')] + _accepted_by(spec)
    try:
        for level, message in _contract.run(spec.dir, repo_arg=spec.repo.root):
            if level != 'OK':
                findings.append((level, 'contract gate: ' + message.replace(str(spec.dir), spec.repo.rel(spec.dir))))
    except Exception as err:
        findings.append(fail(f'contract gate could not run ({err.__class__.__name__}: {err})'))
    return findings + _accepted_by(spec)


def _accepted_by(spec):
    accepted_by = spec.meta.get('accepted_by', '')
    if not accepted_by or re.search(r'<[^>]*>', accepted_by):
        return [fail(f'{spec.label("README.md")}: accepted_by: is not set (record who approved the spec, and when)')]
    return []


def _security(spec):
    value = spec.meta.get('security', '')
    waiver = NOT_APPLICABLE.match(value)
    if waiver:
        return [] if waiver.group(1).strip() else [
            fail(f'{spec.label("README.md")}: security: not-applicable needs "— <reason>"')]
    if not spec.legacy_spec:
        text, _ = read_text(spec.dir / 'spec.md', spec.label('spec.md'))
        if text is not None and spec_security(text):
            return []
        if not (spec.dir / 'security.md').is_file():
            return [fail(f'{spec.label("spec.md")}: Implementation Decisions has no security decisions (a "### Security" '
                         'heading or a "**Security**" bullet: assets, threats, controls), or set README '
                         'security: not-applicable — <reason>')]
    text, error = read_text(spec.dir / 'security.md', spec.label('security.md'))
    if text is None:
        return [fail(error or f'{spec.label("security.md")}: missing (or set security: not-applicable — <reason>)')]
    return [] if text.strip() else [fail(f'{spec.label("security.md")}: empty')]


def gate_planned(spec):
    reqs, findings = spec.requirements
    tasks, problems = spec.tasks
    findings = findings + problems
    if tasks is None:
        return findings + (spec.missing(spec.plan_name) if not problems else [])
    ids = [r['id'] for r in reqs if r['verify'] != 'none'] if reqs is not None else None
    return findings + plan_findings(tasks, ids, spec.label(spec.plan_name))


def gate_building(spec):
    findings, branch = [], spec.repo.branch()
    if not branch:
        findings.append(fail('not on a branch (detached HEAD or no git repository): check out a feature branch'))
    elif branch in spec.repo.default_branches():
        findings.append(fail(f'current branch {branch} is the default branch: create a feature branch'))
    recorded = spec.meta.get('branch', '')
    if recorded and branch and recorded != branch:
        findings.append(fail(f'{spec.label("README.md")}: branch: {recorded} but the current branch is {branch}'))
    return findings


def gate_verified(spec):
    findings = [f for f in gate_planned(spec) if f[0] != 'OK']
    tasks = spec.tasks[0] or []
    events, problems = spec.ledger
    findings += problems
    green = {e['task'] for e in events if e['kind'] == 'task-done' and e.get('exit') == 0}
    for task in tasks:
        where = f'{spec.label(spec.plan_name)}:{task["line"]}'
        if not task['done']:
            findings.append(fail(f'{where}: {task["id"]} is not done (aidlc task-done)'))
        elif task['id'] not in green:
            findings.append(fail(f'{where}: {task["id"]} is ticked but has no green task-done event in ledger.md'))
        findings += _open_criteria(spec, task)
    for req in spec.requirements[0] or []:
        if req['verify'] == 'test' and not spec.repo.tests_referencing(req['id']):
            findings.append(fail(f'{spec.label(spec.spec_name)}:{req["line"]}: {req["id"]} (Verify: test) is not '
                                 'referenced by any test file'))
    return findings + _verify_findings(spec)


def _open_criteria(spec, task):
    return [fail(f'{spec.label(spec.plan_name)}:{c["line"]}: {task["id"]} acceptance criterion not ticked: '
                 f'{c["text"][:80]}') for c in task.get('criteria', []) if not c['done']]


def _verify_findings(spec):
    """The latest verify is green and is the current code."""
    event = spec.last('verify')
    if event is None:
        return [fail(f'{spec.label("ledger.md")}: no verify event (run aidlc verify SPEC --cmd <tests>)')]
    where, findings = f'{spec.label("ledger.md")}:{event["line"]}', []
    if event['exit'] != 0:
        findings.append(fail(f'{where}: the latest verify exited {event["exit"]}'))
    if event.get('before') and event['before'] != event['fingerprint']:
        findings.append(fail(f'{where}: the test command changed code during the latest verify: re-run it'))
    if not fp_matches(event['fingerprint'], spec.repo.fingerprint):
        findings.append(fail(f'{where}: code changed since the latest verify (fingerprint {short(event["fingerprint"])} '
                             f'≠ current {short(spec.repo.fingerprint)}): run aidlc verify again'))
    if event['junit'] in ('unreadable', 'missing'):
        findings.append(fail(f'{where}: the latest verify has {event["junit"]} JUnit results: fix --junit and re-run'))
    elif event['req_fail']:
        findings.append(fail(f'{where}: requirement tests failed: {", ".join(event["req_fail"])}'))
    return findings + _junit_coverage(spec, event, where)


def _junit_coverage(spec, event, where):
    tested = [r['id'] for r in spec.requirements[0] or [] if r['verify'] == 'test']
    if not tested:
        return []
    if not isinstance(event['junit'], dict):
        return [warn(f'{where}: traceability is static (test files reference the IDs; no JUnit results were '
                     'recorded: aidlc verify --junit <glob>)')]
    return [fail(f'{where}: {rid} has no passing test in the JUnit results of the latest verify (skipped or absent)')
            for rid in tested if rid not in event['req_pass'] and rid not in event['req_fail']]


def _evidence(spec, rev=None):
    """One evidence chain: the latest verify is green and current, the review stamp is that same code, and, with
    rev, the commit holds that code."""
    findings = _verify_findings(spec)
    event, review = spec.last('verify'), spec.review[0]
    verified = event['fingerprint'] if event else ''
    stamp = review['fingerprint'] if review else ''
    if event and not fp_matches(stamp, verified):
        findings.append(fail(f'{spec.label("review.md")}: the review stamp ({short(stamp)}) is not the verified code '
                             f'({short(verified)}): re-verify, review the change, re-stamp'))
    if rev is not None:
        at = spec.repo.fingerprint_at(rev)
        if at is None:
            findings.append(fail(f'{rev}: not a commit of {spec.repo.root.name}'))
        elif event and not fp_matches(verified, at):
            findings.append(fail(f'{rev} does not contain the verified code (fingerprint {short(at)} ≠ verify '
                                 f'{short(verified)})'))
    return findings


def _clean_code(spec):
    if spec.repo.code_dirty:
        return [fail('uncommitted code: the pre-PR record and the PR are for commits; commit the code '
                     '(the fingerprint ignores docs and specs), then re-run')]
    return []


def gate_reviewed(spec):
    review, findings = spec.review
    label = spec.label('review.md')
    if review is None:
        return findings or spec.missing('review.md')
    qa = spec.meta.get('qa', '')
    waiver = NOT_APPLICABLE.match(qa)
    if waiver and not waiver.group(1).strip():
        findings.append(fail(f'{spec.label("README.md")}: qa: not-applicable needs "— <reason>"'))
    findings += review_findings(review, label, qa_waived=bool(waiver))
    current = spec.repo.fingerprint
    if not review['fingerprint']:
        findings.append(fail(f'{label}: no fingerprint: (run aidlc stamp SPEC review)'))
    elif not fp_matches(review['fingerprint'], current):
        findings.append(fail(f'{label}: code changed since the review was stamped (fingerprint '
                             f'{short(review["fingerprint"])} ≠ current {short(current)}): review the change, re-stamp'))
    return findings + _evidence(spec) + _clean_code(spec)


def _stage_at_least(spec, stage):
    current = spec.stage
    if current in STAGES and STAGES.index(current) >= STAGES.index(stage):
        return []
    return [fail(f'{spec.label("README.md")}: stage is {current}; this gate needs stage {stage}')]


def gate_shipped(spec):
    findings = _stage_at_least(spec, 'reviewed')
    ship, problems = spec.ship
    findings += problems
    if ship is None:
        return findings + (spec.missing('ship.md') if not problems else [])
    label = spec.label('ship.md')
    findings += ship_findings(ship, label) + _ci_findings(spec, ship, label) + _changelog(spec, ship, label)
    review = spec.review[0]
    if review is None or not fp_matches(review['fingerprint'], spec.repo.fingerprint):
        findings.append(fail(f'code changed since the review (fingerprint {short(spec.repo.fingerprint)} ≠ '
                             f'{spec.label("review.md")} {short(review and review["fingerprint"])})'))
    return findings + _evidence(spec) + _clean_code(spec)


def gh_checks(root, branch):
    """[(name, state)] from `gh pr checks <branch>`, or None when gh is missing, errors or reports nothing."""
    exe = os.environ['AIDLC_GH'] if 'AIDLC_GH' in os.environ else shutil.which('gh')
    if not exe or not branch or branch.startswith('-') or not os.access(exe, os.X_OK):
        return None
    try:  # `--` ends gh's flags, so a branch name can never be read as an option
        result = subprocess.run([exe, 'pr', 'checks', '--', branch], cwd=root, capture_output=True, text=True,
                                timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in result.stdout.splitlines():
        cols = line.split('\t')
        if len(cols) >= 2 and cols[1].strip().lower() in GH_STATES:
            rows.append((cols[0].strip(), cols[1].strip().lower()))
    return rows or None


def _ci_findings(spec, ship, label):
    branch = spec.meta.get('branch') or spec.repo.branch()
    checks = None if spec.repo.fast else gh_checks(spec.repo.root, branch)
    if checks is not None:
        bad = [f'{name} ({state})' for name, state in checks if state not in ('pass', 'skipping')]
        return [fail(f'CI is not green (gh pr checks {branch}): {", ".join(bad[:8])}')] if bad else []
    if ship['ci'] is None:
        return [fail(f'{label}: no "CI:" line in ## Checks (and no PR checks from gh)')]
    if not says_green(ship['ci']):
        return [fail(f'{label}:{ship["ci_line"]}: CI is not green: {ship["ci"]}')]
    return []


def _changelog(spec, ship, label):
    version = ship['version']
    if not version or NOT_APPLICABLE.match(version) or re.match(r'^n/?a\b', version, re.I):
        return []
    service = spec.dir.parents[2] if spec.dir.parent.name == 'specs' else spec.repo.root
    changelog = next((p for p in (service / 'CHANGELOG.md', spec.repo.root / 'CHANGELOG.md') if p.is_file()), None)
    if changelog is None:
        return []
    text, error = read_text(changelog, spec.repo.rel(changelog))
    if text is None:
        return [fail(error)]
    if re.search(rf'(?<![\w.-]){re.escape(version)}(?![\w.-]*\w)', text):
        return []
    return [fail(f'{spec.repo.rel(changelog)} does not mention version {version} ({label})')]


def gate_implemented(spec):
    findings = _stage_at_least(spec, 'shipped')
    lines = strip_noise(spec.readme[1])
    section = section_ranges(lines).get('traceability')
    if not section or not any(re.match(r'^\s*\|.*\|\s*$', x) for x in lines[section[0] + 1:section[1]]):
        findings.append(fail(f'{spec.label("README.md")}: no ## Traceability table (run aidlc trace SPEC --write)'))
    return findings


GATES = {
    'accepted': gate_accepted,
    'planned': gate_planned,
    'building': gate_building,
    'verified': gate_verified,
    'reviewed': gate_reviewed,
    'shipped': gate_shipped,
    'implemented': gate_implemented,
    'partially-implemented': gate_implemented,
}


def next_stage(current):
    if current in STAGES[:-1]:
        return STAGES[STAGES.index(current) + 1]
    return None


def _check(spec, target=None):
    findings = list(spec.readme[2])
    target = target or next_stage(spec.stage)
    label = spec.repo.rel(spec.dir)
    if target is None:
        return findings + [('OK', f'{label}: {spec.stage} has no next stage')]
    if target not in GATES:
        return findings + [fail(f'no gate for stage {target!r} (gates: {", ".join(GATES)})')]
    try:
        findings += GATES[target](spec)
    except Exception as err:  # a gate bug must be a finding, never a traceback
        findings.append(fail(f'{label}: gate {target} could not run ({err.__class__.__name__}: {err})'))
    if not failed(findings):
        findings.append(('OK', f'{label}: gate {target} passes'))
    return findings


# ------------------------------------------------------------------------------------------------------ public API

def find_spec(repo, ref):
    path, _ = resolve_spec(repo, ref)
    return path


def resolve_spec(repo, ref):
    """(path, None) or (None, error): a path when ref contains '/', else a slug under any docs/specs/ folder."""
    repo = pathlib.Path(repo).resolve()
    ref = str(ref)
    if '/' in ref or os.sep in ref:
        for candidate in (pathlib.Path(ref), repo / ref):
            if candidate.is_dir():
                return candidate.resolve(), None
        return None, f'{ref} is not a folder'
    matches = [d for d in Repo(repo).spec_dirs() if d.name == ref]
    if len(matches) > 1:
        return None, f'{ref} is ambiguous: {", ".join(Repo(repo).rel(m) for m in matches)} (pass the path)'
    if not matches:
        return None, f'no spec named {ref} under a docs/specs/ folder in {repo}'
    return matches[0], None


def load_spec(path):
    """Every artifact parsed; `errors` holds parse problems only (gate checks are check()'s job)."""
    spec = Spec(path)
    artifacts, errors = {}, list(spec.readme[2])
    for name in ('parsed_requirements', 'guesses', 'tasks', 'ledger', 'review', 'ship'):
        data, findings = getattr(spec, name)
        artifacts[name] = data
        errors += findings
    reqs = artifacts.pop('parsed_requirements')
    return {'path': str(spec.dir), 'slug': spec.slug, 'repo': str(spec.repo.root), 'stage': spec.stage,
            'readme': spec.meta, 'requirements': None if reqs is None else select_requirements(reqs, spec.key),
            'errors': errors, **artifacts}


def stage(path):
    return Spec(path).stage


def check(path, target=None):
    return _check(Spec(path), target)


def fingerprint(repo, rev=None):
    return Repo(repo).fingerprint if rev is None else Repo(repo).fingerprint_at(rev)


def code_dirty(repo):
    return Repo(repo).code_dirty


def evidence_findings(path, rev=None):
    return _evidence(Spec(path), rev)


def active_specs(repo):
    root = Repo(repo)
    return [d for d in root.spec_dirs() if Spec(d, root).stage in ACTIVE]


def specs_for_branch(repo, branch):
    root = Repo(repo)
    return [d for d in root.spec_dirs() if branch and Spec(d, root).meta.get('branch') == branch]


def status(repo, fast=False):
    root, items = Repo(repo, fast=fast), []
    for folder in root.spec_dirs():
        spec = Spec(folder, root)
        nxt = next_stage(spec.stage)
        legacy = 'key' not in spec.meta
        item = {'path': root.rel(folder), 'slug': spec.slug, 'stage': spec.stage, 'next': nxt, 'passes': None,
                'blockers': [], 'legacy': legacy}
        if nxt and not legacy:
            findings = _check(spec, nxt)
            item['passes'] = not failed(findings)
            item['blockers'] = [m for level, m in findings if level == 'FAIL']
        items.append(item)
    return items


def next_batches(path):
    tasks, _ = Spec(path).tasks
    return batches(tasks) if tasks else []


# -------------------------------------------------------------------------------------------- commands (CLI only)

@contextlib.contextmanager
def spec_lock(folder):
    """Exclusive lock on a spec folder for read-modify-write of plan.md, README.md and ledger.md.

    flock on the folder itself (no lock file to commit); a no-op where fcntl is missing (Windows)."""
    handle = None
    if fcntl is not None:
        try:
            handle = os.open(str(folder), os.O_RDONLY)
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError:
            if handle is not None:
                os.close(handle)
            handle = None
    try:
        yield
    finally:
        if handle is not None:
            fcntl.flock(handle, fcntl.LOCK_UN)
            os.close(handle)


def append_ledger(spec, event):
    """Append one event (the caller holds spec_lock); keeps the file's line ends."""
    path = spec.dir / 'ledger.md'
    if not path.exists():
        path.write_text(LEDGER_SKELETON.format(slug=spec.slug), encoding='utf-8')
    text, newline = read_for_edit(path)
    prefix = '' if text.endswith('\n') or not text else newline
    with open(path, 'ab') as handle:
        handle.write(f'{prefix}- {utc_now()} {event}{newline}'.encode('utf-8'))
    return event


def quoted(text):
    return json.dumps(' '.join(str(text).split()), ensure_ascii=False)


def run_command(cmd, cwd, timeout):
    """(exit code, last ~2KB of combined output); 124 on timeout. Nothing is streamed."""
    timed_out = False
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.Popen(cmd, shell=True, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=os.name == 'posix')
        except OSError as err:
            return 127, str(err)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out, code = True, 124
            _kill_tree(proc)
        size = out.seek(0, 2)
        out.seek(max(0, size - TAIL_BYTES))
        tail = out.read().decode('utf-8', 'replace')
    return code, tail + (f'\n[aidlc: timed out after {timeout}s]' if timed_out else '')


def _kill_tree(proc):
    """Kill the shell and its children (process group on POSIX; the shell alone elsewhere)."""
    killpg, sigkill = getattr(os, 'killpg', None), getattr(signal, 'SIGKILL', None)
    try:
        if killpg and sigkill:
            killpg(proc.pid, sigkill)
        else:
            proc.kill()
    except OSError:
        proc.kill()
    proc.wait()


def parse_junit(paths, req_ids, repo):
    """(summary, findings): summary {passed, failed, req_pass, req_fail, unreadable}."""
    patterns = {rid: id_pattern(rid) for rid in req_ids}
    summary = {'passed': 0, 'failed': 0, 'cases': 0, 'req_pass': set(), 'req_fail': set(), 'unreadable': False}
    findings = []
    for path in paths:
        try:
            root = ET.parse(str(path)).getroot()
        except ET.ParseError as err:
            summary['unreadable'] = True
            findings.append(fail(f'{repo.rel(path)}:{err.position[0]}: JUnit XML does not parse ({err})'))
            continue
        except OSError as err:
            summary['unreadable'] = True
            findings.append(fail(f'{repo.rel(path)}: unreadable ({err.strerror or err})'))
            continue
        for case in root.iter('testcase'):
            summary['cases'] += 1
            bad = case.find('failure') is not None or case.find('error') is not None
            skipped = case.find('skipped') is not None
            summary['failed' if bad else 'passed'] += 0 if skipped and not bad else 1
            name = f'{case.get("classname", "")} {case.get("name", "")}'
            for rid, pattern in patterns.items():
                if pattern.search(name) and not (skipped and not bad):
                    summary['req_fail' if bad else 'req_pass'].add(rid)
    summary['req_pass'] = sorted(summary['req_pass'] - summary['req_fail'])
    summary['req_fail'] = sorted(summary['req_fail'])
    return summary, findings


def cmd_status(args):
    root = repo_arg(args)
    items = status(root, fast=args.fast)
    lines = []
    for item in items:
        state = {True: 'PASS', False: 'BLOCKED', None: ''}[item['passes']]
        lines.append(f'{item["path"]}  {item["stage"]} → {item["next"] or "-"}  {state}'
                     + ('  (legacy: no key)' if item['legacy'] else ''))
        lines += [f'    {b}' for b in item['blockers'][:3]]
    return 0, {'repo': str(root), 'specs': items}, lines or ['no specs under docs/specs/ or */docs/specs/']


def cmd_check(args):
    spec = spec_arg(args)
    findings = _check(spec, args.to)
    return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'stage': spec.stage,
                                     'target': args.to or next_stage(spec.stage)})


def cmd_advance(args):
    spec = spec_arg(args)
    with spec_lock(spec.dir):
        return _advance(spec, args.stage, args)


def _advance(spec, target, args):
    current = spec.stage
    payload = {'spec': spec.repo.rel(spec.dir), 'from': current, 'to': target, 'advanced': False}
    if args.back:
        return _move_back(spec, current, target, args.reason, payload)
    if target == 'abandoned' and not args.reason:
        raise UsageError('abandoned needs --reason')
    if target in ('abandoned', 'superseded'):
        if current not in ACTIVE:
            raise UsageError(f'{target} applies to an active spec; this one is {current}')
        findings = [] if target == 'abandoned' or spec.meta.get('superseded_by') else [
            fail(f'{spec.label("README.md")}: superseded needs superseded_by: <slug>')]
    else:
        expected = 'shipped' if target == 'partially-implemented' else (
            STAGES[STAGES.index(target) - 1] if target in STAGES[1:] else None)
        if expected != current:
            raise UsageError(f'{current} cannot advance to {target} (next: {next_stage(current) or "none"}; '
                             'use --back --reason to move backwards)')
        findings = [] if spec.key else [fail(f'{spec.label("README.md")}: no valid key: — add "key: <2-6 capitals>" '
                                             '(unique per repository) before advancing')]
        findings += _check(spec, target)
    if failed(findings):
        return finding_result(findings, payload)
    if target == 'reviewed':
        findings += _record_pre_pr(spec)
        if failed(findings):
            return finding_result(findings, payload)
    updates = {'status': target, 'updated': today()}
    if target == 'building':
        updates['branch'] = spec.repo.branch()
    set_frontmatter(spec.dir / 'README.md', updates)
    reason = f' reason={quoted(args.reason)}' if args.reason else ''
    payload.update(advanced=True, ledger=append_ledger(spec, f'advance {current}→{target}{reason}'))
    return finding_result(findings + [('OK', f'{payload["spec"]}: {current} → {target}')], payload)


def _move_back(spec, current, target, reason, payload):
    if not reason:
        raise UsageError('--back needs --reason')
    if current not in STAGES or target not in STAGES or STAGES.index(target) >= STAGES.index(current):
        raise UsageError(f'--back moves to an earlier stage than {current}')
    updates = {'status': target, 'updated': today()}
    if target == 'proposed':
        updates['accepted_by'] = ''  # a spec sent back to proposed needs a fresh approval
    set_frontmatter(spec.dir / 'README.md', updates)
    payload.update(advanced=True, ledger=append_ledger(spec, f'advance {current}→{target} back reason={quoted(reason)}'))
    return 0, payload, [f'OK {payload["spec"]}: {current} → {target} (back)']


def _record_pre_pr(spec):
    top, head = spec.repo.git('rev-parse', '--show-toplevel'), spec.repo.git('rev-parse', 'HEAD')
    if top is None or head is None or top.returncode or head.returncode:
        return [fail('no commit at HEAD: cannot record the pre-PR review')]
    review = spec.review[0] or {}
    marker = _load('aidlc_mark_pr_review', HERE / 'mark-pr-review.py')
    marker.record(top.stdout.strip(), head.stdout.strip(), f'aidlc ({review.get("reviewers") or "review.md"})', 0,
                  f'aidlc advance reviewed: {spec.repo.rel(spec.dir)} fingerprint={short(spec.repo.fingerprint)}')
    return [('OK', f'pre-PR review recorded for HEAD {head.stdout.strip()[:12]}')]


def cmd_next(args):
    spec = spec_arg(args)
    tasks, findings = spec.tasks
    if not tasks or failed(findings):
        findings = findings or (spec.missing(spec.plan_name) if tasks is None
                                else plan_findings([], None, spec.label(spec.plan_name)))
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'batches': []})
    groups = batches(tasks)
    lines = [f'batch {i}: ' + ', '.join(f'{t["id"]} ({t["owner"] or "no owner"}: {", ".join(t["files"]) or "files not declared, runs alone"})' for t in g)
             for i, g in enumerate(groups, 1)]
    if not groups:
        lines = ['all tasks are done'] if all(t['done'] for t in tasks) else ['no task is ready (open dependencies)']
    return 0, {'spec': spec.repo.rel(spec.dir), 'batches': groups}, lines


def cmd_task_done(args):
    spec = spec_arg(args)
    tasks, problems = spec.tasks
    task = next((t for t in tasks or [] if t['id'] == args.task), None)
    if task is None:
        raise UsageError(f'{args.task} is not a task in {spec.label(spec.plan_name)}')
    unticked = _open_criteria(spec, task)
    if unticked:  # the implementer ticks each criterion once a test shows it; done means all of them
        return finding_result(unticked, {'spec': spec.repo.rel(spec.dir), 'task': task['id'], 'command_exit': None,
                                         'ticked': False, 'output_tail': ''})
    cmd = args.cmd or task['test']
    if not cmd:
        raise UsageError(f'{args.task} has no "test:" field; pass --cmd')
    done = {t['id'] for t in tasks if t['done']}
    findings = [warn(f'{task["id"]} depends on open {d}') for d in task['depends'] if d not in done]
    code, tail = run_command(cmd, spec.repo.root, args.timeout)
    payload = {'spec': spec.repo.rel(spec.dir), 'task': task['id'], 'command_exit': code, 'ticked': False,
               'output_tail': tail}
    if code != 0:
        findings.append(fail(f'{task["id"]}: command exited {code}; {spec.plan_name} and ledger.md unchanged\n{tail}'))
        return finding_result(findings, payload)
    with spec_lock(spec.dir):  # the plan may have changed while the command ran: re-read, tick by ID
        if not _tick(spec.dir / spec.plan_name, task['id']):
            findings.append(fail(f'{task["id"]} is no longer in {spec.label(spec.plan_name)}; nothing ticked'))
            return finding_result(findings, payload)
        fp = Repo(spec.repo.root).fingerprint
        event = append_ledger(spec, f'task-done {task["id"]} exit=0 fingerprint={fp} cmd={quoted(cmd)}')
    payload.update(ticked=True, ledger=event)
    return finding_result(findings + [('OK', f'{task["id"]} done')], payload)


def _tick(plan, task_id):
    """plan.md: tick the task's box; tickets.md: set the ticket's `Status:` to done."""
    text, newline = read_for_edit(plan)
    tickets = plan.name == 'tickets.md'
    tasks, _ = (parse_tickets if tickets else parse_plan)(text, plan.name)
    task = next((t for t in tasks if t['id'] == task_id), None)
    if task is None:
        return False
    lines = text.split('\n')
    if not tickets:
        lines[task['line'] - 1] = re.sub(r'\[ \]', '[x]', lines[task['line'] - 1], count=1)
    elif task['status_line']:
        line = lines[task['status_line'] - 1]
        lines[task['status_line'] - 1] = line[:len(line) - len(line.lstrip())] + 'Status: done'
    else:
        lines.insert(task['line'], 'Status: done')
    write_atomic(plan, '\n'.join(lines), newline)
    return True


def cmd_verify(args):
    spec = spec_arg(args)
    before = Repo(spec.repo.root).fingerprint
    started = time.time()
    code, tail = run_command(args.cmd, spec.repo.root, args.timeout)
    repo = Repo(spec.repo.root)
    findings, junit, event = [], None, f'verify exit={code} fingerprint={repo.fingerprint} cmd={quoted(args.cmd)}'
    if code != 0:
        findings.append(fail(f'test command exited {code}\n{tail}'))
    if before != repo.fingerprint:  # the tests did not run against one version of the code: not green
        findings.append(fail('the test command changed code files during the run; fix that and re-run'))
        event += f' before={before}'
    if args.junit:
        junit, problems, marker = _junit_results(args.junit, started, spec, repo)
        findings += problems
        event += marker
    with spec_lock(spec.dir):
        append_ledger(spec, event)
    payload = {'spec': spec.repo.rel(spec.dir), 'command_exit': code, 'fingerprint': repo.fingerprint,
               'junit': junit, 'output_tail': tail, 'ledger': event}
    return finding_result(findings + [('OK', f'verify logged: exit={code}')], payload)


def _junit_results(pattern, started, spec, repo):
    """(summary or None, findings, ledger suffix). Reports older than the run (1 s clock slack) are ignored."""
    paths = sorted(p for p in globlib.glob(os.path.join(str(repo.root), pattern), recursive=True) if os.path.isfile(p))
    fresh = [p for p in paths if os.path.getmtime(p) >= started - 1]
    findings = [warn(f'ignored {len(paths) - len(fresh)} JUnit file(s) older than this run')] if len(fresh) < len(paths) else []
    if not fresh:
        return None, findings + [fail(f'--junit {pattern} matches no report written by this run')], ' junit=missing'
    junit, problems = parse_junit(fresh, [r['id'] for r in spec.requirements[0] or []], repo)
    findings += problems
    if junit['unreadable']:
        return junit, findings, ' junit=unreadable'
    if not junit['cases']:
        return junit, findings + [fail(f'--junit {pattern}: the reports hold no test case')], ' junit=missing'
    marker = f' junit={junit["passed"]} passed, {junit["failed"]} failed'
    marker += ''.join(f' {k.replace("_", "-")}={",".join(junit[k])}' for k in ('req_pass', 'req_fail') if junit[k])
    if junit['req_fail']:
        findings.append(fail(f'requirement tests failed: {", ".join(junit["req_fail"])}'))
    return junit, findings, marker


def cmd_ruling(args):
    spec = spec_arg(args)
    task = ''
    if args.task:
        tasks = spec.tasks[0] or []
        if not TASK_ID.match(args.task) or args.task not in {t['id'] for t in tasks}:
            raise UsageError(f'{args.task} is not a task in {spec.label(spec.plan_name)}')
        task = f'{args.task}: '
    clean = [' '.join(str(x).split()) for x in (args.decision, args.why, args.if_wrong)]
    if not all(clean):
        raise UsageError('--decision, --why and --if-wrong must not be empty')
    with spec_lock(spec.dir):
        event = append_ledger(spec, f'ruling {task}{clean[0]} — why: {clean[1]} — if wrong: {clean[2]}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'ledger': event}, [f'OK {event}']


def cmd_stamp(args):
    spec = spec_arg(args)
    review = spec.dir / 'review.md'
    if not review.is_file():
        raise UsageError(f'{spec.label("review.md")} does not exist: write the review first')
    fp = spec.repo.fingerprint
    with spec_lock(spec.dir):
        set_frontmatter(review, {'fingerprint': fp})
        event = append_ledger(spec, f'stamp review fingerprint={fp}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'fingerprint': fp, 'ledger': event}, [f'OK {event}']


def trace_rows(spec):
    tasks = spec.tasks[0] or []
    event, current = spec.last('verify'), spec.repo.fingerprint
    rows = []
    for req in spec.requirements[0] or []:
        tests = spec.repo.tests_referencing(req['id'])
        rows.append({'id': req['id'], 'title': req['title'],
                     'verify': req['verify'] + (f' — {req["verify_detail"]}' if req['verify_detail'] else ''),
                     'tasks': [t['id'] for t in tasks if req['id'] in t['covers']], 'tests': tests,
                     'result': _result(req, tests, event, current)})
    return rows


def _result(req, tests, event, current):
    if req['verify'] != 'test':
        return f'{req["verify"]}: {req["verify_detail"]}'
    if not tests:
        return 'no test'
    if event is None:
        return 'not run'
    if not fp_matches(event['fingerprint'], current):
        return 'stale'
    return 'fail' if event['exit'] != 0 or req['id'] in event['req_fail'] else 'pass'


def trace_table(rows):
    cell = lambda value: str(value).replace('|', '\\|') or '-'  # noqa: E731
    lines = ['| Requirement | Title | Verify | Tasks | Tests | Result |', '|---|---|---|---|---|---|']
    for row in rows:
        lines.append('| ' + ' | '.join(cell(x) for x in (row['id'], row['title'], row['verify'], ', '.join(row['tasks']),
                                                          ', '.join(row['tests']), row['result'])) + ' |')
    return lines


def cmd_lint(args):
    """Check a standalone spec.md (e.g. a drafted prompt) against the accepted gate's spec.md rules."""
    path = pathlib.Path(args.file)
    text, error = read_text(path, str(path))
    if text is None:
        raise UsageError(error or f'{path}: not readable')
    if not KEY.match(args.key):
        raise UsageError(f'--key {args.key!r} must be 2-6 capital letters')
    label = path.name
    stories, findings = parse_spec(text, label, args.key)
    findings += spec_findings(text, label, stories)
    if not args.no_security and not spec_security(text):
        findings.append(fail(f'{label}: Implementation Decisions has no security decisions (a "### Security" heading '
                             'or a "**Security**" bullet: assets, threats, controls); pass --no-security only when '
                             'the trust-boundary check is all NO'))
    if not re.search(r'^\s*Status:\s*ready-for-agent\b', text, re.M | re.I):
        findings.append(warn(f'{label}: no "Status: ready-for-agent" line: the spec stage will ask for approval'))
    if not failed(findings):
        findings.append(('OK', f'{label}: {len(stories)} stories, every template section filled'))
    return finding_result(findings, {'file': str(path), 'stories': [s['id'] for s in stories]})


def cmd_trace(args):
    spec = spec_arg(args)
    reqs, findings = spec.requirements
    if reqs is None:
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'rows': [], 'written': False})
    rows = trace_rows(spec)
    table = trace_table(rows)
    if args.write:
        with spec_lock(spec.dir):
            _write_section(spec.dir / 'README.md', 'Traceability',
                           [f'Generated by `aidlc trace --write` on {today()}.', ''] + table)
    return 0, {'spec': spec.repo.rel(spec.dir), 'rows': rows, 'written': bool(args.write)}, table


def _write_section(path, title, body):
    text, newline = read_for_edit(path)
    lines = text.rstrip('\n').split('\n')
    start = next((i for i, x in enumerate(lines) if re.match(rf'^##\s+{title}\s*$', x, re.I)), None)
    block = [f'## {title}', ''] + body + ['']
    if start is None:
        lines += [''] + block
    else:
        end = next((i for i in range(start + 1, len(lines)) if re.match(r'^#{1,2}\s', lines[i])), len(lines))
        lines[start:end] = block
    write_atomic(path, '\n'.join(lines).rstrip('\n') + '\n', newline)


README_SKELETON = """---
status: proposed
key: {key}
branch:
security: required
contract: none
accepted_by:
updated: {today}
---
# {slug}

Spec: `spec.md`. Tickets: `tickets.md`. Lifecycle events: `ledger.md` (written by `aidlc` only).
"""
SPEC_SKELETON = """# {slug}

<!-- Template: references/aidlc.md §2. User story n is requirement {key}-n; tests reference it as {key}-n. -->

## Problem Statement

## Solution

## User Stories

## Implementation Decisions

## Testing Decisions

## Out of Scope

## Further Notes
"""
TICKETS_SKELETON = """# Tickets — {slug}

<!--
## T1: <vertical slice title>
Blocked by: none
Covers: {key}-1..{key}-3
Status: ready-for-agent        (aidlc task-done sets: done)
What to build: <end-to-end behaviour, from the user's side>
- [ ] <acceptance criterion>
Test: <command>                (optional: default for aidlc task-done)
Files: <glob>, <glob>          (optional: needed to run tickets in parallel)
-->
"""
LEDGER_SKELETON = """# Ledger — {slug}

Append-only, written by `aidlc` only.

"""


def cmd_init(args):
    if not KEY.match(args.key):
        raise UsageError(f'--key {args.key!r} must be 2-6 capital letters')
    root = repo_arg(args)
    ref = args.spec
    target = pathlib.Path(ref).resolve() if ('/' in ref or os.sep in ref) else root / 'docs' / 'specs' / ref
    if not SLUG.match(target.name):
        raise UsageError(f'{target.name!r} is not a kebab-case slug')
    if (target / 'README.md').exists():
        raise UsageError(f'{target} already has a README.md')
    repo = Repo(repo_root(target))
    for other in repo.spec_dirs():
        if Spec(other, repo).meta.get('key') == args.key:
            raise UsageError(f'key {args.key} is already used by {repo.rel(other)}')
    target.mkdir(parents=True, exist_ok=True)
    values = {'key': args.key, 'slug': target.name, 'today': today()}
    written = []
    for name, skeleton in (('README.md', README_SKELETON), ('spec.md', SPEC_SKELETON),
                           ('tickets.md', TICKETS_SKELETON), ('ledger.md', LEDGER_SKELETON)):
        if not (target / name).exists():
            (target / name).write_text(skeleton.format(**values), encoding='utf-8')
            written.append(name)
    rel = repo.rel(target)
    return 0, {'path': rel, 'files': written}, [f'OK created {rel}: {", ".join(written)}']


# ------------------------------------------------------------------------------------------------------------- CLI

def repo_arg(args):
    """--repo (any folder inside the repository) or the current folder, normalized to the git top level."""
    return repo_root(pathlib.Path(args.repo) if args.repo else pathlib.Path.cwd())


def spec_arg(args):
    path, error = resolve_spec(repo_arg(args), args.spec)
    if error:
        raise UsageError(error)
    return Spec(path, Repo(repo_arg(args)) if args.repo else None)


def finding_result(findings, payload):
    payload['findings'] = [{'level': level, 'message': message} for level, message in findings]
    payload['passes'] = not failed(findings)
    return (1 if failed(findings) else 0), payload, [f'{level} {message}' for level, message in findings]


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='print one JSON object')
    common.add_argument('--repo', help='repository root (default: the git top level of the current folder)')
    parser = argparse.ArgumentParser(prog='aidlc', description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def add(name, func, *spec_args):
        command = sub.add_parser(name, parents=[common])
        command.set_defaults(func=func)
        for arg in spec_args:
            command.add_argument(arg)
        return command

    add('status', cmd_status).add_argument('--fast', action='store_true', help='no gh, no contract gate')
    add('check', cmd_check, 'spec').add_argument('--to', choices=list(GATES))
    advance = add('advance', cmd_advance, 'spec')
    advance.add_argument('stage', choices=list(STAGES + SIDE))
    advance.add_argument('--back', action='store_true')
    advance.add_argument('--reason')
    add('next', cmd_next, 'spec')
    task_done = add('task-done', cmd_task_done, 'spec', 'task')
    task_done.add_argument('--cmd')
    task_done.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    verify = add('verify', cmd_verify, 'spec')
    verify.add_argument('--cmd', required=True)
    verify.add_argument('--junit')
    verify.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    ruling = add('ruling', cmd_ruling, 'spec')
    for name in ('--decision', '--why', '--if-wrong'):
        ruling.add_argument(name, required=True)
    ruling.add_argument('--task')
    add('stamp', cmd_stamp, 'spec').add_argument('what', choices=['review'])
    add('trace', cmd_trace, 'spec').add_argument('--write', action='store_true')
    add('init', cmd_init, 'spec').add_argument('--key', required=True)
    lint = add('lint', cmd_lint, 'file')
    lint.add_argument('--key', default='KEY')
    lint.add_argument('--no-security', action='store_true', help='the change crosses no trust boundary')
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # command output may not be UTF-8; never crash printing it
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(errors='replace')
            except (ValueError, OSError):
                pass
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:  # argparse already printed the usage error (or --help)
        return exit_.code if isinstance(exit_.code, int) else 2
    try:
        code, payload, lines = args.func(args)
    except UsageError as err:
        code, payload, lines = 2, {'error': str(err)}, [f'aidlc: {err}']
    except Exception as err:  # never a traceback
        code, payload, lines = 2, {'error': f'internal error: {err.__class__.__name__}: {err}'}, \
            [f'aidlc: internal error: {err.__class__.__name__}: {err}']
    if args.json:
        print(json.dumps({'command': args.command, 'exit': code, **payload}, indent=2, default=list, ensure_ascii=False))
    else:
        print('\n'.join(lines), file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main())
