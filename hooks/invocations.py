#!/usr/bin/env python3
"""Shell-command reading shared by the gates: which git, gh, curl and pr.py invocations a Bash command holds.

A gate that matches text misses `git -C . commit`, `/usr/bin/git push` and `bash -c "git commit"`, and fires on
`echo "git commit"`. These helpers split a command the way a shell does (shlex, with operators and newlines as
separators), look inside `bash -c '…'`, `eval`, `$(…)` and backticks, step over `env`, `sudo`, `command`, `xargs`
and variable assignments, and skip git's global options to reach the subcommand.

They cover the commands a session writes by default. An alias, a script, or another tool is not seen; that is what
`aidlc ci` behind branch protection is for (references/aidlc.md, trust model). Not a hook: imported by the gates.
"""
import pathlib
import re
import shlex

SHELLS = ('bash', 'sh', 'zsh', 'dash', 'ksh')
WRAPPERS = {'command': 0, 'builtin': 0, 'exec': 0, 'nohup': 0, 'time': 0, 'env': 0, 'sudo': 0, 'nice': 0, 'xargs': 0,
            'stdbuf': 0, 'timeout': 1}  # name -> positional arguments it takes before the command
WRAPPER_VALUES = {'sudo': ('-u', '-g', '-h', '-p', '-C', '-D', '-R', '-T'), 'nice': ('-n',), 'xargs': ('-I', '-n', '-P', '-d', '-L', '-s'),
                  'env': ('-u', '-C', '-S'), 'timeout': ('-s', '-k'), 'stdbuf': ('-i', '-o', '-e')}
GIT_VALUES = ('-C', '-c', '--git-dir', '--work-tree', '--namespace', '--super-prefix', '--config-env', '--attr-source')
GH_API_VALUES = ('-X', '--method', '-f', '--raw-field', '-F', '--field', '-H', '--header', '--input', '-q', '--jq',
                 '-t', '--template', '--hostname', '-p', '--preview', '--cache')
GH_API_BODY = ('-f', '--raw-field', '-F', '--field', '--input')
GH_MERGE_VALUES = ('-t', '--subject', '-b', '--body', '-F', '--body-file', '-A', '--author-email',
                   '--match-head-commit', '-R', '--repo', '--strategy')
CURL_BODY = ('-d', '--data', '--data-raw', '--data-binary', '--data-urlencode', '--json', '-F', '--form', '-T')
GITHUB_PULLS = re.compile(r'(?:^|/)repos/[^/\s]+/[^/\s]+/pulls/?(?:\?.*)?$')
GITHUB_MERGE = re.compile(r'(?:^|/)repos/[^/\s]+/[^/\s]+/pulls/(\d+)/merge/?(?:\?.*)?$')
BITBUCKET_PULLS = re.compile(r'api\.bitbucket\.org/\S*/pullrequests/?$')
BITBUCKET_MERGE = re.compile(r'api\.bitbucket\.org/\S*/pullrequests/(\d+)/merge/?$')
ASSIGNMENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
OPERATOR = re.compile(r'^[;&|()<>\n]+$')


def tokens(command):
    """Shell words of a command; operators and newlines come back as their own tokens."""
    lexer = shlex.shlex(command.replace('`', ' ; '), posix=True, punctuation_chars=';&|()<>\n')
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: fall back to a plain split, operators spaced out
        return re.sub(r'(&&|\|\||[;|\n()])', r' \1 ', command).split(' ') if command else []


def name_of(word):
    return pathlib.PurePosixPath(word.replace('\\', '/')).name


def simple_commands(command, depth=0):
    """Every simple command in `command` as a list of words, wrappers and assignments removed, nested shells opened."""
    found, current = [], []
    for word in tokens(command) + [';']:
        if OPERATOR.match(word) or word == '$':
            if current:
                found += _unwrap(current, depth)
            current = []
        elif word != '':
            current.append(word)
    return found


def _unwrap(words, depth):
    while words:
        head = name_of(words[0])
        if ASSIGNMENT.match(words[0]):
            words = words[1:]
        elif head in WRAPPERS:
            rest, positional = words[1:], WRAPPERS[head]
            while rest and (rest[0].startswith('-') or ASSIGNMENT.match(rest[0]) or positional):
                if rest[0] in WRAPPER_VALUES.get(head, ()):
                    rest = rest[2:]
                elif rest[0].startswith('-') or ASSIGNMENT.match(rest[0]):
                    rest = rest[1:]
                else:
                    rest, positional = rest[1:], positional - 1
            words = rest
        else:
            break
    if not words:
        return []
    head = name_of(words[0])
    if depth < 4 and head in SHELLS and '-c' in words[1:]:
        script = words[words.index('-c') + 1:]
        return simple_commands(script[0], depth + 1) if script else []
    if depth < 4 and head == 'eval':
        return simple_commands(' '.join(words[1:]), depth + 1)
    return [words]


def git_calls(command):
    """[{sub, args, dir}] for each git invocation: the subcommand behind any global option, its arguments, and the
    folder `-C` points at (None: where the command runs)."""
    calls, where = [], None
    for words in simple_commands(command):
        if words[0] == 'cd' and len(words) > 1 and not words[1].startswith('-'):
            where = str(pathlib.PurePosixPath(where or '.') / words[1])  # a later git call runs there
            continue
        if name_of(words[0]) not in ('git', 'git.exe'):
            continue
        index, folder = 1, where
        while index < len(words) and words[index].startswith('-'):
            if words[index] == '-C' and index + 1 < len(words):
                folder = str(pathlib.PurePosixPath(folder or '.') / words[index + 1])
            index += 2 if words[index] in GIT_VALUES else 1
        if index < len(words):
            calls.append({'sub': words[index], 'args': words[index + 1:], 'dir': folder})
    return calls


def _operands(words, value_options):
    """Words that are neither options nor the value of an option that takes one."""
    kept, skip = [], False
    for word in words:
        if skip:
            skip = False
        elif word in value_options:
            skip = True
        elif not word.startswith('-'):
            kept.append(word)
    return kept


def _option(words, names):
    """The value of the first of `names` given as `-X v`, `--method v` or `--method=v`; None when absent."""
    for index, word in enumerate(words):
        if word in names and index + 1 < len(words):
            return words[index + 1]
        for name in names:
            if name.startswith('--') and word.startswith(name + '='):
                return word.split('=', 1)[1]
            if not name.startswith('--') and len(word) > 2 and word.startswith(name) and not word.startswith('--'):
                return word[2:]
    return None


def _gh_api(words):
    """(endpoint, method, whole text) of a `gh api …` call."""
    operands = _operands(words, GH_API_VALUES)
    endpoint = operands[0] if operands else ''
    method = _option(words, ('-X', '--method'))
    if method is None:
        method = 'POST' if any(word in GH_API_BODY or word.startswith(('--field=', '--raw-field=', '--input='))
                               for word in words) else 'GET'
    return endpoint, method.upper(), ' '.join(words)


def _curl(words):
    """(url, writes) of a curl call: writes when a method other than GET or a body is given."""
    url = next((word for word in words if re.match(r'^https?://', word)), '')
    method = _option(words, ('-X', '--request'))
    body = any(word in CURL_BODY or word.startswith(('--data', '--json', '--form')) for word in words)
    return url, (method.upper() != 'GET') if method else body


def _pulls(command):
    """(kind, target) for each command that opens ('create') or merges ('merge') a pull request."""
    for words in simple_commands(command):
        head, rest = name_of(words[0]), words[1:]
        if head in ('gh', 'gh.exe'):
            plain = [word for word in rest if not word.startswith('-')]
            if plain[:1] == ['pr'] and 'create' in plain[1:2] + _operands(rest, ('-R', '--repo'))[1:2]:
                yield 'create', None
            elif plain[:1] == ['pr'] and 'merge' in _operands(rest, ('-R', '--repo'))[1:2]:
                after = rest[rest.index('merge') + 1:]
                target = (_operands(after, GH_MERGE_VALUES) or [None])[0]
                yield 'merge', '$' if any(re.search(r'[$`]', word) for word in after) else target
            elif plain[:1] == ['api']:
                endpoint, method, text = _gh_api(rest[rest.index('api') + 1:])
                merge = GITHUB_MERGE.search(endpoint)
                if merge and method in ('PUT', 'POST'):
                    yield 'merge', merge.group(1)
                elif GITHUB_PULLS.search(endpoint) and method == 'POST':
                    yield 'create', None
                elif endpoint == 'graphql' and re.search(r'\b(mergePullRequest|enablePullRequestAutoMerge)\b', text):
                    yield 'merge', '$'
                elif endpoint == 'graphql' and re.search(r'\bcreatePullRequest\b', text):
                    yield 'create', None
        elif head == 'hub' and rest[:1] == ['pull-request']:
            yield 'create', None
        elif head == 'curl':
            url, writes = _curl(rest)
            merge = GITHUB_MERGE.search(url) or BITBUCKET_MERGE.search(url)
            if merge and writes:
                yield 'merge', merge.group(1)
            elif writes and (BITBUCKET_PULLS.search(url) or ('api.github.com' in url and GITHUB_PULLS.search(url))):
                yield 'create', None
        else:  # scripts/pr.py behind an interpreter or on its own
            script = next((index for index, word in enumerate(words) if name_of(word) == 'pr.py'), None)
            if script is not None:
                after = [word for word in words[script + 1:] if not word.startswith('-')]
                if after[:1] == ['create']:
                    yield 'create', None
                elif after[:1] == ['merge']:
                    tail = words[words.index('merge', script) + 1:]
                    yield 'merge', '$' if any(re.search(r'[$`]', word) for word in tail) else (
                        _operands(tail, ('--strategy', '--repo')) or [None])[0]


COMMIT_VALUES = ('-m', '--message', '-F', '--file', '-C', '--reuse-message', '-c', '--reedit-message', '--fixup',
                 '--squash', '--author', '--date', '-t', '--template', '--cleanup', '--pathspec-from-file', '--trailer')


def commit_takes_worktree(args):
    """Whether a `git commit` also commits changes that were never staged: -a/--all, or paths named on the line."""
    for word in args:
        if word == '--all' or (word.startswith('-') and not word.startswith('--') and 'a' in word[1:]):
            return True
    return bool(_operands(args, COMMIT_VALUES))


def opens_pull_request(command):
    return any(kind == 'create' for kind, _ in _pulls(command))


def merges_pull_request(command):
    """(True, target) for the first merge in the command: a PR number, URL or branch, None for the current branch,
    '$' when a variable or a GraphQL call hides which one. (False, None) when it merges nothing."""
    for kind, target in _pulls(command):
        if kind == 'merge':
            return True, target
    return False, None
