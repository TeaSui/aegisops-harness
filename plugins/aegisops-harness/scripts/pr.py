#!/usr/bin/env python3
"""One pull-request interface for the lifecycle: GitHub through `gh`, Bitbucket Cloud through its REST API.

  pr.py provider                      github | bitbucket, and why (exit 0)
  pr.py auth                          can this session open PRs? (exit 0 yes, 1 no, with what to set)
  pr.py view [PR] [--branch B]        JSON {number, state, url, head, base, head_sha}; exit 1 when there is none
  pr.py create --title T (--body B | --body-file F) [--base B] [--head H]     prints the PR URL
  pr.py checks [PR] [--branch B] [--watch] [--interval S] [--timeout S] [--json]
                                      exit 0 all green, 1 a check failed, 8 still pending, 2 no checks reported
  pr.py merge [PR] [--strategy squash|merge|rebase] [--delete-branch]
  pr.py comments [PR]                 JSON [{id, parent, path, line, author, body}]
  pr.py reply PR COMMENT_ID (--body B | --body-file F)
  pr.py default-branch

PR = number or URL; omitted = the PR of the current branch. Provider: AEGISOPS_HARNESS_PR_PROVIDER (github | bitbucket),
else bitbucket when origin's host is bitbucket.org (incl. ssh.bitbucket.org), else github, where `gh` decides
(Enterprise hosts, mirrors and local paths included).
Bitbucket Cloud auth, from the environment only (never printed):
  BITBUCKET_EMAIL + BITBUCKET_API_TOKEN   Atlassian account email + API token with scopes read:repository:bitbucket,
                                          read:pullrequest:bitbucket, write:pullrequest:bitbucket (Basic auth)
  BITBUCKET_ACCESS_TOKEN                  a repository, project or workspace access token (Bearer)
  BITBUCKET_API                           API base, default https://api.bitbucket.org/2.0 (tests)
Pushing uses git's own credentials (SSH key or credential helper); this script never pushes.
"""
import argparse
import base64
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GH_STATES = {'pass': 'pass', 'fail': 'fail', 'pending': 'pending', 'skipping': 'skipping', 'cancel': 'fail'}
BB_STATES = {'SUCCESSFUL': 'pass', 'FAILED': 'fail', 'STOPPED': 'fail', 'INPROGRESS': 'pending'}
BB_STRATEGY = {'squash': 'squash', 'merge': 'merge_commit', 'rebase': 'fast_forward'}
REMOTE = re.compile(r'^(?:[\w+.-]+://)?(?:[^@/]+@)?(?P<host>[^:/]+)(?::\d+)?[:/](?P<path>.+?)(?:\.git)?/?$')


class PRError(Exception):
    """A failure to report to the user as one line (exit 1)."""


def git(args, cwd=None):
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ''


def remote(cwd=None):
    """(host, path) of origin, or (None, None)."""
    match = REMOTE.match(git(['remote', 'get-url', 'origin'], cwd))
    return (match.group('host').lower(), match.group('path')) if match else (None, None)


def provider(cwd=None):
    """(name, reason)."""
    forced = os.environ.get('AEGISOPS_HARNESS_PR_PROVIDER', '').strip().lower()
    if forced in ('github', 'bitbucket'):
        return forced, 'AEGISOPS_HARNESS_PR_PROVIDER'
    host, _ = remote(cwd)
    if host and (host == 'bitbucket.org' or host.endswith('.bitbucket.org')):
        return 'bitbucket', f'origin is on {host}'
    return 'github', f'origin is on {host or "an unknown host"}; gh decides'


def branch(cwd=None):
    return git(['rev-parse', '--abbrev-ref', 'HEAD'], cwd)


def read_body(args):
    if getattr(args, 'body_file', None):
        return pathlib.Path(args.body_file).read_text()
    return args.body or ''


def pr_number(value):
    """A PR number from '42', '#42' or a URL ending in /pull/42 or /pull-requests/42."""
    match = re.search(r'(?:^#?|/pull(?:-requests|requests)?/)(\d+)/?$', str(value or '').strip())
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------- Bitbucket Cloud

class Bitbucket:
    def __init__(self, cwd=None):
        host, path = remote(cwd)
        parts = (path or '').strip('/').split('/')
        if len(parts) < 2:
            raise PRError('origin is not a Bitbucket repository URL (expected <workspace>/<repo>)')
        self.workspace, self.slug, self.cwd = parts[-2], parts[-1], cwd
        self.api = os.environ.get('BITBUCKET_API', 'https://api.bitbucket.org/2.0').rstrip('/')
        self.repo = f'{self.api}/repositories/{urllib.parse.quote(self.workspace)}/{urllib.parse.quote(self.slug)}'

    @staticmethod
    def auth_header():
        token = os.environ.get('BITBUCKET_ACCESS_TOKEN')
        if token:
            return 'Bearer ' + token
        email, api_token = os.environ.get('BITBUCKET_EMAIL'), os.environ.get('BITBUCKET_API_TOKEN')
        if email and api_token:
            return 'Basic ' + base64.b64encode(f'{email}:{api_token}'.encode()).decode()
        return None

    def request(self, method, url, body=None, accept=(200, 201, 202)):
        header = self.auth_header()
        if not header:
            raise PRError('no Bitbucket credentials: set BITBUCKET_EMAIL and BITBUCKET_API_TOKEN (an Atlassian API '
                          'token with read:repository, read:pullrequest and write:pullrequest scopes for Bitbucket), '
                          'or BITBUCKET_ACCESS_TOKEN')
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url if url.startswith('http') else self.repo + url, data=data, method=method,
                                     headers={'Authorization': header, 'Accept': 'application/json',
                                              **({'Content-Type': 'application/json'} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode() or '{}'
                return resp.status, json.loads(raw), resp.headers.get('Location')
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode()).get('error', {}).get('message', '')
            except (ValueError, AttributeError):
                detail = ''
            finally:
                error.close()
            if error.code in accept:
                return error.code, {}, error.headers.get('Location')
            hint = {401: ' (credentials rejected: email + API token, not the username)',
                    403: ' (the token lacks a scope or repository permission)',
                    404: ' (repository or PR not found, or no read access)'}.get(error.code, '')
            raise PRError(f'Bitbucket {method} {url.split("?")[0]}: HTTP {error.code}{hint}'
                          + (f': {detail}' if detail else ''))
        except urllib.error.URLError as error:
            raise PRError(f'Bitbucket API unreachable: {error.reason}')

    def pages(self, url):
        out = []
        while url:
            _, data, _ = self.request('GET', url)
            out += data.get('values', [])
            url = data.get('next')
        return out

    @staticmethod
    def shape(pr):
        return {'number': pr.get('id'), 'state': pr.get('state'),
                'url': ((pr.get('links') or {}).get('html') or {}).get('href'),
                'head': ((pr.get('source') or {}).get('branch') or {}).get('name'),
                'base': ((pr.get('destination') or {}).get('branch') or {}).get('name'),
                'head_sha': ((pr.get('source') or {}).get('commit') or {}).get('hash'), 'title': pr.get('title')}

    def find(self, target=None, head=None):
        number = pr_number(target)
        if number:
            return self.shape(self.request('GET', f'/pullrequests/{number}')[1])
        name = head or target or branch(self.cwd)
        query = urllib.parse.urlencode({'q': f'source.branch.name="{name}"', 'sort': '-updated_on'})
        states = '&'.join('state=' + s for s in ('OPEN', 'MERGED', 'DECLINED', 'SUPERSEDED'))
        found = self.pages(f'/pullrequests?{query}&{states}&pagelen=10')
        open_first = sorted(found, key=lambda p: p.get('state') != 'OPEN')
        return self.shape(open_first[0]) if open_first else None

    def create(self, title, body, base=None, head=None):
        base = base or self.default_branch()
        payload = {'title': title, 'description': body, 'close_source_branch': True,
                   'source': {'branch': {'name': head or branch(self.cwd)}}, 'destination': {'branch': {'name': base}}}
        return self.shape(self.request('POST', '/pullrequests', payload)[1])

    def default_branch(self):
        return (self.request('GET', '')[1].get('mainbranch') or {}).get('name') or 'main'

    def checks(self, target=None):
        pr = self.find(target)
        if pr:
            rows = self.pages(f'/pullrequests/{pr["number"]}/statuses?pagelen=50')
        else:
            sha = git(['rev-parse', 'HEAD'], self.cwd)
            rows = self.pages(f'/commit/{sha}/statuses?pagelen=50') if sha else []
        latest = {}
        for row in rows:  # one row per key: a rerun replaces the earlier state
            key = row.get('key') or row.get('name')
            if key not in latest or str(row.get('updated_on', '')) >= str(latest[key].get('updated_on', '')):
                latest[key] = row
        return [(r.get('name') or r.get('key'), BB_STATES.get(str(r.get('state')).upper(), 'pending'))
                for r in latest.values()]

    def merge(self, target=None, strategy='squash', delete_branch=False):
        pr = self.find(target)
        if not pr:
            raise PRError('no pull request for this branch')
        status, data, location = self.request('POST', f'/pullrequests/{pr["number"]}/merge',
                                              {'merge_strategy': BB_STRATEGY[strategy],
                                               'close_source_branch': bool(delete_branch)})
        deadline = time.time() + 120
        while status == 202 and location and time.time() < deadline:  # merge runs as a task
            time.sleep(2)
            _, task, _ = self.request('GET', location)
            if task.get('task_status') == 'SUCCESS':
                return self.shape(task.get('merge_result') or pr)
            if task.get('task_status') not in (None, 'PENDING'):
                raise PRError(f'merge task ended {task.get("task_status")}')
        return self.shape(data) if data else dict(pr, state='MERGING')

    def comments(self, target=None):
        pr = self.find(target)
        if not pr:
            raise PRError('no pull request for this branch')
        out = []
        for c in self.pages(f'/pullrequests/{pr["number"]}/comments?pagelen=100'):
            if c.get('deleted'):
                continue
            inline = c.get('inline') or {}
            out.append({'id': c.get('id'), 'parent': (c.get('parent') or {}).get('id'), 'path': inline.get('path'),
                        'line': inline.get('to') or inline.get('from'),
                        'author': (c.get('user') or {}).get('display_name'),
                        'body': (c.get('content') or {}).get('raw')})
        return out

    def reply(self, target, comment_id, body):
        pr = self.find(target)
        if not pr:
            raise PRError('no pull request for this branch')
        _, data, _ = self.request('POST', f'/pullrequests/{pr["number"]}/comments',
                                  {'content': {'raw': body}, 'parent': {'id': int(comment_id)}})
        return {'id': data.get('id'), 'url': ((data.get('links') or {}).get('html') or {}).get('href')}


# ---------------------------------------------------------------- GitHub (gh)

class GitHub:
    def __init__(self, cwd=None):
        self.cwd = cwd
        self.gh = os.environ.get('AIDLC_GH') or shutil.which('gh')
        if not self.gh:
            raise PRError('gh is not installed: install the GitHub CLI and run `gh auth login`')

    def run(self, args, check=True):
        result = subprocess.run([self.gh, *args], cwd=self.cwd, capture_output=True, text=True)
        if check and result.returncode:
            raise PRError(f'gh {" ".join(args[:2])}: ' + (result.stderr.strip() or f'exit {result.returncode}'))
        return result

    def find(self, target=None, head=None):
        args = ['pr', 'view'] + ([str(target or head)] if (target or head) else []) + [
            '--json', 'number,state,url,headRefName,baseRefName,headRefOid,title']
        result = self.run(args, check=False)
        if result.returncode:
            return None
        try:
            pr = json.loads(result.stdout)
        except ValueError:
            return None
        return {'number': pr.get('number'), 'state': pr.get('state'), 'url': pr.get('url'),
                'head': pr.get('headRefName'), 'base': pr.get('baseRefName'), 'head_sha': pr.get('headRefOid'),
                'title': pr.get('title')}

    def create(self, title, body, base=None, head=None):
        args = ['pr', 'create', '--title', title, '--body', body] + (['--base', base] if base else []) + (
            ['--head', head] if head else [])
        url = self.run(args).stdout.strip().splitlines()
        return self.find(head) or {'url': url[-1] if url else None}

    def default_branch(self):
        out = self.run(['repo', 'view', '--json', 'defaultBranchRef', '-q', '.defaultBranchRef.name'], check=False)
        return out.stdout.strip() or 'main'

    def checks(self, target=None):
        result = self.run(['pr', 'checks'] + (['--', str(target)] if target else []), check=False)
        rows = []
        for line in result.stdout.splitlines():
            cols = line.split('\t')
            if len(cols) >= 2 and cols[1].strip().lower() in GH_STATES:
                rows.append((cols[0].strip(), GH_STATES[cols[1].strip().lower()]))
        return rows

    def merge(self, target=None, strategy='squash', delete_branch=False):
        args = ['pr', 'merge'] + ([str(target)] if target else []) + ['--' + strategy] + (
            ['--delete-branch'] if delete_branch else [])
        self.run(args)
        return self.find(target) or {'state': 'MERGED'}

    def comments(self, target=None):
        pr = self.find(target)
        if not pr:
            raise PRError('no pull request for this branch')
        out = self.run(['api', '--paginate', f'repos/{{owner}}/{{repo}}/pulls/{pr["number"]}/comments']).stdout
        rows = json.loads(out or '[]')
        return [{'id': c.get('id'), 'parent': c.get('in_reply_to_id'), 'path': c.get('path'),
                 'line': c.get('line') or c.get('original_line'), 'author': (c.get('user') or {}).get('login'),
                 'body': c.get('body')} for c in rows]

    def reply(self, target, comment_id, body):
        pr = self.find(target)
        if not pr:
            raise PRError('no pull request for this branch')
        out = self.run(['api', '-X', 'POST', f'repos/{{owner}}/{{repo}}/pulls/{pr["number"]}/comments/{comment_id}'
                        '/replies', '-f', f'body={body}']).stdout
        data = json.loads(out or '{}')
        return {'id': data.get('id'), 'url': data.get('html_url')}


def client(cwd=None):
    name, _ = provider(cwd)
    return Bitbucket(cwd) if name == 'bitbucket' else GitHub(cwd)


def checks_for(root, target):
    """[(name, state)] for aidlc's CI gate, or None when no provider can tell (missing CLI or credentials,
    no checks reported). Never raises."""
    try:
        rows = client(root).checks(target)
    except (PRError, OSError, ValueError, subprocess.SubprocessError):
        return None
    return rows or None


def verdict(rows):
    if not rows:
        return 2
    states = {state for _, state in rows}
    return 1 if 'fail' in states else 8 if 'pending' in states else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='pr.py', description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('provider')
    sub.add_parser('auth')
    sub.add_parser('default-branch')
    view = sub.add_parser('view')
    view.add_argument('pr', nargs='?')
    view.add_argument('--branch')
    create = sub.add_parser('create')
    create.add_argument('--title', required=True)
    body = create.add_mutually_exclusive_group(required=True)
    body.add_argument('--body')
    body.add_argument('--body-file')
    create.add_argument('--base')
    create.add_argument('--head')
    checks = sub.add_parser('checks')
    checks.add_argument('pr', nargs='?')
    checks.add_argument('--branch')
    checks.add_argument('--watch', action='store_true')
    checks.add_argument('--interval', type=int, default=30)
    checks.add_argument('--timeout', type=int, default=1800)
    checks.add_argument('--json', action='store_true')
    merge = sub.add_parser('merge')
    merge.add_argument('pr', nargs='?')
    merge.add_argument('--strategy', choices=sorted(BB_STRATEGY), default='squash')
    merge.add_argument('--delete-branch', action='store_true')
    comments = sub.add_parser('comments')
    comments.add_argument('pr', nargs='?')
    reply = sub.add_parser('reply')
    reply.add_argument('pr')
    reply.add_argument('comment_id')
    rbody = reply.add_mutually_exclusive_group(required=True)
    rbody.add_argument('--body')
    rbody.add_argument('--body-file')
    args = parser.parse_args(argv)
    try:
        if args.cmd == 'provider':
            name, why = provider()
            print(f'{name}\t{why}')
            return 0
        if args.cmd == 'auth':
            name, why = provider()
            if name == 'bitbucket':
                ok = bool(Bitbucket.auth_header())
                if ok:
                    Bitbucket().request('GET', '')
                print(f'bitbucket ({why}): ' + ('credentials accepted for this repository' if ok else
                      'no credentials: set BITBUCKET_EMAIL + BITBUCKET_API_TOKEN or BITBUCKET_ACCESS_TOKEN'))
                return 0 if ok else 1
            result = GitHub().run(['auth', 'status'], check=False)
            print(f'github ({why}): ' + ('gh is signed in' if result.returncode == 0 else 'run `gh auth login`'))
            return result.returncode and 1
        api = client()
        if args.cmd == 'default-branch':
            print(api.default_branch())
            return 0
        if args.cmd == 'view':
            pr = api.find(args.pr, args.branch)
            print(json.dumps(pr) if pr else 'no pull request for this branch')
            return 0 if pr else 1
        if args.cmd == 'create':
            pr = api.create(args.title, read_body(args), args.base, args.head)
            print(pr.get('url') or json.dumps(pr))
            return 0
        if args.cmd == 'checks':
            target = args.pr or args.branch
            deadline = time.time() + args.timeout
            while True:
                rows = api.checks(target)
                code = verdict(rows)
                if not (args.watch and code in (8, 2)) or time.time() > deadline:
                    break
                time.sleep(args.interval)
            if args.json:
                print(json.dumps([{'name': n, 'state': s} for n, s in rows]))
            else:
                print('\n'.join(f'{n}\t{s}' for n, s in rows) or 'no checks reported')
            return code
        if args.cmd == 'merge':
            pr = api.merge(args.pr, args.strategy, args.delete_branch)
            print(json.dumps(pr))
            return 0
        if args.cmd == 'comments':
            print(json.dumps(api.comments(args.pr), indent=1))
            return 0
        if args.cmd == 'reply':
            print(json.dumps(api.reply(args.pr, args.comment_id, read_body(args))))
            return 0
    except PRError as error:
        print(f'pr.py: {error}', file=sys.stderr)
        return 1
    return 2


if __name__ == '__main__':
    sys.exit(main())
