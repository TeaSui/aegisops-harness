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
        gh.write_text('#!/bin/sh\nprintf \'%s\' "$AIDLC_FAKE_OUT"\nexit ' + str(code) + '\n')
        gh.chmod(0o755)
        os.environ['AIDLC_GH'] = str(gh)
        os.environ['AIDLC_FAKE_OUT'] = output


class DocContractTest(Base):
    """The examples in references/aidlc.md must parse with the engine: the doc and the code cannot drift."""

    def test_every_artifact_example_is_present(self):
        blocks = doc_blocks()
        for name in ('requirements.md', 'spec-check.md', 'plan.md', 'ledger.md', 'review.md', 'ship.md'):
            self.assertIn(name, blocks)

    def test_readme_frontmatter_example(self):
        block = next(v for k, v in doc_blocks().items() if k.startswith('README frontmatter'))
        meta, _ = aidlc.parse_frontmatter(block)
        self.assertEqual(meta['key'], 'RFD')
        self.assertEqual(meta['status'], 'proposed')
        self.assertEqual(meta['branch'], 'feat/refunds')
        self.assertEqual(meta['security'], 'required')

    def test_requirements_example(self):
        reqs, findings = aidlc.parse_requirements(doc_blocks()['requirements.md'], 'requirements.md')
        self.assertPasses(findings)
        self.assertEqual([r['id'] for r in reqs], ['RFD-1', 'RFD-2'])
        self.assertEqual(len(reqs[0]['criteria']), 2)
        self.assertEqual((reqs[0]['verify'], reqs[1]['verify']), ('test', 'check'))
        self.assertEqual(reqs[1]['verify_detail'], 'k6 run load/refund-visibility.js')
        self.assertPasses(aidlc.requirement_findings(reqs, 'RFD', 'requirements.md'))

    def test_spec_check_example(self):
        guesses, findings = aidlc.parse_spec_check(doc_blocks()['spec-check.md'], 'spec-check.md')
        self.assertPasses(findings)
        self.assertEqual([(g['id'], g['open']) for g in guesses], [('G1', True), ('G2', False), ('G3', False)])

    def test_plan_example(self):
        tasks, findings = aidlc.parse_plan(doc_blocks()['plan.md'], 'plan.md')
        self.assertPasses(findings)
        self.assertEqual([t['id'] for t in tasks], ['T1', 'T2', 'T3'])
        self.assertEqual(tasks[0]['files'], ['src/refunds/model.ts', 'src/refunds/repo.ts'])
        self.assertEqual(tasks[1]['depends'], ['T1'])
        self.assertPasses(aidlc.plan_findings(tasks, ['RFD-1', 'RFD-2'], 'plan.md'))

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
        self.assertEqual(events[4]['fingerprint'], '8a01')

    def test_review_example(self):
        review, findings = aidlc.parse_review(doc_blocks()['review.md'], 'review.md')
        self.assertPasses(findings)
        self.assertPasses(aidlc.review_findings(review, 'review.md'))
        self.assertEqual(review['fingerprint'], '8a01')
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
    def test_docs_and_changelog_do_not_change_it_code_does(self):
        before = aidlc.fingerprint(self.repo)
        self.assertRegex(before, r'^[0-9a-f]{64}$')
        self.write('README.md', '# x\n')
        self.write('CHANGELOG.md', '## 1.0.0\n')
        self.write('docs/specs/refunds/review.md', 'x')
        self.write('package.json', '{"version": "2"}')
        self.assertEqual(aidlc.fingerprint(self.repo), before)
        self.write('src/app.py', 'x = 2\n')
        self.assertNotEqual(aidlc.fingerprint(self.repo), before)

    def test_untracked_code_counts_ignored_code_does_not(self):
        before = aidlc.fingerprint(self.repo)
        self.write('ignored/gen.py', 'x')
        self.write('debug.log', 'x')
        self.assertEqual(aidlc.fingerprint(self.repo), before)
        self.write('src/new.py', 'x')
        after = aidlc.fingerprint(self.repo)
        self.assertNotEqual(after, before)
        for name in ('db/1.sql', 'api/a.proto', 'api/s.graphql', 'features/r.feature'):
            self.write(name, 'x')
            self.assertNotEqual(aidlc.fingerprint(self.repo), after, name)
            after = aidlc.fingerprint(self.repo)

    def test_deleting_code_changes_it_and_it_is_stable(self):
        before = aidlc.fingerprint(self.repo)
        self.assertEqual(aidlc.fingerprint(self.repo), before)
        (self.repo / 'src' / 'app.py').unlink()
        self.assertNotEqual(aidlc.fingerprint(self.repo), before)

    def test_works_outside_git(self):
        folder = self.base / 'plain'
        (folder / 'src').mkdir(parents=True)
        (folder / 'src' / 'a.py').write_text('x')
        first = aidlc.fingerprint(folder)
        (folder / 'notes.md').write_text('x')
        self.assertEqual(aidlc.fingerprint(folder), first)
        (folder / 'src' / 'a.py').write_text('y')
        self.assertNotEqual(aidlc.fingerprint(folder), first)


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


class InitTest(Base):
    def test_creates_parsable_skeletons_that_block_acceptance(self):
        code, payload = self.cli_json('init', 'refunds', '--key', 'RFD')
        self.assertEqual(code, 0)
        for name in ('README.md', 'requirements.md', 'spec-check.md', 'plan.md', 'ledger.md'):
            self.assertTrue((self.spec / name).is_file(), name)
        data = aidlc.load_spec(self.spec)
        self.assertEqual([m for level, m in data['errors'] if level == 'FAIL'], [])
        self.assertEqual((data['stage'], data['readme']['key']), ('proposed', 'RFD'))
        self.assertEqual((data['requirements'], data['tasks'], data['ledger']), ([], [], []))
        findings = aidlc.check(self.spec, 'accepted')
        self.assertFails(findings, 'defines no requirement')
        self.assertFails(findings, 'has not run')
        self.assertFails(findings, 'accepted_by')

    def test_init_then_doc_examples_pass_the_gates(self):
        self.assertEqual(self.cli('init', 'refunds', '--key', 'RFD')[0], 0)
        blocks = doc_blocks()
        self.spec_file('requirements.md', '# Requirements\n\n' + blocks['requirements.md'])
        self.spec_file('spec-check.md', blocks['spec-check.md'].replace(
            '- [ ] G1: Is a partial refund allowed', '- [x] G1: Is a partial refund allowed').replace(
            'capture?', 'capture? — resolved: RFD-1 now says full refunds only'))
        self.spec_file('security.md', '# Security\nSTRIDE.\n')
        readme = self.spec / 'README.md'
        readme.write_text(readme.read_text().replace('accepted_by:', 'accepted_by: Tea (2026-11-19)'))
        self.assertPasses(aidlc.check(self.spec, 'accepted'))
        self.assertEqual(self.cli('advance', 'refunds', 'accepted')[0], 0)
        self.spec_file('plan.md', '# Plan\n\n' + blocks['plan.md'])
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
        self.assertTrue(any('plan.md' in b for b in items['payouts']['blockers']))
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


if __name__ == '__main__':
    unittest.main()
