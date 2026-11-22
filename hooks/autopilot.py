#!/usr/bin/env python3
"""tea-sdlc session hooks. Nothing here starts a workflow or loads a skill: tea-sdlc acts only through its
slash commands (skills/session-bootstrap/SKILL.md lists them).

  post      PostToolUse   Edit|Write|MultiEdit|Bash: remember code edited since the last test run.
  stop      Stop          before the session finishes a turn with code changed since the last test run, ask once
                          per change set (max 3 per session) for a test run or a stated reason.
  subagent  SubagentStart the rules a dispatched subagent must follow (it never sees the bootstrap).
  snapshot  (session-start) the active specs, their stage and the next command.

Any internal error is silent. Off with TEA_SDLC_VERIFY_GATE=off (stop).
State: ~/.claude/state/tea-sdlc/autopilot/<session>.json
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'tea-sdlc' / 'autopilot'
NOTE_LIMIT = 1500
MAX_STOP_REMINDERS = 3


def _load_tdd():
    spec = importlib.util.spec_from_file_location('tdd_gate', HERE / 'tdd-gate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tdd = _load_tdd()


def command(name):
    return '/tea-sdlc:' + name


# ---------------------------------------------------------------------------------------------------------------
# Session state, PostToolUse tracking and follow-up notes
# ---------------------------------------------------------------------------------------------------------------

def state_path(session):
    return STATE_DIR / (re.sub(r'[^A-Za-z0-9_-]', '_', session) + '.json')


def load_state(session):
    try:
        return json.loads(state_path(session).read_text())
    except (OSError, ValueError):
        return {}


def save_state(session, state):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        target = state_path(session)
        temp = target.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(state))
        os.replace(temp, target)  # atomic: concurrent hooks never read a half-written file
    except OSError:
        pass


def is_code(path):
    path = path.replace('\\', '/')
    return path.endswith(tdd.CODE_EXT) and not tdd.SKIP_DIRS.search(path)


def display_path(path, cwd):
    try:
        return str(pathlib.Path(path).resolve().relative_to(pathlib.Path(cwd).resolve()))
    except (ValueError, OSError):
        return path


def spec_status(readme):
    try:
        head = readme.read_text(errors='replace')[:2000]
    except OSError:
        return {}
    match = re.match(r'---\s*\n(.*?)\n---', head, re.S)
    meta = {}
    for line in (match.group(1).splitlines() if match else []):
        if ':' in line and not line.startswith((' ', '\t', '#')):
            key, _, value = line.partition(':')
            meta[key.strip()] = value.split('#')[0].strip()
    return meta


def repo_root(cwd):
    here = pathlib.Path(cwd or '.').resolve()
    for folder in [here, *here.parents]:
        if (folder / '.git').exists():
            return folder
        if folder == pathlib.Path.home():
            break
    return here


def active_specs(root, statuses=('proposed', 'accepted')):
    found = []
    for pattern in ('docs/specs/*/README.md', '*/docs/specs/*/README.md'):
        for readme in sorted(root.glob(pattern)):
            meta = spec_status(readme)
            if meta.get('status', 'proposed') in statuses:
                found.append((readme.parent, meta))
    return found[:8]




def post(payload, session, cwd):
    """Track code edited since the last test run (the Stop gate reads it). Emits nothing."""
    tool, tin = payload.get('tool_name'), payload.get('tool_input') or {}
    state = load_state(session)
    before = json.loads(json.dumps(state))
    if tool in ('Edit', 'Write', 'MultiEdit'):
        target = str(tin.get('file_path', ''))
        if is_code(target):
            dirty = state.setdefault('dirty', [])
            shown = display_path(target, cwd)
            if shown not in dirty:
                dirty.append(shown)
                del dirty[:-20]
    elif tool == 'Bash':
        parts = tdd.segments(str(tin.get('command', '')))
        runs = [index for index, part in enumerate(parts) if tdd.RUNNER.match(part)]
        if runs:
            state['dirty'] = []
        # Only writes after the last test run in the same command leave code untested.
        written = tdd.bash_writes_prod('\n'.join(parts[runs[-1] + 1:]) if runs else '\n'.join(parts))
        if written:
            dirty = state.setdefault('dirty', [])
            if written not in dirty:
                dirty.append(written)
    if state != before:
        save_state(session, state)
    return ''


def stop(payload, session, cwd):
    if payload.get('stop_hook_active'):
        return None
    state = load_state(session)
    dirty = state.get('dirty') or []
    if not dirty or not tdd.has_test_setup(cwd):
        return None
    fingerprint = hashlib.sha256('\n'.join(sorted(dirty)).encode()).hexdigest()[:16]
    if fingerprint in state.get('reminded', []) or len(state.get('reminded', [])) >= MAX_STOP_REMINDERS:
        return None
    state.setdefault('reminded', []).append(fingerprint)
    save_state(session, state)
    shown = ', '.join(dirty[:6]) + (f' and {len(dirty) - 6} more' if len(dirty) > 6 else '')
    return (f'tea-sdlc verification: code changed since the last test run in this session ({shown}). Before you '
            f'finish, run the relevant tests and show the result, or say '
            'in your reply why no test applies to this change. This reminder appears once per change set.')


# ---------------------------------------------------------------------------------------------------------------
# Session snapshot (called by hooks/session-start)
# ---------------------------------------------------------------------------------------------------------------

def plan_progress(path):
    """(done, total) tickets in tickets.md (`Status: done`), or ticked tasks in a legacy plan.md."""
    tickets = path.parent / 'tickets.md' if path.name == 'plan.md' else path
    try:
        text = tickets.read_text(errors='replace')
        total = len(re.findall(r'^##\s+T\d+\b', text, re.M))
        done = len(re.findall(r'^\s*\**Status\**\s*:\**\s*done\b', text, re.M | re.I))
        if total:
            return min(done, total), total
    except OSError:
        pass
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return None
    done = len(re.findall(r'^\s*[-*] \[[xX]\]', text, re.M))
    total = done + len(re.findall(r'^\s*[-*] \[ \]', text, re.M))
    return (done, total) if total else None


# The command that moves each stage on (skills/session-bootstrap/SKILL.md lists them).
NEXT_STEP = {
    'proposed': command('spec') + ' (finish spec.md, then the one approval)',
    'accepted': command('plan'),
    'planned': command('build'),
    'building': command('build') + ', then ' + command('verify') + ' once every ticket is done',
    'verified': command('review'),
    'reviewed': command('ship'),
    'shipped': command('upgrade-service-docs') + ' after the merge',
}
STATE_ROOTS = ('tdd', 'contract-gate', 'tea-sdlc/autopilot')
STATE_MAX_AGE_DAYS = 30


def prune_state(now=None):
    """Delete per-session gate state older than STATE_MAX_AGE_DAYS; sessions that old are not resumed."""
    import time
    cutoff = (now or time.time()) - STATE_MAX_AGE_DAYS * 86400
    base = pathlib.Path.home() / '.claude' / 'state'
    for folder in STATE_ROOTS:
        for path in (base / folder).glob('*.json'):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


def load_aidlc():
    spec = importlib.util.spec_from_file_location('tea_sdlc_aidlc', PLUGIN_ROOT / 'scripts' / 'aidlc.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_lines(root):
    """One line per active spec: stage, what the next gate still needs, and the next parallel batch."""
    try:
        aidlc = load_aidlc()
        try:  # fast: no network or slow subprocesses inside the 10 s session-start budget
            rows = aidlc.status(str(root), fast=True)
        except TypeError:
            rows = aidlc.status(str(root))
        rows = [row for row in rows if row.get('stage') in NEXT_STEP]
    except Exception:  # engine missing or broken: fall back to the README status alone
        aidlc, rows = None, [{'path': str(spec), 'stage': meta.get('status', 'proposed'), 'blockers': []}
                             for spec, meta in active_specs(root)]
    lines = []
    for row in rows[:6]:
        path = pathlib.Path(row['path'])
        path = path if path.is_absolute() else root / path  # status() reports repo-relative paths
        rel = display_path(str(path), root)
        stage = row['stage']
        progress = plan_progress(path / 'plan.md')
        detail = f', {progress[0]}/{progress[1]} tickets done' if progress else ''
        if row.get('legacy'):
            detail += ' (legacy: no key, not gated)'
        elif row.get('blockers'):
            detail += f'; next gate blocked by: {"; ".join(str(b) for b in row["blockers"][:3])}'
        elif row.get('passes'):
            detail += f'; the {row.get("next")} gate already passes — advance it'
        if aidlc and stage == 'building':
            try:
                batch = (aidlc.next_batches(path) or [[]])[0]
                if batch:
                    detail += f'; next parallel batch: {", ".join(str(task.get("id")) for task in batch)}'
            except Exception:
                pass
        lines.append(f'Spec {rel} at stage `{stage}`{detail}. Next command (the user runs it): {NEXT_STEP[stage]}.')
    return lines


def snapshot(cwd, which=None):
    """Return (context lines for Claude, message for the user or None)."""
    which = which or __import__('shutil').which
    root = repo_root(cwd)
    lines, user = spec_lines(root), None
    if not which('gitleaks'):
        lines.append('gitleaks is not installed: the security gate will block git commit/push until it is.')
        user = 'tea-sdlc: gitleaks is not installed, so git commit/push will be blocked. Install: brew install gitleaks'
    return lines, user


# Subagents never see the SessionStart bootstrap, so the rules they must follow travel with each dispatch.
READ_ONLY_AGENTS = ('explore', 'claude-code-guide', 'statusline-setup', 'web-fetch', 'plan')


def subagent_rules(agent_type):
    if str(agent_type).split(':')[-1].lower() in READ_ONLY_AGENTS:
        return ''
    rules = PLUGIN_ROOT / 'rules'
    return '\n'.join((
        'tea-sdlc rules for this subagent (the main session dispatched you; its bootstrap does not reach you):',
        '- You are a leaf: do not dispatch further agents. If the task needs more, return the dispatch plan and stop.',
        f'- Return a status (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT or BLOCKED), evidence paths the dispatcher can '
        f'Read, and a check of each exit criterion ({rules}/subagent-return-format.md).',
        '- Evidence before claims: cite file:line or command output; never invent paths, flags or results.',
        '- A business-logic or domain question you cannot answer from the files given: return NEEDS_CONTEXT with the '
        'question and your recommended answer; the main session answers it (Atlassian Rovo first). Never guess a '
        'business rule, and never ask the user yourself.',
        '- TDD: the tdd-gate hook blocks the first production edit without a recorded failing test run. Write the '
        'test, run it, see it fail, then change the code. Name each test with the requirement ID it covers '
        '(for example "RFD-1 rejects over-capture") so the trace gate finds it.',
        '- Stay inside the files your task owns. Do not edit docs/specs/**, contracts/ or another task\'s files unless '
        'the dispatch says so; others work in the same checkout, never revert their changes.',
        '- A contract-gate finding means the contract must change: return NEEDS_CONTEXT with it instead of editing '
        'contracts/.',
    ))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    session = str(payload.get('session_id') or '')
    cwd = payload.get('cwd') or os.getcwd()
    if mode == 'post' and session:
        post(payload, session, cwd)
    elif mode == 'subagent':
        rules = subagent_rules(payload.get('agent_type', ''))
        if rules:
            emit('SubagentStart', rules)
    elif mode == 'stop' and session and os.environ.get('TEA_SDLC_VERIFY_GATE', '').lower() != 'off':
        reason = stop(payload, session, cwd)
        if reason:
            print(json.dumps({'decision': 'block', 'reason': reason}))
    return 0


def emit(event, note):
    note = '<tea-sdlc>\n' + note[:NOTE_LIMIT - 60] + '\n</tea-sdlc>'
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': note}}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # autopilot is advisory: never break the session
        sys.exit(0)
