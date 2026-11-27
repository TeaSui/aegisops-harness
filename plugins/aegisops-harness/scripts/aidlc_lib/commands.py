"""One function per CLI command."""
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403
from aidlc_lib.graph import *  # noqa: F401,F403
from aidlc_lib.model import *  # noqa: F401,F403
from aidlc_lib.gates import *  # noqa: F401,F403
from aidlc_lib.api import *  # noqa: F401,F403

def append_ledger(spec, event):
    """Append one event (the caller holds spec_lock); keeps the file's line ends."""
    path = spec.dir / 'ledger.md'
    if not path.exists():
        path.write_text(LEDGER_SKELETON.format(slug=spec.slug), encoding='utf-8')
    text, newline = read_for_edit(path)
    prefix = '' if text.endswith('\n') or not text else newline
    with open(path, 'ab') as handle:
        handle.write(f'{prefix}- {utc_now()} {event}{newline}'.encode('utf-8'))
    return event


def quoted(text):
    return json.dumps(' '.join(str(text).split()), ensure_ascii=False)


def run_command(cmd, cwd, timeout, env=None):
    """(exit code, last ~2KB of combined output); 124 on timeout. Nothing is streamed. `env` adds variables."""
    timed_out = False
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.Popen(cmd, shell=True, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=os.name == 'posix',
                                    env=dict(os.environ, **env) if env else None)
        except OSError as err:
            return 127, str(err)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out, code = True, 124
            _kill_tree(proc)
        except BaseException:  # Ctrl-C, SIGTERM: do not leave the suite running behind us
            _kill_tree(proc)
            raise
        size = out.seek(0, 2)
        out.seek(max(0, size - TAIL_BYTES))
        tail = out.read().decode('utf-8', 'replace')
    return code, tail + (f'\n[aidlc: timed out after {timeout}s]' if timed_out else '')


def _kill_tree(proc):
    """Kill the shell and its children (process group on POSIX; the shell alone elsewhere)."""
    killpg, sigkill = getattr(os, 'killpg', None), getattr(signal, 'SIGKILL', None)
    try:
        if killpg and sigkill:
            killpg(proc.pid, sigkill)
        else:
            proc.kill()
    except OSError:
        proc.kill()
    proc.wait()


def parse_junit(paths, req_ids, repo):
    """(summary, findings): summary {passed, failed, req_pass, req_fail, unreadable}."""
    patterns = {rid: id_pattern(rid) for rid in req_ids}
    summary = {'passed': 0, 'failed': 0, 'cases': 0, 'req_pass': set(), 'req_fail': set(), 'unreadable': False}
    findings = []
    for path in paths:
        try:
            root = ET.parse(str(path)).getroot()
        except ET.ParseError as err:
            summary['unreadable'] = True
            findings.append(fail(f'{repo.rel(path)}:{err.position[0]}: JUnit XML does not parse ({err})'))
            continue
        except OSError as err:
            summary['unreadable'] = True
            findings.append(fail(f'{repo.rel(path)}: unreadable ({err.strerror or err})'))
            continue
        for case in root.iter('testcase'):
            summary['cases'] += 1
            bad = case.find('failure') is not None or case.find('error') is not None
            skipped = case.find('skipped') is not None
            summary['failed' if bad else 'passed'] += 0 if skipped and not bad else 1
            name = f'{case.get("classname", "")} {case.get("name", "")}'
            for rid, pattern in patterns.items():
                if pattern.search(name) and not (skipped and not bad):
                    summary['req_fail' if bad else 'req_pass'].add(rid)
    summary['req_pass'] = sorted(summary['req_pass'] - summary['req_fail'])
    summary['req_fail'] = sorted(summary['req_fail'])
    return summary, findings


def cmd_status(args):
    root = repo_arg(args)
    items = status(root, fast=args.fast)
    lines = []
    for item in items:
        state = {True: 'PASS', False: 'BLOCKED', None: ''}[item['passes']]
        lines.append(f'{item["path"]}  {item["stage"]} → {item["next"] or "-"}  {state}'
                     + ('  (legacy: no key)' if item['legacy'] else ''))
        lines += [f'    {b}' for b in item['blockers'][:3]]
    return 0, {'repo': str(root), 'specs': items}, lines or ['no specs under docs/specs/ or */docs/specs/']


def cmd_check(args):
    spec = spec_arg(args)
    findings = _check(spec, args.to)
    return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'stage': spec.stage,
                                     'target': args.to or next_stage(spec.stage)})


def cmd_advance(args):
    spec = spec_arg(args)
    with spec_lock(spec.dir):
        return _advance(spec, args.stage, args)


def _advance(spec, target, args):
    current = spec.stage
    payload = {'spec': spec.repo.rel(spec.dir), 'from': current, 'to': target, 'advanced': False}
    if args.back:
        return _move_back(spec, current, target, args.reason, payload)
    if target == 'abandoned' and not args.reason:
        raise UsageError('abandoned needs --reason')
    if target in ('abandoned', 'superseded'):
        if current not in ACTIVE:
            raise UsageError(f'{target} applies to an active spec; this one is {current}')
        findings = [] if target == 'abandoned' or spec.meta.get('superseded_by') else [
            fail(f'{spec.label("README.md")}: superseded needs superseded_by: <slug>')]
    else:
        expected = 'shipped' if target == 'partially-implemented' else (
            STAGES[STAGES.index(target) - 1] if target in STAGES[1:] else None)
        if expected != current:
            raise UsageError(f'{current} cannot advance to {target} (next: {next_stage(current) or "none"}; '
                             'use --back --reason to move backwards)')
        findings = [] if spec.key else [fail(f'{spec.label("README.md")}: no valid key: — add "key: <2-6 capitals>" '
                                             '(unique per repository) before advancing')]
        findings += _check(spec, target)
    if failed(findings):
        return finding_result(findings, payload)
    if target == 'reviewed':
        findings += _record_pre_pr(spec)
        if failed(findings):
            return finding_result(findings, payload)
    updates = {'status': target, 'updated': today()}
    if target == 'building':
        updates['branch'] = spec.repo.branch()
    set_frontmatter(spec.dir / 'README.md', updates)
    reason = f' reason={quoted(args.reason)}' if args.reason else ''
    payload.update(advanced=True, ledger=append_ledger(spec, f'advance {current}→{target}{reason}'))
    return finding_result(findings + [('OK', f'{payload["spec"]}: {current} → {target}')], payload)


def _move_back(spec, current, target, reason, payload):
    if not reason:
        raise UsageError('--back needs --reason')
    if current not in STAGES or target not in STAGES or STAGES.index(target) >= STAGES.index(current):
        raise UsageError(f'--back moves to an earlier stage than {current}')
    updates = {'status': target, 'updated': today()}
    if target == 'proposed':
        updates['accepted_by'] = ''  # a spec sent back to proposed needs a fresh approval
    set_frontmatter(spec.dir / 'README.md', updates)
    payload.update(advanced=True, ledger=append_ledger(spec, f'advance {current}→{target} back reason={quoted(reason)}'))
    return 0, payload, [f'OK {payload["spec"]}: {current} → {target} (back)']


def _record_pre_pr(spec):
    top, head = spec.repo.git('rev-parse', '--show-toplevel'), spec.repo.git('rev-parse', 'HEAD')
    if top is None or head is None or top.returncode or head.returncode:
        return [fail('no commit at HEAD: cannot record the pre-PR review')]
    review = spec.review[0] or {}
    marker = _load('aidlc_mark_pr_review', HERE / 'mark-pr-review.py')
    marker.record(top.stdout.strip(), head.stdout.strip(), f'aidlc ({review.get("reviewers") or "review.md"})', 0,
                  f'aidlc advance reviewed: {spec.repo.rel(spec.dir)} fingerprint={short(spec.repo.fingerprint)}')
    return [('OK', f'pre-PR review recorded for HEAD {head.stdout.strip()[:12]}')]


def cmd_next(args):
    spec = spec_arg(args)
    tasks, findings = spec.tasks
    if not tasks or failed(findings):
        findings = findings or (spec.missing(spec.plan_name) if tasks is None
                                else plan_findings([], None, spec.label(spec.plan_name)))
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'batches': []})
    groups = batches(tasks)
    lines = [f'batch {i}: ' + ', '.join(f'{t["id"]} ({t["owner"] or "no owner"}: {", ".join(t["files"]) or "files not declared, runs alone"})' for t in g)
             for i, g in enumerate(groups, 1)]
    if not groups:
        lines = ['all tasks are done'] if all(t['done'] for t in tasks) else ['no task is ready (open dependencies)']
    return 0, {'spec': spec.repo.rel(spec.dir), 'batches': groups}, lines


def cmd_task_done(args):
    spec = spec_arg(args)
    tasks, problems = spec.tasks
    task = next((t for t in tasks or [] if t['id'] == args.task), None)
    if task is None:
        raise UsageError(f'{args.task} is not a task in {spec.label(spec.plan_name)}')
    unticked = _open_criteria(spec, task)
    if unticked:  # the implementer ticks each criterion once a test shows it; done means all of them
        return finding_result(unticked, {'spec': spec.repo.rel(spec.dir), 'task': task['id'], 'command_exit': None,
                                         'ticked': False, 'output_tail': ''})
    cmd = args.cmd or task['test']
    if not cmd:
        raise UsageError(f'{args.task} has no "test:" field; pass --cmd')
    done = {t['id'] for t in tasks if t['done']}
    findings = [warn(f'{task["id"]} depends on open {d}') for d in task['depends'] if d not in done]
    code, tail = run_command(cmd, spec.repo.root, args.timeout)
    payload = {'spec': spec.repo.rel(spec.dir), 'task': task['id'], 'command_exit': code, 'ticked': False,
               'output_tail': tail}
    if code != 0:
        findings.append(fail(f'{task["id"]}: command exited {code}; {spec.plan_name} and ledger.md unchanged\n{tail}'))
        return finding_result(findings, payload)
    with spec_lock(spec.dir):  # the plan may have changed while the command ran: re-read, tick by ID
        if not _tick(spec.dir / spec.plan_name, task['id']):
            findings.append(fail(f'{task["id"]} is no longer in {spec.label(spec.plan_name)}; nothing ticked'))
            return finding_result(findings, payload)
        fp = Repo(spec.repo.root).fingerprint
        event = append_ledger(spec, f'task-done {task["id"]} exit=0 fingerprint={fp} cmd={quoted(cmd)}')
    payload.update(ticked=True, ledger=event)
    return finding_result(findings + [('OK', f'{task["id"]} done')], payload)


def _tick(plan, task_id):
    """plan.md: tick the task's box; tickets.md: set the ticket's `Status:` to done."""
    text, newline = read_for_edit(plan)
    tickets = plan.name == 'tickets.md'
    tasks, _ = (parse_tickets if tickets else parse_plan)(text, plan.name)
    task = next((t for t in tasks if t['id'] == task_id), None)
    if task is None:
        return False
    lines = text.split('\n')
    if not tickets:
        lines[task['line'] - 1] = re.sub(r'\[ \]', '[x]', lines[task['line'] - 1], count=1)
    elif task['status_line']:
        line = lines[task['status_line'] - 1]
        lines[task['status_line'] - 1] = line[:len(line) - len(line.lstrip())] + 'Status: done'
    else:
        lines.insert(task['line'], 'Status: done')
    write_atomic(plan, '\n'.join(lines), newline)
    return True


def run_pinned(spec, config, timeout):
    """Run the pinned verify command once in the config's folder: (ledger text of the event, findings, payload).
    Nothing is written; the caller logs the event (`aidlc verify`) or uses it as it is (`aidlc ci`)."""
    root = spec.repo.root
    before = Repo(root).fingerprint
    started = time.time()
    code, tail = run_command(config['cmd'], config['dir'], timeout)
    repo = Repo(root)
    findings, junit = [], None
    event = f'verify exit={code} fingerprint={repo.fingerprint} cmd={quoted(config["cmd"])} pinned={config["source"]}'
    if code != 0:
        findings.append(fail(f'the pinned command exited {code}\n{tail}'))
    if before != repo.fingerprint:  # the tests did not run against one version of the code: not green
        findings.append(fail('the test command changed code files during the run (reports and build output belong '
                             'in git-ignored paths); fix that and re-run'))
        event += f' before={before}'
    if config['junit']:
        junit, problems, marker = _junit_results(config['junit'], started, spec, repo, config['dir'])
        findings += problems
        event += marker
    return event, findings, {'spec': repo.rel(spec.dir), 'pinned_command': config['cmd'], 'pinned': config['source'],
                             'command_exit': code, 'fingerprint': repo.fingerprint, 'junit': junit,
                             'output_tail': tail, 'ledger': event}


def _git_dir(repo):
    result = repo.git('rev-parse', '--absolute-git-dir') if repo.is_git else None
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    return pathlib.Path(result.stdout.strip())


def production_changes(repo, base):
    """[(status, path)] of the production source that differs between commit `base` and HEAD: A added, M modified,
    D deleted (a rename is a D and an A). Production source is code that is not a test (the TDD gate's rule)."""
    listing = repo._z('diff', '--name-status', '--no-renames', '-z', base, 'HEAD') or []
    return [(status[:1], path) for status, path in zip(listing[0::2], listing[1::2]) if _tdd.is_prod_code(path)]


class RevertRefused(Exception):
    """The revert check would touch work it cannot get back; nothing was changed."""


def _unsafe(repo, changes):
    """Why the revert check must not rewrite these files, or None: uncommitted work in them (the code fingerprint
    leaves out docs/ and names such as license_*.py, so `code_dirty` cannot see it), or a symbolic link."""
    paths = [path for _, path in changes]
    result = repo.git('status', '--porcelain', '--untracked-files=all', '--', *paths)
    if result is None or result.returncode != 0:
        return 'git status failed, so it is not known that these files are clean'
    dirty = [line[3:] for line in result.stdout.splitlines()]
    if dirty:
        return (f'uncommitted changes in {", ".join(dirty[:5])}: the revert check rewrites {"them" if len(dirty) > 1 else "it"}; '
                'commit or stash them first')
    for path in paths:
        probe = repo.root / path
        while probe != repo.root and probe != probe.parent:
            if probe.is_symlink():
                return f'{path} is, or sits behind, a symbolic link: the revert check does not write through links'
            probe = probe.parent
    return None


def _put_back(repo, changes):
    """Give the files a revert check rewrote the content HEAD holds. False when git could not restore them."""
    inside = [(status, path) for status, path in changes
              if repo.root in (repo.root / path).resolve().parents]  # never follow a path out of the repository
    for status, path in inside:  # first: on a case-insensitive filesystem a deleted `Foo.py` and an added `foo.py`
        if status == 'D':        # are one file, and unlinking it after the checkout would delete what was restored
            try:
                (repo.root / path).unlink()
            except OSError:
                pass
    at_head = [path for status, path in inside if status != 'D']
    restored = True
    if at_head:
        result = repo.git('checkout', 'HEAD', '--', *at_head)
        restored = result is not None and result.returncode == 0
    return restored


def heal_revert(root):
    """Finish the restore of a revert check that was killed mid-run; a note for the user, or None."""
    repo = Repo(root)
    folder = _git_dir(repo)
    marker = folder / REVERT_MARKER if folder else None
    if marker is None or not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text())
        changes = [(str(status), str(path)) for status, path in data['changes']]
        head = data.get('head')
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        changes, head = [], None
    now = repo.git('rev-parse', 'HEAD')
    now = now.stdout.strip() if now is not None and now.returncode == 0 else None
    if head and now != head:  # the work was moved on since: HEAD is no longer what the check was restoring to
        try:
            marker.unlink()
        except OSError:
            pass
        return ('aidlc: an interrupted revert check was found, but HEAD is not the commit it ran on: the files were '
                'not touched. Run `git status` and compare src with the branch before trusting the tree')
    if not _put_back(repo, changes):
        return ('aidlc: an interrupted revert check left production files at their base version and they could not be '
                'restored from HEAD (the marker is kept): run `git status`, then `git checkout HEAD -- <file>`')
    try:
        marker.unlink()
    except OSError:
        pass
    return (f'aidlc: an interrupted revert check had left {len(changes)} production file(s) at their base version; '
            'restored from HEAD')


def revert_check(spec, config, timeout):
    """Does any test depend on the production change? Put the production source of this branch back to the merge base
    with the trusted ref, run the pinned command (it must fail), restore HEAD. (ledger text of the event, findings);
    nothing is written to the ledger. The caller made sure the code is committed, so HEAD is the way back."""
    repo = Repo(spec.repo.root, base=spec.repo.base)
    current = repo.fingerprint

    def skipped(reason):
        return (f'revert-check skipped fingerprint={current} reason={quoted(reason)}',
                [warn(f'revert check skipped: {reason}')])

    trusted = repo.trusted_ref
    if not trusted:
        return skipped('no default branch to compare this branch with')
    merge = repo.git('merge-base', 'HEAD', trusted)
    base = merge.stdout.strip() if merge is not None and merge.returncode == 0 else ''
    if not base:
        return skipped(f'no merge base with {trusted} (a shallow clone? fetch the history)')
    changes = production_changes(repo, base)
    if not changes:
        return skipped(f'no production source changed since {trusted}')
    problem = _unsafe(repo, changes)
    if problem:
        raise RevertRefused(problem)
    folder = _git_dir(repo)
    marker = folder / REVERT_MARKER if folder else None
    head = repo.git('rev-parse', 'HEAD')
    head = head.stdout.strip() if head is not None and head.returncode == 0 else None
    if marker is not None:
        marker.write_text(json.dumps({'head': head, 'changes': changes}))
    started, junit, restored = time.time(), None, True
    previous = {}

    def terminate(signum, frame):
        raise SystemExit(128 + signum)  # the `finally` below puts the tree back

    try:
        for name in ('SIGTERM', 'SIGHUP'):
            if hasattr(signal, name):
                previous[getattr(signal, name)] = signal.signal(getattr(signal, name), terminate)
    except ValueError:  # not the main thread: no handler, the next command heals
        previous = {}
    try:
        for status, path in changes:  # added files go first (see _put_back): a case-only rename is a D and an A
            if status == 'A':
                try:
                    (repo.root / path).unlink()
                except OSError:
                    pass
        for status, path in changes:
            if status == 'A':
                continue
            data = repo.show(base, path)
            if data is None:
                raise OSError(f'cannot read {path} at {base[:12]}')
            target = repo.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        # No bytecode: a same-size edit within one second would leave a stale __pycache__ that outlives the restore.
        code, _ = run_command(config['cmd'], config['dir'], timeout, env={'PYTHONDONTWRITEBYTECODE': '1'})
        if config['junit']:
            junit, _, _ = _junit_results(config['junit'], started, spec, repo, config['dir'])
    finally:
        restored = _put_back(repo, changes)
        if marker is not None and restored:
            try:
                marker.unlink()
            except OSError:
                pass
        for number, handler in previous.items():
            signal.signal(number, handler)
    usable = isinstance(junit, dict) and not junit.get('unreadable') and junit.get('cases')
    tested = _tested(spec)
    still = sorted(set(junit['req_pass']) & set(tested)) if usable else []
    event = f'revert-check exit={code} fingerprint={current} base={base[:12]} files={len(changes)}'
    if usable:
        event += f' junit={junit["passed"]} passed, {junit["failed"]} failed'
    if still:
        event += f' still-green={",".join(still)}'
    findings = []
    if not restored or Repo(repo.root).fingerprint != current:
        findings.append(fail('the revert check could not restore the tree: run `git status`, then restore the '
                             'production files with `git checkout HEAD -- <file>` (the next aidlc command also tries)'))
    level, message = _revert_verdict(code, junit if usable else None, still, tested)
    findings.append((level, f'revert check ({len(changes)} production file(s) put back to {trusted}): {message}'))
    if level != 'FAIL' and still:
        findings.append(warn(f'{", ".join(still)}: the tests that name these stories pass without the production change '
                             '(existing behaviour, or tests that prove nothing)'))
    return event, findings


def pinned_config(spec, args):
    """The usable config of a spec, or raise UsageError; (None, result) when the config itself has failures."""
    config = spec.config
    if config is None:
        raise UsageError(NO_CONFIG.format(name=CONFIG_NAME))
    if failed(config['findings']):
        return None, finding_result(config['findings'], {'spec': spec.repo.rel(spec.dir), 'command_exit': None})
    source = f'{config["label"]} on {config["ref"]}' if config['source'] == 'base' else config['label']
    given = getattr(args, 'cmd', None)
    if given is not None and not same_command(given, config['cmd']):
        raise UsageError(f'the verify command is pinned by {source}: {config["cmd"]!r}. Run `aidlc verify '
                         f'{args.spec}` without --cmd; another command is not gate evidence (change the pin in its '
                         'own change, read by a person)')
    given = getattr(args, 'junit', None)
    if given is not None and given != config['junit']:
        raise UsageError(f'the JUnit reports are pinned by {source}: {config["junit"] or "waived"}. Run `aidlc verify '
                         f'{args.spec}` without --junit')
    return config, None


def cmd_verify(args):
    spec = spec_arg(args)
    config, refused = pinned_config(spec, args)
    if refused:
        return refused
    notes = [f for f in config['findings'] if f[0] == 'WARN']
    if config['revert_check']:  # red first, so that reports and build output end on the run of the real code
        blank = {'spec': spec.repo.rel(spec.dir), 'command_exit': None}
        if spec.repo.code_dirty:
            return finding_result(notes + [fail(
                'commit the code first: the revert check puts production files back to their base version and '
                'restores them from HEAD, so nothing uncommitted may be in its way')], blank)
        try:
            event, findings = revert_check(spec, config, args.timeout)
        except RevertRefused as refused:
            return finding_result(notes + [fail(str(refused))], blank)
        with spec_lock(spec.dir):
            append_ledger(spec, event)
        notes += findings
        if failed(findings):
            return finding_result(notes, dict(blank, ledger=event))
    event, findings, payload = run_pinned(spec, config, args.timeout)
    with spec_lock(spec.dir):
        append_ledger(spec, event)
    return finding_result(notes + findings + [('OK', f'verify logged: exit={payload["command_exit"]}')], payload)


def _junit_results(pattern, started, spec, repo, folder=None):
    """(summary or None, findings, ledger suffix). Reports older than the run (1 s clock slack) are ignored."""
    paths = sorted(p for p in globlib.glob(os.path.join(str(folder or repo.root), pattern), recursive=True)
                   if os.path.isfile(p))
    fresh = [p for p in paths if os.path.getmtime(p) >= started - 1]
    findings = [warn(f'ignored {len(paths) - len(fresh)} JUnit file(s) older than this run')] if len(fresh) < len(paths) else []
    if not fresh:
        return None, findings + [fail(f'verify.junit {pattern} matches no report written by this run')], ' junit=missing'
    junit, problems = parse_junit(fresh, [r['id'] for r in spec.requirements[0] or []], repo)
    findings += problems
    if junit['unreadable']:
        return junit, findings, ' junit=unreadable'
    if not junit['cases']:
        return junit, findings + [fail(f'verify.junit {pattern}: the reports hold no test case')], ' junit=missing'
    marker = f' junit={junit["passed"]} passed, {junit["failed"]} failed'
    marker += ''.join(f' {k.replace("_", "-")}={",".join(junit[k])}' for k in ('req_pass', 'req_fail') if junit[k])
    if junit['req_fail']:
        findings.append(fail(f'requirement tests failed: {", ".join(junit["req_fail"])}'))
    return junit, findings, marker


def cmd_ruling(args):
    spec = spec_arg(args)
    task = ''
    if args.task:
        tasks = spec.tasks[0] or []
        if not TASK_ID.match(args.task) or args.task not in {t['id'] for t in tasks}:
            raise UsageError(f'{args.task} is not a task in {spec.label(spec.plan_name)}')
        task = f'{args.task}: '
    clean = [' '.join(str(x).split()) for x in (args.decision, args.why, args.if_wrong)]
    if not all(clean):
        raise UsageError('--decision, --why and --if-wrong must not be empty')
    with spec_lock(spec.dir):
        event = append_ledger(spec, f'ruling {task}{clean[0]} — why: {clean[1]} — if wrong: {clean[2]}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'ledger': event}, [f'OK {event}']


def cmd_approve(args):
    """Record that a person approved this spec text (or that the request delegated the decision)."""
    spec = spec_arg(args)
    digest = spec_digest(spec)
    if digest is None:
        raise UsageError(f'{spec.label(spec.spec_name)} does not exist: nothing to approve')
    by = args.by
    if not by:
        user = spec.repo.git('config', 'user.name')
        by = user.stdout.strip() if user is not None and user.returncode == 0 else ''
    by = ' '.join(str(by or '').split())
    if not by:
        raise UsageError('pass --by "<name>" (git user.name is not set)')
    how = 'delegated' if args.delegated else 'approved'
    stamp = f'{by} (delegated in request)' if args.delegated else f'{by} ({today()})'
    with spec_lock(spec.dir):
        set_frontmatter(spec.dir / 'README.md', {'accepted_by': stamp})
        event = append_ledger(spec, f'approve spec={digest} by={quoted(by)} how={how}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'approved': digest, 'by': by, 'how': how, 'ledger': event}, [
        f'OK {event}', f'accepted_by: {stamp}. The approval is of {spec.spec_name} as it is now ({short(digest)}): '
                       'an edit needs a new approval.']


def cmd_attest(args):
    """Store what a reviewer returned (a file, or standard input). The plugin's hook does this when a reviewer agent
    returns; a person uses it for a review that happened elsewhere."""
    spec = spec_arg(args)
    if args.file:
        text, error = read_text(args.file, str(args.file))
        if text is None:
            raise UsageError(error or f'{args.file}: not readable')
    else:
        text = sys.stdin.read()
    if not text.strip():
        raise UsageError('nothing to store: the return is empty')
    path, written = record_return(spec.dir, args.agent, args.axis, text)
    rel = spec.repo.rel(path)
    return 0, {'spec': spec.repo.rel(spec.dir), 'path': rel, 'written': written}, [
        f'OK stored {rel}' if written else f'OK already stored as {rel}']


def cmd_stamp(args):
    spec = spec_arg(args)
    review = spec.dir / 'review.md'
    if not review.is_file():
        raise UsageError(f'{spec.label("review.md")} does not exist: write the review first')
    fp = spec.repo.fingerprint
    with spec_lock(spec.dir):
        set_frontmatter(review, {'fingerprint': fp})
        event = append_ledger(spec, f'stamp review fingerprint={fp}')
    return 0, {'spec': spec.repo.rel(spec.dir), 'fingerprint': fp, 'ledger': event}, [f'OK {event}']


def trace_rows(spec):
    tasks = spec.tasks[0] or []
    event, current = spec.last('verify'), spec.repo.fingerprint
    rows = []
    for req in spec.requirements[0] or []:
        tests = spec.repo.tests_referencing(req['id'])
        rows.append({'id': req['id'], 'title': req['title'],
                     'verify': req['verify'] + (f' — {req["verify_detail"]}' if req['verify_detail'] else ''),
                     'tasks': [t['id'] for t in tasks if req['id'] in t['covers']], 'tests': tests,
                     'result': _result(req, tests, event, current)})
    return rows


def _result(req, tests, event, current):
    if req['verify'] != 'test':
        return f'{req["verify"]}: {req["verify_detail"]}'
    if not tests:
        return 'no test'
    if event is None:
        return 'not run'
    if not fp_matches(event['fingerprint'], current):
        return 'stale'
    if event['exit'] != 0 or req['id'] in event['req_fail']:
        return 'fail'
    if isinstance(event.get('junit'), dict) and req['id'] not in event['req_pass']:
        return 'no passing test'  # the report is the evidence: an ID in a comment ran nothing
    return 'pass'


def trace_table(rows):
    cell = lambda value: str(value).replace('|', '\\|') or '-'  # noqa: E731
    lines = ['| Requirement | Title | Verify | Tasks | Tests | Result |', '|---|---|---|---|---|---|']
    for row in rows:
        lines.append('| ' + ' | '.join(cell(x) for x in (row['id'], row['title'], row['verify'], ', '.join(row['tasks']),
                                                          ', '.join(row['tests']), row['result'])) + ' |')
    return lines


def cmd_lint(args):
    """Check a standalone spec.md (e.g. a drafted prompt) against the accepted gate's spec.md rules."""
    path = pathlib.Path(args.file)
    text, error = read_text(path, str(path))
    if text is None:
        raise UsageError(error or f'{path}: not readable')
    if not KEY.match(args.key):
        raise UsageError(f'--key {args.key!r} must be 2-6 capital letters')
    label = path.name
    stories, findings = parse_spec(text, label, args.key)
    findings += spec_findings(text, label, stories)
    if not args.no_security and not spec_security(text):
        findings.append(fail(f'{label}: Implementation Decisions has no security decisions (a "### Security" heading '
                             'or a "**Security**" bullet: assets, threats, controls); pass --no-security only when '
                             'the trust-boundary check is all NO'))
    if not re.search(r'^\s*Status:\s*ready-for-agent\b', text, re.M | re.I):
        findings.append(warn(f'{label}: no "Status: ready-for-agent" line: the spec stage will ask for approval'))
    findings += lint_open_decisions(text, label, args.no_security)
    if not failed(findings):
        findings.append(('OK', f'{label}: {len(stories)} stories, every template section filled'))
    return finding_result(findings, {'file': str(path), 'stories': [s['id'] for s in stories]})


NATIONAL_ID = re.compile(r'\b(?:SAID|NRIC|national ID|ID number|passport number|social security)\b', re.I)
ID_RULE = re.compile(r'\b(?:mask\w*|pseudonym\w*|tokeni[sz]\w*|profile ?id|internal id|hash\w*|never (?:log|sen[dt]))',
                     re.I)
REGIME = re.compile(r'\b(?:compliance|regime|POPIA|PDPA|GDPR|PCI[ -]?DSS|SARB|MAS|CCPA|LGPD)\b', re.I)


def lint_open_decisions(text, label, no_security):
    """Warnings for what a security review would otherwise have to settle (and might ask about): the compliance
    regime, and a national ID with no rule for events and logs."""
    if no_security:
        return []
    out = []
    if not REGIME.search(text):
        out.append(warn(f'{label}: no compliance regime named (e.g. "Compliance: POPIA + SARB"): the security '
                        'review will have to assume one'))
    if NATIONAL_ID.search(text) and not ID_RULE.search(text):
        out.append(warn(f'{label}: a national ID is used but no decision says how it appears in events and logs '
                        '(masked, replaced by the profile ID, never logged)'))
    return out


class Unbound:
    """What `aidlc ci` runs the pinned suite for when no spec is bound to the branch (a fix, a chore)."""

    def __init__(self, repo):
        self.repo, self.dir, self.requirements = repo, repo.root, ([], [])


CI_GATE = {'accepted': 'accepted', 'planned': 'planned', 'building': 'planned', 'verified': 'verified',
           'reviewed': 'reviewed', 'shipped': 'reviewed'}  # `shipped` itself waits for this check's result


def _fresh(text):
    """The text of a ledger event as the event the gates read, marked as produced by this run."""
    kind, _, rest = text.partition(' ')
    event, problem = _event(kind, rest)
    if event is None:
        raise ValueError(problem[1])
    event.update(kind=kind, ts=utc_now(), line=None, fresh=True)
    return event


def _ci_base(args):
    if args.base:
        return args.base
    for name in ('GITHUB_BASE_REF', 'BITBUCKET_PR_DESTINATION_BRANCH'):
        if os.environ.get(name):
            return 'origin/' + os.environ[name]
    return None


def _claims(spec, config):
    """What CI cannot check and a person should read: who is said to have approved and reviewed, and every waiver."""
    lines = [f'accepted_by: {spec.meta.get("accepted_by") or "(not set)"}']
    review = spec.review[0]
    if review:
        lines.append(f'reviewers: {review["reviewers"] or "(not named)"}; QA verdict: {review["qa"] or "(none)"}')
    for event in spec.ledger[0]:
        if event['kind'] == 'ruling' and 'RISK-ACCEPTANCE NEEDED' in (event.get('decision') or ''):
            lines.append(f'ruling: {event["decision"]}')
    return lines + _waivers(config)


def _waivers(config):
    lines = []
    if config['source'] == 'onboarding':
        lines.append(f'ONBOARDING: the verify command comes from this change ({config["label"]} is not on '
                     f'{config["ref"] or "the default branch"} yet): read that file before approving')
    if config.get('junit_waiver'):
        lines.append(f'JUnit is waived ({config["junit_waiver"]}): stories are traced by a text search, not by a test '
                     'that ran')
    if not config.get('revert_check'):
        lines.append('the revert check is off: nothing shows that the tests depend on the change')
    if config.get('ci_waiver'):
        lines.append(f'CI is waived ({config["ci_waiver"]})')
    if config.get('returns_waiver'):
        lines.append(f'reviewer returns are waived ({config["returns_waiver"]}): review.md is the session\'s own account')
    return lines


def cmd_ci(args):
    """Recompute the evidence on the checked-out head with the config of the base ref. Reads no verify or revert line
    from a ledger and writes nothing to a spec folder: the local files are a cache of what this run finds."""
    root = repo_arg(args)
    base = _ci_base(args)
    repo = Repo(root, base=base)
    trusted = repo.trusted_ref
    if trusted is None:
        what = f'--base {base} is not a commit in this checkout' if base else 'no base ref found'
        raise UsageError(f'{what}: fetch the base branch with its history (actions/checkout fetch-depth: 0, or '
                         '`git fetch origin <branch>`) and pass --base origin/<branch>')
    branch = args.branch or os.environ.get('GITHUB_HEAD_REF') or os.environ.get('BITBUCKET_BRANCH') or repo.branch()
    head = repo.git('rev-parse', 'HEAD')
    head = head.stdout.strip()[:12] if head is not None and head.returncode == 0 else '?'
    specs = [spec for spec in (Spec(folder, repo) for folder in repo.spec_dirs())
             if branch and spec.meta.get('branch') == branch and spec.stage in ACTIVE]
    findings, rows = [], []
    if repo.code_dirty:
        findings.append(fail('the checkout has uncommitted code: this check judges a commit'))
    for spec in specs or [Unbound(repo)]:
        bound = isinstance(spec, Spec)
        name = repo.rel(spec.dir) if bound else f'(no spec bound to {branch or "this checkout"})'
        config = spec.config if bound else load_config(repo, [root])
        row = {'name': name, 'stage': spec.stage if bound else '-', 'config': None, 'claims': []}
        rows.append(row)
        if config is None:
            findings.append(fail(NO_CONFIG.format(name=CONFIG_NAME)))
            continue
        findings += config['findings']
        if failed(config['findings']):
            continue
        row.update(config=f'`{config["cmd"]}` ({config["label"]}, {config["source"]})',
                   claims=_claims(spec, config) if bound else _waivers(config))
        if bound and config['revert_check'] and not repo.code_dirty:
            try:
                text, result = revert_check(spec, config, args.timeout)
            except RevertRefused as refused:
                findings.append(fail(str(refused)))
                continue
            spec.fresh['revert-check'] = _fresh(text)
            findings += result
            if text.startswith('revert-check skipped') and 'no merge base' in text:
                findings.append(fail('no merge base with the base ref (a shallow checkout): the revert check cannot '
                                     'run, so this job cannot vouch for the tests; fetch the history '
                                     '(actions/checkout fetch-depth: 0) and re-run'))
        text, result, _ = run_pinned(spec, config, args.timeout)
        findings += result
        if not bound:
            findings.append(('OK', f'no spec is bound to {branch or "this checkout"}: only the pinned suite was run'))
            continue
        spec.fresh['verify'] = _fresh(text)
        if args.require != 'none' and STAGES.index(spec.stage) < STAGES.index(args.require):
            findings.append(fail(f'{name}: the spec is at {spec.stage}; this check needs it at {args.require} '
                                 '(finish the stages, commit the spec folder and push)'))
        findings += _check(spec, CI_GATE[spec.stage]) if spec.stage in CI_GATE else []
    findings = unique(findings)
    summary = _ci_summary(head, branch, trusted, rows, findings)
    target = args.summary or os.environ.get('GITHUB_STEP_SUMMARY')
    if target:
        try:
            with open(target, 'a', encoding='utf-8') as handle:
                handle.write('\n'.join(summary) + '\n')
        except OSError:
            pass
    return finding_result(findings, {'base': trusted, 'branch': branch, 'head': head,
                                     'specs': [row['name'] for row in rows], 'summary': summary})


def _ci_summary(head, branch, trusted, rows, findings):
    bound = any(row['stage'] != '-' for row in rows)
    ran = ('The suite and the revert check were run by this job; nothing was taken from a ledger.' if bound else
           'No spec is bound to this branch. Only the pinned suite was run by this job (no revert check, no stage '
           'required); nothing was taken from a ledger.')
    lines = [f'## Lifecycle gate: {"FAIL" if failed(findings) else "PASS"}', '',
             f'Head `{head}` ({branch or "detached"}) against `{trusted}`. {ran}', '']
    for row in rows:
        lines.append(f'- **{row["name"]}**, stage `{row["stage"]}`, verify command {row["config"] or "(none)"}')
    claims = [(row['name'], claim) for row in rows for claim in row['claims']]
    if claims:
        lines += ['', '### Not checked by this job (read it)', ''] + [f'- {name}: {claim}' for name, claim in claims]
    shown = [(level, message) for level, message in findings if level != 'OK']
    if shown:
        lines += ['', '### Findings', ''] + [f'- **{level}** {message.splitlines()[0]}' for level, message in shown]
    return lines


CONFIG_SKELETON = {'schema': SCHEMA, 'verify': {'cmd': '', 'junit': '', 'revert_check': True}}


def cmd_config(args):
    """init: write the repository config (never overwrites). show: the config the gates use here, and where from."""
    root = repo_arg(args)
    folder = (root / args.dir).resolve() if args.dir else root
    path = folder / CONFIG_NAME
    if args.action == 'init':
        if path.exists():
            raise UsageError(f'{path} already exists: edit it (in its own change, read by a person)')
        if not args.cmd or not args.junit:
            raise UsageError('config init needs --cmd "<full test suite>" and --junit "<report glob>" '
                             '(or --junit "none — <reason>")')
        data = json.loads(json.dumps(CONFIG_SKELETON))
        data['verify'].update(cmd=args.cmd, junit=args.junit, revert_check=not args.no_revert_check)
        text = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
        _, findings = parse_config(text, CONFIG_NAME)
        if failed(findings):
            raise UsageError('; '.join(m for level, m in findings if level == 'FAIL'))
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        rel = Repo(root).rel(path)
        return 0, {'path': rel, 'config': data}, [
            f'OK wrote {rel}', 'Keep the JUnit reports and build output git-ignored, protect this file '
            '(CODEOWNERS), and merge it to the default branch: until then the gates run in onboarding mode.']
    repo = Repo(root)
    config = load_config(repo, [folder] if folder == root else [folder, root])
    if config is None:
        return finding_result([fail(NO_CONFIG.format(name=CONFIG_NAME))], {'config': None})
    shown = {k: (str(v) if isinstance(v, pathlib.Path) else v) for k, v in config.items() if k != 'findings'}
    lines = [f'{config["label"]}: {config["source"]}' + (f' (read from {config["ref"]})' if config['source'] == 'base'
                                                         else ' (only on this branch)'),
             f'  verify.cmd: {config.get("cmd")}', f'  verify.junit: {config.get("junit") or "none — " + str(config.get("junit_waiver"))}',
             f'  verify.revert_check: {config.get("revert_check")}',
             f'  ci: {"none — " + config["ci_waiver"] if config.get("ci_waiver") else "required"}',
             f'  review.returns: {"none — " + config["returns_waiver"] if config.get("returns_waiver") else "required"}']
    code, payload, found = finding_result(config['findings'], {'config': shown})
    return code, payload, lines + found


def cmd_trace(args):
    spec = spec_arg(args)
    reqs, findings = spec.requirements
    if reqs is None:
        return finding_result(findings, {'spec': spec.repo.rel(spec.dir), 'rows': [], 'written': False})
    rows = trace_rows(spec)
    table = trace_table(rows)
    if args.write:
        with spec_lock(spec.dir):
            _write_section(spec.dir / 'README.md', 'Traceability',
                           [f'Generated by `aidlc trace --write` on {today()}.', ''] + table)
    return 0, {'spec': spec.repo.rel(spec.dir), 'rows': rows, 'written': bool(args.write)}, table


def _write_section(path, title, body):
    text, newline = read_for_edit(path)
    lines = text.rstrip('\n').split('\n')
    start = next((i for i, x in enumerate(lines) if re.match(rf'^##\s+{title}\s*$', x, re.I)), None)
    block = [f'## {title}', ''] + body + ['']
    if start is None:
        lines += [''] + block
    else:
        end = next((i for i in range(start + 1, len(lines)) if re.match(r'^#{1,2}\s', lines[i])), len(lines))
        lines[start:end] = block
    write_atomic(path, '\n'.join(lines).rstrip('\n') + '\n', newline)


README_SKELETON = """---
schema: {schema}
status: proposed
key: {key}
branch:
security: required
contract: none
accepted_by:
updated: {today}
---
# {slug}

Spec: `spec.md`. Tickets: `tickets.md`. Lifecycle events: `ledger.md` (written by `aidlc` only).
"""
SPEC_SKELETON = """# {slug}

<!-- Template: references/aidlc.md §2. User story n is requirement {key}-n; tests reference it as {key}-n. -->

## Problem Statement

## Solution

## User Stories

## Implementation Decisions

## Testing Decisions

## Out of Scope

## Further Notes
"""
TICKETS_SKELETON = """# Tickets — {slug}

<!--
## T1: <vertical slice title>
Blocked by: none
Covers: {key}-1..{key}-3
Status: ready-for-agent        (aidlc task-done sets: done)
What to build: <end-to-end behaviour, from the user's side>
- [ ] <acceptance criterion>
Test: <command>                (optional: default for aidlc task-done)
Files: <glob>, <glob>          (optional: needed to run tickets in parallel)
-->
"""
LEDGER_SKELETON = """# Ledger — {slug}

Append-only, written by `aidlc` only.

"""


def cmd_init(args):
    if not KEY.match(args.key):
        raise UsageError(f'--key {args.key!r} must be 2-6 capital letters')
    root = repo_arg(args)
    ref = args.spec
    target = pathlib.Path(ref).resolve() if ('/' in ref or os.sep in ref) else root / 'docs' / 'specs' / ref
    if not SLUG.match(target.name):
        raise UsageError(f'{target.name!r} is not a kebab-case slug')
    if (target / 'README.md').exists():
        raise UsageError(f'{target} already has a README.md')
    repo = Repo(repo_root(target))
    for other in repo.spec_dirs():
        if Spec(other, repo).meta.get('key') == args.key:
            raise UsageError(f'key {args.key} is already used by {repo.rel(other)}')
    target.mkdir(parents=True, exist_ok=True)
    values = {'key': args.key, 'slug': target.name, 'today': today(), 'schema': SCHEMA}
    written = []
    for name, skeleton in (('README.md', README_SKELETON), ('spec.md', SPEC_SKELETON),
                           ('tickets.md', TICKETS_SKELETON), ('ledger.md', LEDGER_SKELETON)):
        if not (target / name).exists():
            (target / name).write_text(skeleton.format(**values), encoding='utf-8')
            written.append(name)
    rel = repo.rel(target)
    return 0, {'path': rel, 'files': written}, [f'OK created {rel}: {", ".join(written)}']


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
