import base64
import http.server
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
PR = ROOT / 'scripts' / 'pr.py'
SHIP_GATE = ROOT / 'hooks' / 'ship-gate.py'
REVIEW_GATE = ROOT / 'hooks' / 'pr-review-gate.py'
_spec = importlib.util.spec_from_file_location('tea_sdlc_pr', PR)
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


class FakeBitbucket(http.server.BaseHTTPRequestHandler):
    """Just enough of api.bitbucket.org/2.0 for scripts/pr.py, for repository ws/repo."""
    state = None

    def log_message(self, *args):
        pass

    def reply(self, code, body=None, headers=None):
        data = json.dumps(body if body is not None else {}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        header = self.headers.get('Authorization', '')
        ok = header in ('Bearer tok', 'Basic ' + base64.b64encode(b'me@x.io:api').decode())
        if not ok:
            self.reply(401, {'error': {'message': 'Unauthorized'}})
        return ok

    def body(self):
        size = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(size) or b'{}')

    def pr_json(self, p):
        return {'id': p['id'], 'state': p['state'], 'title': p['title'],
                'links': {'html': {'href': f'https://bitbucket.org/ws/repo/pull-requests/{p["id"]}'}},
                'source': {'branch': {'name': p['head']}, 'commit': {'hash': p['sha'][:12]}},
                'destination': {'branch': {'name': p['base']}}}

    def do_GET(self):
        if not self.authorized():
            return
        url = urllib.parse.urlparse(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        s = self.state
        if path == '/2.0/repositories/ws/repo':
            return self.reply(200, {'mainbranch': {'name': 'main'}})
        if path == '/2.0/repositories/ws/repo/pullrequests':
            name = re.search(r'"(.*)"', query.get('q', [''])[0]).group(1)
            return self.reply(200, {'values': [self.pr_json(p) for p in s['prs'].values() if p['head'] == name]})
        match = re.fullmatch(r'/2.0/repositories/ws/repo/pullrequests/(\d+)(/\w+)?', path)
        if not match or int(match.group(1)) not in s['prs']:
            return self.reply(404, {'error': {'message': 'not found'}})
        p = s['prs'][int(match.group(1))]
        if match.group(2) == '/statuses':
            values = s['statuses']
            if 'page2' in query:
                return self.reply(200, {'values': values[1:]})
            return self.reply(200, {'values': values[:1], 'next': f'http://{self.headers["Host"]}{path}?page2=1'})
        if match.group(2) == '/comments':
            return self.reply(200, {'values': s['comments']})
        return self.reply(200, self.pr_json(p))

    def do_POST(self):
        if not self.authorized():
            return
        path, body, s = urllib.parse.urlparse(self.path).path, self.body(), self.state
        if path == '/2.0/repositories/ws/repo/pullrequests':
            n = len(s['prs']) + 1
            s['prs'][n] = {'id': n, 'state': 'OPEN', 'title': body['title'], 'head': body['source']['branch']['name'],
                           'base': body['destination']['branch']['name'], 'sha': s['sha'],
                           'description': body['description']}
            return self.reply(201, self.pr_json(s['prs'][n]))
        match = re.fullmatch(r'/2.0/repositories/ws/repo/pullrequests/(\d+)/(merge|comments)', path)
        p = s['prs'][int(match.group(1))]
        if match.group(2) == 'merge':
            s['merged'] = body
            p['state'] = 'MERGED'
            return self.reply(200, self.pr_json(p))
        s['replies'].append(body)
        return self.reply(201, {'id': 99, 'links': {'html': {'href': 'https://bitbucket.org/c/99'}}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        for args in (['init', '-q', '-b', 'main'], ['config', 'user.email', 't@e'], ['config', 'user.name', 't'],
                     ['remote', 'add', 'origin', 'git@ssh.bitbucket.org:ws/repo.git']):
            self.git(*args)
        (self.repo / 'a.txt').write_text('x')
        self.git('add', '-A')
        self.git('commit', '-qm', 'base')
        self.git('checkout', '-q', '-b', 'feat/x')
        self.sha = self.git('rev-parse', 'HEAD')
        FakeBitbucket.state = {'prs': {}, 'statuses': [], 'comments': [], 'replies': [], 'sha': self.sha}
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), FakeBitbucket)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('BITBUCKET_', 'TEA_SDLC_'))}
        self.env.update({'BITBUCKET_API': f'http://127.0.0.1:{self.server.server_port}/2.0',
                         'BITBUCKET_EMAIL': 'me@x.io', 'BITBUCKET_API_TOKEN': 'api', 'HOME': self.tmp.name})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True,
                              text=True).stdout.strip()

    def cli(self, *args, env=None):
        result = subprocess.run([sys.executable, str(PR), *args], cwd=self.repo, capture_output=True, text=True,
                                env=dict(self.env, **(env or {})))
        return result.returncode, result.stdout, result.stderr


class ProviderTest(unittest.TestCase):
    def test_remote_urls(self):
        for url in ('git@bitbucket.org:ws/repo.git', 'git@ssh.bitbucket.org:ws/repo.git',
                    'https://me@bitbucket.org/ws/repo.git', 'ssh://git@bitbucket.org/ws/repo'):
            match = pr.REMOTE.match(url)
            self.assertTrue(match.group('host').endswith('bitbucket.org'), url)
            self.assertEqual(match.group('path'), 'ws/repo', url)
        self.assertEqual([pr.pr_number(v) for v in ('42', '#42', 'https://bitbucket.org/ws/r/pull-requests/7',
                                                    'https://github.com/o/r/pull/9', 'feat/x')], [42, 42, 7, 9, None])


class BitbucketTest(Base):
    def test_provider_and_auth(self):
        self.assertTrue(self.cli('provider')[1].startswith('bitbucket\t'))
        self.assertTrue(self.cli('provider', env={'TEA_SDLC_PR_PROVIDER': 'github'})[1].startswith('github'))
        self.assertEqual(self.cli('auth')[0], 0)
        code, _, err = self.cli('auth', env={'BITBUCKET_API_TOKEN': 'wrong'})
        self.assertEqual(code, 1)
        self.assertIn('HTTP 401', err)
        self.assertNotIn('wrong', err)  # the token is never printed
        code, out, _ = self.cli('auth', env={'BITBUCKET_EMAIL': '', 'BITBUCKET_API_TOKEN': ''})
        self.assertEqual(code, 1)
        self.assertIn('BITBUCKET_API_TOKEN', out)
        self.assertEqual(self.cli('auth', env={'BITBUCKET_EMAIL': '', 'BITBUCKET_ACCESS_TOKEN': 'tok'})[0], 0)

    def test_create_view_checks_merge(self):
        self.assertEqual(self.cli('view')[0], 1)
        body = pathlib.Path(self.tmp.name) / 'body.md'
        body.write_text('Summary\n\nThreats checked: replay.')
        code, out, err = self.cli('create', '--title', 'Refunds', '--body-file', str(body))
        self.assertEqual((code, out.strip()), (0, 'https://bitbucket.org/ws/repo/pull-requests/1'), err)
        created = FakeBitbucket.state['prs'][1]
        self.assertEqual((created['head'], created['base'], created['description']), ('feat/x', 'main', body.read_text()))
        view = json.loads(self.cli('view')[1])
        self.assertEqual((view['number'], view['head'], view['head_sha']), (1, 'feat/x', self.sha[:12]))
        self.assertEqual(self.cli('checks')[0], 2)  # no checks reported
        FakeBitbucket.state['statuses'] = [
            {'key': 'build', 'name': 'build', 'state': 'INPROGRESS', 'updated_on': '2026-11-22T01:00:00Z'},
            {'key': 'build', 'name': 'build', 'state': 'SUCCESSFUL', 'updated_on': '2026-11-22T02:00:00Z'},
            {'key': 'sonar', 'name': 'sonar', 'state': 'FAILED', 'updated_on': '2026-11-22T02:00:00Z'}]
        code, out, _ = self.cli('checks', '--json')
        self.assertEqual(code, 1)
        self.assertEqual(sorted((r['name'], r['state']) for r in json.loads(out)), [('build', 'pass'), ('sonar', 'fail')])
        FakeBitbucket.state['statuses'][2]['state'] = 'INPROGRESS'
        self.assertEqual(self.cli('checks', '1')[0], 8)
        FakeBitbucket.state['statuses'][2]['state'] = 'SUCCESSFUL'
        self.assertEqual(self.cli('checks', 'feat/x')[0], 0)
        code, out, _ = self.cli('merge', '1', '--strategy', 'squash', '--delete-branch')
        self.assertEqual((code, json.loads(out)['state']), (0, 'MERGED'))
        self.assertEqual(FakeBitbucket.state['merged'], {'merge_strategy': 'squash', 'close_source_branch': True})

    def test_comments_and_reply(self):
        self.cli('create', '--title', 'T', '--body', 'b')
        FakeBitbucket.state['comments'] = [
            {'id': 5, 'content': {'raw': 'rename this'}, 'inline': {'path': 'src/a.js', 'to': 3},
             'user': {'display_name': 'Ann'}},
            {'id': 6, 'deleted': True, 'content': {'raw': 'x'}}]
        rows = json.loads(self.cli('comments')[1])
        self.assertEqual(rows, [{'id': 5, 'parent': None, 'path': 'src/a.js', 'line': 3, 'author': 'Ann',
                                 'body': 'rename this'}])
        code, out, _ = self.cli('reply', '1', '5', '--body', 'Fixed in abc123.')
        self.assertEqual(code, 0)
        self.assertEqual(FakeBitbucket.state['replies'], [{'content': {'raw': 'Fixed in abc123.'}, 'parent': {'id': 5}}])

    def test_aidlc_ci_gate_reads_bitbucket_statuses(self):
        self.cli('create', '--title', 'T', '--body', 'b')
        FakeBitbucket.state['statuses'] = [{'key': 'b', 'name': 'build', 'state': 'FAILED'}]
        old = dict(os.environ)
        os.environ.update(self.env)
        try:
            self.assertEqual(pr.checks_for(str(self.repo), 'feat/x'), [('build', 'fail')])
            os.environ['BITBUCKET_API_TOKEN'] = 'wrong'
            self.assertIsNone(pr.checks_for(str(self.repo), 'feat/x'))  # cannot tell → the CI: line decides
        finally:
            os.environ.clear()
            os.environ.update(old)


class BitbucketShipGateTest(Base):
    def hook(self, command):
        payload = {'tool_name': 'Bash', 'tool_input': {'command': command}, 'cwd': str(self.repo)}
        return subprocess.run([sys.executable, str(SHIP_GATE)], input=json.dumps(payload), capture_output=True,
                              text=True, env=self.env)

    def test_merge_by_bitbucket_pr_number_is_gated_on_the_spec(self):
        folder = self.repo / 'docs' / 'specs' / 'refunds'
        folder.mkdir(parents=True)
        (folder / 'README.md').write_text('---\nstatus: reviewed\nkey: RFD\nbranch: feat/x\n---\n# Refunds\n')
        self.git('add', '-f', '-A')  # a global gitignore may hide docs/
        self.git('commit', '-qm', 'spec')
        FakeBitbucket.state['sha'] = self.git('rev-parse', 'HEAD')
        self.cli('create', '--title', 'T', '--body', 'b')
        self.git('checkout', '-q', 'main')
        result = self.hook('python3 scripts/pr.py merge 1 --strategy squash')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('branch feat/x carries a spec', result.stderr)
        self.git('checkout', '-q', 'feat/x')
        self.assertEqual(self.hook('python3 scripts/pr.py merge --strategy squash').returncode, 2)


class GateMatchTest(unittest.TestCase):
    def load(self, path, name):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_gates_see_every_way_to_open_or_merge(self):
        review = self.load(REVIEW_GATE, 'pr_review_gate')
        ship = self.load(SHIP_GATE, 'ship_gate')
        for command in ('gh pr create --fill', 'python3 "/p/scripts/pr.py" create --title T --body b',
                        'curl -s -X POST -u "$E:$T" https://api.bitbucket.org/2.0/repositories/ws/repo/pullrequests '
                        '-d @b.json'):
            self.assertTrue(review.PR_CREATE.search(command), command)
        self.assertFalse(review.PR_CREATE.search('python3 scripts/pr.py view'))
        self.assertFalse(review.PR_CREATE.search('curl https://api.bitbucket.org/2.0/repositories/ws/repo/pullrequests/3'))
        cases = {'gh pr merge 12 --squash': '12', 'python3 "/p/scripts/pr.py" merge 7 --strategy squash': '7',
                 'python3 scripts/pr.py merge --strategy rebase': None, 'gh pr merge': None,
                 'curl -X POST https://api.bitbucket.org/2.0/repositories/ws/r/pullrequests/31/merge': '31',
                 'python3 scripts/pr.py merge "$PR"': '$'}
        for command, target in cases.items():
            self.assertTrue(ship.MERGE.search(command), command)
            self.assertEqual(ship.merge_target(command), target, command)
        self.assertTrue(ship.PR_REF.fullmatch('https://bitbucket.org/ws/repo/pull-requests/7'))


if __name__ == '__main__':
    unittest.main()
