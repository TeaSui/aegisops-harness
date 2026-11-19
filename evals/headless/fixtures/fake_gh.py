#!/usr/bin/env python3
"""A local stand-in for the GitHub CLI so the lifecycle suite can reach `shipped` without a network.

PRs live in <state dir>/prs.json next to a bare `origin`. `gh pr checks` is real CI: it runs `npm test` on a clean
checkout of the PR head and reports pass or fail, so a session cannot ship red code through it. Supported:
  gh pr create [--title T] [--body B] [--base B] [--head H] [--fill]
  gh pr view [N|BRANCH] [--json FIELDS] [-q EXPR]
  gh pr list [--head BRANCH] [--json FIELDS]
  gh pr checks [N|BRANCH] [--watch] [--required]
  gh pr merge [N|BRANCH] [--squash|--merge|--rebase] [--delete-branch]
  gh auth status, gh repo view --json defaultBranchRef
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

STATE = pathlib.Path(os.environ.get('FAKE_GH_STATE') or pathlib.Path(__file__).resolve().parent.parent / 'gh-state')
ORIGIN = STATE.parent / 'origin.git'


def git(*args, cwd=None, check=True):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=check).stdout.strip()


def load():
    try:
        return json.loads((STATE / 'prs.json').read_text())
    except (OSError, ValueError):
        return []


def save(prs):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / 'prs.json').write_text(json.dumps(prs, indent=2))


def opt(args, *names, default=None):
    for i, word in enumerate(args):
        if word in names and i + 1 < len(args):
            return args[i + 1]
    return default


def positional(args):
    skip = False
    for word in args:
        if skip:
            skip = False
            continue
        if word.startswith('-'):
            skip = word in ('--title', '-t', '--body', '-b', '--base', '-B', '--head', '-H', '--json', '-q', '--jq',
                            '-R', '--repo')
            continue
        return word
    return None


def find(prs, ref):
    if ref is None:
        ref = git('rev-parse', '--abbrev-ref', 'HEAD', check=False)
    for pr in prs:
        if str(pr['number']) == str(ref).rsplit('/', 1)[-1] or pr['headRefName'] == ref:
            return pr
    return None


def head_oid(branch):
    return git('--git-dir', str(ORIGIN), 'rev-parse', 'refs/heads/' + branch, check=False)


def emit(obj, args):
    fields = opt(args, '--json')
    if fields:
        obj = {k: obj.get(k) for k in fields.split(',')}
    query = opt(args, '-q', '--jq')
    if query and query.startswith('.') and isinstance(obj, dict):
        value = obj.get(query[1:])
        print(value if not isinstance(value, (dict, list)) else json.dumps(value))
    else:
        print(json.dumps(obj))


def ci(pr):
    """Run npm test on a clean checkout of the PR head; return (passed, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        git('clone', '--quiet', '--branch', pr['headRefName'], str(ORIGIN), tmp)
        run = subprocess.run('npm test', shell=True, cwd=tmp, capture_output=True, text=True, timeout=600)
        return run.returncode == 0, (run.stdout + run.stderr)[-2000:]


def main(argv):
    if argv[:2] == ['auth', 'status']:
        print('Logged in to github.local as fixture')
        return 0
    if argv[:2] == ['repo', 'view']:
        emit({'defaultBranchRef': {'name': 'main'}, 'name': 'shop'}, argv[2:])
        return 0
    if len(argv) < 2 or argv[0] != 'pr':
        sys.stderr.write('fake gh: unsupported command: %s\n' % ' '.join(argv))
        return 1
    command, args, prs = argv[1], argv[2:], load()
    if command == 'create':
        branch = opt(args, '--head', '-H') or git('rev-parse', '--abbrev-ref', 'HEAD')
        if not head_oid(branch):
            sys.stderr.write('fake gh: push %s to origin first (git push -u origin %s)\n' % (branch, branch))
            return 1
        if find(prs, branch):
            sys.stderr.write('fake gh: a pull request for branch "%s" already exists\n' % branch)
            return 1
        pr = {'number': len(prs) + 1, 'headRefName': branch, 'baseRefName': opt(args, '--base', '-B', default='main'),
              'title': opt(args, '--title', '-t', default=branch), 'state': 'OPEN'}
        save(prs + [pr])
        print('https://github.local/shop/pull/%d' % pr['number'])
        return 0
    if command == 'list':
        head = opt(args, '--head', '-H')
        rows = [dict(pr, headRefOid=head_oid(pr['headRefName']), url='https://github.local/shop/pull/%d' % pr['number'])
                for pr in prs if not head or pr['headRefName'] == head]
        print(json.dumps(rows))
        return 0
    pr = find(prs, positional(args))
    if pr is None:
        sys.stderr.write('fake gh: no pull requests found for branch\n')
        return 1
    if command == 'view':
        emit(dict(pr, headRefOid=head_oid(pr['headRefName']), url='https://github.local/shop/pull/%d' % pr['number'],
                  mergeable='MERGEABLE'), args)
        return 0
    if command == 'checks':
        passed, output = ci(pr)
        print('ci/npm-test\t%s\t12s\thttps://github.local/shop/actions/%d' % ('pass' if passed else 'fail',
                                                                             pr['number']))
        if not passed:
            sys.stderr.write(output + '\n')
        return 0 if passed else 1
    if command == 'merge':
        if pr['state'] != 'OPEN':
            sys.stderr.write('fake gh: pull request is %s\n' % pr['state'])
            return 1
        with tempfile.TemporaryDirectory() as tmp:
            git('clone', '--quiet', str(ORIGIN), tmp)
            git('-c', 'user.email=ci@github.local', '-c', 'user.name=github', 'merge', '--no-ff', '--quiet',
                '-m', 'Merge pull request #%d' % pr['number'], 'origin/' + pr['headRefName'], cwd=tmp)
            git('push', '--quiet', 'origin', 'HEAD:main', cwd=tmp)
        pr['state'] = 'MERGED'
        save(prs)
        print('Merged pull request #%d' % pr['number'])
        return 0
    sys.stderr.write('fake gh: unsupported pr command: %s\n' % command)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
