"""Constants, text helpers and the spec lock."""
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

HERE = pathlib.Path(__file__).resolve().parent.parent  # scripts/ (this file is scripts/aidlc_lib/core.py)


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
CONFIG_NAME = '.aidlc.json'  # the repository config: pins the verify command (parse_config)
REVERT_MARKER = 'aidlc-revert-check.json'  # in the git dir while a revert check has production files rewritten
RETURNS = 'returns'  # folder in a spec folder: what each review-stage reviewer returned, verbatim (record_return)
RETURNED_FINDING = re.compile(r'^\s*[-*+]\s+(?:\[[ xX]\]\s+)?[*_`]*([SQ]\d+)\b[*_`]*\s*(?:\(([^)]*)\))?')
VERDICT = re.compile(r'^\s*(?:[-*+]\s+)?[*_]*verdict[*_]*\s*:[*_]*\s*(.*)$', re.I)
SCHEMA = 1  # of the repository config and the spec README; a file written for a newer schema is refused
WAIVER = re.compile(r'^none\b' + DASH + r'(.*)$', re.I)
NO_CONFIG = ('no pinned verify command: {name} is on neither the default branch nor this branch. The command that '
             'counts as gate evidence is not the session\'s to choose: a person adds the file (aidlc config init '
             '--cmd "<full test suite>" --junit "<report glob>" writes it) and merges it to the default branch')


class UsageError(Exception):
    """Exit 2: bad arguments or input that is not a gate finding."""


def fail(message):
    return ('FAIL', message)


def warn(message):
    return ('WARN', message)


def failed(findings):
    return any(level == 'FAIL' for level, _ in findings)


def earlier(findings):
    """The findings of an earlier gate as a later gate carries them: every gate re-checks the gates before it, so a
    stage that was set by hand, or evidence that went stale, grants nothing. The earlier gate's OK line is dropped."""
    return [finding for finding in findings if finding[0] != 'OK']


def unique(findings):
    seen, kept = set(), []
    for finding in findings:
        if finding not in seen:
            seen.add(finding)
            kept.append(finding)
    return kept


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


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
