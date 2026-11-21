"""Lifecycle suite judge: how far did the AIDLC lifecycle get (references/aidlc.md)?

Scores six stage artifacts in the fixture's spec folder, one point each (partial credit):
  spec        README.md with `key:` and either spec.md (to-spec template, >=1 numbered user story) or the legacy
              requirements.md with >=1 `<KEY>-<n>` requirement that has acceptance bullets
  spec-check  no open guess: spec-check.md closed, or (spec.md format, where the check is optional) absent
  plan        tickets.md has >=1 `## T<n>` ticket, each with Covers and Blocked by; or the legacy plan.md has >=1
              `T<n>` task, every task with covers, depends, owner and files
  build       ledger.md has >=1 `task-done` event and a `verify ... exit=0` event
  review      review.md has `## Spec` and `## Standards`
  ship        ship.md says `decision: GO` and has non-empty `## Rollback` and `## Post-release verification`
A case with "judge": "outcome" (lean mode) is scored on the result instead: `npm test` green, the hidden refund
checks in hidden_refund.mjs (money back to the sender, at most once, never more than sent), a PR opened through the
fixture's gh, and the threats checked named in the PR body or the final report. Needs node; without it the hidden
checks count as failed and the summary says so.
Full-mode cases also get the outcome checks (reported, not scored) and `doc_lines`: lines written under the spec
folder plus GLOSSARY.md and docs/adr/, the size of the paper trail. Separately reports gate discipline: the stage transitions recorded by `aidlc advance` in the ledger, and the stage
`python3 scripts/aidlc.py status --json --repo <fixture>` reports. The judge works without scripts/aidlc.py (it then
reports the CLI as unavailable and scores from files alone).
"""
import json
import pathlib
import re
import subprocess
import sys

STAGES = ('proposed', 'accepted', 'planned', 'building', 'verified', 'reviewed', 'shipped', 'implemented')
ARTIFACTS = ('spec', 'spec-check', 'plan', 'build', 'review', 'ship')


def read(path):
    """File text without HTML comments and fenced code: the `init` skeletons keep their examples there."""
    try:
        text = pathlib.Path(path).read_text(errors='replace')
    except OSError:
        return ''
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    return re.sub(r'^```.*?^```', '', text, flags=re.S | re.M)


def frontmatter(text):
    match = re.match(r'---\s*\n(.*?)\n---', text, re.S)
    fields = {}
    for line in (match.group(1).splitlines() if match else []):
        if ':' in line and not line.startswith((' ', '\t', '#')):
            key, _, value = line.partition(':')
            fields[key.strip()] = value.split('#')[0].strip()
    return fields


def section(text, heading):
    match = re.search(r'^##\s+%s\s*$(.*?)(?=^##\s|\Z)' % re.escape(heading), text, re.M | re.S | re.I)
    return match.group(1).strip() if match else None


def spec_dirs(repo):
    repo = pathlib.Path(repo)
    found = [p.parent for pattern in ('docs/specs/*/README.md', '*/docs/specs/*/README.md') for p in repo.glob(pattern)]
    return sorted(set(found))


def score_spec(spec):
    """Per-artifact booleans and details for one spec folder."""
    readme = read(spec / 'README.md')
    meta = frontmatter(readme)
    key = meta.get('key', '')
    spec_text = read(spec / 'spec.md')
    stories = section(spec_text, 'User Stories') or ''
    template = bool(spec_text.strip())
    if template:
        req_ids = re.findall(r'^(\d+)[.)]\s+\S', stories, re.M)
        with_acceptance = len(req_ids)
    else:
        reqs_text = read(spec / 'requirements.md')
        req_ids = re.findall(r'^#{2,4}\s+(%s-\d+)\b' % re.escape(key), reqs_text, re.M) if key else []
        with_acceptance = 0
        for block in re.split(r'^#{2,4}\s+', reqs_text, flags=re.M)[1:]:
            if key and re.match(r'%s-\d+\b' % re.escape(key), block) and re.search(r'^Acceptance:\s*\n\s*[-*] ', block,
                                                                                   re.M):
                with_acceptance += 1
    check_text = read(spec / 'spec-check.md')
    tickets_text = read(spec / 'tickets.md')
    if tickets_text.strip():
        tasks = re.split(r'^##\s+(?=T\d+)', tickets_text, flags=re.M)[1:]
        complete_tasks = [t for t in tasks if all(re.search(r'^\W*%s\W*:' % field, t, re.M | re.I)
                                                  for field in ('covers', 'blocked by'))]
    else:
        plan_text = read(spec / 'plan.md')
        tasks = re.split(r'^\s*[-*] \[[ xX]\] (?=T\d+)', plan_text, flags=re.M)[1:]
        complete_tasks = [t for t in tasks if all(re.search(r'^\s*[-*] %s:' % field, t, re.M)
                                                  for field in ('covers', 'depends', 'owner', 'files'))]
    ledger = read(spec / 'ledger.md')
    review = read(spec / 'review.md')
    ship = read(spec / 'ship.md')
    artifacts = {
        'spec': bool(key) and bool(req_ids) and with_acceptance >= 1,
        'spec-check': (bool(check_text.strip()) or template) and not re.search(r'^\s*[-*] \[ \]', check_text, re.M),
        'plan': bool(tasks) and len(complete_tasks) == len(tasks),
        'build': bool(re.search(r'\btask-done\b', ledger)) and bool(re.search(r'\bverify\b.*\bexit=0\b', ledger)),
        'review': section(review, 'Spec') is not None and section(review, 'Standards') is not None,
        'ship': frontmatter(ship).get('decision', '').upper() == 'GO' and bool(section(ship, 'Rollback'))
        and bool(section(ship, 'Post-release verification')),
    }
    advances = re.findall(r'\badvance\s+(\w[\w-]*)\s*(?:→|->)\s*(\w[\w-]*)', ledger)
    return {'artifacts': artifacts, 'key': key, 'format': 'spec.md' if template else 'requirements.md',
            'requirements': len(req_ids), 'tasks': len(tasks), 'doc_lines': doc_lines(spec),
            'status': meta.get('status'), 'advances': ['%s→%s' % pair for pair in advances],
            'task_done_events': len(re.findall(r'\btask-done\b', ledger)),
            'verify_events': len(re.findall(r'\bverify\b.*\bexit=', ledger))}


def doc_lines(spec):
    """Lines of every text file in the spec folder, plus the project's GLOSSARY.md / CONTEXT.md and docs/adr/."""
    repo = spec.parent.parent.parent
    files = [p for p in spec.rglob('*') if p.is_file()]
    files += [repo / name for name in ('GLOSSARY.md', 'CONTEXT.md', 'glossary.md') if (repo / name).is_file()]
    files += sorted((repo / 'docs' / 'adr').glob('*.md')) if (repo / 'docs' / 'adr').is_dir() else []
    total = 0
    for path in files:
        try:
            total += len(path.read_text(errors='replace').splitlines())
        except OSError:
            pass
    return total


def aidlc_status(repo, plugin_dir):
    """`aidlc.py status --json --repo`; returns (data or None, note)."""
    script = pathlib.Path(plugin_dir or '.') / 'scripts' / 'aidlc.py'
    if not script.is_file():
        return None, 'scripts/aidlc.py not found'
    try:
        result = subprocess.run([sys.executable, str(script), 'status', '--json', '--repo', str(repo)],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, 'aidlc status failed: %s' % type(error).__name__
    try:
        return json.loads(result.stdout), 'exit %d' % result.returncode
    except ValueError:
        return None, 'aidlc status printed no JSON (exit %d): %s' % (result.returncode, result.stderr.strip()[-200:])


def stages_from_status(data):
    """Pull {spec name: stage} out of aidlc status JSON, tolerant to its exact shape."""
    entries = data.get('specs', data) if isinstance(data, dict) else data
    if isinstance(entries, dict):
        entries = [dict(v, spec=k) if isinstance(v, dict) else {'spec': k, 'stage': v} for k, v in entries.items()
                   if isinstance(v, dict) or v in STAGES]
    stages = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        name = entry.get('spec') or entry.get('slug') or entry.get('path') or entry.get('name') or '?'
        stage = entry.get('stage') or entry.get('status')
        if stage:
            stages[pathlib.Path(str(name)).name] = str(stage)
    return stages


def aidlc_calls(stream):
    commands = [str(c['input'].get('command', '')) for c in stream['calls'] if c['name'] == 'Bash']
    return [c for c in commands if 'aidlc' in c]


HIDDEN = pathlib.Path(__file__).resolve().parent / 'hidden_refund.mjs'
THREATS = re.compile(r'\b(threats?|security|stride|double refund|tamper\w*|spoof\w*|abuse)\b', re.I)


def outcome(case, stream, repo):
    """Lean-mode score: does the change work and is it ready to ship?"""
    checks, notes = {}, []
    try:
        checks['tests'] = subprocess.run(['npm', 'test', '--silent'], cwd=str(repo), capture_output=True, text=True,
                                         timeout=180).returncode == 0
    except (OSError, subprocess.TimeoutExpired) as error:
        checks['tests'] = False
        notes.append('npm test: %s' % type(error).__name__)
    hidden = {}
    try:
        result = subprocess.run(['node', str(HIDDEN), str((repo / 'src' / 'wallet.js').resolve())], capture_output=True,
                                text=True, timeout=60)
        hidden = json.loads((result.stdout.strip().splitlines() or ['{}'])[-1])
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        notes.append('hidden checks: %s' % type(error).__name__)
    for name in ('money_returned', 'at_most_once', 'never_more_than_sent'):
        checks[name] = hidden.get(name) is True
    prs = repo.parent / 'gh-state' / 'prs.json'
    try:
        checks['pr_opened'] = bool(json.loads(prs.read_text()))
    except (OSError, ValueError):
        checks['pr_opened'] = False
    creates = ' '.join(c for c in (str(call['input'].get('command', '')) for call in stream['calls']
                                   if call['name'] == 'Bash') if 'gh pr create' in c)
    checks['threats_listed'] = bool(THREATS.search(creates + ' ' + str(stream.get('result') or '')))
    score = sum(checks.values()) / float(len(checks))
    summary = '%d/%d checks (%s)%s' % (sum(checks.values()), len(checks),
                                       ', '.join(k for k, v in checks.items() if not v) or 'all pass',
                                       ('; ' + '; '.join(notes)) if notes else '')
    return {'pass': score >= float(case.get('pass_score', 1.0)), 'score': round(score, 3), 'checks': checks,
            'hidden': hidden, 'skills': stream['skills'], 'agents': stream['agents'], 'summary': summary}


def judge(case, stream, repo=None, plugin_dir=None):
    if case.get('judge') == 'outcome':
        return outcome(case, stream, pathlib.Path(repo))
    repo = pathlib.Path(repo) if repo else None
    specs = spec_dirs(repo) if repo else []
    scored = {spec.name: score_spec(spec) for spec in specs}
    best_name = max(scored, key=lambda n: (sum(scored[n]['artifacts'].values()), n)) if scored else None
    best = scored.get(best_name) or {'artifacts': {a: False for a in ARTIFACTS}, 'advances': []}
    points = sum(best['artifacts'][a] for a in ARTIFACTS)
    score = points / float(len(ARTIFACTS))
    status_data, status_note = aidlc_status(repo, plugin_dir) if repo else (None, 'no fixture')
    stages = stages_from_status(status_data) if status_data is not None else {}
    stage = stages.get(best_name) if best_name else None
    stage = stage or best.get('status')
    reached = STAGES.index(stage) if stage in STAGES else 0
    advances = best.get('advances', [])
    gate_discipline = (len(advances) / float(reached)) if reached else None
    passed = score >= float(case.get('pass_score', 0.67))
    result = outcome(case, stream, repo) if repo else None
    summary = '%d/%d stages (%s); stage %s; advances: %s; aidlc calls: %d; outcome %s; %s, %s doc lines' % (
        points, len(ARTIFACTS), ', '.join(a for a in ARTIFACTS if best['artifacts'][a]) or 'none', stage or 'none',
        ', '.join(advances) or 'none', len(aidlc_calls(stream)), result['summary'] if result else 'n/a',
        best.get('format', '-'), best.get('doc_lines', 0))
    return {'pass': passed, 'score': round(score, 3), 'spec': best_name, 'specs_found': sorted(scored),
            'artifacts': best['artifacts'], 'detail': best, 'stage': stage, 'aidlc_status': stages,
            'aidlc_status_note': status_note, 'advances': advances,
            'gate_discipline': None if gate_discipline is None else round(min(gate_discipline, 1.0), 3),
            'aidlc_calls': len(aidlc_calls(stream)), 'skills': stream['skills'], 'agents': stream['agents'],
            'outcome': result and {'score': result['score'], 'checks': result['checks']},
            'doc_lines': best.get('doc_lines', 0), 'summary': summary}
