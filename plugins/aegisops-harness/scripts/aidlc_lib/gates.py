"""The gates of each stage, the evidence they read and the reviewer returns."""
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403
from aidlc_lib.graph import *  # noqa: F401,F403
from aidlc_lib.model import *  # noqa: F401,F403

def record_return(spec_dir, agent, axis, text):
    """Store what a reviewer returned, verbatim, as its own file in <spec>/returns/. (path, True) when written,
    (path, False) when the same text is already stored. Called by hooks/record-returns.py and `aidlc attest`."""
    spec = Spec(spec_dir)
    body = text.replace('\r\n', '\n').strip('\n') + '\n'
    digest = hashlib.sha256(body.encode('utf-8')).hexdigest()
    folder = spec.dir / RETURNS
    with spec_lock(spec.dir):
        folder.mkdir(exist_ok=True)
        existing = sorted(folder.glob('*.md'))
        for path in existing:
            meta, _ = parse_frontmatter(path.read_text(encoding='utf-8', errors='replace'))
            if meta and meta.get('sha256') == digest:
                return path, False
        now = datetime.datetime.now(datetime.timezone.utc)
        name = '%s-%02d-%s-%s.md' % (now.strftime('%Y%m%dT%H%M%SZ'), len(existing) + 1,
                                     re.sub(r'[^a-z0-9-]', '-', str(agent).split(':')[-1].lower()), axis)
        header = (f'---\nagent: {agent}\naxis: {axis}\nfingerprint: {spec.repo.fingerprint}\nsha256: {digest}\n'
                  f'recorded: {now.strftime("%Y-%m-%dT%H:%M:%SZ")}\n---\n')
        write_atomic(folder / name, header + body)
    return folder / name, True


def returns_findings(spec, review, qa_waived):
    """review.md rests on what the reviewers returned: both axes and QA covered, every returned finding present with
    the severity it was given, the QA verdict the one QA gave last."""
    config = spec.config or {}
    if config.get('returns_waiver'):
        return [warn(f'reviewer returns are waived in {config["label"]} ({config["returns_waiver"]}): review.md is the '
                     'session\'s own account of the review')]
    returns, findings = spec.returns
    folder = spec.label(RETURNS)
    if not returns:
        return findings + [fail(
            f'{folder}/: no reviewer return is stored, so review.md rests on nothing. Dispatch '
            'aegisops-harness:code-reviewer (AXIS: spec and AXIS: standards) and aegisops-harness:qa-subagent in the '
            'foreground: the plugin stores what each returns (a person can store one with `aidlc attest`). A '
            f'repository that reviews another way says so in {CONFIG_NAME}: "review": {{"returns": "none — <reason>"}}')]
    covered = set()
    for item in returns:
        covered |= {'spec', 'standards'} if item['axis'] == 'both' else {item['axis']}
    findings += [fail(f'{folder}/: no stored return covers the {axis} axis') for axis in ('spec', 'standards')
                 if axis not in covered]
    if not qa_waived and 'qa' not in covered:
        findings.append(fail(f'{folder}/: no stored return from the QA agent'))
    mine = {item['id']: item for item in review['findings'] if item['id']}
    for item in returns:
        for finding, severity in item['findings']:
            kept = mine.get(finding)
            if kept is None:
                findings.append(fail(f'{item["label"]}: {finding}{" (" + severity + ")" if severity else ""} was '
                                     f'returned by {item["agent"]} and is not in review.md (a finding is closed with '
                                     '"fixed:" or "cleared:", never left out)'))
            elif severity and not kept['severity']:
                findings.append(fail(f'{spec.label("review.md")}:{kept["line"]}: {finding} has no severity here but was '
                                     f'returned as ({severity}) by {item["agent"]}: a finding is closed with its severity'))
            elif severity and kept['severity'] != severity:
                findings.append(fail(f'{spec.label("review.md")}:{kept["line"]}: {finding} is ({kept["severity"]}) here '
                                     f'but was returned as ({severity}) by {item["agent"]}'))
    latest = next((item for item in reversed(returns) if item['axis'] == 'qa'), None)
    if latest and not qa_waived:
        kind = verdict_kind(latest['verdict'])
        if not kind:
            findings.append(fail(f'{folder}/: the latest QA return has no verdict the gate can read ({latest["label"]}): '
                                 'a line "Verdict: GO", "Verdict: CONDITIONAL GO — <conditions>" or "Verdict: NO-GO — '
                                 '<reason>" (ask the QA agent again; an unreadable verdict is not a pass)'))
        elif verdict_kind(review['qa']) != kind:
            findings.append(fail(f'{spec.label("review.md")}: the QA verdict here is {verdict_kind(review["qa"]) or "missing"}; '
                                 f'the latest QA return says {kind} ({latest["label"]}). Only a new return from the QA '
                                 'agent changes it'))
    if review['fingerprint'] and not any(fp_matches(review['fingerprint'], item['fingerprint']) or
                                         fp_matches(item['fingerprint'], review['fingerprint']) for item in returns):
        findings.append(warn(f'{spec.label("review.md")}: code changed after the last reviewer return: what was stamped '
                             'is not exactly what a reviewer read (the fixes made after the re-review)'))
    return findings


# ----------------------------------------------------------------------------------------------------------- gates

def gate_accepted(spec):
    readme, findings = spec.label('README.md'), []
    key = spec.meta.get('key', '')
    if not KEY.match(key):
        findings.append(fail(f'{readme}: key: {key!r} must be 2-6 capital letters (prefix of every requirement ID)'))
    else:
        for other in spec.repo.spec_dirs():
            if other != spec.dir and Spec(other, spec.repo).meta.get('key') == key:
                findings.append(fail(f'{readme}: key {key} is also used by {spec.repo.rel(other)}'))
    findings += spec.requirements[1]
    guesses, problems = spec.guesses
    if guesses is not None or problems or spec.legacy_spec:  # spec.md: the blind check is optional
        findings += problems if guesses is not None or problems else spec.missing('spec-check.md')
    text, _ = read_text(spec.dir / 'spec-check.md', spec.label('spec-check.md'))
    if text is not None and not spec_check_ran(text):
        findings.append(fail(f'{spec.label("spec-check.md")}: the blind spec check has not run '
                             '(no guess lines and no "Checked:" line)'))
    for guess in guesses or []:
        if guess['open']:
            findings.append(fail(f'{spec.label("spec-check.md")}:{guess["line"]}: open guess {guess["id"] or ""}: '
                                 f'{guess["text"][:100]}'))
    findings += _security(spec)
    if spec.repo.fast:
        return findings + [warn('contract gate not run (fast status)')] + _accepted_by(spec)
    try:
        for level, message in _contract.run(spec.dir, repo_arg=spec.repo.root):
            if level != 'OK':
                findings.append((level, 'contract gate: ' + message.replace(str(spec.dir), spec.repo.rel(spec.dir))))
    except Exception as err:
        findings.append(fail(f'contract gate could not run ({err.__class__.__name__}: {err})'))
    return findings + _accepted_by(spec)


def spec_digest(spec):
    """SHA-256 of the text a person approves: spec.md (requirements.md for a legacy spec), line ends normalised."""
    text, _ = read_text(spec.dir / spec.spec_name, spec.label(spec.spec_name))
    return None if text is None else hashlib.sha256(text.encode('utf-8')).hexdigest()


def approval(spec):
    """The approval in force: the latest `approve` event that no later move back to `proposed` has voided."""
    found = None
    for event in spec.ledger[0]:
        if event['kind'] == 'approve':
            found = event
        elif event['kind'] == 'advance' and event.get('back') and event.get('to') == 'proposed':
            found = None
    return found


def _accepted_by(spec):
    """Somebody approved this spec text. `accepted_by:` names them; the `approve` event carries the hash of what
    they approved, so an edit after the approval (a story added during the build) needs a new one."""
    findings = []
    accepted_by = spec.meta.get('accepted_by', '')
    if not accepted_by or re.search(r'<[^>]*>', accepted_by):
        findings.append(fail(f'{spec.label("README.md")}: accepted_by: is not set (aidlc approve records who approved '
                             'the spec, and when)'))
    event, digest = approval(spec), spec_digest(spec)
    if event is None:
        findings.append(fail(f'{spec.label("ledger.md")}: no approval of this spec is recorded: a person approves it '
                             f'(/aegisops-harness:approve {spec.slug}, or `aidlc approve {spec.slug}` from their own '
                             'terminal); `aidlc approve --delegated` when the request handed the decisions over'))
    elif digest is not None and event['spec'] != digest:
        findings.append(fail(f'{spec.label(spec.spec_name)} changed after it was approved (approved {short(event["spec"])}'
                             f', now {short(digest)}): what is built must be what was approved, so it needs a new '
                             'approval'))
    return findings


def _security(spec):
    value = spec.meta.get('security', '')
    waiver = NOT_APPLICABLE.match(value)
    if waiver:
        return [] if waiver.group(1).strip() else [
            fail(f'{spec.label("README.md")}: security: not-applicable needs "— <reason>"')]
    if not spec.legacy_spec:
        text, _ = read_text(spec.dir / 'spec.md', spec.label('spec.md'))
        if text is not None and spec_security(text):
            return []
        if not (spec.dir / 'security.md').is_file():
            return [fail(f'{spec.label("spec.md")}: Implementation Decisions has no security decisions (a "### Security" '
                         'heading or a "**Security**" bullet: assets, threats, controls), or set README '
                         'security: not-applicable — <reason>')]
    text, error = read_text(spec.dir / 'security.md', spec.label('security.md'))
    if text is None:
        return [fail(error or f'{spec.label("security.md")}: missing (or set security: not-applicable — <reason>)')]
    return [] if text.strip() else [fail(f'{spec.label("security.md")}: empty')]


def gate_planned(spec):
    reqs = spec.requirements[0]
    tasks, problems = spec.tasks
    findings = earlier(gate_accepted(spec)) + problems
    if tasks is None:
        return unique(findings + (spec.missing(spec.plan_name) if not problems else []))
    ids = [r['id'] for r in reqs if r['verify'] != 'none'] if reqs is not None else None
    return unique(findings + plan_findings(tasks, ids, spec.label(spec.plan_name)))


def gate_building(spec):
    findings, branch = [], spec.repo.branch()
    if not branch:
        findings.append(fail('not on a branch (detached HEAD or no git repository): check out a feature branch'))
    elif branch in spec.repo.default_branches():
        findings.append(fail(f'current branch {branch} is the default branch: create a feature branch'))
    recorded = spec.meta.get('branch', '')
    if recorded and branch and recorded != branch:
        findings.append(fail(f'{spec.label("README.md")}: branch: {recorded} but the current branch is {branch}'))
    return findings


def gate_verified(spec):
    findings = earlier(gate_planned(spec))
    tasks = spec.tasks[0] or []
    events, problems = spec.ledger
    findings += problems
    green = {e['task'] for e in events if e['kind'] == 'task-done' and e.get('exit') == 0}
    for task in tasks:
        where = f'{spec.label(spec.plan_name)}:{task["line"]}'
        if not task['done']:
            findings.append(fail(f'{where}: {task["id"]} is not done (aidlc task-done)'))
        elif task['id'] not in green:
            findings.append(fail(f'{where}: {task["id"]} is ticked but has no green task-done event in ledger.md'))
        findings += _open_criteria(spec, task)
    for req in spec.requirements[0] or []:
        if req['verify'] == 'test' and not spec.repo.tests_referencing(req['id']):
            findings.append(fail(f'{spec.label(spec.spec_name)}:{req["line"]}: {req["id"]} (Verify: test) is not '
                                 'referenced by any test file'))
    return unique(findings + _verify_findings(spec) + _revert_findings(spec))


def _open_criteria(spec, task):
    return [fail(f'{spec.label(spec.plan_name)}:{c["line"]}: {task["id"]} acceptance criterion not ticked: '
                 f'{c["text"][:80]}') for c in task.get('criteria', []) if not c['done']]


def _verify_findings(spec):
    """The latest verify ran the pinned command, is green and is the current code."""
    config = spec.config
    if config is None:
        return [fail(NO_CONFIG.format(name=CONFIG_NAME))]
    findings = list(config['findings'])
    if failed(findings):
        return findings
    event = spec.last('verify')
    if event is None:
        return findings + [fail(f'{spec.label("ledger.md")}: no verify event (run aidlc verify SPEC)')]
    where = spec.at(event)
    if event.get('pinned') not in ('base', 'onboarding') or not same_command(event.get('cmd', ''), config['cmd']):
        findings.append(fail(f'{where}: the latest verify did not run the pinned command ({config["cmd"]!r}, '
                             f'{config["label"]}): run aidlc verify again'))
    if event['exit'] != 0:
        findings.append(fail(f'{where}: the latest verify exited {event["exit"]}'))
    if event.get('before') and event['before'] != event['fingerprint']:
        findings.append(fail(f'{where}: the test command changed code during the latest verify: re-run it'))
    if not fp_matches(event['fingerprint'], spec.repo.fingerprint):
        findings.append(fail(f'{where}: code changed since the latest verify (fingerprint {short(event["fingerprint"])} '
                             f'≠ current {short(spec.repo.fingerprint)}): run aidlc verify again'))
    if event['junit'] in ('unreadable', 'missing'):
        findings.append(fail(f'{where}: the latest verify has {event["junit"]} JUnit results: make the pinned command '
                             f'write {config["junit"] or "its reports"} and re-run'))
    elif config['junit'] and not isinstance(event['junit'], dict):
        findings.append(fail(f'{where}: the latest verify recorded no JUnit results ({config["junit"]} is configured): '
                             'run aidlc verify again'))
    elif event['req_fail']:
        findings.append(fail(f'{where}: requirement tests failed: {", ".join(event["req_fail"])}'))
    elif isinstance(event['junit'], dict) and event['junit'].get('failed'):
        findings.append(fail(f'{where}: the JUnit results hold {event["junit"]["failed"]} failed test(s) although the '
                             'pinned command exited 0 (a runner that ignores failures is not a green suite)'))
    return findings + _junit_coverage(spec, event, where)


def _tested(spec):
    return [r['id'] for r in spec.requirements[0] or [] if r['verify'] == 'test']


def _revert_verdict(code, junit, still_green, tested):
    """(level, message) of a revert-check run: the suite must fail without the production change, and with JUnit at
    least one story of this spec must have a test that stopped passing."""
    if code == 124:
        return fail('the revert check timed out: a suite that does not finish proves nothing')
    if code == 0:
        return fail('the suite still passes without the production change: no test depends on it')
    if isinstance(junit, dict) and tested and set(tested) <= set(still_green):
        return fail(f'every story test of this spec still passes without the production change '
                    f'({", ".join(still_green)}): the suite went red for another reason')
    return 'OK', f'the suite goes red without the production change (exit {code})'


def _revert_findings(spec):
    """The latest revert check is for the current code and went red (or was skipped with a reason)."""
    config = spec.config
    if not config or failed(config['findings']) or not config.get('revert_check'):
        return []
    event = spec.last('revert-check')
    if event is None:
        return [fail(f'{spec.label("ledger.md")}: no revert check (aidlc verify runs it before the green run)')]
    where = spec.at(event)
    if not fp_matches(event['fingerprint'], spec.repo.fingerprint):
        return [fail(f'{where}: code changed since the revert check: run aidlc verify again')]
    if event['skipped']:
        return [warn(f'{where}: revert check skipped: {event["reason"]}')]
    level, message = _revert_verdict(event['exit'], event['junit'], event['still_green'], _tested(spec))
    if level == 'FAIL':
        return [fail(f'{where}: {message}')]
    return [warn(f'{where}: {", ".join(event["still_green"])}: the tests that name these stories pass without the '
                 'production change (existing behaviour, or tests that prove nothing)')] if event['still_green'] else []


def _junit_coverage(spec, event, where):
    tested = [r['id'] for r in spec.requirements[0] or [] if r['verify'] == 'test']
    if not tested:
        return []
    if not isinstance(event['junit'], dict):
        config = spec.config or {}
        if config.get('junit_waiver'):  # a person waived JUnit in the config: the weaker, static check stands
            return [warn(f'{where}: traceability is static (test files name the story IDs; no test is known to have '
                         f'run for them). JUnit is waived in {config["label"]}: {config["junit_waiver"]}')]
        return []  # a missing report is already a failure of the verify itself
    return [fail(f'{where}: {rid} has no passing test in the JUnit results of the latest verify (skipped or absent)')
            for rid in tested if rid not in event['req_pass'] and rid not in event['req_fail']]


def _evidence(spec, rev=None):
    """One evidence chain: the latest verify is green and current, the review stamp is that same code, and, with
    rev, the commit holds that code."""
    return _verify_findings(spec) + _stamp_findings(spec, rev)


def _stamp_findings(spec, rev=None):
    """The review stamp is the verified code and, with rev, that commit holds it."""
    findings = []
    event, review = spec.last('verify'), spec.review[0]
    verified = event['fingerprint'] if event else ''
    stamp = review['fingerprint'] if review else ''
    if event and not fp_matches(stamp, verified):
        findings.append(fail(f'{spec.label("review.md")}: the review stamp ({short(stamp)}) is not the verified code '
                             f'({short(verified)}): re-verify, review the change, re-stamp'))
    if rev is not None:
        at = spec.repo.fingerprint_at(rev)
        if at is None:
            findings.append(fail(f'{rev}: not a commit of {spec.repo.root.name}'))
        elif event and not fp_matches(verified, at):
            findings.append(fail(f'{rev} does not contain the verified code (fingerprint {short(at)} ≠ verify '
                                 f'{short(verified)})'))
    return findings


def _clean_code(spec):
    if spec.repo.code_dirty:
        return [fail('uncommitted code: the pre-PR record and the PR are for commits; commit the code '
                     '(the fingerprint ignores docs and specs), then re-run')]
    return []


def gate_reviewed(spec):
    before = earlier(gate_verified(spec))
    review, findings = spec.review
    label = spec.label('review.md')
    if review is None:
        return unique(before + (findings or spec.missing('review.md')))
    findings = before + findings
    qa = spec.meta.get('qa', '')
    waiver = NOT_APPLICABLE.match(qa)
    if waiver and not waiver.group(1).strip():
        findings.append(fail(f'{spec.label("README.md")}: qa: not-applicable needs "— <reason>"'))
    findings += review_findings(review, label, qa_waived=bool(waiver))
    findings += returns_findings(spec, review, qa_waived=bool(waiver))
    current = spec.repo.fingerprint
    if not review['fingerprint']:
        findings.append(fail(f'{label}: no fingerprint: (run aidlc stamp SPEC review)'))
    elif not fp_matches(review['fingerprint'], current):
        findings.append(fail(f'{label}: code changed since the review was stamped (fingerprint '
                             f'{short(review["fingerprint"])} ≠ current {short(current)}): review the change, re-stamp'))
    return unique(findings + _stamp_findings(spec) + _clean_code(spec))


def _stage_at_least(spec, stage):
    current = spec.stage
    if current in STAGES and STAGES.index(current) >= STAGES.index(stage):
        return []
    return [fail(f'{spec.label("README.md")}: stage is {current}; this gate needs stage {stage}')]


def gate_shipped(spec):
    findings = _stage_at_least(spec, 'reviewed') + earlier(gate_reviewed(spec))
    ship, problems = spec.ship
    findings += problems
    if ship is None:
        return unique(findings + (spec.missing('ship.md') if not problems else []))
    label = spec.label('ship.md')
    return unique(findings + ship_findings(ship, label) + _ci_findings(spec, ship, label) + _changelog(spec, ship, label))


def gh_checks(root, branch):
    """[(name, state)] from the PR's CI: `gh pr checks <branch>`, or Bitbucket's PR statuses (scripts/pr.py); None
    when nothing can tell (CLI or credentials missing, no checks reported)."""
    if not branch or branch.startswith('-'):
        return None
    try:
        spec = importlib.util.spec_from_file_location('aegisops_harness_pr', HERE / 'pr.py')
        pr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pr)
        if pr.provider(root)[0] == 'bitbucket':
            return pr.checks_for(root, branch)
    except Exception:
        pass
    exe = os.environ['AIDLC_GH'] if 'AIDLC_GH' in os.environ else shutil.which('gh')
    if not exe or not os.access(exe, os.X_OK):
        return None
    try:  # `--` ends gh's flags, so a branch name can never be read as an option
        result = subprocess.run([exe, 'pr', 'checks', '--', branch], cwd=root, capture_output=True, text=True,
                                timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in result.stdout.splitlines():
        cols = line.split('\t')
        if len(cols) >= 2 and cols[1].strip().lower() in GH_STATES:
            rows.append((cols[0].strip(), cols[1].strip().lower()))
    return rows or None


def _ci_findings(spec, ship, label):
    """CI is green according to the provider. A sentence in ship.md is taken at its word only when the repository
    config waives CI, which is a person's decision on the default branch."""
    if spec.repo.fast:
        return [warn('CI not checked (fast status)')]
    branch = spec.meta.get('branch') or spec.repo.branch()
    checks = gh_checks(spec.repo.root, branch)
    if checks is not None:
        bad = [f'{name} ({state})' for name, state in checks if state not in ('pass', 'skipping')]
        return [fail(f'CI is not green (pr.py checks {branch}): {", ".join(bad[:8])}')] if bad else []
    config = spec.config or {}
    if not config.get('ci_waiver'):
        return [fail(f'no CI result for {branch}: `pr.py checks` returned nothing (gh missing or not signed in, no PR '
                     f'yet, or no CI on this repository). The shipped gate needs a result from CI, not a line in '
                     f'{label}; a repository without CI says so in {CONFIG_NAME}: "ci": "none — <reason>"')]
    waived = warn(f'CI is waived in {config["label"]} ({config["ci_waiver"]}): the "CI:" line of {label} is taken at '
                  'its word')
    if ship['ci'] is None:
        return [waived, fail(f'{label}: no "CI:" line in ## Checks')]
    if not says_green(ship['ci']):
        return [waived, fail(f'{label}:{ship["ci_line"]}: CI is not green: {ship["ci"]}')]
    return [waived]


def _changelog(spec, ship, label):
    version = ship['version']
    if not version or NOT_APPLICABLE.match(version) or re.match(r'^n/?a\b', version, re.I):
        return []
    service = spec.dir.parents[2] if spec.dir.parent.name == 'specs' else spec.repo.root
    changelog = next((p for p in (service / 'CHANGELOG.md', spec.repo.root / 'CHANGELOG.md') if p.is_file()), None)
    if changelog is None:
        return []
    text, error = read_text(changelog, spec.repo.rel(changelog))
    if text is None:
        return [fail(error)]
    if re.search(rf'(?<![\w.-]){re.escape(version)}(?![\w.-]*\w)', text):
        return []
    return [fail(f'{spec.repo.rel(changelog)} does not mention version {version} ({label})')]


def gate_implemented(spec):
    findings = _stage_at_least(spec, 'shipped')
    lines = strip_noise(spec.readme[1])
    section = section_ranges(lines).get('traceability')
    if not section or not any(re.match(r'^\s*\|.*\|\s*$', x) for x in lines[section[0] + 1:section[1]]):
        findings.append(fail(f'{spec.label("README.md")}: no ## Traceability table (run aidlc trace SPEC --write)'))
    return findings


GATES = {
    'accepted': gate_accepted,
    'planned': gate_planned,
    'building': gate_building,
    'verified': gate_verified,
    'reviewed': gate_reviewed,
    'shipped': gate_shipped,
    'implemented': gate_implemented,
    'partially-implemented': gate_implemented,
}


def next_stage(current):
    if current in STAGES[:-1]:
        return STAGES[STAGES.index(current) + 1]
    return None


def _check(spec, target=None):
    findings = list(spec.readme[2])
    target = target or next_stage(spec.stage)
    label = spec.repo.rel(spec.dir)
    if target is None:
        return findings + [('OK', f'{label}: {spec.stage} has no next stage')]
    if target not in GATES:
        return findings + [fail(f'no gate for stage {target!r} (gates: {", ".join(GATES)})')]
    try:
        findings += GATES[target](spec)
    except Exception as err:  # a gate bug must be a finding, never a traceback
        findings.append(fail(f'{label}: gate {target} could not run ({err.__class__.__name__}: {err})'))
    if not failed(findings):
        findings.append(('OK', f'{label}: gate {target} passes'))
    return findings


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
