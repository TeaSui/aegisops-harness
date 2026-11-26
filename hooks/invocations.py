#!/usr/bin/env python3
"""Shell-command reading shared by the gates: which git, gh, curl and pr.py invocations a Bash command holds.

A gate that matches text misses `git -C . commit`, `/usr/bin/git push` and `bash -c "git commit"`, and fires on
`echo "run git commit"`. These helpers split a command the way a shell does (shlex, with operators and newlines as
separators), look inside `bash -c '…'`, `su -c`, `eval`, `$(…)`, backticks, `find -exec` and a here-document fed
to a shell, step over reserved words (`if … then`, `for … do`, `{`, `!`), `env`, `sudo`, `command`, `xargs` and
variable assignments, and skip git's global options to reach the subcommand. The text of a here-document that feeds
anything else (`cat > notes.md <<EOF`) is text, not commands.

`unquoted()` is the same command for a gate's text match, its floor for what the parser does not know (a wrapper
such as `chronic git push`): quoted strings emptied, here-document text dropped.

They cover the commands a session writes by default. An alias, a script, or another tool is not seen; that is what
`aidlc ci` behind branch protection is for (references/aidlc.md, trust model). Not a hook: imported by the gates.
"""
import pathlib
import re
import shlex

SHELLS = ('bash', 'sh', 'zsh', 'dash', 'ksh')
RUNNERS = SHELLS + ('su', 'runuser')  # take a script after -c
KEYWORDS = ('if', 'then', 'else', 'elif', 'do', 'while', 'until', '!', '{', '}')  # a command can follow these
FIND_EXEC = ('-exec', '-execdir', '-ok', '-okdir')
WRAPPERS = {'command': 0, 'builtin': 0, 'exec': 0, 'nohup': 0, 'time': 0, 'env': 0, 'sudo': 0, 'doas': 0, 'nice': 0,
            'xargs': 0, 'stdbuf': 0, 'setsid': 0, 'watch': 0, 'timeout': 1, 'flock': 1}  # name -> positionals before the command
WRAPPER_VALUES = {'sudo': ('-u', '-g', '-h', '-p', '-C', '-D', '-R', '-T'), 'doas': ('-u', '-C'), 'nice': ('-n',),
                  'xargs': ('-I', '-n', '-P', '-d', '-L', '-s'), 'env': ('-u', '-C', '-S'), 'timeout': ('-s', '-k'),
                  'stdbuf': ('-i', '-o', '-e'), 'watch': ('-n', '--interval'),
                  'flock': ('-w', '--timeout', '-E', '--conflict-exit-code')}
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
QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
COMMENT = re.compile(r'(?:^|(?<=\s))#')
HEREDOC = re.compile(r'(?<!<)<<(?!<)-?\s*(?:\'([^\'\n]+)\'|"([^"\n]+)"|\\?([A-Za-z_][A-Za-z0-9_]*))')
TO_SHELL = re.compile(r'\|\s*(?:sudo\s+)?(?:\S*/)?(?:%s)\b' % '|'.join(SHELLS))


def tokens(command):
    """Shell words of a command; operators and newlines come back as their own tokens."""
    text = _scan(command)
    lexer = shlex.shlex((command if text is None else text).replace('`', ' ; '), posix=True,
                        punctuation_chars=';&|()<>\n')
    lexer.commenters = ''  # comments were taken out by _scan: shlex would cut `fix#123` at the `#`
    lexer.whitespace = ' \t\r'
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:  # unbalanced quotes: fall back to a plain split, operators spaced out
        return re.sub(r'(&&|\|\||[;|\n()])', r' \1 ', command).split(' ') if command else []


def _scan(text, empty=False):
    """The text without its comments (a `#` that starts a word, outside quotes, up to the end of the line) and, with
    `empty`, with the inside of quoted strings emptied. None when a quote is left open: the caller keeps the text."""
    out, i, n, start = [], 0, len(text), True
    while i < n:
        char = text[i]
        if char == '\\' and i + 1 < n:
            out.append(text[i:i + 2])
            i, start = i + 2, False
        elif char in '"\'':
            j = i + 1
            while j < n and text[j] != char:
                j += 2 if char == '"' and text[j] == '\\' else 1
            if j >= n:
                return None
            out.append(char * 2 if empty else text[i:j + 1])
            i, start = j + 1, False
        elif char == '#' and start:
            while i < n and text[i] != '\n':
                i += 1
        else:
            out.append(char)
            i, start = i + 1, char in ' \t\r\n;&|()<>'
    return ''.join(out)


def name_of(word):
    return pathlib.PurePosixPath(word.replace('\\', '/')).name


def _segments(text):
    """The words of each simple command in a text, as the shell would split it."""
    found, current = [], []
    for word in tokens(text) + [';']:
        if OPERATOR.match(word) or word == '$':
            if current:
                found.append(current)
            current = []
        elif word != '':
            current.append(word)
    return found


def _heredocs(command):
    """(the command without the text of its here-documents, the documents a shell reads). A `<<WORD` with no
    terminator line, inside a quoted string or behind a `#` is left alone: its lines stay commands."""
    kept, scripts, lines, index = [], [], command.split('\n'), 0
    while index < len(lines):
        line = lines[index]
        index += 1
        kept.append(line)
        quoted = [match.span() for match in QUOTED.finditer(line)]
        outside = [m.start() for m in COMMENT.finditer(line) if not any(a < m.start() < b for a, b in quoted)]
        comment = outside[0] if outside else len(line)
        for match in HEREDOC.finditer(line):
            if match.start() >= comment or any(a < match.start() < b for a, b in quoted):
                continue
            word = match.group(1) or match.group(2) or match.group(3)
            end = next((i for i in range(index, len(lines)) if lines[i].strip() == word), None)
            if end is None:
                continue
            if _feeds_shell(line[:match.start()], line[match.end():comment]):
                scripts.append('\n'.join(lines[index:end]))
            index = end + 1
    return '\n'.join(kept), scripts


def _feeds_shell(before, after):
    """Whether the here-document opened on this line is read by a shell: `bash <<EOF`, `sudo sh -s <<EOF`,
    `cat <<EOF | sh`."""
    if TO_SHELL.search(after):
        return True
    words, _ = _strip((_segments(before) or [[]])[-1])
    return any(name_of(word) in SHELLS for word in words)  # `bash`, `sudo sh -s`, `ssh host bash`


def unquoted(command):
    """The command as a text match may read it: quoted strings emptied and here-document text dropped (kept when the
    document feeds a shell). A command name left in this text stands where a command can stand, or is an unquoted
    mention. An unbalanced quote is left as it is: the text stays readable to the match."""
    text, scripts = _heredocs(command)
    scanned = _scan(text, empty=True)
    return '\n'.join([text if scanned is None else scanned] + [unquoted(script) for script in scripts])


def simple_commands(command, depth=0):
    """Every simple command in `command` as a list of words, reserved words, wrappers and assignments removed, nested
    shells opened."""
    text, scripts = _heredocs(command)
    found = []
    for words in _segments(text):
        found += _unwrap(words, depth)
    if depth < 4:
        for script in scripts:
            found += simple_commands(script, depth + 1)
    return found


def _strip(words):
    """(words, wrapped): the words without leading reserved words, assignments and wrapper commands."""
    wrapped = False
    while words:
        head = name_of(words[0])
        if ASSIGNMENT.match(words[0]) or words[0] in KEYWORDS:
            words = words[1:]
        elif words[0] == 'function':
            words = words[2:]
        elif head in WRAPPERS:
            rest, positional = words[1:], WRAPPERS[head]
            while rest and (rest[0].startswith('-') or ASSIGNMENT.match(rest[0]) or positional):
                if rest[0] in WRAPPER_VALUES.get(head, ()):
                    rest = rest[2:]
                elif rest[0].startswith('-') or ASSIGNMENT.match(rest[0]):
                    rest = rest[1:]
                else:
                    rest, positional = rest[1:], positional - 1
            words, wrapped = rest, True
        else:
            break
    return words, wrapped


def _unwrap(words, depth):
    """The simple command itself, the commands it runs (see `_run`) and the ones in a quoted `$(…)` it holds."""
    found = _run(words, depth)
    if depth < 4:
        for word in words:
            inner = re.search(r'\$\((.*)\)', word, re.S) if '$(' in word else None
            if inner:
                found += simple_commands(inner.group(1), depth + 1)
    return found


def _run(words, depth):
    """The simple command itself, and the commands it runs: a script after `-c`, `eval`, `find -exec`."""
    words, wrapped = _strip(words)
    if not words:
        return []
    if depth >= 4:
        return [words]
    head = name_of(words[0])
    if wrapped and len(words) == 1 and re.search(r'\s', words[0]):  # watch "git push": the command is one word
        return simple_commands(words[0], depth + 1)
    if head == 'eval':
        return simple_commands(' '.join(words[1:]), depth + 1)
    found = [words]
    if head == 'find':
        for index, word in enumerate(words):
            if word in FIND_EXEC and words[index + 1:]:
                found += _unwrap(words[index + 1:], depth + 1)
        return found
    for index, word in enumerate(words):  # `flock lock sh -c "…"`, `su dev -c "…"`: the runner need not come first
        flag = next((i for i in range(index + 1, len(words)) if re.fullmatch(r'-[A-Za-z]*c[A-Za-z]*', words[i])), None)
        if name_of(word) in RUNNERS and flag is not None:  # -c, -lc, -ec: the script is the word after it
            if flag + 1 < len(words):
                found += simple_commands(words[flag + 1], depth + 1)
            break
    return found


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


def merge_targets(command):
    """Every pull request a command merges, in order: a number, URL or branch, None for the current branch, '$' when
    it cannot be known."""
    return [('$' if target is None and re.search(r'\bmerge\b[^;&|\n]*[$`]', command) else target)
            for kind, target in _pulls(command) if kind == 'merge']


def merges_pull_request(command):
    """(True, target) for the first merge in the command: a PR number, URL or branch, None for the current branch,
    '$' when a variable or a GraphQL call hides which one. (False, None) when it merges nothing."""
    for kind, target in _pulls(command):
        if kind == 'merge':
            if target is None and re.search(r'\bmerge\b[^;&|\n]*[$`]', command):
                target = '$'  # `gh pr merge $(…)`: the substitution was split off as a command of its own
            return True, target
    return False, None
