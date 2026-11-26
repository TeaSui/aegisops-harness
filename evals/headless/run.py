#!/usr/bin/env python3
"""Headless eval runner: real `claude -p` sessions with the plugin loaded, judged from their stream-json output.

These suites cost money (each run is a full Claude Code session). Suites live in suites/<name>/:
  suite.json    CLI settings: max_turns, timeout_s, permission_mode, allowed_tools
  cases.jsonl   one case per line: id, prompt and suite-specific fields
  fixture.py    build(repo, case): creates the fixture repository the session runs in
  judge.py      judge(case, stream, repo, plugin_dir) -> {pass, score, summary, ...}

Examples
  run.py --suite passive --runs 1 --parallel 6
  run.py --suite passive,tdd --runs 3 --compare            # exit 1 on a regression against baseline.json,
                                                           # exit 3 when too few runs were judged (no signal)
  run.py --suite tdd --rejudge evals/headless/results/X    # re-judge recorded sessions, no model calls
  run.py --suite passive --cases 01-feature,03-expert --runs 1
  run.py --suite tdd --runs 3 --update-baseline            # accept these scores as the new baseline

Outputs in --out: results.json (every run, summaries, comparison) and report.md (per-case outcome, cost, duration).
Each run keeps its fixture repo, out.jsonl (stream-json), err.txt and judge.json under <out>/<suite>/<case>-r<n>/.
"""
import argparse
import concurrent.futures
import datetime
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(HERE), str(HERE / 'fixtures')]
import harness  # noqa: E402

SUITES = ('passive', 'tdd', 'lifecycle')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_suite(name):
    folder = HERE / 'suites' / name
    if not folder.is_dir():
        raise SystemExit('unknown suite %r (have: %s)' % (name, ', '.join(sorted(p.name for p in (HERE / 'suites').iterdir()))))
    config = json.loads((folder / 'suite.json').read_text())
    cases = []
    for line in (folder / 'cases.jsonl').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            cases.append(json.loads(line))
    return {'name': name, 'config': config, 'cases': cases,
            'fixture': load_module(folder / 'fixture.py', 'eval_fixture_' + name),
            'judge': load_module(folder / 'judge.py', 'eval_judge_' + name)}


def find_claude(explicit):
    if explicit:
        return explicit
    if os.environ.get('CLAUDE_BIN'):
        return os.environ['CLAUDE_BIN']
    return shutil.which('claude')


def claude_command(claude, prompt, plugin_dir, config, case, model, extra_args):
    command = [claude, '-p', prompt, '--plugin-dir', str(plugin_dir), '--output-format', 'stream-json', '--verbose',
               '--max-turns', str(case.get('max_turns', config.get('max_turns', 20)))]
    if config.get('permission_mode'):
        command += ['--permission-mode', config['permission_mode']]
    if model:
        command += ['--model', model]
    command += list(extra_args or [])
    tools = case.get('allowed_tools', config.get('allowed_tools'))
    tools = list(tools or []) + list(case.get('allowed_tools_extra') or [])
    if tools:
        command += ['--allowedTools', *tools]  # variadic: keep it last
    return command


def judge_run(suite, case, run_dir, plugin_dir):
    stream = harness.read_stream(run_dir / 'out.jsonl')
    try:
        verdict = suite['judge'].judge(case, stream, run_dir / 'repo', plugin_dir)
    except Exception as error:  # a judge bug must not hide the other runs
        verdict = {'pass': False, 'score': 0.0, 'summary': 'judge error: %s: %s' % (type(error).__name__, error)}
    (run_dir / 'judge.json').write_text(json.dumps(verdict, indent=2, default=str))
    result = stream['result']
    return stream, {
        'suite': suite['name'], 'case': case['id'], 'pass': bool(verdict.get('pass')), 'score': verdict.get('score'),
        'judge': verdict, 'infra_error': harness.infra_error(stream),
        'cost_usd': result.get('total_cost_usd'), 'duration_ms': result.get('duration_ms'),
        'num_turns': result.get('num_turns'), 'session_error': result.get('is_error'),
        'terminal_reason': result.get('terminal_reason') or result.get('subtype'),
        'claude_version': stream['init'].get('claude_code_version'), 'model': stream['init'].get('model'),
        'dir': str(run_dir)}


def execute(suite, case, index, args, claude):
    run_dir = args.out / suite['name'] / ('%s-r%d' % (case['id'], index))
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    error = None
    started = time.time()
    try:
        suite['fixture'].build(run_dir / 'repo', case)
        command = claude_command(claude, case['prompt'], args.plugin_dir, suite['config'], case, args.model,
                                 args.extra_arg)
        env = {k: v for k, v in os.environ.items() if not k.startswith('AEGISOPS_HARNESS_')}
        env.update({k: str(v) for k, v in (case.get('env') or {}).items()})  # e.g. AEGISOPS_HARNESS_WORKFLOW=full
        if (run_dir / 'bin').is_dir():  # fixture tools (e.g. a fake gh) shadow the real ones
            env['PATH'] = str(run_dir / 'bin') + os.pathsep + env.get('PATH', '')
        timeout = case.get('timeout_s', suite['config'].get('timeout_s', 900))
        with open(run_dir / 'out.jsonl', 'w') as out, open(run_dir / 'err.txt', 'w') as err:
            try:
                proc = subprocess.run(command, cwd=str(run_dir / 'repo'), stdin=subprocess.DEVNULL, stdout=out,
                                      stderr=err, env=env, timeout=timeout)
                if proc.returncode:
                    error = None if os.path.getsize(run_dir / 'out.jsonl') else 'claude exited %d' % proc.returncode
            except subprocess.TimeoutExpired:
                error = 'timeout after %ds' % timeout
    except Exception as exc:
        error = '%s: %s' % (type(exc).__name__, exc)
    _, record = judge_run(suite, case, run_dir, args.plugin_dir)
    record['run'] = index
    # Wall clock of the whole session: a session that waits on background agents emits several `result` events,
    # each with only its own segment's duration, so the last one undercounts badly.
    record['duration_ms'] = int((time.time() - started) * 1000)
    if error:
        record['error'] = error
    outcome = 'INFRA' if record.get('infra_error') else ('PASS' if record['pass'] else ('ERR' if error else 'FAIL'))
    print('%-5s %-10s %-16s r%d  %s  $%.3f %4.0fs' % (outcome,
                                                      suite['name'], case['id'], index,
                                                      (record['judge'] or {}).get('summary', '')[:80],
                                                      record['cost_usd'] or 0, record['duration_ms'] / 1000),
          flush=True)
    return record


def rejudge(suite, cases, args):
    records = []
    for case in cases:
        for run_dir in sorted((args.rejudge / suite['name']).glob('%s-r*' % case['id'])):
            if not (run_dir / 'out.jsonl').exists():
                continue
            _, record = judge_run(suite, case, run_dir, args.plugin_dir)
            record['run'] = int(run_dir.name.rsplit('-r', 1)[1])
            records.append(record)
    return records


def plugin_version(plugin_dir):
    try:
        return json.loads((pathlib.Path(plugin_dir) / '.claude-plugin' / 'plugin.json').read_text()).get('version')
    except (OSError, ValueError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--suite', action='append', required=True,
                        help='passive, tdd, lifecycle or all; repeat or comma-separate')
    parser.add_argument('--runs', type=int, default=1, help='runs per case (default 1)')
    parser.add_argument('--parallel', type=int, default=4, help='concurrent sessions (default 4)')
    parser.add_argument('--plugin-dir', type=pathlib.Path, default=ROOT, help='plugin under test (default: this repo)')
    parser.add_argument('--model', help='model alias or id passed to claude --model (default: the CLI default)')
    parser.add_argument('--out', type=pathlib.Path, help='output folder (default evals/headless/results/<UTC time>)')
    parser.add_argument('--cases', help='comma-separated case ids to run (default: all)')
    parser.add_argument('--claude-bin', help='claude executable (default $CLAUDE_BIN or claude on PATH)')
    parser.add_argument('--extra-arg', action='append', default=[], help='extra argument for claude (repeatable)')
    parser.add_argument('--rejudge', type=pathlib.Path, help='re-judge the recorded runs in this results folder')
    parser.add_argument('--compare', action='store_true', help='exit 1 when a suite regresses against the baseline')
    parser.add_argument('--baseline', type=pathlib.Path, default=HERE / 'baseline.json')
    parser.add_argument('--tolerance', type=float, default=0.10,
                        help='allowed pass-rate drop before a regression is considered (default 0.10)')
    parser.add_argument('--strict', action='store_true',
                        help='fail on any drop beyond the tolerance, even when the Wilson interval reaches the baseline')
    parser.add_argument('--min-judged', type=float, default=0.8,
                        help='share of the planned runs that must be judged (not excluded as infrastructure) for a '
                             'suite to count; below it --compare and --update-baseline exit 3 (default 0.8)')
    parser.add_argument('--update-baseline', action='store_true', help='write these scores into the baseline file')
    args = parser.parse_args(argv)

    names = []
    for value in args.suite:
        for name in value.split(','):
            name = name.strip()
            names += list(SUITES) if name == 'all' else [name] if name else []
    suites = [load_suite(name) for name in dict.fromkeys(names)]
    wanted = set(args.cases.split(',')) if args.cases else None
    args.plugin_dir = args.plugin_dir.resolve()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    if args.rejudge:
        args.rejudge = args.rejudge.resolve()
        args.out = args.out or args.rejudge
    args.out = (args.out or HERE / 'results' / stamp).resolve()
    args.out.mkdir(parents=True, exist_ok=True)

    claude = None
    if not args.rejudge:
        claude = find_claude(args.claude_bin)
        if not claude:
            print('claude CLI not found: install it (npm install -g @anthropic-ai/claude-code) or pass --claude-bin',
                  file=sys.stderr)
            return 2

    all_runs = {}
    for suite in suites:
        cases = [c for c in suite['cases'] if wanted is None or c['id'] in wanted]
        if not cases:
            continue
        if args.rejudge:
            records = rejudge(suite, cases, args)
        else:
            jobs = [(case, index) for case in cases for index in range(1, args.runs + 1)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
                records = list(pool.map(lambda job: execute(suite, job[0], job[1], args, claude), jobs))
        all_runs[suite['name']] = sorted(records, key=lambda r: (r['case'], r['run']))

    versions = {r.get('claude_version') for runs in all_runs.values() for r in runs if r.get('claude_version')}
    models = {r.get('model') for runs in all_runs.values() for r in runs if r.get('model')}
    meta = {'started': stamp, 'plugin_dir': str(args.plugin_dir), 'plugin_version': plugin_version(args.plugin_dir),
            'claude_version': ', '.join(sorted(versions)) or None, 'model': args.model or ', '.join(sorted(models)) or None,
            'runs': args.runs, 'parallel': args.parallel, 'rejudged': bool(args.rejudge)}
    summaries = {name: harness.summarize(runs) for name, runs in all_runs.items()}
    try:
        baseline = json.loads(args.baseline.read_text())
    except (OSError, ValueError):
        baseline = {}
    verdicts = harness.compare(summaries, baseline, args.tolerance, noise_guard=not args.strict,
                               min_judged=args.min_judged, plugin_version=meta['plugin_version'])
    results = {'meta': meta, 'suites': summaries, 'compare': verdicts, 'runs': all_runs,
               'tolerance': args.tolerance, 'strict': args.strict}
    (args.out / 'results.json').write_text(json.dumps(results, indent=2, default=str))
    report = harness.markdown_report(results)
    (args.out / 'report.md').write_text(report)
    print('\n' + report.split('\n## ')[0])
    print('Results: %s\nReport:  %s' % (args.out / 'results.json', args.out / 'report.md'))

    silent = [name for name, verdict in verdicts.items() if verdict.get('no_signal')]
    if args.update_baseline:
        accepted = [name for name in summaries if name not in silent]  # never record a score nobody measured
        if accepted:
            baseline.setdefault('suites', {})
            for name in accepted:
                baseline['suites'][name] = harness.baseline_entry(summaries[name], meta)
            args.baseline.write_text(json.dumps(baseline, indent=2) + '\n')
            print('Baseline updated: ' + ', '.join(accepted))
    regressions = [name for name, verdict in verdicts.items() if verdict['regression']] if args.compare else []
    if regressions:
        print('REGRESSION: ' + ', '.join(regressions))
    if silent and (args.compare or args.update_baseline):
        print('NO SIGNAL: ' + '; '.join('%s (%s)' % (name, verdicts[name]['notes'][0]) for name in silent))
    if regressions:
        return 1
    return 3 if silent and (args.compare or args.update_baseline) else 0


if __name__ == '__main__':
    sys.exit(main())
