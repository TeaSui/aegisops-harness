#!/usr/bin/env python3
"""Routing eval: replay labelled prompts through hooks/autopilot.py and score the notes it emits.

Deterministic and free (no model call). Each line of cases.jsonl is one case:

  {"id": "...", "prompt": "...",            # mode "prompt" (UserPromptSubmit), the default
   "expect": ["skill", ...],                # must appear in the note (tea-sdlc:<skill> or an agent name)
   "forbid": ["skill", ...],                # must not appear
   "trust": ["money", ...],                 # trust-boundary labels that must be signalled
   "forbid_trust": ["auth"] | true,         # labels that must not be signalled (true: none at all)
   "tier": "full" | "fast",                 # routing line the note must carry
   "expect_text": ["..."], "forbid_text": ["..."],   # raw substrings of the note
   "silent": true,                          # no note at all
   "env": {"TEA_SDLC_AUTOPILOT": "off"},    # extra environment for the hook
   "xfail": "why",                          # known gap: reported, never fails the run; XPASS is reported too
   "tags": ["intent", ...]}

  {"id": "...", "mode": "subagent", "agent_type": "backend-engineer-subagent", "expect_text": [...]}  # SubagentStart

The hook runs as a subprocess with the same JSON contract Claude Code uses, so the eval covers the real entry point.
Prints a per-skill precision/recall table; exits 1 on any failing (non-xfail) case or uncovered router output.
Precision counts only labelled outcomes: a skill emitted where the case expected it (TP) versus emitted where the
case forbade it or required silence (FP). Emissions a case does not mention are listed as unlabelled.
"""
import argparse
import collections
import concurrent.futures
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EVENTS = {'prompt': 'UserPromptSubmit', 'subagent': 'SubagentStart'}
SKILL_RE = re.compile(r'(?<![\w-])tea-sdlc:([a-z0-9][a-z0-9-]*[a-z0-9])')
AGENT_RE = re.compile(r'\b([a-z][a-z-]*-subagent)\b')
TRUST_RE = re.compile(r'trust boundary: (.*?)\.(?:\n|$)')


def load_cases(path):
    cases = []
    for number, line in enumerate(pathlib.Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            case = json.loads(line)
        except ValueError as error:
            raise SystemExit('%s:%d: invalid JSON: %s' % (path, number, error))
        case.setdefault('id', 'line-%d' % number)
        cases.append(case)
    ids = [c['id'] for c in cases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit('duplicate case ids: ' + ', '.join(dupes))
    return cases


def run_hook(hook, case, home):
    mode = case.get('mode', 'prompt')
    payload = {'session_id': 'routing-eval', 'cwd': str(home)}
    if mode == 'prompt':
        payload['prompt'] = case.get('prompt', '')
    elif mode == 'subagent':
        payload['agent_type'] = case.get('agent_type', '')
        payload['agent_id'] = 'routing-eval-agent'
    env = {k: v for k, v in os.environ.items() if not k.startswith('TEA_SDLC_')}
    env['HOME'] = str(home)
    env.update(case.get('env') or {})
    result = subprocess.run([sys.executable, str(hook), mode], input=json.dumps(payload), env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        return None, 'hook exited %d: %s' % (result.returncode, result.stderr.strip()[-300:])
    if not result.stdout.strip():
        return '', None
    try:
        out = json.loads(result.stdout)
        specific = out['hookSpecificOutput']
    except (ValueError, KeyError, TypeError):
        return None, 'hook printed non-contract output: %r' % result.stdout[:200]
    if specific.get('hookEventName') != EVENTS.get(mode):
        return None, 'hookEventName %r, expected %r' % (specific.get('hookEventName'), EVENTS.get(mode))
    return specific.get('additionalContext', ''), None


def parse_note(note):
    """Skills/agents named in the note, and the trust-boundary labels it signals."""
    emitted = set(SKILL_RE.findall(note)) | set(AGENT_RE.findall(note))
    trust = set()
    match = TRUST_RE.search(note)
    if match:
        for part in re.split(r'\),\s*', match.group(1)):
            label = part.split(' ("')[0].strip()
            if label:
                trust.add(label)
    return emitted, trust


def check(case, note):
    """Return the list of failure reasons for one case (empty = pass)."""
    problems = []
    emitted, trust = parse_note(note)
    if case.get('silent'):
        if note.strip():
            problems.append('expected silence, got: ' + ', '.join(sorted(emitted)) if emitted
                            else 'expected silence, got a note')
        return problems
    for name in case.get('expect', []):
        if name not in emitted:
            problems.append('missing ' + name)
    for name in case.get('forbid', []):
        if name in emitted:
            problems.append('forbidden ' + name)
    for label in case.get('trust', []):
        if label not in trust:
            problems.append('missing trust label ' + label)
    forbid_trust = case.get('forbid_trust')
    if forbid_trust is True and trust:
        problems.append('unexpected trust labels ' + ', '.join(sorted(trust)))
    elif isinstance(forbid_trust, list):
        for label in forbid_trust:
            if label in trust:
                problems.append('forbidden trust label ' + label)
    tier = case.get('tier')
    if tier == 'full' and 'Full workflow' not in note:
        problems.append('expected Full workflow routing')
    if tier == 'fast' and 'Fast path' not in note:
        problems.append('expected Fast path routing')
    for text in case.get('expect_text', []):
        if text not in note:
            problems.append('missing text %r' % text)
    for text in case.get('forbid_text', []):
        if text in note:
            problems.append('forbidden text %r' % text)
    if not note.strip() and not problems and not case.get('allow_silent'):
        problems.append('expected a note, got silence')
    return problems


def metrics(results):
    """Per-skill TP/FP/FN over labelled outcomes, plus unlabelled emissions."""
    table = collections.defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'unlabelled': 0})
    for case, emitted in results:
        if emitted is None:
            continue
        expect, forbid = set(case.get('expect', [])), set(case.get('forbid', []))
        for name in expect:
            table[name]['tp' if name in emitted else 'fn'] += 1
        for name in forbid:
            if name in emitted:
                table[name]['fp'] += 1
            else:
                table[name]  # labelled negative, kept so the skill shows in the table
        for name in emitted:
            if case.get('silent'):
                table[name]['fp'] += 1
            elif name not in expect and name not in forbid:
                table[name]['unlabelled'] += 1
    rows = {}
    for name, c in sorted(table.items()):
        precision = c['tp'] / (c['tp'] + c['fp']) if c['tp'] + c['fp'] else None
        recall = c['tp'] / (c['tp'] + c['fn']) if c['tp'] + c['fn'] else None
        rows[name] = dict(c, precision=precision, recall=recall)
    return rows


def router_outputs(root):
    """Names the router can emit, read from the hook module; None when it cannot be introspected."""
    try:
        spec = importlib.util.spec_from_file_location('tea_sdlc_autopilot_eval', root / 'hooks' / 'autopilot.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = set(getattr(module, 'CHAIN', ()))
        names |= {name for name, _ in getattr(module, 'DOMAINS', ())}
        names |= {name for name, _ in getattr(module, 'INTENTS', ())}
        trust = {label for label, _ in getattr(module, 'TRUST', ())}
        return names, trust
    except Exception:
        return None


def fmt(value):
    return '  -  ' if value is None else '%.2f' % value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cases', type=pathlib.Path, default=HERE / 'cases.jsonl')
    parser.add_argument('--root', type=pathlib.Path, default=ROOT, help='plugin root holding hooks/autopilot.py')
    parser.add_argument('--json', action='store_true', help='print the full result as JSON')
    parser.add_argument('--no-coverage', action='store_true',
                        help='do not fail when a router output or trust label has no case expecting it')
    parser.add_argument('-q', '--quiet', action='store_true', help='print failures and the summary only')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    hook = root / 'hooks' / 'autopilot.py'
    cases = load_cases(args.cases)

    with tempfile.TemporaryDirectory() as home:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            outputs = list(pool.map(lambda c: run_hook(hook, c, pathlib.Path(home)), cases))

    failures, xfails, xpasses, records, scored = [], [], [], [], []
    for case, (note, error) in zip(cases, outputs):
        problems = [error] if error else check(case, note)
        emitted = parse_note(note)[0] if note is not None else None
        scored.append((case, emitted))
        status = 'pass'
        if case.get('xfail'):
            status = 'xpass' if not problems else 'xfail'
            (xpasses if not problems else xfails).append(case['id'])
        elif problems:
            status = 'FAIL'
            failures.append(case['id'])
        records.append({'id': case['id'], 'status': status, 'problems': problems,
                        'emitted': sorted(emitted) if emitted is not None else None, 'tags': case.get('tags', [])})

    table = metrics(scored)
    uncovered = []
    known = router_outputs(root)
    if known is not None:
        names, labels = known
        expected = {n for c in cases if not c.get('xfail') for n in c.get('expect', [])}
        expected_trust = {t for c in cases if not c.get('xfail') for t in c.get('trust', [])}
        uncovered = sorted(names - expected) + ['trust:' + t for t in sorted(labels - expected_trust)]
    summary = {'cases': len(cases), 'passed': sum(r['status'] == 'pass' for r in records), 'failed': failures,
               'xfail': xfails, 'xpass': xpasses, 'uncovered': uncovered,
               'silent_cases': sum(bool(c.get('silent')) for c in cases)}

    if args.json:
        print(json.dumps({'summary': summary, 'metrics': table, 'cases': records}, indent=2))
    else:
        for record in records:
            if args.quiet and record['status'] in ('pass', 'xfail'):
                continue
            detail = '; '.join(record['problems'])
            print('%-5s %-34s %s' % (record['status'].upper(), record['id'], detail or ', '.join(record['emitted'] or [])))
        print('\n%-32s %4s %4s %4s %5s %9s %6s' % ('skill / agent', 'TP', 'FP', 'FN', 'unlab', 'precision', 'recall'))
        for name, row in table.items():
            print('%-32s %4d %4d %4d %5d %9s %6s' % (name, row['tp'], row['fp'], row['fn'], row['unlabelled'],
                                                    fmt(row['precision']), fmt(row['recall'])))
        print('\n%d cases (%d silent): %d passed, %d failed, %d known gaps (xfail), %d xpass'
              % (len(cases), summary['silent_cases'], summary['passed'], len(failures), len(xfails), len(xpasses)))
        if failures:
            print('FAILED: ' + ', '.join(failures))
        if xpasses:
            print('XPASS (known gap now passes; drop its "xfail"): ' + ', '.join(xpasses))
        if uncovered:
            print('UNCOVERED router outputs (add a case that expects each): ' + ', '.join(uncovered))
    return 1 if failures or (uncovered and not args.no_coverage) else 0


if __name__ == '__main__':
    sys.exit(main())
