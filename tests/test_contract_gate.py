import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GATE = ROOT / 'hooks' / 'contract-gate.py'
PR_GATE = ROOT / 'hooks' / 'pr-review-gate.py'

BAD = {'paths': {'/u': {'get': {'operationId': 'getUser', 'responses': {'200': {'description': 'ok'}}}}}}
ERR = {'content': {'application/json': {'schema': {'type': 'object', 'properties': {'error': {
    'type': 'object', 'properties': {'code': {'type': 'string'}, 'message': {'type': 'string'}}}}}}}}
GOOD = {'paths': {'/u': {'get': {'operationId': 'getUser',
                                 'responses': {'200': {'description': 'ok'}, '404': {'description': 'x', **ERR}}}}}}


class ContractGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.home, self.repo = base / 'home', base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 't@e')
        self.git('config', 'user.name', 't')
        (self.repo / 'a.txt').write_text('x')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.spec = self.repo / 'docs' / 'specs' / 'feat'
        (self.spec / 'contracts').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, capture_output=True, text=True, check=True)

    def spec_readme(self, **meta):
        meta = {'status': 'accepted', **meta}
        (self.spec / 'README.md').write_text('---\n' + '\n'.join(f'{k}: {v}' for k, v in meta.items()) + '\n---\n')

    def contract(self, doc):
        (self.spec / 'contracts' / 'api.json').write_text(json.dumps(doc))

    def hook(self, script, payload, env=None):
        full = {'session_id': 's1', 'cwd': str(self.repo), **payload}
        return subprocess.run([sys.executable, str(script)], input=json.dumps(full), capture_output=True, text=True,
                              env={**os.environ, 'HOME': str(self.home), **(env or {})})

    def edit(self, path='core/src/main/java/A.java', env=None):
        return self.hook(GATE, {'tool_name': 'Edit', 'tool_input': {'file_path': str(self.repo / path)}}, env)

    def test_failing_external_contract_blocks_first_production_edit_once(self):
        self.spec_readme(contract='external')
        self.contract(BAD)
        first = self.edit()
        self.assertEqual(first.returncode, 2)
        self.assertIn('no error response', first.stderr)
        self.assertEqual(self.edit().returncode, 0)

    def test_passing_contract_does_not_block(self):
        self.spec_readme(contract='external')
        self.contract(GOOD)
        self.assertEqual(self.edit().returncode, 0)

    def test_specs_without_external_contract_or_inactive_do_not_block(self):
        self.contract(BAD)
        self.spec_readme(contract='none')
        self.assertEqual(self.edit().returncode, 0)
        self.spec_readme(contract='external', status='implemented')
        self.assertEqual(self.edit('core/src/main/java/B.java').returncode, 0)

    def test_non_production_files_and_env_off_pass(self):
        self.spec_readme(contract='external')
        self.contract(BAD)
        self.assertEqual(self.edit('core/src/test/java/ATest.java').returncode, 0)
        self.assertEqual(self.edit('README.md').returncode, 0)
        self.assertEqual(self.edit(env={'TEA_SDLC_CONTRACT_GATE': 'off'}).returncode, 0)

    def record_review(self, open_findings=0):
        sha = self.git('rev-parse', 'HEAD').stdout.strip()
        top = self.git('rev-parse', '--show-toplevel').stdout.strip()
        folder = self.home / '.claude' / 'state' / 'pr-review' / hashlib.sha256(top.encode()).hexdigest()[:16]
        folder.mkdir(parents=True)
        (folder / f'{sha}.json').write_text(json.dumps({'open_findings': open_findings}))

    def open_pr(self):
        return self.hook(PR_GATE, {'tool_name': 'Bash', 'tool_input': {'command': 'gh pr create --fill'}})

    def test_pr_is_blocked_while_the_contract_fails_and_allowed_when_it_passes(self):
        self.record_review()
        self.spec_readme(contract='external')
        self.contract(BAD)
        blocked = self.open_pr()
        self.assertEqual(blocked.returncode, 2)
        self.assertIn('contract gate', blocked.stderr)
        self.contract(GOOD)
        self.assertEqual(self.open_pr().returncode, 0)

    def test_pr_without_external_contract_is_unaffected(self):
        self.record_review()
        self.spec_readme(contract='none')
        self.contract(BAD)
        self.assertEqual(self.open_pr().returncode, 0)


if __name__ == '__main__':
    unittest.main()
