#!/usr/bin/env python3
"""AIDLC lifecycle engine: the stages, artifacts and gates of references/aidlc.md (stdlib only, Python 3.9+).

CLI: python3 scripts/aidlc.py <command> [--json] [--repo DIR]   exit 0 pass, 1 gate findings, 2 usage or input error
  status                                   every spec: stage, next stage, whether its gate passes, blockers
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
SPEC is a folder path (contains '/') or a slug found under docs/specs/ or */docs/specs/ (init: <repo>/docs/specs/<slug>).
task-done and verify accept --timeout SECONDS (default 1800).

Python API (load with importlib.util.spec_from_file_location; hooks call it):
  find_spec(repo, ref) -> Path | None          spec folder for a path or slug; None when missing or ambiguous
  load_spec(path) -> dict                      path, slug, repo, stage, readme (frontmatter), requirements, guesses,
                                               tasks, ledger, review, ship (None when the file is missing),
                                               errors [(level, message)] from parsing
  stage(path) -> str                           README status: (default proposed)
  check(path, target=None) -> [(level, msg)]   level FAIL | WARN | OK; target defaults to the next stage
  fingerprint(repo) -> str                     SHA-256 hex over code and test files (tracked or untracked, not ignored)
  active_specs(repo) -> [Path]                 specs whose status is proposed..shipped
  specs_for_branch(repo, branch) -> [Path]     active specs whose README branch: is `branch`
  status(repo) -> [dict]                       path (repo-relative), slug, stage, next, passes (None = not evaluated),
                                               blockers [str], legacy (no key:, not evaluated)
  next_batches(path) -> [[task dict]]          the frontier; tasks in one batch share no file
Environment: AIDLC_GH = the gh executable for the shipped gate's CI check (tests point it at a fake).
"""
import argparse
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
import xml.etree.ElementTree as ET
from functools import cached_property

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_tdd = _load('aidlc_tdd_gate', HERE.parent / 'hooks' / 'tdd-gate.py')
_contract = _load('aidlc_check_contract', HERE / 'check-contract.py')

CODE_EXT = tuple(_tdd.CODE_EXT) + ('.feature', '.sql', '.proto', '.graphql')
TEST_PATH = _tdd.TEST_PATH
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
VERIFY = re.compile(r'^(test|check|manual)\b' + DASH + r'(.*)$', re.I)
NOT_APPLICABLE = re.compile(r'^not-applicable\b' + DASH + r'(.*)$', re.I)
LEDGER_LINE = re.compile(r'^[-*]\s+(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)\s+([\w-]+)\s*(.*)$')
JUNIT = re.compile(r'\bjunit=(?:(\d+) passed, (\d+) failed|(unreadable|missing))')
KV = re.compile(r'([\w-]+)=("(?:[^"\\]|\\.)*"|\S+)')
RULING = re.compile(r'^(?:(T\d+):\s+)?(.*?)\s+—\s+why:\s+(.*?)\s+—\s+if wrong:\s+(.*)$')
ADVANCE = re.compile(r'^([\w-]+)\s*(?:→|->)\s*([\w-]+)\s*(.*)$')
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
        return data.decode('utf-8'), None
    except UnicodeDecodeError as err:
        line = data[:err.start].count(b'\n') + 1
        return None, f'{label}:{line}: not UTF-8 text'


def write_atomic(path, text):
    temp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp.write_text(text, encoding='utf-8')
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
        value = re.split(r'(?:^|\s)#', value, 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        meta[key.strip()] = value
    return meta, end + 1


def set_frontmatter(path, updates):
    """Set `key: value` lines in a file's frontmatter (created when missing); inline comments are kept."""
    lines = path.read_text(encoding='utf-8').split('\n')
    end = None
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
    write_atomic(path, '\n'.join(lines))


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
    """RFD-1 also matches RFD_1 and rfd-1 (test function names), never RFD-10."""
    prefix, number = req_id.rsplit('-', 1)
    return re.compile(rf'(?<![A-Za-z0-9]){re.escape(prefix)}[-_]{number}(?![0-9])', re.I)


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
        return [fail(f'{where}: {req["id"]} Verify: {value!r} is not test, check — <command> or manual — <reason>')]
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
    raw.update({'covers': [] if none or covers is None else re.findall(r'\b[A-Z][A-Z0-9]*-\d+\b', covers),
                'covers_given': covers is not None, 'covers_none': none.group(1).strip() if none else None,
                'depends': re.findall(r'\bT\d+\b', fields.get('depends') or ''),
                'owner': fields.get('owner', ''), 'files': files, 'new_files': new,
                'exit': fields.get('exit', ''), 'test': fields.get('test', '')})
    return raw


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
        event.setdefault('junit', None)
        for name in ('req_pass', 'req_fail'):
            event[name] = [x for x in str(data.get(name, '')).split(',') if x]
    return event, None


def parse_review(text, label):
    meta, start = parse_frontmatter(text)
    lines = strip_noise(text)
    review = {'fingerprint': (meta or {}).get('fingerprint', '').rstrip('…'), 'reviewers': (meta or {}).get('reviewers', ''),
              'axes': {}, 'findings': [], 'qa': None, 'qa_line': None}
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
            box = CHECKBOX.match(lines[i].strip())
            if box:
                match = FINDING.match(box.group(3).strip())
                review['findings'].append({
                    'axis': name, 'id': match.group(1) if match else None, 'open': box.group(2) == ' ',
                    'severity': (match.group(2) or '').strip().lower() if match else '', 'text': box.group(3).strip(),
                    'line': i + 1})
    return review, []


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
        pa, pb = re.split(r'[*?]', a, 1)[0], re.split(r'[*?]', b, 1)[0]
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
        return [fail(f'{label}: defines no task ("- [ ] T1: <title>" with indented fields)')]
    for task in tasks:
        where, tid = f'{label}:{task["line"]}', task['id']
        if tid in seen:
            findings.append(fail(f'{where}: duplicate task {tid} (also line {seen[tid]})'))
        seen.setdefault(tid, task['line'])
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
        for group in groups:
            if not any(overlaps(a, b) for other in group for a in other['files'] for b in task['files']):
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


class Repo:
    """A repository root with cached file listing, fingerprint and test-file contents."""

    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()

    def git(self, *args):
        try:
            return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True, timeout=30,
                                  encoding='utf-8', errors='surrogateescape')
        except (OSError, subprocess.SubprocessError):
            return None

    def rel(self, path):
        try:
            return pathlib.Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    @cached_property
    def files(self):
        listing = self.git('ls-files', '-z', '--cached', '--others', '--exclude-standard')
        if listing is not None and listing.returncode == 0:
            return sorted({p for p in listing.stdout.split('\0') if p})
        found = []
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not _tdd.SKIP_DIRS.search(d + '/')]
            found += [self.rel(os.path.join(folder, name)) for name in names]
        return sorted(found)

    @cached_property
    def code_files(self):
        return [f for f in self.files if f.endswith(CODE_EXT)]

    @cached_property
    def fingerprint(self):
        digest = hashlib.sha256()
        for rel in self.code_files:
            try:
                content = hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
            except OSError:  # deleted but still in the index, or a directory (submodule)
                continue
            digest.update(f'{rel}\0{content}\n'.encode('utf-8', 'surrogateescape'))
        return digest.hexdigest()

    @cached_property
    def test_texts(self):
        texts = {}
        for rel in self.code_files:
            if (TEST_PATH.search(rel) or rel.endswith('.feature')) and not re.search(r'(^|/)docs/specs/', rel):
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

    def spec_dirs(self):
        found = []
        for pattern in ('docs/specs/*/README.md', '*/docs/specs/*/README.md'):
            found += [p.parent for p in sorted(self.root.glob(pattern))]
        return found


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

    @cached_property
    def parsed_requirements(self):
        return self._parse('requirements.md', parse_requirements)

    @cached_property
    def requirements(self):
        """(requirements of this spec's key or None, parse findings + requirement_findings)."""
        reqs, findings = self.parsed_requirements
        if reqs is None:
            return None, findings or self.missing('requirements.md')
        return (select_requirements(reqs, self.key),
                findings + requirement_findings(reqs, self.key, self.label('requirements.md')))

    @cached_property
    def guesses(self):
        return self._parse('spec-check.md', parse_spec_check)

    @cached_property
    def tasks(self):
        return self._parse('plan.md', parse_plan)

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
    return bool(recorded) and current.startswith(recorded)


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
    try:
        for level, message in _contract.run(spec.dir, repo_arg=spec.repo.root):
            if level != 'OK':
                findings.append((level, 'contract gate: ' + message.replace(str(spec.dir), spec.repo.rel(spec.dir))))
    except Exception as err:
        findings.append(fail(f'contract gate could not run ({err.__class__.__name__}: {err})'))
    accepted_by = spec.meta.get('accepted_by', '')
    if not accepted_by or re.search(r'<[^>]*>', accepted_by):
        findings.append(fail(f'{readme}: accepted_by: is not set (record who approved the spec, and when)'))
    return findings


def _security(spec):
    value = spec.meta.get('security', '')
    waiver = NOT_APPLICABLE.match(value)
    if waiver:
        return [] if waiver.group(1).strip() else [
            fail(f'{spec.label("README.md")}: security: not-applicable needs "— <reason>"')]
    text, error = read_text(spec.dir / 'security.md', spec.label('security.md'))
    if text is None:
        return [fail(error or f'{spec.label("security.md")}: missing (or set security: not-applicable — <reason>)')]
    return [] if text.strip() else [fail(f'{spec.label("security.md")}: empty')]


def gate_planned(spec):
    reqs, findings = spec.requirements
    tasks, problems = spec.tasks
    findings = findings + problems
    if tasks is None:
        return findings + (spec.missing('plan.md') if not problems else [])
    ids = [r['id'] for r in reqs] if reqs is not None else None
    return findings + plan_findings(tasks, ids, spec.label('plan.md'))


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
        where = f'{spec.label("plan.md")}:{task["line"]}'
        if not task['done']:
            findings.append(fail(f'{where}: {task["id"]} is not done (aidlc task-done)'))
        elif task['id'] not in green:
            findings.append(fail(f'{where}: {task["id"]} is ticked but has no green task-done event in ledger.md'))
    for req in spec.requirements[0] or []:
        if req['verify'] == 'test' and not spec.repo.tests_referencing(req['id']):
            findings.append(fail(f'{spec.label("requirements.md")}:{req["line"]}: {req["id"]} (Verify: test) is not '
                                 'referenced by any test file'))
    return findings + _verify_findings(spec)


def _verify_findings(spec):
    event = spec.last('verify')
    if event is None:
        return [fail(f'{spec.label("ledger.md")}: no verify event (run aidlc verify SPEC --cmd <tests>)')]
    where, findings = f'{spec.label("ledger.md")}:{event["line"]}', []
    if event['exit'] != 0:
        findings.append(fail(f'{where}: the latest verify exited {event["exit"]}'))
    if not fp_matches(event['fingerprint'], spec.repo.fingerprint):
        findings.append(fail(f'{where}: code changed since the latest verify (fingerprint {short(event["fingerprint"])} '
                             f'≠ current {short(spec.repo.fingerprint)}): run aidlc verify again'))
    if event['junit'] in ('unreadable', 'missing'):
        findings.append(fail(f'{where}: the latest verify has {event["junit"]} JUnit results: fix --junit and re-run'))
    elif event['req_fail']:
        findings.append(fail(f'{where}: requirement tests failed: {", ".join(event["req_fail"])}'))
    return findings


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
    event = spec.last('verify')
    if event is None:
        findings.append(fail(f'{spec.label("ledger.md")}: no verify event'))
    elif not fp_matches(event['fingerprint'], current):
        findings.append(fail(f'{spec.label("ledger.md")}:{event["line"]}: code changed since the latest verify: '
                             'run aidlc verify again'))
    return findings


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
    return findings


def gh_checks(root, branch):
    """[(name, state)] from `gh pr checks <branch>`, or None when gh is missing, errors or reports nothing."""
    exe = os.environ['AIDLC_GH'] if 'AIDLC_GH' in os.environ else shutil.which('gh')
    if not exe or not branch or not os.access(exe, os.X_OK):
        return None
    try:
        result = subprocess.run([exe, 'pr', 'checks', branch], cwd=root, capture_output=True, text=True, timeout=20)
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
    checks = gh_checks(spec.repo.root, branch)
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
    """(path, None) or (None, error): a path when ref contains '/', else a slug under docs/specs or */docs/specs."""
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
        return None, f'no spec named {ref} under docs/specs/ or */docs/specs/ in {repo}'
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


def fingerprint(repo):
    return Repo(repo).fingerprint


def active_specs(repo):
    root = Repo(repo)
    return [d for d in root.spec_dirs() if Spec(d, root).stage in ACTIVE]


def specs_for_branch(repo, branch):
    root = Repo(repo)
    return [d for d in active_specs(root.root) if Spec(d, root).meta.get('branch') == branch]


def status(repo):
    root, items = Repo(repo), []
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

def append_ledger(spec, event):
    path = spec.dir / 'ledger.md'
    if not path.exists():
        path.write_text(LEDGER_SKELETON.format(slug=spec.slug), encoding='utf-8')
    existing = path.read_text(encoding='utf-8')
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(('' if existing.endswith('\n') or not existing else '\n') + f'- {utc_now()} {event}\n')
    return event


def quoted(text):
    return json.dumps(' '.join(str(text).split()), ensure_ascii=False)


def run_command(cmd, cwd, timeout):
    """(exit code, last ~2KB of combined output); 124 on timeout. Nothing is streamed."""
    timed_out = False
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.Popen(cmd, shell=True, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as err:
            return 127, str(err)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out, code = True, 124
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait()
        size = out.seek(0, 2)
        out.seek(max(0, size - TAIL_BYTES))
        tail = out.read().decode('utf-8', 'replace')
    return code, tail + (f'\n[aidlc: timed out after {timeout}s]' if timed_out else '')


def parse_junit(paths, req_ids, repo):
    """(summary, findings): summary {passed, failed, req_pass, req_fail, unreadable}."""
    patterns = {rid: id_pattern(rid) for rid in req_ids}
    summary = {'passed': 0, 'failed': 0, 'req_pass': set(), 'req_fail': set(), 'unreadable': False}
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
    items = status(root)
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
    spec, target = spec_arg(args), args.stage
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
    findings = [('OK', f'pre-PR review recorded for HEAD {head.stdout.strip()[:12]}')]
    dirty = spec.repo.git('status', '--porcelain', '--untracked-files=all')
    if dirty is not None and any(line[3:].endswith(CODE_EXT) for line in dirty.stdout.splitlines()):
        findings.append(warn('uncommitted code: the pre-PR record is bound to HEAD; commit, then re-run the check'))
    return findings


def cmd_next(args):
    spec = spec_arg(args)
    tasks, findings = spec.tasks
    if not tasks or failed(findings):
        findings = findings or (spec.missing('plan.md') if tasks is None else plan_findings([], None, spec.label('plan.md')))
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'batches': []})
    groups = batches(tasks)
    lines = [f'batch {i}: ' + ', '.join(f'{t["id"]} ({t["owner"] or "no owner"}: {", ".join(t["files"])})' for t in g)
             for i, g in enumerate(groups, 1)]
    if not groups:
        lines = ['all tasks are done'] if all(t['done'] for t in tasks) else ['no task is ready (open dependencies)']
    return 0, {'spec': spec.repo.rel(spec.dir), 'batches': groups}, lines


def cmd_task_done(args):
    spec = spec_arg(args)
    tasks, problems = spec.tasks
    task = next((t for t in tasks or [] if t['id'] == args.task), None)
    if task is None:
        raise UsageError(f'{args.task} is not a task in {spec.label("plan.md")}')
    cmd = args.cmd or task['test']
    if not cmd:
        raise UsageError(f'{args.task} has no "test:" field; pass --cmd')
    done = {t['id'] for t in tasks if t['done']}
    findings = [warn(f'{task["id"]} depends on open {d}') for d in task['depends'] if d not in done]
    code, tail = run_command(cmd, spec.repo.root, args.timeout)
    payload = {'spec': spec.repo.rel(spec.dir), 'task': task['id'], 'exit': code, 'ticked': False, 'output_tail': tail}
    if code != 0:
        findings.append(fail(f'{task["id"]}: command exited {code}; plan.md and ledger.md unchanged\n{tail}'))
        return finding_result(findings, payload)
    plan = spec.dir / 'plan.md'
    lines = plan.read_text(encoding='utf-8').split('\n')
    lines[task['line'] - 1] = re.sub(r'\[ \]', '[x]', lines[task['line'] - 1], count=1)
    write_atomic(plan, '\n'.join(lines))
    fp = Repo(spec.repo.root).fingerprint
    payload.update(ticked=True, ledger=append_ledger(spec, f'task-done {task["id"]} exit=0 fingerprint={fp} cmd={quoted(cmd)}'))
    return finding_result(findings + [('OK', f'{task["id"]} done')], payload)


def cmd_verify(args):
    spec = spec_arg(args)
    before = Repo(spec.repo.root).fingerprint
    code, tail = run_command(args.cmd, spec.repo.root, args.timeout)
    repo = Repo(spec.repo.root)
    findings, junit, event = [], None, f'verify exit={code} fingerprint={repo.fingerprint} cmd={quoted(args.cmd)}'
    if code != 0:
        findings.append(fail(f'test command exited {code}\n{tail}'))
    if before != repo.fingerprint:
        findings.append(warn('the command changed code files during the run; the fingerprint after the run is logged'))
    if args.junit:
        paths = sorted(p for p in globlib.glob(os.path.join(str(repo.root), args.junit), recursive=True)
                       if os.path.isfile(p))
        if not paths:
            findings.append(fail(f'--junit {args.junit} matches no file'))
            event += ' junit=missing'
        else:
            junit, problems = parse_junit(paths, [r['id'] for r in spec.requirements[0] or []], repo)
            findings += problems
            if junit['unreadable']:
                event += ' junit=unreadable'
            else:
                event += f' junit={junit["passed"]} passed, {junit["failed"]} failed'
                event += ''.join(f' {k.replace("_", "-")}={",".join(junit[k])}' for k in ('req_pass', 'req_fail')
                                 if junit[k])
            if junit['req_fail']:
                findings.append(fail(f'requirement tests failed: {", ".join(junit["req_fail"])}'))
    append_ledger(spec, event)
    payload = {'spec': spec.repo.rel(spec.dir), 'exit': code, 'fingerprint': repo.fingerprint, 'junit': junit,
               'output_tail': tail, 'ledger': event}
    return finding_result(findings + [('OK', f'verify logged: exit={code}')], payload)


def cmd_ruling(args):
    spec = spec_arg(args)
    task = ''
    if args.task:
        tasks = spec.tasks[0] or []
        if not TASK_ID.match(args.task) or args.task not in {t['id'] for t in tasks}:
            raise UsageError(f'{args.task} is not a task in {spec.label("plan.md")}')
        task = f'{args.task}: '
    clean = [' '.join(str(x).split()) for x in (args.decision, args.why, args.if_wrong)]
    if not all(clean):
        raise UsageError('--decision, --why and --if-wrong must not be empty')
    event = append_ledger(spec, f'ruling {task}{clean[0]} — why: {clean[1]} — if wrong: {clean[2]}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'ledger': event}, [f'OK {event}']


def cmd_stamp(args):
    spec = spec_arg(args)
    review = spec.dir / 'review.md'
    if not review.is_file():
        raise UsageError(f'{spec.label("review.md")} does not exist: write the review first')
    fp = spec.repo.fingerprint
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


def cmd_trace(args):
    spec = spec_arg(args)
    reqs, findings = spec.requirements
    if reqs is None:
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'rows': [], 'written': False})
    rows = trace_rows(spec)
    table = trace_table(rows)
    if args.write:
        _write_section(spec.dir / 'README.md', 'Traceability',
                       [f'Generated by `aidlc trace --write` on {today()}.', ''] + table)
    return 0, {'spec': spec.repo.rel(spec.dir), 'rows': rows, 'written': bool(args.write)}, table


def _write_section(path, title, body):
    lines = path.read_text(encoding='utf-8').rstrip('\n').split('\n')
    start = next((i for i, x in enumerate(lines) if re.match(rf'^##\s+{title}\s*$', x, re.I)), None)
    block = [f'## {title}', ''] + body + ['']
    if start is None:
        lines += [''] + block
    else:
        end = next((i for i in range(start + 1, len(lines)) if re.match(r'^#{1,2}\s', lines[i])), len(lines))
        lines[start:end] = block
    write_atomic(path, '\n'.join(lines).rstrip('\n') + '\n')


README_SKELETON = """---
status: proposed
key: {key}
branch:
security: required
accepted_by:
updated: {today}
---
# {slug}

<!-- One paragraph: what changes and why. Set `contract: external` or `contract: none` (layout §4). -->

| File | Content |
|---|---|
| requirements.md | requirements `{key}-<n>` with acceptance criteria and `Verify:` |
| spec-check.md | blind spec check guesses |
| plan.md | tasks, owners, files, dependencies |
| ledger.md | lifecycle events, written by `aidlc` only |
"""
REQUIREMENTS_SKELETON = """# Requirements — {slug}

<!--
Each requirement is a heading whose first token is its ID:

### {key}-1: <title>
Priority: must
Acceptance:
- Given <context>, when <action>, then <outcome>.
Verify: test            (or: check — <command or procedure>, or: manual — <reason>)
-->
"""
SPEC_CHECK_SKELETON = """# Spec check — {slug}

<!--
Written by the blind spec checker (skill spec-check): one line per guess,
- [ ] G1: <question>
closed as "- [x] G1: <question> — resolved: <where the spec answers it>" or "— accepted risk: <why>".
When there is nothing to guess the checker writes "Checked: no guesses."
-->
"""
PLAN_SKELETON = """# Plan — {slug}

<!--
One checkbox per task; [x] is set only by `aidlc task-done`.
- [ ] T1: <title>
  - covers: {key}-1            (or: none — <reason>)
  - depends: none              (or: T<n>, …)
  - owner: <agent or main>
  - files: <path> (new), <glob>
  - test: <command>            (optional: default for aidlc task-done)
  - exit: <done criterion>
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
    for name, skeleton in (('README.md', README_SKELETON), ('requirements.md', REQUIREMENTS_SKELETON),
                           ('spec-check.md', SPEC_CHECK_SKELETON), ('plan.md', PLAN_SKELETON),
                           ('ledger.md', LEDGER_SKELETON)):
        if not (target / name).exists():
            (target / name).write_text(skeleton.format(**values), encoding='utf-8')
            written.append(name)
    rel = repo.rel(target)
    return 0, {'path': rel, 'files': written}, [f'OK created {rel}: {", ".join(written)}']


# ------------------------------------------------------------------------------------------------------------- CLI

def repo_arg(args):
    return pathlib.Path(args.repo).resolve() if args.repo else repo_root(pathlib.Path.cwd())


def spec_arg(args):
    path, error = resolve_spec(repo_arg(args), args.spec)
    if error:
        raise UsageError(error)
    return Spec(path, Repo(args.repo) if args.repo else None)


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

    add('status', cmd_status)
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
    return parser


def main(argv=None):
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
