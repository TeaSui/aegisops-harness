"""Shared pieces of the headless eval runner: stream-json parsing, Wilson intervals, baseline comparison and reports.

No model calls here; run.py drives the `claude` CLI. Everything in this module is unit-tested on recorded fixtures.
"""
import datetime
import json
import math
import re
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


# ---------------------------------------------------------------------------------------------------------------
# stream-json
# ---------------------------------------------------------------------------------------------------------------

def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return '\n'.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in content)
    return json.dumps(content) if content is not None else ''


def parse_stream(lines):
    """Parse `claude -p --output-format stream-json --verbose` output.

    Returns a dict with `calls` (tool uses in order, each with name, input, result text, is_error), `skills`
    (Skill tool `skill` inputs), `agents` (Agent/Task `subagent_type`), `result` (the final result event or {}),
    `results` (every result event: a session that waits on background agents emits several), `init` (the system init
    event or {}) and `notes` (hook additionalContext strings seen in hook_response events).
    Unparseable lines are skipped.
    """
    calls, by_id, skills, agents, notes, results = [], {}, [], [], [], []
    result, init = {}, {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        kind = message.get('type')
        if kind == 'system' and message.get('subtype') == 'init':
            init = message
        elif kind == 'system' and message.get('subtype') == 'hook_response':
            notes.append(_text(message.get('output') or message.get('stdout') or ''))
        elif kind == 'assistant':
            for part in (message.get('message') or {}).get('content') or []:
                if isinstance(part, dict) and part.get('type') == 'tool_use':
                    call = {'id': part.get('id'), 'name': part.get('name', ''), 'input': part.get('input') or {},
                            'result': None, 'is_error': False}
                    calls.append(call)
                    by_id[call['id']] = call
                    if call['name'] == 'Skill':
                        skills.append(str(call['input'].get('skill', '')))
                    elif call['name'] in ('Agent', 'Task'):
                        agents.append(str(call['input'].get('subagent_type', '')))
        elif kind == 'user':
            content = (message.get('message') or {}).get('content')
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get('type') == 'tool_result' and part.get('tool_use_id') in by_id:
                        call = by_id[part['tool_use_id']]
                        call['result'] = _text(part.get('content'))
                        call['is_error'] = bool(part.get('is_error'))
        elif kind == 'result':
            result = message
            results.append(message)
    return {'calls': calls, 'skills': skills, 'agents': agents, 'result': result, 'results': results, 'init': init,
            'notes': notes}


# A session the account or the API cut short says nothing about the plugin: its run is excluded, not failed.
# Only short system notices count: a model's own summary may well talk about "rate limits".
INFRA = re.compile(r"^\W*(you'?ve hit your .{0,40}limit|claude ai usage limit|usage limit reached|rate limit reached|"
                   r"api error|overloaded|credit balance is too low|request timed out|internal server error|"
                   r"connection error)", re.I)
NOTICE_MAX = 300


def no_model_turn(event):
    """A result event that reports no cost and no output tokens: the CLI never reached a model (no API key, not signed
    in, no network). An event that reports neither field says nothing either way, unless it is an error."""
    cost, tokens = event.get('total_cost_usd'), (event.get('usage') or {}).get('output_tokens')
    reported = cost is not None or tokens is not None or bool(event.get('is_error'))
    return reported and not cost and not tokens


def infra_error(stream):
    """A short reason when the session ended for an account/API reason rather than by itself, else None."""
    results = stream.get('results') or ([stream['result']] if stream.get('result') else [])
    if not results:
        return 'no result event (session crashed, was killed or never started)'
    for event in results:
        text = str(event.get('result') or event.get('error') or '').strip()
        if len(text) <= NOTICE_MAX and INFRA.search(text):
            return 'cut off: %s' % text[:120]
    if all(no_model_turn(event) for event in results):
        text = str(results[-1].get('result') or results[-1].get('error') or '').strip()
        return 'no model turn ($0, no output tokens): %s' % (text[:100] or 'the CLI never reached a model')
    return None


def read_stream(path):
    try:
        with open(path, errors='replace') as handle:
            return parse_stream(handle)
    except OSError:
        return parse_stream([])


def bare(name):
    """`aegisops-harness:spec` -> `spec`."""
    return str(name).split(':')[-1]


# ---------------------------------------------------------------------------------------------------------------
# Statistics and baseline comparison
# ---------------------------------------------------------------------------------------------------------------

def wilson(passed, total, z=1.96):
    """Wilson score interval for a binomial proportion; (0, 1) when total is 0."""
    if total <= 0:
        return 0.0, 1.0
    p = passed / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(runs):
    """Aggregate run records of one suite. `planned` counts every run, `total` only the judged ones."""
    planned = len(runs)
    infra = [r for r in runs if r.get('infra_error')]
    runs = [r for r in runs if not r.get('infra_error')]  # cut off by the account or the API: no signal
    total = len(runs)
    passed = sum(1 for r in runs if r.get('pass'))
    low, high = wilson(passed, total)
    costs = [r.get('cost_usd') or 0.0 for r in runs]
    durations = [r.get('duration_ms') or 0 for r in runs]
    scores = [r.get('score') for r in runs if isinstance(r.get('score'), (int, float))]
    return {'passed': passed, 'total': total, 'rate': passed / total if total else 0.0,
            'wilson95': [round(low, 3), round(high, 3)],
            'mean_score': round(sum(scores) / len(scores), 3) if scores else None,
            'cost_usd': round(sum(costs), 4), 'mean_duration_s': round(sum(durations) / total / 1000, 1) if total else 0,
            'cases': sorted({r['case'] for r in runs}), 'errors': sum(1 for r in runs if r.get('error')),
            'infra_errors': len(infra), 'planned': planned}


def minor(version):
    """'4.0.1' -> ('4', '0'); None when the text is not a version."""
    parts = str(version or '').split('.')
    return tuple(parts[:2]) if len(parts) >= 2 and all(p.isdigit() for p in parts[:2]) else None


def signal(summary, min_judged):
    """(enough judged runs, note). A suite with no judged run, or fewer than `min_judged` of the planned ones, says
    nothing about the plugin: an outage must not read as a green (or a red) result."""
    planned = summary.get('planned', summary['total'])
    need = max(1, math.ceil(min_judged * planned))
    if summary['total'] >= need:
        return True, None
    return False, 'judged %d of %d planned runs (%d excluded as infrastructure); %d needed' % (
        summary['total'], planned, summary.get('infra_errors', 0), need)


def compare(current, baseline, tolerance=0.10, noise_guard=True, min_judged=0.8, plugin_version=None):
    """Compare suite summaries against baseline entries.

    A suite regresses when its pass rate is more than `tolerance` below the baseline rate and, with the noise guard
    on, the baseline rate also lies above the upper bound of the current Wilson 95% interval (so a drop that small-N
    noise can explain is reported, not failed). A suite with too few judged runs is `no-signal` whatever its rate.
    A baseline measured on another minor version of the plugin is flagged `stale`. Returns {suite: verdict dict}.
    """
    verdicts = {}
    for suite, summary in current.items():
        base = (baseline.get('suites') or {}).get(suite)
        enough, shortfall = signal(summary, min_judged)
        if not enough:
            verdicts[suite] = {'status': 'no-signal', 'regression': False, 'no_signal': True, 'stale': False,
                               'baseline': '%d/%d' % (base['passed'], base['total']) if base and base.get('total') else '-',
                               'notes': [shortfall]}
            continue
        if not base or not base.get('total'):
            verdicts[suite] = {'status': 'no-baseline', 'regression': False, 'no_signal': False, 'stale': False}
            continue
        base_rate = base['passed'] / base['total']
        drop = base_rate - summary['rate']
        low, high = wilson(summary['passed'], summary['total'])
        beyond_noise = base_rate > high
        regression = drop > tolerance and (beyond_noise or not noise_guard)
        if regression:
            status = 'regression'
        elif drop > tolerance:
            status = 'drop-within-noise'
        elif drop < -tolerance:
            status = 'improved'
        else:
            status = 'ok'
        notes = []
        if sorted(base.get('cases') or []) and sorted(base.get('cases') or []) != summary.get('cases'):
            notes.append('case set differs from the baseline')
        measured, now = minor(base.get('plugin_version')), minor(plugin_version)
        stale = bool(measured and now and measured != now)
        if stale:
            notes.append('baseline measured on plugin %s, this is %s: re-measure before trusting the comparison'
                         % (base['plugin_version'], plugin_version))
        verdicts[suite] = {'status': status, 'regression': regression, 'no_signal': False, 'stale': stale,
                           'baseline_rate': round(base_rate, 3),
                           'baseline': '%d/%d' % (base['passed'], base['total']), 'rate': round(summary['rate'], 3),
                           'drop': round(drop, 3), 'wilson95': [round(low, 3), round(high, 3)], 'notes': notes}
    return verdicts


def baseline_entry(summary, meta):
    return {'passed': summary['passed'], 'total': summary['total'], 'rate': round(summary['rate'], 3),
            'mean_score': summary.get('mean_score'), 'cases': summary['cases'], 'runs_per_case': meta.get('runs'),
            'model': meta.get('model'), 'claude_version': meta.get('claude_version'),
            'plugin_version': meta.get('plugin_version'), 'cost_usd': summary.get('cost_usd'),
            'accepted': datetime.date.today().isoformat()}


# ---------------------------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------------------------

def _pct(value):
    return '-' if value is None else '%.0f%%' % (100 * value)


def markdown_report(results):
    meta = results.get('meta', {})
    lines = ['# Headless eval report', '',
             '- Started: %s' % meta.get('started', '?'),
             '- Claude Code: %s; model: %s; plugin: %s %s' % (meta.get('claude_version') or '?',
                                                             meta.get('model') or 'CLI default',
                                                             meta.get('plugin_dir', '?'),
                                                             meta.get('plugin_version') or ''),
             '- Runs per case: %s; parallel: %s' % (meta.get('runs'), meta.get('parallel')), '',
             '| Suite | Passed | Rate | Wilson 95% | Mean score | Baseline | Verdict | Cost (USD) | Mean duration | Excluded (infra) |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for suite, summary in results.get('suites', {}).items():
        verdict = (results.get('compare') or {}).get(suite, {})
        lines.append('| %s | %d/%d | %s | %s–%s | %s | %s | %s | %.2f | %.0f s | %d |' % (
            suite, summary['passed'], summary['total'], _pct(summary['rate']), _pct(summary['wilson95'][0]),
            _pct(summary['wilson95'][1]), '-' if summary.get('mean_score') is None else summary['mean_score'],
            verdict.get('baseline', '-'), verdict.get('status', 'not compared')
            + ('' if not verdict.get('notes') else ' (' + '; '.join(verdict['notes']) + ')'),
            summary['cost_usd'], summary['mean_duration_s'], summary.get('infra_errors', 0)))
    for suite, runs in results.get('runs', {}).items():
        lines += ['', '## %s' % suite, '', '| Case | Run | Outcome | Score | Cost (USD) | Duration | Detail |',
                  '|---|---|---|---|---|---|---|']
        for r in runs:
            outcome = 'INFRA' if r.get('infra_error') else ('ERROR' if r.get('error') else ('PASS' if r.get('pass') else 'FAIL'))
            detail = (r.get('judge') or {}).get('summary') or r.get('error') or ''
            lines.append('| %s | %d | %s | %s | %.3f | %.0f s | %s |' % (
                r['case'], r['run'], outcome, '-' if r.get('score') is None else '%.2f' % r['score'],
                r.get('cost_usd') or 0.0, (r.get('duration_ms') or 0) / 1000, str(detail).replace('|', '\\|')))
    return '\n'.join(lines) + '\n'
