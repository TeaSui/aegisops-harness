"""Tests for scripts/aidlc.py, the AIDLC lifecycle engine (references/aidlc.md).

Every git call runs with GIT_CONFIG_GLOBAL=/dev/null and GIT_CONFIG_NOSYSTEM=1, HOME is a temp folder and
AIDLC_GH points at a missing or fake `gh`, so the real user config, state and GitHub are never touched.
Run: python3 -m unittest discover -s tests -v
"""
import contextlib
import datetime
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / 'references' / 'aidlc.md'


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


aidlc = load('aidlc', 'scripts/aidlc.py')
mpr = load('mark_pr_review', 'scripts/mark-pr-review.py')

REQS = """# Requirements

### RFD-1: Refund a captured payment
Priority: must
Acceptance:
- Given a captured payment, when a full refund is requested, then it is refunded.
Verify: test

### RFD-2: Refunds are visible to support staff
Acceptance:
- p95 visibility delay <= 60 s.
Verify: check — k6 run load/refund-visibility.js
"""
SPEC_CHECK = '- [x] G1: Which currency? — resolved: RFD-1 says the capture currency\n'
PLAN = """# Plan

- [ ] T1: Refund model
  - covers: RFD-1
  - depends: none
  - owner: backend-engineer-subagent
  - files: src/refunds/model.py (new)
- [ ] T2: Load test
  - covers: RFD-2
  - depends: T1
  - owner: platform-engineer-subagent
  - files: load/refund-visibility.js (new)
"""
REVIEW = """---
fingerprint: {fp}
reviewers: spec=code-reviewer standards=code-reviewer
---
## Spec
- [x] S1 (must): over-capture is not rejected — fixed: src/refunds/model.py:3
## Standards
- [x] Q1 (nit): rename amt — cleared: matches the PSP field name
## QA
Verdict: GO
"""
SHIP = """---
decision: GO
version: n/a — internal service
---
## Checks
- CI: green
## Rollback
Revert the merge commit.
## Post-release verification
Smoke test the refund endpoint.
"""
ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
       'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com'}


def doc_blocks():
    """{heading text without backticks: first fenced block under that ### heading} from references/aidlc.md."""
    blocks, heading, inside, lines = {}, None, False, []
    for line in DOC.read_text().split('\n'):
        if inside:
            if line.startswith('```'):
                blocks.setdefault(heading, '\n'.join(lines) + '\n')
                inside = False
            else:
                lines.append(line)
            continue
        match = re.match(r'^###\s+(.*?)\s*$', line)
        if match:
            heading = match.group(1).replace('`', '')
        elif line.startswith('```') and heading:
            inside, lines = True, []
    return blocks


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = pathlib.Path(tmp.name).resolve()
        self.home, self.repo = self.base / 'home', self.base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        patcher = mock.patch.dict(os.environ, {**ENV, 'HOME': str(self.home), 'AIDLC_GH': str(self.base / 'no-gh')})
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        self.git('init', '-q', '-b', 'main')
        self.write('.gitignore', 'ignored/\n*.log\n')
        self.write('src/app.py', 'x = 1\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.spec = self.repo / 'docs' / 'specs' / 'refunds'

    # helpers -------------------------------------------------------------------------------------------------
    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, message='work'):
        self.git('add', '-A')
        self.git('commit', '-qm', message)

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def spec_file(self, name, text, spec=None):
        path = (spec or self.spec) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def readme(self, spec=None, body='# refunds\n', **meta):
        fields = {'status': 'proposed', 'key': 'RFD', 'security': 'required', 'contract': 'none',
                  'accepted_by': 'Tea (2026-11-19)', 'updated': '2026-11-19'}
        fields.update(meta)
        text = '---\n' + ''.join(f'{k}: {v}\n' for k, v in fields.items() if v is not None) + '---\n' + body
        return self.spec_file('README.md', text, spec)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = aidlc.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def cli_json(self, *argv):
        code, out, err = self.cli(*argv, '--json')
        try:
            return code, json.loads(out)
        except ValueError:
            self.fail(f'not JSON: {out!r} {err!r}')

    def fails(self, findings):
        return [m for level, m in findings if level == 'FAIL']

    def assertFails(self, findings, needle):
        failures = self.fails(findings)
        self.assertTrue(any(needle in m for m in failures), f'{needle!r} not in {failures}')

    def assertPasses(self, findings):
        self.assertEqual(self.fails(findings), [])

    def ledger(self):
        return (self.spec / 'ledger.md').read_text()

    # stage builders ------------------------------------------------------------------------------------------
    def accepted_ready(self, **meta):
        self.readme(**meta)
        self.spec_file('requirements.md', REQS)
        self.spec_file('spec-check.md', SPEC_CHECK)
        self.spec_file('security.md', '# Security\nThreat model: refunds move money.\n')

    def planned_ready(self):
        self.accepted_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('plan.md', PLAN)

    def building(self):
        self.planned_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'planned')[0], 0)
        self.git('checkout', '-q', '-b', 'feat/refunds')
        code, out, err = self.cli('advance', 'refunds', 'building')
        self.assertEqual(code, 0, out + err)

    def verified_ready(self):
        self.building()
        self.write('src/refunds/model.py', 'def refund(amount):\n    return amount\n')
        self.write('tests/test_refunds.py', '# RFD-1: refund a captured payment\n')
        self.write('load/refund-visibility.js', 'export default function () {}\n')
        self.commit('code')  # the reviewed gate needs the verified code committed
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')[0], 0)
        self.assertEqual(self.cli('task-done', 'refunds', 'T2', '--cmd', 'true')[0], 0)
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)

    def reviewed_ready(self):
        self.verified_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'verified')[0], 0)
        self.spec_file('review.md', REVIEW.format(fp='pending'))
        self.assertEqual(self.cli('stamp', 'refunds', 'review')[0], 0)

    def shipped_ready(self):
        self.reviewed_ready()
        code, out, err = self.cli('advance', 'refunds', 'reviewed')
        self.assertEqual(code, 0, out + err)
        self.spec_file('ship.md', SHIP)

    def fake_gh(self, output, code=0):
        gh = self.base / 'fake-gh'
        gh.write_text('#!/bin/sh\necho "$@" >> "$AIDLC_FAKE_LOG"\nprintf \'%s\' "$AIDLC_FAKE_OUT"\nexit '
                      + str(code) + '\n')
        os.environ['AIDLC_FAKE_LOG'] = str(self.base / 'gh-calls.log')
        gh.chmod(0o755)
        os.environ['AIDLC_GH'] = str(gh)
        os.environ['AIDLC_FAKE_OUT'] = output


class DocContractTest(Base):
    """The examples in references/aidlc.md must parse with the engine: the doc and the code cannot drift."""

    def test_every_artifact_example_is_present(self):
        blocks = doc_blocks()
        for name in ('spec.md', 'tickets.md', 'spec-check.md (optional)', 'ledger.md', 'review.md', 'ship.md'):
            self.assertIn(name, blocks)

    def test_readme_frontmatter_example(self):
        block = next(v for k, v in doc_blocks().items() if k.startswith('README frontmatter'))
        meta, _ = aidlc.parse_frontmatter(block)
        self.assertEqual(meta['key'], 'RFD')
        self.assertEqual(meta['status'], 'proposed')
        self.assertEqual(meta['branch'], 'feat/refunds')
        self.assertEqual(meta['security'], 'required')

    def test_spec_example(self):
        stories, findings = aidlc.parse_spec(doc_blocks()['spec.md'], 'spec.md', 'RFD')
        self.assertPasses(findings)
        self.assertEqual([r['id'] for r in stories], ['RFD-1', 'RFD-2', 'RFD-3', 'RFD-4'])
        self.assertEqual([r['verify'] for r in stories], ['test', 'test', 'check', 'none'])
        self.assertEqual(stories[2]['verify_detail'], 'k6 run load/refund-visibility.js')
        self.assertTrue(stories[2]['title'].endswith('so that I can confirm it on the call.'))
        self.assertTrue(aidlc.spec_security(doc_blocks()['spec.md']))

    def test_spec_check_example(self):
        guesses, findings = aidlc.parse_spec_check(doc_blocks()['spec-check.md (optional)'], 'spec-check.md')
        self.assertPasses(findings)
        self.assertEqual([(g['id'], g['open']) for g in guesses], [('G1', True), ('G2', False), ('G3', False)])

    def test_tickets_example(self):
        tickets, findings = aidlc.parse_tickets(doc_blocks()['tickets.md'], 'tickets.md')
        self.assertPasses(findings)
        self.assertEqual([t['id'] for t in tickets], ['T1', 'T2'])
        self.assertEqual((tickets[0]['covers'], tickets[0]['depends'], tickets[1]['depends']),
                         (['RFD-1', 'RFD-2'], [], ['T1']))
        self.assertEqual((tickets[0]['files'], tickets[1]['files']), (['src/refunds/**'], []))
        self.assertEqual((len(tickets[0]['criteria']), tickets[0]['done'], tickets[0]['owner']), (3, False, 'main'))
        self.assertEqual(tickets[1]['test'], 'k6 run load/refund-visibility.js')
        self.assertPasses(aidlc.plan_findings(tickets, ['RFD-1', 'RFD-2', 'RFD-3'], 'tickets.md'))

    def test_ledger_example(self):
        events, findings = aidlc.parse_ledger(doc_blocks()['ledger.md'], 'ledger.md')
        self.assertEqual(findings, [])
        self.assertEqual([e['kind'] for e in events], ['advance', 'task-done', 'ruling', 'verify', 'stamp'])
        self.assertEqual((events[0]['from'], events[0]['to']), ('accepted', 'planned'))
        self.assertEqual((events[1]['task'], events[1]['exit']), ('T1', 0))
        self.assertEqual(events[2]['task'], 'T2')
        self.assertIn('double refunds', events[2]['if_wrong'])
        self.assertEqual(events[3]['junit'], {'passed': 42, 'failed': 0})
        self.assertEqual(events[3]['cmd'], 'npm test')
        self.assertEqual(events[4]['fingerprint'], '8a01c6e95f3b')
        self.assertEqual(events[1]['fingerprint'], '3f9c0b7d21e4')

    def test_review_example(self):
        review, findings = aidlc.parse_review(doc_blocks()['review.md'], 'review.md')
        self.assertPasses(findings)
        self.assertPasses(aidlc.review_findings(review, 'review.md'))
        self.assertEqual(review['fingerprint'], '8a01c6e95f3b')
        self.assertEqual(len(review['findings']), 3)

    def test_ship_example(self):
        ship, findings = aidlc.parse_ship(doc_blocks()['ship.md'], 'ship.md')
        self.assertPasses(findings)
        self.assertPasses(aidlc.ship_findings(ship, 'ship.md'))
        self.assertEqual((ship['decision'], ship['version']), ('GO', '2.4.0'))
        self.assertTrue(aidlc.says_green(ship['ci']))


class AcceptedGateTest(Base):
    def test_passes_with_complete_artifacts(self):
        self.accepted_ready()
        self.assertPasses(aidlc.check(self.spec, 'accepted'))
        self.assertEqual(aidlc.check(self.spec)[-1][0], 'OK')  # default target: the next stage

    def test_key_must_be_two_to_six_capitals(self):
        for key in ('', 'rfd', 'R', 'REFUNDS'):
            self.accepted_ready(key=key)
            self.assertFails(aidlc.check(self.spec, 'accepted'), 'key')

    def test_key_must_be_unique_across_specs(self):
        self.accepted_ready()
        self.readme(spec=self.repo / 'svc' / 'docs' / 'specs' / 'old', status='implemented')
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'svc/docs/specs/old')

    def test_requirement_problems(self):
        cases = {
            'no acceptance criterion': '### RFD-1: x\nVerify: test\n',
            'duplicate': '### RFD-1: x\nAcceptance:\n- a\n### RFD-1: y\nAcceptance:\n- b\n',
            'is not test, check': '### RFD-1: x\nAcceptance:\n- a\nVerify: unit\n',
            'check needs': '### RFD-1: x\nAcceptance:\n- a\nVerify: check\n',
            'not RFD-<n>': '### RFD-1: x\nAcceptance:\n- a\n### RDF-2: typo\nAcceptance:\n- b\n',
            'defines no requirement': '# Requirements\nNothing yet.\n',
        }
        for needle, text in cases.items():
            self.accepted_ready()
            self.spec_file('requirements.md', text)
            self.assertFails(aidlc.check(self.spec, 'accepted'), needle)

    def test_story_headings_without_acceptance_are_not_requirements(self):
        self.accepted_ready()
        self.spec_file('requirements.md', REQS + '\n### BR-1: no refunds after 180 days\nPlain business rule.\n')
        self.assertPasses(aidlc.check(self.spec, 'accepted'))

    def test_verify_defaults_to_test_and_criteria_tolerate_blank_lines(self):
        reqs, findings = aidlc.parse_requirements('### RFD-1: x\nAcceptance:\n\n- a\n  continued\n- b\nNotes.\n',
                                                  'r.md')
        self.assertEqual(findings, [])
        self.assertEqual(reqs[0]['verify'], 'test')
        self.assertEqual(reqs[0]['criteria'], ['a continued', 'b'])

    def test_html_comments_and_code_fences_do_not_define_requirements(self):
        reqs, _ = aidlc.parse_requirements('<!--\n### RFD-1: x\n-->\n```\n### RFD-2: y\n```\n', 'r.md')
        self.assertEqual(reqs, [])

    def test_spec_check_problems(self):
        cases = {'open guess G1': '- [ ] G1: partial refunds?\n',
                 'neither': '- [x] G1: partial refunds?\n',
                 'has not run': '# Spec check\n\nSome prose only.\n'}
        for needle, text in cases.items():
            self.accepted_ready()
            self.spec_file('spec-check.md', text)
            self.assertFails(aidlc.check(self.spec, 'accepted'), needle)
        (self.spec / 'spec-check.md').unlink()
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'spec-check.md: missing')

    def test_spec_check_without_guesses_needs_a_checked_line(self):
        self.accepted_ready()
        self.spec_file('spec-check.md', '# Spec check\n\nChecked: no guesses.\n')
        self.assertPasses(aidlc.check(self.spec, 'accepted'))

    def test_spec_check_tolerates_a_second_appended_run(self):
        self.accepted_ready()
        self.spec_file('spec-check.md', SPEC_CHECK + '\nSecond run, after the edits:\n\n'
                       '- [x] G2: Retry policy? — accepted risk: client retries\n\n- [x] G3: Limits? — resolved: RFD-1\n')
        self.assertPasses(aidlc.check(self.spec, 'accepted'))
        guesses, _ = aidlc.parse_spec_check((self.spec / 'spec-check.md').read_text(), 'spec-check.md')
        self.assertEqual([g['id'] for g in guesses], ['G1', 'G2', 'G3'])

    def test_security(self):
        self.accepted_ready()
        (self.spec / 'security.md').unlink()
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'security.md')
        self.accepted_ready(security='not-applicable — internal batch job, no trust boundary')
        (self.spec / 'security.md').unlink()
        self.assertPasses(aidlc.check(self.spec, 'accepted'))
        self.accepted_ready(security='not-applicable')
        (self.spec / 'security.md').unlink()
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'reason')

    def test_accepted_by(self):
        for value in (None, '', '<name> (<date>)'):
            self.accepted_ready(accepted_by=value)
            self.assertFails(aidlc.check(self.spec, 'accepted'), 'accepted_by')

    def test_external_contract_must_pass_the_contract_gate(self):
        self.accepted_ready(contract='external')
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'contract')
        err = {'content': {'application/json': {'schema': {'type': 'object', 'properties': {'error': {
            'type': 'object', 'properties': {'code': {'type': 'string'}, 'message': {'type': 'string'}}}}}}}}
        good = {'paths': {'/r': {'post': {'operationId': 'refund',
                                          'responses': {'201': {'description': 'ok'}, '400': {'description': 'x', **err}}}}}}
        self.spec_file('contracts/api.json', json.dumps(good))
        self.assertPasses(aidlc.check(self.spec, 'accepted'))


class PlannedGateTest(Base):
    def plan(self, text):
        self.accepted_ready(status='accepted')
        self.spec_file('plan.md', text)
        return aidlc.check(self.spec, 'planned')

    def task(self, tid, covers='RFD-1, RFD-2', depends='none', owner='main', files=None, done=' '):
        lines = [f'- [{done}] {tid}: task {tid}']
        for name, value in (('covers', covers), ('depends', depends), ('owner', owner),
                            ('files', files if files is not None else f'src/{tid.lower()}.py')):
            if value is not None:
                lines.append(f'  - {name}: {value}')
        return '\n'.join(lines) + '\n'

    def test_passes(self):
        self.assertPasses(self.plan(PLAN))

    def test_plan_missing_or_empty(self):
        self.accepted_ready(status='accepted')
        self.assertFails(aidlc.check(self.spec, 'planned'), 'plan.md: missing')
        self.assertFails(self.plan('# Plan\nProse only.\n'), 'defines no task')

    def test_task_structure_failures(self):
        cases = {
            'duplicate task': self.task('T1') + self.task('T1', files='src/other.py'),
            'unknown T9': self.task('T1', depends='T9'),
            'no owner': self.task('T1', owner=None),
            'no files': self.task('T1', files=''),
            'covers nothing': self.task('T1', covers=None) + self.task('T2'),
            'needs a reason': self.task('T1', covers='none') + self.task('T2'),
            'unknown requirement RFD-7': self.task('T1', covers='RFD-1, RFD-2, RFD-7'),
            'RFD-2 is not covered': self.task('T1', covers='RFD-1'),
            'must be T<n>': self.task('T1') + '- [ ] T1a: bad id\n  - covers: RFD-1\n',
        }
        for needle, text in cases.items():
            self.assertFails(self.plan(text), needle)

    def test_covers_none_with_reason_passes(self):
        self.assertPasses(self.plan(self.task('T1') + self.task('T2', covers='none — CI wiring only')))

    def test_cycle_is_reported_with_its_path(self):
        findings = self.plan(self.task('T1', depends='T3') + self.task('T2', depends='T1', files='src/b.py')
                             + self.task('T3', depends='T2', files='src/c.py'))
        self.assertFails(findings, 'cycle')
        self.assertTrue(any('T1' in m and 'T2' in m and 'T3' in m for m in self.fails(findings)))

    def test_parallel_tasks_must_not_share_files(self):
        findings = self.plan(self.task('T1', files='src/a.py') + self.task('T2', files='src/a.py, src/b.py'))
        self.assertFails(findings, 'src/a.py')

    def test_dependent_tasks_may_share_files_even_transitively(self):
        text = (self.task('T1', files='src/a.py') + self.task('T2', depends='T1', files='src/b.py')
                + self.task('T3', depends='T2', files='src/a.py'))
        self.assertPasses(self.plan(text))

    def test_globs_overlap(self):
        self.assertFails(self.plan(self.task('T1', files='src/refunds/**') + self.task('T2', files='src/refunds/api.py')),
                         'share')
        self.assertFails(self.plan(self.task('T1', files='src/refunds/') + self.task('T2', files='src/refunds/x/y.py')),
                         'share')
        self.assertPasses(self.plan(self.task('T1', files='src/refunds/**') + self.task('T2', files='src/payouts/a.py')))

    def test_overlap_helper(self):
        self.assertTrue(aidlc.overlaps('src/**/*.ts', 'src/a/b.ts'))
        self.assertTrue(aidlc.overlaps('src/*.ts', 'src/a.ts'))
        self.assertFalse(aidlc.overlaps('src/*.ts', 'src/a/b.ts'))
        self.assertTrue(aidlc.overlaps('src/a/**', 'src/a/b/**'))
        self.assertFalse(aidlc.overlaps('src/a.ts', 'src/a.tsx'))


class NextTest(Base):
    def tasks(self, text):
        self.accepted_ready(status='accepted')
        self.spec_file('plan.md', text)

    def test_frontier_and_conflict_free_batches(self):
        self.tasks('- [x] T1: done\n  - files: src/a.py\n'
                   '- [ ] T2: ready\n  - depends: T1\n  - files: src/b.py, src/c.py\n'
                   '- [ ] T3: ready\n  - files: src/d.py\n'
                   '- [ ] T4: ready, conflicts with T2\n  - files: src/c.py\n'
                   '- [ ] T5: blocked\n  - depends: T2\n  - files: src/e.py\n'
                   '- [ ] T6: blocked by unknown\n  - depends: T9\n  - files: src/f.py\n')
        batches = aidlc.next_batches(self.spec)
        self.assertEqual([[t['id'] for t in batch] for batch in batches], [['T2', 'T3'], ['T4']])
        code, payload = self.cli_json('next', 'refunds')
        self.assertEqual(code, 0)
        self.assertEqual([[t['id'] for t in b] for b in payload['batches']], [['T2', 'T3'], ['T4']])

    def test_all_done_is_empty(self):
        self.tasks('- [x] T1: done\n  - files: a.py\n')
        self.assertEqual(aidlc.next_batches(self.spec), [])
        self.assertIn('all tasks are done', self.cli('next', 'refunds')[1])

    def test_unparsable_plan(self):
        self.accepted_ready(status='accepted')
        self.assertEqual(aidlc.next_batches(self.spec), [])
        self.assertEqual(self.cli('next', 'refunds')[0], 1)
        self.spec_file('plan.md', '# Plan\n<!-- - [ ] T1: example -->\n')
        code, out, _ = self.cli('next', 'refunds')
        self.assertEqual(code, 1)
        self.assertIn('defines no task', out)


class BuildingGateTest(Base):
    def test_default_branch_fails_and_feature_branch_passes(self):
        self.planned_ready()
        self.assertFails(aidlc.check(self.spec, 'building'), 'default branch')
        self.git('checkout', '-q', '-b', 'feat/refunds')
        self.assertPasses(aidlc.check(self.spec, 'building'))

    def test_recorded_branch_must_be_the_current_one(self):
        self.planned_ready()
        self.git('checkout', '-q', '-b', 'feat/refunds')
        self.readme(status='planned', branch='feat/other')
        self.assertFails(aidlc.check(self.spec, 'building'), 'feat/other')

    def test_detached_head_fails(self):
        self.planned_ready()
        self.git('checkout', '-q', '--detach')
        self.assertFails(aidlc.check(self.spec, 'building'), 'not on a branch')

    def test_advance_records_the_branch(self):
        self.building()
        meta, _ = aidlc.parse_frontmatter((self.spec / 'README.md').read_text())
        self.assertEqual((meta['status'], meta['branch']), ('building', 'feat/refunds'))
        self.assertEqual(aidlc.specs_for_branch(self.repo, 'feat/refunds'), [self.spec])
        self.assertEqual(aidlc.specs_for_branch(self.repo, 'main'), [])


class FingerprintTest(Base):
    def test_excluded_paths_do_not_change_it_everything_else_does(self):
        before = aidlc.fingerprint(self.repo)
        self.assertRegex(before, r'^[0-9a-f]{64}$')
        for rel in ('README.md', 'notes/todo.md', 'CHANGELOG.md', 'CHANGELOG', 'LICENSE', 'LICENSE.txt',
                    'docs/guide.txt', 'docs/specs/refunds/review.md', 'svc/docs/specs/x/plan.json', 'a/b/docs/specs/y/x.yaml',
                    'ignored/gen.py', 'debug.log'):
            self.write(rel, 'x')
            self.assertEqual(aidlc.fingerprint(self.repo), before, rel)
        for rel in ('package.json', 'src/new.py', 'db/1.sql', 'config/app.yaml', 'svc/docs/api.yaml', 'Makefile'):
            self.write(rel, 'x')
            after = aidlc.fingerprint(self.repo)
            self.assertNotEqual(after, before, rel)
            before = after

    def test_clean_tree_equals_head_and_dirty_code_is_detected(self):
        self.assertEqual(aidlc.fingerprint(self.repo), aidlc.fingerprint(self.repo, 'HEAD'))
        self.assertFalse(aidlc.code_dirty(self.repo))
        self.write('docs/x.md', 'x')
        self.assertFalse(aidlc.code_dirty(self.repo))
        self.write('src/app.py', 'x = 2\n')
        self.assertTrue(aidlc.code_dirty(self.repo))
        working = aidlc.fingerprint(self.repo)
        self.commit()
        self.assertEqual(aidlc.fingerprint(self.repo, 'HEAD'), working)
        self.assertEqual(aidlc.fingerprint(self.repo), working)
        self.assertFalse(aidlc.code_dirty(self.repo))
        self.write('src/app.py', 'x = 3\n')
        self.git('add', '-A')  # staged, not committed
        self.assertTrue(aidlc.code_dirty(self.repo))
        self.commit()
        self.write('src/new.py', 'x')  # untracked
        self.assertTrue(aidlc.code_dirty(self.repo))
        (self.repo / 'src' / 'new.py').unlink()
        (self.repo / 'src' / 'app.py').unlink()  # deleted
        self.assertTrue(aidlc.code_dirty(self.repo))
        self.assertNotEqual(aidlc.fingerprint(self.repo), aidlc.fingerprint(self.repo, 'HEAD'))

    def test_rev_of_an_older_commit_and_unknown_rev(self):
        first = aidlc.fingerprint(self.repo)
        self.write('src/app.py', 'x = 2\n')
        self.commit()
        self.assertEqual(aidlc.fingerprint(self.repo, 'HEAD~1'), first)
        self.assertIsNone(aidlc.fingerprint(self.repo, 'no-such-rev'))

    def test_only_modified_and_untracked_files_are_hashed(self):
        for i in range(300):
            self.write(f'src/gen/m{i}.py', f'x = {i}\n')
        self.commit()
        self.write('src/gen/m7.py', 'changed\n')
        self.write('src/brand_new.py', 'x')
        hashed = []
        original = aidlc.Repo._hash_paths

        def spy(repo, paths):
            hashed.extend(paths)
            return original(repo, paths)

        with mock.patch.object(aidlc.Repo, '_hash_paths', spy):
            aidlc.fingerprint(self.repo)
        self.assertEqual(sorted(hashed), ['src/brand_new.py', 'src/gen/m7.py'])

    def test_symlink_and_crlf_files_match_head_after_commit(self):
        os.symlink('app.py', self.repo / 'src' / 'link.py')
        self.write('src/win.py', 'a = 1\r\nb = 2\r\n')
        self.commit()
        self.assertEqual(aidlc.fingerprint(self.repo), aidlc.fingerprint(self.repo, 'HEAD'))

    def test_works_outside_git(self):
        folder = self.base / 'plain'
        (folder / 'src').mkdir(parents=True)
        (folder / 'src' / 'a.py').write_text('x')
        first = aidlc.fingerprint(folder)
        (folder / 'notes.md').write_text('x')
        self.assertEqual(aidlc.fingerprint(folder), first)
        (folder / 'src' / 'a.py').write_text('y')
        self.assertNotEqual(aidlc.fingerprint(folder), first)
        self.assertIsNone(aidlc.fingerprint(folder, 'HEAD'))
        self.assertFalse(aidlc.code_dirty(folder))


class TaskDoneTest(Base):
    def setUp(self):
        super().setUp()
        self.building()

    def test_exit_zero_ticks_and_logs(self):
        code, out, _ = self.cli('task-done', 'refunds', 'T1', '--cmd', 'echo ok')
        self.assertEqual(code, 0, out)
        self.assertIn('- [x] T1: Refund model', (self.spec / 'plan.md').read_text())
        self.assertIn('- [ ] T2: Load test', (self.spec / 'plan.md').read_text())
        events, _ = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        done = [e for e in events if e['kind'] == 'task-done']
        self.assertEqual((done[0]['task'], done[0]['exit'], done[0]['cmd']), ('T1', 0, 'echo ok'))
        self.assertEqual(done[0]['fingerprint'], aidlc.fingerprint(self.repo))

    def test_failure_changes_nothing_and_shows_the_tail(self):
        plan, ledger = (self.spec / 'plan.md').read_text(), self.ledger()
        code, out, _ = self.cli('task-done', 'refunds', 'T1', '--cmd', 'echo boom-output; exit 3')
        self.assertEqual(code, 1)
        self.assertIn('boom-output', out)
        self.assertIn('3', out)
        self.assertEqual((self.spec / 'plan.md').read_text(), plan)
        self.assertEqual(self.ledger(), ledger)

    def test_output_tail_is_bounded(self):
        code, payload = self.cli_json('task-done', 'refunds', 'T1', '--cmd', 'python3 -c "print(\'x\' * 100000)"; exit 1')
        self.assertEqual(code, 1)
        self.assertLessEqual(len(payload['output_tail']), 2200)

    def test_timeout(self):
        code, out, _ = self.cli('task-done', 'refunds', 'T1', '--cmd', 'sleep 5', '--timeout', '1')
        self.assertEqual(code, 1)
        self.assertIn('timed out', out)
        self.assertIn('- [ ] T1', (self.spec / 'plan.md').read_text())

    def test_unknown_task_is_a_usage_error(self):
        self.assertEqual(self.cli('task-done', 'refunds', 'T9', '--cmd', 'true')[0], 2)

    def test_test_field_is_the_default_command(self):
        self.assertEqual(self.cli('task-done', 'refunds', 'T1')[0], 2)  # neither --cmd nor a test field
        plan = self.spec / 'plan.md'
        plan.write_text(plan.read_text().replace('  - files: src/refunds/model.py (new)\n',
                                                 '  - files: src/refunds/model.py (new)\n  - test: echo from-plan\n'))
        tasks, findings = aidlc.parse_plan(plan.read_text(), 'plan.md')
        self.assertEqual(tasks[0]['test'], 'echo from-plan')
        self.assertEqual(self.cli('task-done', 'refunds', 'T1')[0], 0)
        self.assertIn('cmd="echo from-plan"', self.ledger())

    def test_command_runs_in_the_repo_root(self):
        os.chdir(self.spec)
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'test -f src/app.py')[0], 0)


JUNIT_PYTEST = """<?xml version="1.0"?>
<testsuites><testsuite name="pytest" tests="3">
<testcase classname="tests.test_refunds" name="test_RFD_1_full_refund"/>
<testcase classname="tests.test_refunds" name="test_other"><failure message="x">boom</failure></testcase>
<testcase classname="tests.test_refunds" name="test_skip"><skipped/></testcase>
</testsuite></testsuites>
"""
JUNIT_JEST = """<testsuites><testsuite name="refunds">
<testcase classname="RFD-1 refunds rejects over-capture" name="RFD-1 refunds rejects over-capture"><failure>x</failure></testcase>
</testsuite></testsuites>
"""
JUNIT_GRADLE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.x.RefundTest" tests="2" failures="0" errors="1">
  <testcase name="RFD-1 refunds a captured payment()" classname="com.x.RefundTest" time="0.1"/>
  <testcase name="RFD-10 other()" classname="com.x.RefundTest"><error message="npe"/></testcase>
</testsuite>
"""


class VerifyTest(Base):
    def setUp(self):
        super().setUp()
        self.building()
        self.write('tests/test_refunds.py', '# RFD-1\n')

    def last_verify(self):
        events, findings = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertEqual(findings, [])
        return [e for e in events if e['kind'] == 'verify'][-1]

    def test_logs_exit_and_fingerprint(self):
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
        event = self.last_verify()
        self.assertEqual((event['exit'], event['fingerprint'], event['junit']), (0, aidlc.fingerprint(self.repo), None))

    def test_failing_command_is_logged_and_exits_1(self):
        code, out, _ = self.cli('verify', 'refunds', '--cmd', 'echo red; exit 4')
        self.assertEqual(code, 1)
        self.assertIn('red', out)
        self.assertEqual(self.last_verify()['exit'], 4)

    def test_pytest_junit(self):
        self.write('reports/a.xml', JUNIT_PYTEST)
        code, payload = self.cli_json('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/*.xml')
        self.assertEqual(code, 0)
        self.assertEqual(payload['junit']['passed'], 1)
        self.assertEqual(payload['junit']['failed'], 1)
        event = self.last_verify()
        self.assertEqual(event['junit'], {'passed': 1, 'failed': 1})
        self.assertEqual(event['req_pass'], ['RFD-1'])
        self.assertEqual(event['req_fail'], [])

    def test_jest_junit_failure_of_a_requirement_test(self):
        self.write('reports/jest.xml', JUNIT_JEST)
        code, out, _ = self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/**/*.xml')
        self.assertEqual(code, 1)
        self.assertIn('RFD-1', out)
        self.assertEqual(self.last_verify()['req_fail'], ['RFD-1'])

    def test_gradle_junit_does_not_confuse_rfd_10_with_rfd_1(self):
        self.write('build/test-results/test/TEST-com.x.RefundTest.xml', JUNIT_GRADLE)
        code, payload = self.cli_json('verify', 'refunds', '--cmd', 'true', '--junit', 'build/test-results/**/*.xml')
        self.assertEqual(code, 0)
        self.assertEqual(payload['junit']['req_pass'], ['RFD-1'])
        self.assertEqual(payload['junit']['req_fail'], [])

    def test_glob_without_match_is_recorded_as_missing(self):
        code, out, _ = self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'nothing/*.xml')
        self.assertEqual(code, 1)
        self.assertEqual(self.last_verify()['junit'], 'missing')

    def test_malformed_junit_reports_file_and_line(self):
        self.write('reports/bad.xml', '<testsuite>\n<testcase name="x">\n')
        code, out, _ = self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/bad.xml')
        self.assertEqual(code, 1)
        self.assertRegex(out, r'reports/bad\.xml:\d+')
        self.assertEqual(self.last_verify()['junit'], 'unreadable')


class VerifiedGateTest(Base):
    def test_passes(self):
        self.verified_ready()
        self.assertPasses(aidlc.check(self.spec, 'verified'))

    def test_open_task_and_hand_ticked_task(self):
        self.building()
        self.write('tests/test_refunds.py', '# RFD-1\n')
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')[0], 0)
        plan = self.spec / 'plan.md'
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'T2 is not done')
        plan.write_text(plan.read_text().replace('- [ ] T2', '- [x] T2'))
        self.assertFails(aidlc.check(self.spec, 'verified'), 'T2 is ticked but has no green task-done')

    def test_requirement_without_test_reference(self):
        self.verified_ready()
        self.write('tests/test_refunds.py', '# RFD-10 only\n')
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1 (Verify: test) is not referenced')

    def test_requirement_reference_forms(self):
        self.verified_ready()
        for text in ('def test_rfd_1_refund(): pass\n', 'it("RFD-1 refunds", () => {})\n'):
            self.write('tests/test_refunds.py', text)
            self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
            self.assertPasses(aidlc.check(self.spec, 'verified'))

    def test_no_verify_or_failed_verify(self):
        self.building()
        self.assertFails(aidlc.check(self.spec, 'verified'), 'no verify event')
        self.verified_ready_from_building()
        self.cli('verify', 'refunds', '--cmd', 'exit 1')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'exited 1')

    def verified_ready_from_building(self):
        self.write('tests/test_refunds.py', '# RFD-1\n')
        self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')
        self.cli('task-done', 'refunds', 'T2', '--cmd', 'true')

    def test_code_change_after_verify_is_stale_doc_change_is_not(self):
        self.verified_ready()
        self.write('docs/notes.md', 'x')
        self.write('CHANGELOG.md', 'x')
        self.assertPasses(aidlc.check(self.spec, 'verified'))
        self.write('src/refunds/model.py', 'def refund(a):\n    return 0\n')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'code changed since the latest verify')

    def test_plan_structure_is_rechecked(self):
        self.verified_ready()
        plan = self.spec / 'plan.md'
        plan.write_text(plan.read_text() + '- [x] T3: added late\n  - covers: RFD-1\n  - depends: T7\n'
                        '  - owner: main\n  - files: src/x.py\n')
        findings = aidlc.check(self.spec, 'verified')
        self.assertFails(findings, 'unknown T7')
        self.assertFails(findings, 'T3 is ticked but has no green task-done')

    def test_latest_verify_wins(self):
        self.verified_ready()
        self.cli('verify', 'refunds', '--cmd', 'exit 2')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'exited 2')
        self.cli('verify', 'refunds', '--cmd', 'true')
        self.assertPasses(aidlc.check(self.spec, 'verified'))

    def test_failed_requirement_test_and_unreadable_junit_block(self):
        self.verified_ready()
        self.write('reports/jest.xml', JUNIT_JEST)
        self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/jest.xml')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1')
        self.write('reports/jest.xml', '<oops')
        self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/jest.xml')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'JUnit')


class StampTest(Base):
    def test_writes_fingerprint_and_logs(self):
        self.verified_ready()
        self.spec_file('review.md', REVIEW.format(fp='old  # written by stamp'))
        code, payload = self.cli_json('stamp', 'refunds', 'review')
        self.assertEqual(code, 0)
        fp = aidlc.fingerprint(self.repo)
        self.assertEqual(payload['fingerprint'], fp)
        review, _ = aidlc.parse_review((self.spec / 'review.md').read_text(), 'review.md')
        self.assertEqual(review['fingerprint'], fp)
        self.assertIn('## Standards', (self.spec / 'review.md').read_text())
        self.assertIn(f'stamp review fingerprint={fp}', self.ledger())

    def test_adds_frontmatter_when_missing(self):
        self.verified_ready()
        self.spec_file('review.md', '## Spec\nNo findings.\n## Standards\nNo findings.\n')
        self.assertEqual(self.cli('stamp', 'refunds', 'review')[0], 0)
        self.assertTrue((self.spec / 'review.md').read_text().startswith('---\nfingerprint: '))

    def test_missing_review_is_a_usage_error(self):
        self.verified_ready()
        self.assertEqual(self.cli('stamp', 'refunds', 'review')[0], 2)


class ReviewedGateTest(Base):
    def test_passes_and_records_the_pre_pr_review(self):
        self.reviewed_ready()
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))
        code, out, err = self.cli('advance', 'refunds', 'reviewed')
        self.assertEqual(code, 0, out + err)
        head = self.git('rev-parse', 'HEAD')
        top = self.git('rev-parse', '--show-toplevel')
        record = (self.home / '.claude' / 'state' / 'pr-review' / hashlib.sha256(top.encode()).hexdigest()[:16]
                  / f'{head}.json')
        data = json.loads(record.read_text())
        self.assertEqual((data['head'], data['open_findings']), (head, 0))
        self.assertEqual(set(data), {'head', 'reviewer', 'open_findings', 'note', 'recorded_at'})
        hook = subprocess.run([sys.executable, str(ROOT / 'hooks' / 'pr-review-gate.py')], capture_output=True, text=True,
                              input=json.dumps({'tool_name': 'Bash', 'cwd': str(self.repo),
                                                'tool_input': {'command': 'gh pr create --fill'}}))
        self.assertEqual(hook.returncode, 0, hook.stderr)

    def test_review_structure_failures(self):
        self.reviewed_ready()
        fp = aidlc.fingerprint(self.repo)
        cases = {
            '## Standards': f'---\nfingerprint: {fp}\n---\n## Spec\nNo findings.\n',
            'open finding S1': f'---\nfingerprint: {fp}\n---\n## Spec\n- [ ] S1 (must): missing\n## Standards\nNone.\n',
            'neither "fixed:" nor "cleared:"': f'---\nfingerprint: {fp}\n---\n## Spec\n- [x] S1 (must): x\n## Standards\nok\n',
            'is empty': f'---\nfingerprint: {fp}\n---\n## Spec\n## Standards\nNo findings.\n',
            'stamp': '---\nreviewers: x\n---\n## Spec\nNo findings.\n## Standards\nNo findings.\n',
        }
        for needle, text in cases.items():
            self.spec_file('review.md', text)
            self.assertFails(aidlc.check(self.spec, 'reviewed'), needle)

    def test_code_change_after_stamp_fails(self):
        self.reviewed_ready()
        self.write('src/refunds/model.py', 'changed = True\n')
        self.assertFails(aidlc.check(self.spec, 'reviewed'), 'since the review was stamped')

    def test_stamp_after_code_change_without_reverify_fails(self):
        self.reviewed_ready()
        self.write('src/refunds/model.py', 'changed = True\n')
        self.cli('stamp', 'refunds', 'review')
        self.assertFails(aidlc.check(self.spec, 'reviewed'), 'since the latest verify')

    def test_qa_verdict(self):
        self.reviewed_ready()
        text = (self.spec / 'review.md').read_text()
        cases = {'## QA': text.replace('## QA\nVerdict: GO\n', ''),
                 'NO-GO': text.replace('Verdict: GO', 'Verdict: NO-GO — refunds double-post'),
                 'conditions': text.replace('Verdict: GO', 'Verdict: CONDITIONAL GO'),
                 'Verdict:': text.replace('Verdict: GO', 'Looks fine.')}
        for needle, body in cases.items():
            self.spec_file('review.md', body)
            self.assertFails(aidlc.check(self.spec, 'reviewed'), needle)
        self.spec_file('review.md', text.replace('Verdict: GO', 'Verdict: CONDITIONAL GO — watch the PSP error rate'))
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))
        self.spec_file('review.md', text.replace('## QA\nVerdict: GO\n', ''))
        readme = self.spec / 'README.md'
        readme.write_text(readme.read_text().replace('---\n#', 'qa: not-applicable\n---\n#'))
        self.assertFails(aidlc.check(self.spec, 'reviewed'), 'qa: not-applicable')
        readme.write_text(readme.read_text().replace('qa: not-applicable', 'qa: not-applicable — library, no UI'))
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))

    def test_finding_lines_are_tolerant(self):
        self.reviewed_ready()
        text = (self.spec / 'review.md').read_text().replace(
            '- [x] Q1 (nit): rename amt — cleared: matches the PSP field name',
            '- [x] SEC12 (should): token logged at src/a.py:3 (confidence: high) — fixed: redacted\n'
            '- [x] X7: no severity given — cleared: style')
        self.spec_file('review.md', text)
        findings = aidlc.check(self.spec, 'reviewed')
        self.assertPasses(findings)
        self.assertTrue(any(level == 'WARN' and 'X7' in m and 'severity' in m for level, m in findings))

    def test_recheck_after_advance_and_commits(self):
        self.shipped_ready()  # advanced to reviewed
        self.git('add', '-A')
        self.git('commit', '-qm', 'review, ledger and code')
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))
        self.assertPasses(aidlc.check(self.spec, 'verified'))

    def pr_create(self):
        return subprocess.run([sys.executable, str(ROOT / 'hooks' / 'pr-review-gate.py')], capture_output=True,
                              text=True, input=json.dumps({'tool_name': 'Bash', 'cwd': str(self.repo),
                                                           'tool_input': {'command': 'gh pr create --fill'}}))

    def test_pr_allowed_after_committing_the_spec_files(self):
        # advance reviewed records HEAD; committing review.md/ledger/README moves HEAD but not the reviewed code.
        self.shipped_ready()
        self.git('add', '-A')
        self.git('commit', '-qm', 'review and ledger')
        hook = self.pr_create()
        self.assertEqual(hook.returncode, 0, hook.stderr)

    def test_pr_blocked_while_the_branch_spec_is_not_reviewed(self):
        self.verified_ready()
        self.git('add', '-A')
        self.git('commit', '-qm', 'wip')
        hook = self.pr_create()
        self.assertEqual(hook.returncode, 2)
        self.assertIn('docs/specs/refunds', hook.stderr)
        self.assertIn('reviewed', hook.stderr)

    def test_gate_failure_writes_no_record(self):
        self.reviewed_ready()
        self.spec_file('review.md', '## Spec\n- [ ] S1 (must): x\n')
        self.assertEqual(self.cli('advance', 'refunds', 'reviewed')[0], 1)
        self.assertFalse((self.home / '.claude' / 'state' / 'pr-review').exists())


class ShippedGateTest(Base):
    def test_passes_with_ci_line_when_gh_is_missing(self):
        self.shipped_ready()
        self.assertPasses(aidlc.check(self.spec, 'shipped'))

    def test_stage_must_be_reviewed(self):
        self.reviewed_ready()
        self.spec_file('ship.md', SHIP)
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'stage')

    def test_ship_md_failures(self):
        self.shipped_ready()
        cases = {
            'decision': SHIP.replace('decision: GO', 'decision: NO-GO'),
            '## Rollback': SHIP.replace('Revert the merge commit.\n', ''),
            '## Post-release verification': SHIP.replace('## Post-release verification\n', ''),
            'CI is not green': SHIP.replace('CI: green', 'CI: red, 2 failing'),
            'no "CI:" line': SHIP.replace('- CI: green\n', ''),
        }
        for needle, text in cases.items():
            self.spec_file('ship.md', text)
            self.assertFails(aidlc.check(self.spec, 'shipped'), needle)

    def test_gh_checks_override_the_ci_line(self):
        self.shipped_ready()
        self.spec_file('ship.md', SHIP.replace('- CI: green\n', ''))
        self.fake_gh('build\tpass\t1m\thttps://ci/1\nlint\tskipping\t0\thttps://ci/2\n')
        self.assertPasses(aidlc.check(self.spec, 'shipped'))
        self.fake_gh('build\tfail\t1m\thttps://ci/1\n', code=1)
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'build (fail)')
        self.spec_file('ship.md', SHIP)
        self.fake_gh('build\tpending\t1m\thttps://ci/1\n', code=8)
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'build (pending)')

    def test_gh_error_or_no_pr_falls_back_to_the_ci_line(self):
        self.shipped_ready()
        self.fake_gh('', code=1)
        self.assertPasses(aidlc.check(self.spec, 'shipped'))
        self.spec_file('ship.md', SHIP.replace('CI: green', 'CI: pending'))
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'CI is not green')

    def test_version_must_be_in_the_changelog(self):
        self.shipped_ready()
        self.spec_file('ship.md', SHIP.replace('version: n/a — internal service', 'version: 2.4.0'))
        self.assertPasses(aidlc.check(self.spec, 'shipped'))  # no CHANGELOG.md in the repository
        self.write('CHANGELOG.md', '## 2.4.1\n- x\n## 2.4.0-rc1\n')
        self.assertFails(aidlc.check(self.spec, 'shipped'), '2.4.0')
        self.write('CHANGELOG.md', '## [2.4.0] - 2026-11-19\n- refunds\n')
        self.assertPasses(aidlc.check(self.spec, 'shipped'))

    def test_code_change_after_review_fails(self):
        self.shipped_ready()
        self.write('src/refunds/model.py', 'late = True\n')
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'since the review')

    def test_shipped_spec_still_passes_its_gate(self):
        self.shipped_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'shipped')[0], 0)
        self.assertPasses(aidlc.check(self.spec, 'shipped'))


class ImplementedAndTraceTest(Base):
    def test_trace_matrix(self):
        self.verified_ready()
        code, payload = self.cli_json('trace', 'refunds')
        self.assertEqual(code, 0)
        rows = {r['id']: r for r in payload['rows']}
        self.assertEqual(rows['RFD-1']['tests'], ['tests/test_refunds.py'])
        self.assertEqual(rows['RFD-1']['tasks'], ['T1'])
        self.assertEqual(rows['RFD-1']['result'], 'pass')
        self.assertEqual(rows['RFD-2']['result'], 'check: k6 run load/refund-visibility.js')
        self.write('src/refunds/model.py', 'changed = 1\n')
        rows = {r['id']: r for r in self.cli_json('trace', 'refunds')[1]['rows']}
        self.assertEqual(rows['RFD-1']['result'], 'stale')

    def test_trace_write_is_idempotent_and_unlocks_implemented(self):
        self.shipped_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'shipped')[0], 0)
        self.assertFails(aidlc.check(self.spec, 'implemented'), 'Traceability')
        (self.spec / 'README.md').write_text((self.spec / 'README.md').read_text() + '\n## Notes\nkeep me\n')
        self.assertEqual(self.cli('trace', 'refunds', '--write')[0], 0)
        self.assertEqual(self.cli('trace', 'refunds', '--write')[0], 0)
        text = (self.spec / 'README.md').read_text()
        self.assertEqual(text.count('## Traceability'), 1)
        self.assertIn('keep me', text)
        self.assertIn('| RFD-1 |', text)
        self.assertPasses(aidlc.check(self.spec, 'implemented'))
        self.assertEqual(self.cli('advance', 'refunds', 'implemented')[0], 0)
        self.assertEqual(aidlc.stage(self.spec), 'implemented')
        self.assertEqual(aidlc.active_specs(self.repo), [])

    def test_implemented_needs_stage_shipped(self):
        self.reviewed_ready()
        self.cli('trace', 'refunds', '--write')
        self.assertFails(aidlc.check(self.spec, 'implemented'), 'stage')


class AdvanceTest(Base):
    def test_pass_updates_readme_and_ledger(self):
        self.accepted_ready(updated='2020-01-01')
        code, payload = self.cli_json('advance', 'refunds', 'accepted')
        self.assertEqual(code, 0)
        self.assertTrue(payload['advanced'])
        meta, _ = aidlc.parse_frontmatter((self.spec / 'README.md').read_text())
        self.assertEqual(meta['status'], 'accepted')
        self.assertEqual(meta['updated'], datetime.date.today().isoformat())
        events, _ = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertEqual((events[-1]['kind'], events[-1]['from'], events[-1]['to']), ('advance', 'proposed', 'accepted'))

    def test_gate_failure_changes_nothing(self):
        self.accepted_ready(accepted_by='')
        before = (self.spec / 'README.md').read_text()
        code, out, _ = self.cli('advance', 'refunds', 'accepted')
        self.assertEqual(code, 1)
        self.assertIn('FAIL', out)
        self.assertEqual((self.spec / 'README.md').read_text(), before)
        self.assertFalse((self.spec / 'ledger.md').exists())

    def test_cannot_skip_a_stage(self):
        self.accepted_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'planned')[0], 2)

    def test_back_needs_a_reason_and_an_earlier_stage(self):
        self.building()
        self.assertEqual(self.cli('advance', 'refunds', 'planned', '--back')[0], 2)
        self.assertEqual(self.cli('advance', 'refunds', 'verified', '--back', '--reason', 'x')[0], 2)
        code, _, _ = self.cli('advance', 'refunds', 'planned', '--back', '--reason', 'late finding: split T1')
        self.assertEqual(code, 0)
        self.assertEqual(aidlc.stage(self.spec), 'planned')
        events, _ = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertTrue(events[-1]['back'])
        self.assertEqual(events[-1]['reason'], 'late finding: split T1')
        meta, _ = aidlc.parse_frontmatter((self.spec / 'README.md').read_text())
        self.assertEqual(meta['accepted_by'], 'Tea (2026-11-19)')

    def test_back_to_proposed_clears_the_approval(self):
        self.planned_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'proposed', '--back', '--reason', 'scope changed')[0], 0)
        meta, _ = aidlc.parse_frontmatter((self.spec / 'README.md').read_text())
        self.assertEqual((meta['status'], meta['accepted_by']), ('proposed', ''))
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'accepted_by')

    def test_abandoned_and_superseded(self):
        self.planned_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'abandoned')[0], 2)
        self.assertEqual(self.cli('advance', 'refunds', 'superseded')[0], 1)
        self.assertEqual(self.cli('advance', 'refunds', 'abandoned', '--reason', 'PSP does it now')[0], 0)
        self.assertEqual(aidlc.stage(self.spec), 'abandoned')
        self.assertIn('reason="PSP does it now"', self.ledger())
        self.assertEqual(self.cli('advance', 'refunds', 'superseded')[0], 2)  # not active any more

    def test_superseded_needs_superseded_by(self):
        self.planned_ready()
        readme = self.spec / 'README.md'
        readme.write_text(readme.read_text().replace('---\n#', 'superseded_by: refunds-v2-slug\n---\n#'))
        self.assertEqual(self.cli('advance', 'refunds', 'superseded')[0], 0)
        self.assertEqual(aidlc.stage(self.spec), 'superseded')

    def test_partially_implemented_from_shipped(self):
        self.shipped_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'partially-implemented')[0], 2)
        self.assertEqual(self.cli('advance', 'refunds', 'shipped')[0], 0)
        self.assertEqual(self.cli('advance', 'refunds', 'partially-implemented')[0], 1)
        self.cli('trace', 'refunds', '--write')
        self.assertEqual(self.cli('advance', 'refunds', 'partially-implemented')[0], 0)

    def test_full_lifecycle(self):
        self.shipped_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'shipped')[0], 0)
        self.cli('trace', 'refunds', '--write')
        self.assertEqual(self.cli('advance', 'refunds', 'implemented')[0], 0)
        events, findings = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertEqual(findings, [])
        moves = [e['to'] for e in events if e['kind'] == 'advance']
        self.assertEqual(moves, list(aidlc.STAGES[1:]))


class RulingTest(Base):
    def test_ruling_with_and_without_task(self):
        self.building()
        self.assertEqual(self.cli('ruling', 'refunds', '--decision', 'Use the PSP key', '--why', 'dedupe',
                                  '--if-wrong', 'double refunds', '--task', 'T1')[0], 0)
        self.assertEqual(self.cli('ruling', 'refunds', '--decision', 'Keep\nEUR only', '--why', 'scope',
                                  '--if-wrong', 'rework')[0], 0)
        events, findings = aidlc.parse_ledger(self.ledger(), 'ledger.md')
        self.assertEqual(findings, [])
        rulings = [e for e in events if e['kind'] == 'ruling']
        self.assertEqual((rulings[0]['task'], rulings[0]['decision'], rulings[0]['why'], rulings[0]['if_wrong']),
                         ('T1', 'Use the PSP key', 'dedupe', 'double refunds'))
        self.assertEqual((rulings[1]['task'], rulings[1]['decision']), (None, 'Keep EUR only'))

    def test_unknown_task_is_a_usage_error(self):
        self.building()
        self.assertEqual(self.cli('ruling', 'refunds', '--decision', 'a', '--why', 'b', '--if-wrong', 'c',
                                  '--task', 'T9')[0], 2)


SPEC_MD = """# Refunds

Status: ready-for-agent

## Problem Statement

Support cannot refund a captured payment.

## Solution

A support agent refunds a captured payment once.

## User Stories

### Refund

1. As a support agent, I want to refund a captured payment, so that the customer gets the money back.
2. As a support agent, I want refunds visible within 1 minute,
   so that I can confirm them. (Verify: check — k6 run load/refund-visibility.js)
3. As a customer, I want a refund email, so that I know. (Verify: none — the notifications service sends it)

## Implementation Decisions

- One seam: the refund service.
- **Security:** assets payment amount; threats replay, over-refund; controls idempotency key, amount cap.

## Testing Decisions

- Test through the refund service only.

## Out of Scope

- Partial refunds.
"""
TICKETS_MD = """# Tickets

## T1: Refund a captured payment
Blocked by: none
Covers: RFD-1
Status: ready-for-agent
What to build: a full refund, once.
- [ ] A full refund returns REFUNDED
Files: src/refunds/**

## T2: Refund visibility
Blocked by: T1
Covers: RFD-2
Status: ready-for-agent
What to build: visible in the console within 1 minute.
- [ ] p95 under 60 s
"""


class SpecTemplateLifecycleTest(Base):
    """spec.md (the to-spec template) + tickets.md through every gate."""

    def accepted_ready(self, **meta):
        self.readme(**meta)
        self.spec_file('spec.md', SPEC_MD)

    def test_stories_are_requirements(self):
        stories, findings = aidlc.parse_spec(SPEC_MD, 'spec.md', 'RFD')
        self.assertPasses(findings)
        self.assertEqual([(r['id'], r['verify']) for r in stories], [('RFD-1', 'test'), ('RFD-2', 'check'),
                                                                     ('RFD-3', 'none')])
        self.assertEqual(stories[1]['verify_detail'], 'k6 run load/refund-visibility.js')
        self.assertIn('so that I can confirm them.', stories[1]['title'])

    def test_accepted_needs_no_spec_check_or_security_md(self):
        self.accepted_ready()
        self.assertPasses(aidlc.check(self.spec, 'accepted'))

    def test_accepted_gate_failures(self):
        self.accepted_ready()
        self.spec_file('spec.md', SPEC_MD.replace('- **Security:** assets', '- Assets').replace(
            '## Out of Scope\n\n- Partial refunds.\n', '').replace('2. As a', '1. As a'))
        findings = aidlc.check(self.spec, 'accepted')
        self.assertFails(findings, 'no security decisions')
        self.assertFails(findings, 'no "## Out Of Scope" section')
        self.assertFails(findings, 'duplicate user story 1')
        self.readme(security='not-applicable — internal tool')
        self.assertFalse(any('security' in m for m in self.fails(aidlc.check(self.spec, 'accepted'))))

    def test_bad_verify_tag_and_open_optional_guess(self):
        self.accepted_ready()
        self.spec_file('spec.md', SPEC_MD.replace('(Verify: none — the notifications service sends it)',
                                                  '(Verify: maybe)'))
        self.spec_file('spec-check.md', '- [ ] G1: which currency?\n')
        findings = aidlc.check(self.spec, 'accepted')
        self.assertFails(findings, "Verify: 'maybe'")
        self.assertFails(findings, 'open guess G1')

    def test_planned_coverage_skips_verify_none_and_accepts_ranges(self):
        self.accepted_ready(status='accepted')
        self.spec_file('tickets.md', TICKETS_MD)
        self.assertPasses(aidlc.check(self.spec, 'planned'))
        self.spec_file('tickets.md', TICKETS_MD.replace('Covers: RFD-2', 'Covers: none — later'))
        self.assertFails(aidlc.check(self.spec, 'planned'), 'RFD-2 is not covered')
        self.spec_file('tickets.md', TICKETS_MD.replace('Covers: RFD-1\n', 'Covers: RFD-1..2\n').replace(
            'Covers: RFD-2', 'Covers: none — load test only'))
        self.assertPasses(aidlc.check(self.spec, 'planned'))

    def test_tickets_without_files_run_alone(self):
        tickets, _ = aidlc.parse_tickets(TICKETS_MD.replace('Blocked by: T1', 'Blocked by: none'), 'tickets.md')
        self.assertEqual([[t['id'] for t in g] for g in aidlc.batches(tickets)], [['T1'], ['T2']])
        both = TICKETS_MD.replace('Blocked by: T1', 'Blocked by: none').replace(
            'What to build: visible', 'Files: load/**\nWhat to build: visible')
        tickets, _ = aidlc.parse_tickets(both, 'tickets.md')
        self.assertEqual([[t['id'] for t in g] for g in aidlc.batches(tickets)], [['T1', 'T2']])

    def test_full_lifecycle(self):
        self.accepted_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('tickets.md', TICKETS_MD)
        self.assertEqual(self.cli('advance', 'refunds', 'planned')[0], 0)
        self.git('checkout', '-q', '-b', 'feat/refunds')
        self.assertEqual(self.cli('advance', 'refunds', 'building')[0], 0)
        self.write('src/refunds/model.py', 'def refund(amount):\n    return amount\n')
        self.write('tests/test_refunds.py', '# RFD-1: refund a captured payment\n')
        self.commit('code')
        code, out, _ = self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')
        self.assertEqual(code, 1)
        self.assertIn('acceptance criterion not ticked', out)
        tickets = self.spec / 'tickets.md'
        tickets.write_text(tickets.read_text().replace('- [ ] ', '- [x] '))
        for tid in ('T1', 'T2'):
            code, out, err = self.cli('task-done', 'refunds', tid, '--cmd', 'true')
            self.assertEqual(code, 0, out + err)
        text = tickets.read_text()
        self.assertEqual(text.count('Status: done'), 2)
        self.assertNotIn('ready-for-agent', text)
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true')[0], 0)
        self.assertPasses(aidlc.check(self.spec, 'verified'))
        rows = {r['id']: r for r in aidlc.trace_rows(aidlc.Spec(self.spec))}
        self.assertEqual((rows['RFD-1']['tasks'], rows['RFD-1']['result']), (['T1'], 'pass'))
        self.assertTrue(rows['RFD-3']['result'].startswith('none'))

    def test_verified_needs_story_tests(self):
        self.accepted_ready()
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('tickets.md', TICKETS_MD.replace('- [ ] ', '- [x] '))
        self.assertEqual(self.cli('advance', 'refunds', 'planned')[0], 0)
        findings = aidlc.check(self.spec, 'verified')
        self.assertFails(findings, 'spec.md')
        self.assertFails(findings, 'RFD-1 (Verify: test) is not referenced by any test file')
        self.assertFalse(any('RFD-3' in m for m in self.fails(findings)))


class LintTest(Base):
    def test_lint_passes_a_complete_spec_and_lists_failures(self):
        good = self.write('draft/spec.md', SPEC_MD)
        code, payload = self.cli_json('lint', good, '--key', 'RFD')
        self.assertEqual((code, payload['stories']), (0, ['RFD-1', 'RFD-2', 'RFD-3']))
        bad = self.write('draft/bad.md', SPEC_MD.replace('- **Security:** assets', '- Assets').replace(
            '## Out of Scope', '## Notes').replace('Status: ready-for-agent', ''))
        code, payload = self.cli_json('lint', bad, '--key', 'RFD')
        messages = ' '.join(f['message'] for f in payload['findings'])
        self.assertEqual(code, 1)
        self.assertIn('no security decisions', messages)
        self.assertIn('no "## Out Of Scope" section', messages)
        self.assertIn('no "Status: ready-for-agent"', messages)
        code, payload = self.cli_json('lint', bad, '--key', 'RFD', '--no-security')
        self.assertNotIn('security', ' '.join(f['message'] for f in payload['findings'] if f['level'] == 'FAIL'))


class InitTest(Base):
    def test_creates_parsable_skeletons_that_block_acceptance(self):
        code, payload = self.cli_json('init', 'refunds', '--key', 'RFD')
        self.assertEqual(code, 0)
        for name in ('README.md', 'spec.md', 'tickets.md', 'ledger.md'):
            self.assertTrue((self.spec / name).is_file(), name)
        data = aidlc.load_spec(self.spec)
        self.assertEqual([m for level, m in data['errors'] if level == 'FAIL'], [])
        self.assertEqual((data['stage'], data['readme']['key']), ('proposed', 'RFD'))
        self.assertEqual((data['tasks'], data['ledger']), ([], []))
        findings = aidlc.check(self.spec, 'accepted')
        self.assertFails(findings, '"## Problem Statement" is empty')
        self.assertFails(findings, 'has no numbered story')
        self.assertFails(findings, 'no security decisions')
        self.assertFails(findings, 'accepted_by')
        self.assertFalse(any('spec-check' in m for m in self.fails(findings)))

    def test_init_then_doc_examples_pass_the_gates(self):
        self.assertEqual(self.cli('init', 'refunds', '--key', 'RFD')[0], 0)
        blocks = doc_blocks()
        self.spec_file('spec.md', blocks['spec.md'])
        readme = self.spec / 'README.md'
        readme.write_text(readme.read_text().replace('accepted_by:', 'accepted_by: Tea (2026-11-19)'))
        self.assertPasses(aidlc.check(self.spec, 'accepted'))
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('tickets.md', '# Tickets\n\n' + blocks['tickets.md'])
        self.assertPasses(aidlc.check(self.spec, 'planned'))

    def test_path_slug_and_errors(self):
        self.assertEqual(self.cli('init', 'svc/docs/specs/payouts', '--key', 'PAY')[0], 0)
        self.assertTrue((self.repo / 'svc' / 'docs' / 'specs' / 'payouts' / 'README.md').is_file())
        self.assertEqual(self.cli('init', 'payouts', '--key', 'PAY')[0], 2)          # duplicate key
        self.assertEqual(self.cli('init', 'svc/docs/specs/payouts', '--key', 'PAX')[0], 2)  # exists
        self.assertEqual(self.cli('init', 'refunds', '--key', 'rfd')[0], 2)          # bad key
        self.assertEqual(self.cli('init', 'Bad_Slug', '--key', 'BAD')[0], 2)          # bad slug


class StatusAndResolutionTest(Base):
    def setUp(self):
        super().setUp()
        self.accepted_ready()
        self.payouts = self.repo / 'svc' / 'docs' / 'specs' / 'payouts'
        self.readme(spec=self.payouts, key='PAY', status='accepted')
        self.old = self.repo / 'docs' / 'specs' / 'old-thing'
        self.readme(spec=self.old, key='OLD', status='implemented')

    def test_status_over_several_specs(self):
        items = {i['slug']: i for i in aidlc.status(self.repo)}
        self.assertEqual(set(items), {'refunds', 'payouts', 'old-thing'})
        self.assertEqual(items['refunds']['path'], 'docs/specs/refunds')
        self.assertEqual((items['refunds']['stage'], items['refunds']['next'], items['refunds']['passes']),
                         ('proposed', 'accepted', True))
        self.assertEqual(items['payouts']['path'], 'svc/docs/specs/payouts')
        self.assertFalse(items['payouts']['passes'])
        self.assertTrue(any('tickets.md' in b for b in items['payouts']['blockers']))
        self.assertEqual((items['old-thing']['next'], items['old-thing']['passes']), (None, None))
        code, payload = self.cli_json('status')
        self.assertEqual(code, 0)
        self.assertEqual(len(payload['specs']), 3)
        code, out, _ = self.cli('status', '--repo', self.repo)
        self.assertIn('svc/docs/specs/payouts', out)

    def test_legacy_spec_without_key(self):
        legacy = self.repo / 'docs' / 'specs' / 'legacy'
        self.readme(spec=legacy, key=None, status='proposed')
        items = {i['slug']: i for i in aidlc.status(self.repo)}
        self.assertEqual((items['legacy']['stage'], items['legacy']['legacy'], items['legacy']['passes']),
                         ('proposed', True, None))
        self.assertFalse(items['refunds']['legacy'])
        code, out, _ = self.cli('advance', 'legacy', 'accepted')
        self.assertEqual(code, 1)
        self.assertIn('key:', out)
        self.readme(spec=legacy, key=None, status='accepted')
        code, out, _ = self.cli('advance', 'legacy', 'planned')
        self.assertEqual(code, 1)
        self.assertIn('key:', out)

    def test_active_specs(self):
        self.assertEqual(aidlc.active_specs(self.repo), [self.spec, self.payouts])

    def test_slug_and_path_resolution(self):
        self.assertEqual(aidlc.find_spec(self.repo, 'refunds'), self.spec)
        self.assertEqual(aidlc.find_spec(self.repo, 'payouts'), self.payouts)
        self.assertEqual(aidlc.find_spec(self.repo, 'docs/specs/refunds'), self.spec)
        self.assertEqual(aidlc.find_spec(self.repo, str(self.payouts)), self.payouts)
        self.assertIsNone(aidlc.find_spec(self.repo, 'nope'))
        self.readme(spec=self.repo / 'other' / 'docs' / 'specs' / 'refunds', key='RFX')
        self.assertIsNone(aidlc.find_spec(self.repo, 'refunds'))
        code, _, err = self.cli('check', 'refunds')
        self.assertEqual(code, 2)
        self.assertIn('ambiguous', err)
        self.assertEqual(self.cli('check', 'nope')[0], 2)

    def test_check_exit_codes(self):
        self.assertEqual(self.cli('check', 'refunds')[0], 0)
        self.assertEqual(self.cli('check', 'payouts')[0], 1)
        self.assertEqual(self.cli('check', 'refunds', '--to', 'nonsense')[0], 2)

    def test_load_spec(self):
        data = aidlc.load_spec(self.spec)
        self.assertEqual(data['slug'], 'refunds')
        self.assertEqual([r['id'] for r in data['requirements']], ['RFD-1', 'RFD-2'])
        self.assertIsNone(data['tasks'])
        self.assertEqual(data['errors'], [])


class RobustnessTest(Base):
    def test_malformed_files_are_findings_not_tracebacks(self):
        self.verified_ready()
        with open(self.spec / 'ledger.md', 'a') as fh:
            fh.write('- yesterday something happened\n')
        findings = aidlc.check(self.spec, 'verified')
        self.assertTrue(any(re.search(r'docs/specs/refunds/ledger\.md:\d+', m) for m in self.fails(findings)))
        (self.spec / 'requirements.md').write_bytes(b'### RFD-1: x\n\xff\xfe broken\n')
        findings = aidlc.check(self.spec, 'verified')
        self.assertFails(findings, 'docs/specs/refunds/requirements.md:2')

    def test_readme_without_frontmatter(self):
        self.spec_file('README.md', '# refunds\n')
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'README.md:1: no frontmatter')
        self.readme(status='drafting')
        self.assertFails(aidlc.check(self.spec), 'not an AIDLC stage')

    def test_findings_use_repo_relative_paths(self):
        self.accepted_ready(accepted_by='')
        (self.spec / 'security.md').unlink()
        for _, message in aidlc.check(self.spec, 'accepted'):
            self.assertNotIn(str(self.base), message)


class JsonOutputTest(Base):
    def test_every_command_prints_json(self):
        self.verified_ready()
        self.spec_file('review.md', REVIEW.format(fp='x'))
        commands = [
            ('status',), ('check', 'refunds'), ('next', 'refunds'), ('trace', 'refunds'),
            ('task-done', 'refunds', 'T1', '--cmd', 'true'), ('verify', 'refunds', '--cmd', 'true'),
            ('ruling', 'refunds', '--decision', 'a', '--why', 'b', '--if-wrong', 'c'),
            ('stamp', 'refunds', 'review'), ('advance', 'refunds', 'verified'), ('init', 'payouts', '--key', 'PAY'),
            ('check', 'nope'),
        ]
        for argv in commands:
            code, payload = self.cli_json(*argv)
            self.assertIn(code, (0, 1, 2), argv)
            self.assertEqual(payload['command'], argv[0], argv)
            self.assertEqual(payload['exit'], code, argv)
        self.assertIn('error', self.cli_json('check', 'nope')[1])


class MarkPrReviewTest(Base):
    def test_record_function_and_cli_write_the_same_format(self):
        top = self.git('rev-parse', '--show-toplevel')
        head = self.git('rev-parse', 'HEAD')
        target = mpr.record(top, head, 'code-reviewer', 0, 'pass 1')
        self.assertEqual(target, self.home / '.claude' / 'state' / 'pr-review'
                         / hashlib.sha256(top.encode()).hexdigest()[:16] / f'{head}.json')
        from_function = json.loads(target.read_text())
        target.unlink()
        cli = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'mark-pr-review.py'), '--reviewer', 'code-reviewer',
                              '--open-findings', '0', '--note', 'pass 1'], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        from_cli = json.loads(target.read_text())
        self.assertEqual(set(from_cli), set(from_function))
        self.assertEqual({k: v for k, v in from_cli.items() if k != 'recorded_at'},
                         {k: v for k, v in from_function.items() if k != 'recorded_at'})
        self.assertTrue(target.read_text().endswith('}\n'))



class EvidenceChainTest(Base):
    def test_red_latest_verify_blocks_reviewed_and_shipped(self):
        self.shipped_ready()
        self.cli('verify', 'refunds', '--cmd', 'exit 1')
        self.assertFails(aidlc.check(self.spec, 'reviewed'), 'exited 1')
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'exited 1')

    def test_dirty_code_blocks_reviewed_and_writes_no_record(self):
        self.reviewed_ready()
        self.write('src/refunds/extra.py', 'x = 1\n')
        self.cli('verify', 'refunds', '--cmd', 'true')
        self.cli('stamp', 'refunds', 'review')
        findings = aidlc.check(self.spec, 'reviewed')
        self.assertEqual(len(self.fails(findings)), 1, findings)
        self.assertFails(findings, 'uncommitted code')
        self.assertEqual(self.cli('advance', 'refunds', 'reviewed')[0], 1)
        self.assertFalse((self.home / '.claude' / 'state' / 'pr-review').exists())
        self.commit()
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))

    def test_dirty_code_blocks_shipped(self):
        self.shipped_ready()
        self.write('src/refunds/extra.py', 'x = 1\n')
        self.assertFails(aidlc.check(self.spec, 'shipped'), 'uncommitted code')

    def test_evidence_findings_against_a_revision(self):
        self.reviewed_ready()
        self.assertPasses(aidlc.evidence_findings(self.spec))
        self.assertPasses(aidlc.evidence_findings(self.spec, 'HEAD'))
        self.assertFails(aidlc.evidence_findings(self.spec, 'HEAD~1'), 'HEAD~1')
        self.assertFails(aidlc.evidence_findings(self.spec, 'nope'), 'nope')

    def test_verify_and_stamp_must_be_the_same_code(self):
        self.reviewed_ready()
        self.write('src/refunds/model.py', 'v = 2\n')
        self.commit()
        self.cli('verify', 'refunds', '--cmd', 'true')
        findings = aidlc.evidence_findings(self.spec)
        self.assertFails(findings, 'review stamp')

    def test_short_fingerprints_never_match(self):
        self.reviewed_ready()
        fp = aidlc.fingerprint(self.repo)
        with open(self.spec / 'ledger.md', 'a') as fh:
            fh.write(f'- 2026-11-19T12:00:00Z verify exit=0 fingerprint={fp[:8]} cmd="true"\n')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'code changed since the latest verify')
        self.assertFalse(aidlc.fp_matches(fp[:11], fp))
        self.assertTrue(aidlc.fp_matches(fp[:12], fp))


class LockAndTickTest(Base):
    def setUp(self):
        super().setUp()
        self.building()

    def test_tick_by_id_after_the_command_edited_plan(self):
        cmd = ("python3 -c \"p='docs/specs/refunds/plan.md'; s=open(p).read(); "
               "open(p,'w').write('# Plan\\n\\nIntro added while T1 ran.\\n- [ ] note\\n' + s)\"")
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', cmd)[0], 0)
        text = (self.spec / 'plan.md').read_text()
        self.assertIn('- [x] T1: Refund model', text)
        self.assertIn('- [ ] note', text)
        self.assertIn('- [ ] T2: Load test', text)

    @unittest.skipIf(aidlc.fcntl is None, 'no fcntl')
    def test_writers_wait_for_the_spec_lock(self):
        import threading
        import time
        results = []
        with aidlc.spec_lock(self.spec):
            worker = threading.Thread(target=lambda: results.append(
                self.cli('ruling', 'refunds', '--decision', 'a', '--why', 'b', '--if-wrong', 'c')[0]))
            worker.start()
            time.sleep(0.4)
            self.assertNotIn('ruling', self.ledger())
        worker.join(10)
        self.assertEqual(results, [0])
        self.assertIn('ruling a', self.ledger())

    def test_parallel_task_done_keeps_every_tick(self):
        plan = self.spec / 'plan.md'
        plan.write_text(plan.read_text().replace('  - depends: T1\n', '  - depends: none\n'))
        procs = [subprocess.Popen([sys.executable, str(ROOT / 'scripts' / 'aidlc.py'), 'task-done', 'refunds', t,
                                   '--cmd', 'sleep 0.2'], cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for t in ('T1', 'T2')]
        self.assertEqual([proc.wait(30) for proc in procs], [0, 0])
        self.assertIn('- [x] T1', plan.read_text())
        self.assertIn('- [x] T2', plan.read_text())
        self.assertEqual(self.ledger().count('task-done'), 2)

    def test_crlf_files_keep_their_line_endings(self):
        for name in ('plan.md', 'README.md', 'ledger.md'):
            path = self.spec / name
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        self.assertEqual(self.cli('task-done', 'refunds', 'T1', '--cmd', 'true')[0], 0)
        self.assertEqual(self.cli('advance', 'refunds', 'planned', '--back', '--reason', 'x')[0], 0)
        for name in ('plan.md', 'README.md', 'ledger.md'):
            data = (self.spec / name).read_bytes()
            self.assertEqual(data.count(b'\n'), data.count(b'\r\n'), name)
        self.assertIn(b'- [x] T1', (self.spec / 'plan.md').read_bytes())

    def test_timeout_without_killpg(self):
        saved = os.killpg
        del os.killpg
        try:
            code, out, _ = self.cli('task-done', 'refunds', 'T1', '--cmd', 'sleep 5', '--timeout', '1')
        finally:
            os.killpg = saved
        self.assertEqual(code, 1)
        self.assertIn('timed out', out)


class DiscoveryTest(Base):
    def test_specs_at_any_depth_untracked_included_ignored_excluded(self):
        deep = self.repo / 'platform' / 'svc' / 'docs' / 'specs' / 'deep-one'
        self.readme(spec=deep, key='DEP')
        self.readme(spec=self.repo / 'ignored' / 'docs' / 'specs' / 'hidden', key='HID')
        self.accepted_ready()
        self.assertEqual(aidlc.find_spec(self.repo, 'deep-one'), deep)
        self.assertIsNone(aidlc.find_spec(self.repo, 'hidden'))
        self.assertEqual({i['slug'] for i in aidlc.status(self.repo)}, {'deep-one', 'refunds'})
        self.readme(spec=deep, key='RFD')
        self.assertFails(aidlc.check(self.spec, 'accepted'), 'platform/svc/docs/specs/deep-one')

    def test_filesystem_fallback_outside_git(self):
        folder = self.base / 'plain'
        self.readme(spec=folder / 'a' / 'b' / 'docs' / 'specs' / 'x', key='XX')
        self.readme(spec=folder / 'node_modules' / 'p' / 'docs' / 'specs' / 'y', key='YY')
        self.assertEqual([i['slug'] for i in aidlc.status(folder)], ['x'])

    def test_specs_for_branch_returns_any_status(self):
        self.readme(status='implemented', branch='feat/refunds')
        self.assertEqual(aidlc.specs_for_branch(self.repo, 'feat/refunds'), [self.spec])
        self.assertEqual(aidlc.active_specs(self.repo), [])

    def test_repo_option_is_normalized_to_the_top_level(self):
        self.accepted_ready()
        code, payload = self.cli_json('status', '--repo', self.repo / 'src')
        self.assertEqual(code, 0)
        self.assertEqual([i['slug'] for i in payload['specs']], ['refunds'])
        self.assertEqual(self.cli('check', 'refunds', '--repo', self.repo / 'src')[0], 0)


class TraceabilityMatchingTest(Base):
    def test_reference_forms(self):
        self.accepted_ready()
        repo = aidlc.Repo(self.repo)
        cases = {'# covers RFD-1\n': True, 'def test_rfd_1_rejects(): pass\n': True,
                 'void test_RFD_1_refund() {}\n': True, 'it("RFD-1: refunds")\n': True,
                 '# RFD-10 only\n': False, 'rfd-1 in lower case\n': False, 'order_rfd_1 = 1\n': False,
                 'XRFD-1\n': False, 'RFD_1 = 3\n': False}
        for text, expected in cases.items():
            self.write('tests/test_x.py', text)
            refs = aidlc.Repo(self.repo).tests_referencing('RFD-1')
            self.assertEqual(bool(refs), expected, text)
        self.assertIsNotNone(repo)

    def test_order_key_is_not_matched_by_snake_case(self):
        pattern = aidlc.id_pattern('ORDER-1')
        self.assertFalse(pattern.search('order_1 = place_order()'))
        self.assertTrue(pattern.search('def test_order_1_places(): pass'))

    def test_junit_must_pass_every_verify_test_requirement(self):
        self.verified_ready()
        skipped = ('<testsuite><testcase classname="t" name="test_RFD_1_refund"><skipped/></testcase>'
                   '<testcase classname="t" name="test_other"/></testsuite>')
        self.write('reports/a.xml', skipped)
        self.cli('verify', 'refunds', '--cmd', 'touch reports/a.xml', '--junit', 'reports/a.xml')
        self.assertFails(aidlc.check(self.spec, 'verified'), 'RFD-1 has no passing test')
        self.write('reports/a.xml', '<testsuite><testcase classname="t" name="test_RFD_1_refund"/></testsuite>')
        self.cli('verify', 'refunds', '--cmd', 'touch reports/a.xml', '--junit', 'reports/a.xml')
        findings = aidlc.check(self.spec, 'verified')
        self.assertPasses(findings)
        self.assertFalse(any('static' in m for _, m in findings))

    def test_without_junit_traceability_is_static(self):
        self.verified_ready()
        findings = aidlc.check(self.spec, 'verified')
        self.assertPasses(findings)
        self.assertTrue(any(level == 'WARN' and 'static' in m for level, m in findings))

    def test_stale_or_empty_junit_counts_as_missing(self):
        self.verified_ready()
        report = self.write('reports/old.xml', '<testsuite><testcase classname="t" name="test_RFD_1_x"/></testsuite>')
        os.utime(report, (report.stat().st_atime - 600, report.stat().st_mtime - 600))
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/*.xml')[0], 1)
        self.assertIn('junit=missing', self.ledger().splitlines()[-1])
        self.write('reports/new.xml', '<testsuites><testsuite name="empty"/></testsuites>')
        self.assertEqual(self.cli('verify', 'refunds', '--cmd', 'true', '--junit', 'reports/new.xml')[0], 1)
        self.assertIn('junit=missing', self.ledger().splitlines()[-1])


class ReviewCheckboxTest(Base):
    def test_finding_bullets_must_be_checkboxes(self):
        self.reviewed_ready()
        text = (self.spec / 'review.md').read_text()
        for line in ('- S2 (must): refund twice possible', '- **Q3 (must)**: secret in log', '* S4: untracked'):
            self.spec_file('review.md', text.replace('## Standards\n', '## Standards\n' + line + '\n'))
            self.assertFails(aidlc.check(self.spec, 'reviewed'), 'not a checkbox')
        self.spec_file('review.md', text.replace('## Standards\n', '## Standards\n- Overall the code is clean.\n'))
        self.assertPasses(aidlc.check(self.spec, 'reviewed'))


class VerifyHardeningTest(Base):
    def setUp(self):
        super().setUp()
        self.building()
        self.write('tests/test_refunds.py', '# RFD-1\n')

    def test_json_exit_is_the_cli_exit(self):
        code, payload = self.cli_json('verify', 'refunds', '--cmd', 'exit 4')
        self.assertEqual((code, payload['exit'], payload['command_exit']), (1, 1, 4))
        code, payload = self.cli_json('task-done', 'refunds', 'T1', '--cmd', 'exit 5')
        self.assertEqual((code, payload['exit'], payload['command_exit']), (1, 1, 5))

    def test_code_changed_during_the_run_is_not_green(self):
        code, out, _ = self.cli('verify', 'refunds', '--cmd', 'echo "y = 1" >> src/app.py')
        self.assertEqual(code, 1)
        self.assertIn('changed code', out)
        self.assertFails(aidlc.check(self.spec, 'verified'), 'changed code during')

    def test_gh_gets_the_branch_after_a_double_dash(self):
        self.fake_gh('build\tpass\t1m\thttps://ci/1\n')
        self.assertEqual(aidlc.gh_checks(self.repo, 'feat/refunds'), [('build', 'pass')])
        self.assertIn('pr checks -- feat/refunds', (self.base / 'gh-calls.log').read_text())
        self.assertIsNone(aidlc.gh_checks(self.repo, '-R evil/repo'))


class FastStatusTest(Base):
    def test_fast_status_runs_no_gh_and_no_contract_gate(self):
        self.shipped_ready()
        self.readme(spec=self.repo / 'docs' / 'specs' / 'api-change', key='API', contract='external')
        self.fake_gh('build\tpass\t1m\thttps://ci/1\n')
        log = self.base / 'gh-calls.log'
        import time
        with mock.patch.object(aidlc._contract, 'run', side_effect=AssertionError('contract gate ran')):
            started = time.time()
            items = {i['slug']: i for i in aidlc.status(self.repo, fast=True)}
            self.assertLess(time.time() - started, 1.5)
        self.assertFalse(log.exists())
        self.assertEqual(items['refunds']['next'], 'shipped')
        self.assertIsNotNone(items['refunds']['passes'])
        self.assertIsNotNone(items['api-change']['passes'])
        code, payload = self.cli_json('status', '--fast')
        self.assertEqual((code, len(payload['specs'])), (0, 2))
        self.assertFalse(log.exists())
        aidlc.status(self.repo)
        self.assertTrue(log.exists())


if __name__ == '__main__':
    unittest.main()
