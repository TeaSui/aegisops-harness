"""Unit tests for the deterministic parts of evals/: description lint, statistics, baseline
comparison, headless judges on recorded stream-json, and the headless runner driven by a fake `claude` binary.
No test calls the real claude CLI or a model."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVALS = ROOT / 'evals'
HEADLESS = EVALS / 'headless'
TESTDATA = HEADLESS / 'testdata'
sys.path[:0] = [str(HEADLESS), str(HEADLESS / 'fixtures')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


descriptions = load(EVALS / 'descriptions' / 'run.py', 'eval_descriptions_run')
harness = load(HEADLESS / 'harness.py', 'harness')
runner = load(HEADLESS / 'run.py', 'eval_headless_run')
passive_judge = load(HEADLESS / 'suites' / 'passive' / 'judge.py', 'eval_test_passive_judge')
tdd_judge = load(HEADLESS / 'suites' / 'tdd' / 'judge.py', 'eval_test_tdd_judge')
lifecycle_judge = load(HEADLESS / 'suites' / 'lifecycle' / 'judge.py', 'eval_test_lifecycle_judge')


def quiet(function, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = function(*args)
    return code, out.getvalue()


def stream(name):
    return harness.read_stream(TESTDATA / name)


class DescriptionLintTest(unittest.TestCase):
    def make(self, root, files, flag=True):
        for rel, text in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            text = textwrap.dedent(text).lstrip()
            if flag and text.startswith('---\n'):  # AegisOps-Harness skills and commands are slash-command only
                text = '---\ndisable-model-invocation: true\n' + text[4:]
            path.write_text(text)

    BASE = {
        'skills/alpha/SKILL.md': '''
            ---
            name: alpha
            description: |
              Use when a Kafka consumer needs retries, a dead-letter topic and idempotent handling of
              order events; covers backoff and poison messages.
            ---
            body
            ''',
        'skills/beta/SKILL.md': '''
            ---
            name: beta
            description: "Use when a Kafka consumer needs retries, a dead-letter topic and idempotent handling of order events, with backoff."
            ---
            ''',
        'skills/gamma/SKILL.md': '''
            ---
            name: gamma
            description: >
              Use before writing a Postgres migration: zero-downtime expand and contract steps, index
              creation without locks and rollback plans.
            ---
            ''',
        'commands/delta.md': '''
            ---
            description: Use when the user asks for a changelog entry for a release, written from the merged pull requests and tags.
            ---
            ''',
    }

    def test_parse_fields_handles_block_and_quoted_scalars(self):
        fields = descriptions.parse_fields('name: x\ndescription: |\n  line one\n  line two\nmodel: "sonnet"\n')
        self.assertEqual(fields['description'], 'line one\nline two')
        self.assertEqual(fields['model'], 'sonnet')
        folded = descriptions.parse_fields('description: >\n  a\n  b\nother: 1\n')
        self.assertEqual(folded['description'], 'a b')

    def test_collision_is_detected_and_allowlist_accepts_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.make(root, self.BASE)
            code, out = quiet(descriptions.main, ['--root', str(root), '--allowlist', str(root / 'none.json')])
            self.assertEqual(code, 1, out)
            self.assertIn('COLLISION', out)
            self.assertIn('alpha <> beta', out)
            self.assertNotIn('gamma', out.split('COLLISION', 1)[1].split('\n')[0])
            (root / 'allow.json').write_text(json.dumps({'pairs': [{'pair': ['beta', 'alpha'], 'reason': 'test'}]}))
            code, out = quiet(descriptions.main, ['--root', str(root), '--allowlist', str(root / 'allow.json')])
            self.assertEqual(code, 0, out)
            self.assertIn('allowed', out)

    def test_stale_allowlist_entries_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            files = dict(self.BASE)
            del files['skills/beta/SKILL.md']
            self.make(root, files)
            (root / 'allow.json').write_text(json.dumps({'pairs': [{'pair': ['alpha', 'gamma'], 'reason': 'old'}]}))
            code, out = quiet(descriptions.main, ['--root', str(root), '--allowlist', str(root / 'allow.json')])
            self.assertEqual(code, 0, out)
            self.assertIn('stale', out)

    def test_lint_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.make(root, {
                'skills/short/SKILL.md': '---\nname: short\ndescription: Use when short.\n---\n',
                'skills/wrongname/SKILL.md': '---\nname: other\ndescription: Use when the folder and the name '
                                             'differ, which breaks namespaced invocation of this skill entirely.\n---\n',
                'skills/noflag/SKILL.md': '---\nname: noflag\ndescription: A long description that only '
                                          'says what this does, and leaves the model free to load it by itself.\n---\n',
                'skills/nofront/SKILL.md': 'no frontmatter\n',
                'commands/long.md': '---\ndescription: Use when ' + 'x' * 1100 + '\n---\n',
            }, flag=False)
            errors, warnings, _ = descriptions.lint(root, descriptions.collect(root), None)
            text = '\n'.join(errors)
            self.assertIn('skills/short/SKILL.md: description is', text)
            self.assertIn('does not match the folder', text)
            self.assertIn('skills/noflag/SKILL.md: needs disable-model-invocation: true', text)
            self.assertIn('skills/nofront/SKILL.md: missing frontmatter', text)
            self.assertIn('commands/long.md: description is', text)
            self.assertTrue(any('YAML parsing skipped' in w for w in warnings))

    def test_trigger_language(self):
        for text in ('Use when X happens.', 'Use in the full workflow once the plan exists.', 'Triggers on: Kafka.',
                     'load it only if the block is missing', 'Use for /goal or requests to handle it'):
            self.assertTrue(descriptions.TRIGGER.search(text), text)
        self.assertFalse(descriptions.TRIGGER.search('Reference for drafting security rules.'))

    def test_similarity_is_symmetric_and_bounded(self):
        texts = {'a': 'kafka consumer retries dead letter', 'b': 'kafka consumer retries dead letter',
                 'c': 'postgres index migration'}
        vectors = descriptions.tfidf_vectors(texts)
        self.assertAlmostEqual(descriptions.cosine(vectors['a'], vectors['b']), 1.0, places=6)
        self.assertAlmostEqual(descriptions.cosine(vectors['a'], vectors['c']), 0.0, places=6)
        self.assertEqual([p['pair'] for p in descriptions.similar_pairs(texts, 0.5)], [['a', 'b']])

    def test_plugin_descriptions_pass(self):
        code, out = quiet(descriptions.main, [])
        self.assertEqual(code, 0, out)


class StatisticsTest(unittest.TestCase):
    def test_wilson_interval(self):
        self.assertEqual(harness.wilson(0, 0), (0.0, 1.0))
        low, high = harness.wilson(12, 12)
        self.assertAlmostEqual(low, 0.7575, places=3)
        self.assertEqual(high, 1.0)
        low, high = harness.wilson(16, 18)
        self.assertAlmostEqual(low, 0.6720, places=3)
        self.assertAlmostEqual(high, 0.9690, places=3)
        low, high = harness.wilson(0, 5)
        self.assertEqual(low, 0.0)
        self.assertLess(high, 0.5)

    def summary(self, passed, total, cases=None):
        return dict(harness.summarize([{'case': c, 'pass': i < passed} for i, c in
                                       enumerate(cases or ['c%d' % i for i in range(total)])]))

    BASELINE = {'suites': {'tdd': {'passed': 12, 'total': 12}, 'passive': {'passed': 16, 'total': 18}}}

    def test_compare_flags_drops_beyond_tolerance_and_noise(self):
        verdict = harness.compare({'tdd': self.summary(9, 12)}, self.BASELINE)['tdd']
        self.assertEqual(verdict['status'], 'regression')
        self.assertTrue(verdict['regression'])

    def test_compare_tolerates_small_drops(self):
        verdict = harness.compare({'tdd': self.summary(11, 12)}, self.BASELINE)['tdd']
        self.assertEqual(verdict['status'], 'ok')

    def test_compare_noise_guard_and_strict_mode(self):
        # 14/18 is 11 points below 16/18, but the Wilson interval of 14/18 still reaches 0.889.
        verdict = harness.compare({'passive': self.summary(14, 18)}, self.BASELINE)['passive']
        self.assertEqual(verdict['status'], 'drop-within-noise')
        self.assertFalse(verdict['regression'])
        strict = harness.compare({'passive': self.summary(14, 18)}, self.BASELINE, noise_guard=False)['passive']
        self.assertTrue(strict['regression'])

    def test_compare_without_baseline_and_improvement(self):
        verdicts = harness.compare({'lifecycle': self.summary(1, 1), 'passive': self.summary(18, 18)}, self.BASELINE)
        self.assertEqual(verdicts['lifecycle']['status'], 'no-baseline')
        self.assertEqual(verdicts['passive']['status'], 'improved')

    def test_case_set_change_is_noted(self):
        base = {'suites': {'tdd': {'passed': 3, 'total': 3, 'cases': ['a', 'b', 'c']}}}
        verdict = harness.compare({'tdd': self.summary(1, 1, ['a'])}, base)['tdd']
        self.assertIn('case set differs from the baseline', verdict['notes'])

    def test_eta_10_compare_needs_enough_judged_runs(self):
        # 10 planned, 3 cut off: 7 judged is below the default 80%, so the comparison carries no signal.
        runs = [{'case': 'c%d' % i, 'pass': True} for i in range(7)]
        runs += [{'case': 'x%d' % i, 'pass': False, 'infra_error': 'usage limit'} for i in range(3)]
        summary = harness.summarize(runs)
        self.assertEqual((summary['total'], summary['planned']), (7, 10))
        verdict = harness.compare({'tdd': summary}, self.BASELINE)['tdd']
        self.assertEqual(verdict['status'], 'no-signal')
        self.assertTrue(verdict['no_signal'])
        self.assertIn('judged 7 of 10', ' '.join(verdict['notes']))
        enough = harness.summarize(runs[:7] + [{'case': 'c8', 'pass': True}] + runs[7:9])
        self.assertFalse(harness.compare({'tdd': enough}, self.BASELINE)['tdd'].get('no_signal'))
        loose = harness.compare({'tdd': summary}, self.BASELINE, min_judged=0.5)['tdd']
        self.assertFalse(loose.get('no_signal'))

    def test_eta_10_no_signal_also_without_a_baseline(self):
        empty = harness.summarize([{'case': 'c', 'pass': False, 'infra_error': 'no model turn'}])
        verdict = harness.compare({'new-suite': empty}, {'suites': {}})['new-suite']
        self.assertEqual(verdict['status'], 'no-signal')
        self.assertTrue(verdict['no_signal'])

    def test_eta_12_stale_baseline_is_flagged(self):
        base = {'suites': {'tdd': {'passed': 8, 'total': 8, 'plugin_version': '4.0.0'}}}
        verdict = harness.compare({'tdd': self.summary(8, 8)}, base, plugin_version='5.0.0')['tdd']
        self.assertTrue(verdict['stale'])
        self.assertIn('baseline measured on plugin 4.0.0, this is 5.0.0', ' '.join(verdict['notes']))
        report = harness.markdown_report({'meta': {}, 'suites': {'tdd': self.summary(8, 8)}, 'compare': {'tdd': verdict},
                                          'runs': {}})
        self.assertIn('baseline measured on plugin 4.0.0', report)
        patch = harness.compare({'tdd': self.summary(8, 8)}, base, plugin_version='4.0.3')['tdd']
        self.assertFalse(patch['stale'])  # a patch release keeps the baseline
        unknown = harness.compare({'tdd': self.summary(8, 8)}, self.BASELINE, plugin_version='5.0.0')['tdd']
        self.assertFalse(unknown['stale'])  # a baseline that names no version cannot be called stale

    def test_summary_and_report(self):
        runs = [{'case': 'a', 'run': 1, 'pass': True, 'score': 1.0, 'cost_usd': 0.5, 'duration_ms': 3000,
                 'judge': {'summary': 'hit x|y'}},
                {'case': 'b', 'run': 1, 'pass': False, 'score': 0.0, 'cost_usd': 0.25, 'duration_ms': 1000,
                 'error': 'timeout after 5s', 'judge': {}}]
        summary = harness.summarize(runs)
        self.assertEqual((summary['passed'], summary['total'], summary['cost_usd'], summary['errors']), (1, 2, 0.75, 1))
        report = harness.markdown_report({'meta': {}, 'suites': {'s': summary}, 'compare': {}, 'runs': {'s': runs}})
        self.assertIn('| s | 1/2 | 50% |', report)
        self.assertIn('hit x\\|y', report)
        self.assertIn('ERROR', report)


class StreamAndJudgeTest(unittest.TestCase):
    def test_parse_stream(self):
        parsed = stream('passive_hit.jsonl')
        self.assertEqual(parsed['skills'], ['aegisops-harness:expert-lens'])
        self.assertEqual(parsed['result']['total_cost_usd'], 0.25)
        self.assertEqual(parsed['init']['claude_code_version'], '9.9.9')
        self.assertEqual(parsed['calls'][0]['result'], 'Launching skill: aegisops-harness:expert-lens')
        self.assertIn('AegisOps-Harness-autopilot', parsed['notes'][0])
        self.assertEqual(harness.read_stream(TESTDATA / 'missing.jsonl')['calls'], [])

    def test_infra_errors_are_recognised(self):
        # Seen for real: three lifecycle runs cut off together by the account's usage limit were scored as FAIL.
        self.assertIn('limit', harness.infra_error(stream('limit_hit.jsonl')))
        self.assertIsNone(harness.infra_error(stream('passive_miss.jsonl')))
        self.assertIsNone(harness.infra_error(stream('passive_hit.jsonl')))
        self.assertIn('no result', harness.infra_error(harness.parse_stream([])))
        # A final summary that talks about rate limits is the model's own text, not a cutoff.
        summary = harness.parse_stream([json.dumps({'type': 'result', 'subtype': 'success', 'result':
                                                    'Refunds are ready. Before exposing them add permission checks, '
                                                    'logging and rate limits. ' + 'More detail. ' * 40})])
        self.assertIsNone(harness.infra_error(summary))
        for text in ('API Error: 529 Overloaded', 'Credit balance is too low', 'Rate limit reached for requests'):
            parsed = harness.parse_stream([json.dumps({'type': 'result', 'is_error': True, 'result': text})])
            self.assertIsNotNone(harness.infra_error(parsed), text)

    def test_eta_10_session_without_a_model_turn_is_infra(self):
        # CI run 45165209409: the API key was empty, every session ended in 1-2 s at $0.000, and the passive suite
        # scored 18/18 because a session that does nothing also invokes nothing. The stream is rebuilt from that log.
        reason = harness.infra_error(stream('no_model_turn.jsonl'))
        self.assertIsNotNone(reason)
        self.assertIn('no model turn', reason)
        for name in ('passive_hit.jsonl', 'passive_miss.jsonl', 'tdd_red_first.jsonl'):
            self.assertIsNone(harness.infra_error(stream(name)), name)
        # Cost unreported but tokens produced: a model ran.
        ran = harness.parse_stream([json.dumps({'type': 'result', 'total_cost_usd': 0, 'usage': {'output_tokens': 12},
                                                'result': 'done'})])
        self.assertIsNone(harness.infra_error(ran))
        # No cost or usage field at all (older CLI): nothing to conclude from.
        bare = harness.parse_stream([json.dumps({'type': 'result', 'subtype': 'success', 'result': 'done'})])
        self.assertIsNone(harness.infra_error(bare))
        # Several result events (a session that waited on background agents): one paid segment is enough.
        mixed = harness.parse_stream([json.dumps({'type': 'result', 'total_cost_usd': 0.4, 'result': 'waiting'}),
                                      json.dumps({'type': 'result', 'total_cost_usd': 0, 'result': 'done'})])
        self.assertIsNone(harness.infra_error(mixed))

    def test_passive_judge_alone_would_pass_a_dead_session(self):
        # Why the exclusion above matters: silence is also what a session that never started looks like.
        self.assertTrue(passive_judge.judge({'silent': True}, stream('no_model_turn.jsonl'))['pass'])

    def test_summary_excludes_infra_errors(self):
        runs = [{'case': 'a', 'pass': True}, {'case': 'b', 'pass': False},
                {'case': 'c', 'pass': False, 'infra_error': 'usage limit'}]
        summary = harness.summarize(runs)
        self.assertEqual((summary['passed'], summary['total'], summary['infra_errors']), (1, 2, 1))
        empty = harness.summarize([{'case': 'c', 'pass': False, 'infra_error': 'usage limit'}])
        self.assertEqual(empty['total'], 0)
        verdict = harness.compare({'x': empty}, {'suites': {'x': {'passed': 3, 'total': 3}}})['x']
        self.assertFalse(verdict['regression'])  # not a regression of the plugin ...
        self.assertTrue(verdict['no_signal'])    # ... and not a result either

    def test_lifecycle_judge_ignores_template_comments(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('lifecycle_judge', HEADLESS / 'suites' / 'lifecycle' / 'judge.py')
        judge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(judge)
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp) / 'docs' / 'specs' / 'x'
            folder.mkdir(parents=True)
            (folder / 'spec-check.md').write_text('# Spec check\n<!--\n- [ ] G1: <question>\n-->\n'
                                                  '- [x] G1: real guess — resolved: RFD-1\n')
            self.assertTrue(judge.score_spec(folder)['artifacts']['spec-check'])

    def test_passive_judge(self):
        self.assertTrue(passive_judge.judge({'expect': ['expert-lens']}, stream('passive_hit.jsonl'))['pass'])
        agent = passive_judge.judge({'expect': ['fintech-security', 'security-engineer-subagent']},
                                    stream('passive_agent.jsonl'))
        self.assertTrue(agent['pass'])
        self.assertFalse(passive_judge.judge({'silent': True}, stream('passive_hit.jsonl'))['pass'])
        self.assertIn('activated: aegisops-harness:', passive_judge.judge({'silent': True}, stream('passive_agent.jsonl'))['summary'])
        miss = passive_judge.judge({'expect': ['review']}, stream('passive_miss.jsonl'))
        self.assertFalse(miss['pass'])
        self.assertIn('code-review', miss['summary'])

    def test_tdd_judge_red_first(self):
        verdict = tdd_judge.judge({}, stream('tdd_red_first.jsonl'))
        self.assertEqual(verdict['events'], ['test', 'red', 'prod', 'green'])
        self.assertTrue(verdict['pass'])

    def test_tdd_judge_code_first_fails(self):
        verdict = tdd_judge.judge({}, stream('tdd_code_first.jsonl'))
        self.assertFalse(verdict['red_before_prod'])
        self.assertTrue(verdict['tested_after_last_edit'])
        self.assertFalse(verdict['pass'])

    def test_tdd_judge_ignores_blocked_edits_and_needs_a_final_run(self):
        verdict = tdd_judge.judge({}, stream('tdd_blocked_then_red.jsonl'))
        self.assertEqual(verdict['events'], ['test', 'red', 'prod'])
        self.assertTrue(verdict['red_before_prod'])
        self.assertFalse(verdict['tested_after_last_edit'])
        self.assertFalse(verdict['pass'])

    def test_tdd_red_detection(self):
        self.assertTrue(tdd_judge.RED.search('# fail 2'))
        self.assertTrue(tdd_judge.RED.search('Tests: 1 failed, 3 passed'))
        self.assertFalse(tdd_judge.RED.search('Tests: 0 failed, 3 passed\n# fail 0'))

    SPEC = {
        'README.md': '---\nstatus: reviewed\nkey: RFD\nsecurity: required\n---\n# Refunds\n',
        'requirements.md': ('### RFD-1: Refund a transfer\nPriority: must\nAcceptance:\n- Given a transfer, when '
                            'refunded, then the sender is credited.\nVerify: test\n\n### RFD-2: Once only\n'
                            'Acceptance:\n- A second refund is rejected.\n'),
        'spec-check.md': '- [x] G1: currency? — resolved: RFD-1 says the transfer currency\n',
        'plan.md': ('- [x] T1: Refund model\n  - covers: RFD-1, RFD-2\n  - depends: none\n  - owner: main\n'
                    '  - files: src/wallet.js\n'),
        'ledger.md': ('- 2026-11-19T10:00:00Z advance proposed→accepted\n- 2026-11-19T10:01:00Z advance accepted→planned\n'
                      '- 2026-11-19T10:02:00Z advance planned→building\n'
                      '- 2026-11-19T10:40:03Z task-done T1 exit=0 fingerprint=3f9c cmd="npm test"\n'
                      '- 2026-11-19T11:15:47Z verify exit=0 fingerprint=8a01 cmd="npm test"\n'
                      '- 2026-11-19T11:16:00Z advance building→verified\n'),
        'review.md': '---\nfingerprint: 8a01\n---\n## Spec\n- [x] S1 (must): x — fixed: src/wallet.js:4\n## Standards\n',
    }

    def make_repo(self, root, files):
        spec = root / 'repo' / 'docs' / 'specs' / 'refunds'
        spec.mkdir(parents=True)
        for name, text in files.items():
            (spec / name).write_text(text)
        return root / 'repo'

    def test_lifecycle_judge_scores_stages_without_aidlc(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(pathlib.Path(tmp), self.SPEC)
            verdict = lifecycle_judge.judge({'pass_score': 0.67}, harness.parse_stream([]), repo, pathlib.Path(tmp))
            self.assertEqual(verdict['artifacts'], {'spec': True, 'spec-check': True, 'plan': True, 'build': True,
                                                    'review': True, 'ship': False})
            self.assertAlmostEqual(verdict['score'], 5 / 6, places=3)
            self.assertTrue(verdict['pass'])
            self.assertIn('not found', verdict['aidlc_status_note'])
            self.assertEqual(verdict['stage'], 'reviewed')  # from README when aidlc is unavailable
            self.assertEqual(len(verdict['advances']), 4)
            self.assertAlmostEqual(verdict['gate_discipline'], 4 / 5, places=3)

    def test_lifecycle_judge_partial_credit_and_open_guesses(self):
        files = {k: v for k, v in self.SPEC.items() if k in ('README.md', 'requirements.md')}
        files['spec-check.md'] = '- [ ] G1: open guess\n'
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(pathlib.Path(tmp), files)
            verdict = lifecycle_judge.judge({}, harness.parse_stream([]), repo, pathlib.Path(tmp))
            self.assertEqual(verdict['score'], round(1 / 6, 3))
            self.assertFalse(verdict['artifacts']['spec-check'])
            self.assertFalse(verdict['pass'])

    def test_lifecycle_judge_with_no_spec_scores_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / 'repo').mkdir()
            verdict = lifecycle_judge.judge({}, harness.parse_stream([]), pathlib.Path(tmp) / 'repo', None)
            self.assertEqual(verdict['score'], 0.0)
            self.assertIsNone(verdict['spec'])

    @unittest.skipUnless(shutil.which('node') and shutil.which('npm'), 'needs node and npm')
    def test_lifecycle_outcome_judge_scores_the_result_not_the_artifacts(self):
        good = textwrap.dedent('''
            const balances = new Map(); const transfers = new Map(); let next = 1;
            export function deposit(u, a) { balances.set(u, (balances.get(u) || 0) + a); }
            export const balance = (u) => balances.get(u) || 0;
            export function transfer(f, t, a) { deposit(f, -a); deposit(t, a); const id = next++;
              transfers.set(id, { f, t, a, refunded: false }); return id; }
            export function refund(id, amount) { const x = transfers.get(id);
              if (!x || x.refunded) throw new Error('no'); const a = amount ?? x.a;
              if (!(a > 0) || a > x.a) throw new Error('bad'); x.refunded = true; deposit(x.t, -a); deposit(x.f, a); }
        ''')
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / 'repo'
            (repo / 'src').mkdir(parents=True)
            (repo / 'src' / 'wallet.js').write_text(good)
            (repo / 'package.json').write_text('{"type": "module", "scripts": {"test": "node -e 0"}}')
            (pathlib.Path(tmp) / 'gh-state').mkdir()
            (pathlib.Path(tmp) / 'gh-state' / 'prs.json').write_text('[{"number": 1}]')
            events = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 't1', 'name': 'Bash',
                       'input': {'command': 'gh pr create --body "Threats checked: double refund"'}}]}}]
            verdict = lifecycle_judge.judge({'judge': 'outcome'}, harness.parse_stream(map(json.dumps, events)), repo)
            self.assertTrue(verdict['pass'], verdict['summary'])
            (repo / 'src' / 'wallet.js').write_text(good.replace("if (!x || x.refunded)", "if (!x)"))
            (pathlib.Path(tmp) / 'gh-state' / 'prs.json').write_text('[]')
            verdict = lifecycle_judge.judge({'judge': 'outcome'}, harness.parse_stream([]), repo)
            self.assertFalse(verdict['pass'])
            self.assertFalse(verdict['checks']['at_most_once'])
            self.assertFalse(verdict['checks']['pr_opened'])

    def test_lifecycle_judge_reads_aidlc_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo = self.make_repo(root, dict(self.SPEC, **{'ship.md': (
                '---\ndecision: GO\nversion: n/a — fixture\n---\n## Checks\n- CI: green\n## Rollback\nRevert the merge.\n'
                '## Post-release verification\nRun the smoke test.\n')}))
            (root / 'plugin' / 'scripts').mkdir(parents=True)
            (root / 'plugin' / 'scripts' / 'aidlc.py').write_text(
                'import json, sys\nassert sys.argv[1:4] == ["status", "--json", "--repo"]\n'
                'print(json.dumps({"specs": [{"spec": "docs/specs/refunds", "stage": "shipped", "next": "implemented"}]}))\n')
            verdict = lifecycle_judge.judge({}, harness.parse_stream([]), repo, root / 'plugin')
            self.assertEqual(verdict['score'], 1.0)
            self.assertEqual(verdict['stage'], 'shipped')
            self.assertEqual(verdict['aidlc_status'], {'refunds': 'shipped'})

    def test_status_shapes(self):
        self.assertEqual(lifecycle_judge.stages_from_status([{'path': 'a/docs/specs/x', 'status': 'planned'}]),
                         {'x': 'planned'})
        self.assertEqual(lifecycle_judge.stages_from_status({'specs': {'y': {'stage': 'building'}}}), {'y': 'building'})
        self.assertEqual(lifecycle_judge.stages_from_status({'unexpected': 1}), {})


FAKE_CLAUDE = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
prompt = args[args.index('-p') + 1]
assert '--plugin-dir' in args and '--output-format' in args
skill = 'aegisops-harness:spec' if 'clamp' in prompt else 'code-review'
print(json.dumps({"type": "system", "subtype": "init", "claude_code_version": "0.0.0-fake", "model": "fake"}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "1", "name": "Skill",
                                                               "input": {"skill": skill}}]}}))
print(json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 0.01, "duration_ms": 1500, "num_turns": 1}))
'''


class HeadlessRunnerTest(unittest.TestCase):
    def test_suites_load_and_fixture_builds(self):
        for name in runner.SUITES:
            suite = runner.load_suite(name)
            self.assertTrue(suite['cases'], name)
            for case in suite['cases']:
                self.assertTrue(case.get('id') and case.get('prompt'), case)
        with tempfile.TemporaryDirectory() as tmp:
            repo = runner.load_suite('tdd')['fixture'].build(pathlib.Path(tmp) / 'repo', {'setup': 'failing'})
            self.assertIn('a * b', (repo / 'src' / 'math.js').read_text())
            self.assertTrue((repo / '.git').is_dir())

    def test_command_line(self):
        command = runner.claude_command('claude', 'do it', '/p', {'max_turns': 8, 'permission_mode': 'acceptEdits',
                                                                  'allowed_tools': ['Read', 'Bash(npm *)']},
                                        {}, 'sonnet', ['--foo'])
        self.assertEqual(command[:3], ['claude', '-p', 'do it'])
        self.assertEqual(command[-3:], ['--allowedTools', 'Read', 'Bash(npm *)'])
        for flag in ('--plugin-dir', '--verbose', '--permission-mode', '--model', '--foo'):
            self.assertIn(flag, command)

    def test_end_to_end_with_a_fake_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            fake = tmp / 'claude'
            fake.write_text(FAKE_CLAUDE.replace('#!/usr/bin/env python3', '#!' + sys.executable))
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            baseline = tmp / 'baseline.json'
            baseline.write_text(json.dumps({'suites': {'passive': {'passed': 2, 'total': 2}}}))
            out = tmp / 'out'
            code, printed = quiet(runner.main, ['--suite', 'passive', '--cases', '01-feature,03-expert', '--runs', '2',
                                                '--parallel', '2', '--claude-bin', str(fake), '--out', str(out),
                                                '--baseline', str(baseline), '--compare', '--strict'])
            results = json.loads((out / 'results.json').read_text())
            self.assertEqual(results['suites']['passive']['passed'], 2)
            self.assertEqual(results['suites']['passive']['total'], 4)
            self.assertAlmostEqual(results['suites']['passive']['cost_usd'], 0.04)
            self.assertEqual(code, 1, printed)  # 50% against a 100% baseline, strict
            self.assertTrue((out / 'report.md').read_text().startswith('# Headless eval report'))
            self.assertTrue((out / 'passive' / '03-expert-r2' / 'judge.json').is_file())
            # Re-judging the recorded runs needs no claude binary and gives the same result.
            code, printed = quiet(runner.main, ['--suite', 'passive', '--rejudge', str(out),
                                                '--baseline', str(baseline), '--update-baseline'])
            self.assertEqual(code, 0, printed)
            self.assertEqual(json.loads(baseline.read_text())['suites']['passive']['passed'], 2)
            self.assertEqual(json.loads(baseline.read_text())['suites']['passive']['total'], 4)


DEAD_CLAUDE = '''#!/usr/bin/env python3
import json, sys
print(json.dumps({"type": "system", "subtype": "init", "claude_code_version": "0.0.0-fake", "model": "fake"}))
print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "total_cost_usd": 0,
                  "usage": {"input_tokens": 0, "output_tokens": 0}, "result": "Invalid API key"}))
sys.exit(1)
'''


class NoSignalTest(unittest.TestCase):
    """ETA-10: an eval run that reached no model is not a green run."""

    def run_suite(self, tmp, script, *extra):
        fake = tmp / 'claude'
        fake.write_text(script.replace('#!/usr/bin/env python3', '#!' + sys.executable))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        baseline = tmp / 'baseline.json'
        if not baseline.exists():
            baseline.write_text(json.dumps({'suites': {'passive': {'passed': 2, 'total': 2}}}))
        code, printed = quiet(runner.main, ['--suite', 'passive', '--cases', '01-feature,03-expert', '--runs', '1',
                                            '--parallel', '2', '--claude-bin', str(fake), '--out', str(tmp / 'out'),
                                            '--baseline', str(baseline), *extra])
        return code, printed, json.loads((tmp / 'out' / 'results.json').read_text()), baseline

    def test_eta_10_dead_sessions_fail_the_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, results, _ = self.run_suite(pathlib.Path(tmp), DEAD_CLAUDE, '--compare')
            self.assertEqual(results['suites']['passive']['total'], 0)
            self.assertEqual(results['suites']['passive']['infra_errors'], 2)
            self.assertEqual(results['compare']['passive']['status'], 'no-signal')
            self.assertEqual(code, 3, printed)
            self.assertIn('NO SIGNAL: passive', printed)

    def test_eta_10_baseline_is_not_overwritten_without_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, _, baseline = self.run_suite(pathlib.Path(tmp), DEAD_CLAUDE, '--update-baseline')
            self.assertEqual(code, 3, printed)
            self.assertEqual(json.loads(baseline.read_text())['suites']['passive'], {'passed': 2, 'total': 2})

    def test_live_sessions_still_compare(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, printed, results, _ = self.run_suite(pathlib.Path(tmp), FAKE_CLAUDE, '--compare')
            self.assertEqual(results['suites']['passive']['total'], 2)
            self.assertFalse(results['compare']['passive'].get('no_signal'))
            self.assertNotEqual(code, 3, printed)


class WorkflowFilesTest(unittest.TestCase):
    def test_ci_runs_the_deterministic_evals(self):
        ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
        for command in ('unittest discover -s tests', 'scripts/check-setup.py', 'evals/descriptions/run.py'):
            self.assertIn(command, ci)
        evals = (ROOT / '.github' / 'workflows' / 'evals.yml').read_text()
        self.assertIn('ANTHROPIC_API_KEY', evals)
        self.assertIn('--compare', evals)

    def test_eta_10_eval_workflow_stops_without_a_key(self):
        # The only scheduled run so far had an empty key and spent its time scoring dead sessions.
        evals = (ROOT / '.github' / 'workflows' / 'evals.yml').read_text()
        preflight, _, rest = evals.partition('Run headless suites')
        self.assertIn('ANTHROPIC_API_KEY is not set', preflight)
        self.assertIn('exit 1', preflight)


if __name__ == '__main__':
    unittest.main()
