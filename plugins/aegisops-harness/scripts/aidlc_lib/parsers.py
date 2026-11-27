"""Parsers for spec.md, tickets.md, ledger.md, review.md, ship.md, .aidlc.json and JUnit reports."""
from aidlc_lib.core import *  # noqa: F401,F403

# -------------------------------------------------------------------------------------------------------- parsers

def parse_requirements(text, label):
    """Requirement candidates: headings whose first token is an ID; criteria under Acceptance:, Verify: kind."""
    reqs, findings, current, in_acceptance = [], [], None, False
    for n, line in enumerate(strip_noise(text), 1):
        heading = HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if current and level <= current['level']:
                current = None
            token = (title.split() or [''])[0]
            match = REQ_ID.match(token.rstrip(':.'))
            if match:
                current = {'id': match.group(0), 'prefix': match.group(1), 'line': n, 'level': level,
                           'title': title[len(token):].strip(' :—-'), 'criteria': [], 'verify': 'test',
                           'verify_detail': '', 'verify_line': None, 'priority': None}
                reqs.append(current)
                in_acceptance = False
            continue
        if current is None:
            continue
        field = REQ_FIELD.match(line.strip())
        if field:
            name, value = field.group(1).lower(), field.group(2).strip()
            in_acceptance = name == 'acceptance'
            if in_acceptance and value:
                current['criteria'].append(value)
            elif name == 'priority':
                current['priority'] = value
            elif name == 'verify':
                current['verify_line'] = n
                findings += _set_verify(current, value, f'{label}:{n}')
            continue
        if in_acceptance:
            bullet = BULLET.match(line)
            if bullet:
                current['criteria'].append(bullet.group(1))
            elif line.strip() and line[0] in ' \t' and current['criteria']:
                current['criteria'][-1] += ' ' + line.strip()
            elif line.strip():
                in_acceptance = False
    for req in reqs:
        del req['level']
    return reqs, findings


def _set_verify(req, value, where):
    match = VERIFY.match(value)
    if not match:
        return [fail(f'{where}: {req["id"]} Verify: {value!r} is not test, check — <command>, manual — <reason> '
                     'or none — <reason>')]
    req['verify'], req['verify_detail'] = match.group(1).lower(), match.group(2).strip()
    if req['verify'] != 'test' and not req['verify_detail']:
        return [fail(f'{where}: {req["id"]} Verify: {req["verify"]} needs "— <command, procedure or reason>"')]
    return []


def requirement_findings(reqs, key, label):
    """Gate checks on parsed requirements for README key `key` (foreign IDs fail only if they look like requirements)."""
    findings, seen = [], {}
    for req in reqs:
        looks_like = req['criteria'] or req['verify_line']
        if key and req['prefix'] != key:
            if looks_like:
                findings.append(fail(f'{label}:{req["line"]}: {req["id"]} is not {key}-<n> (README key: {key})'))
            continue
        if not key and not looks_like:
            continue
        if req['id'] in seen:
            findings.append(fail(f'{label}:{req["line"]}: duplicate requirement {req["id"]} (also line {seen[req["id"]]})'))
        seen.setdefault(req['id'], req['line'])
        if not req['criteria']:
            findings.append(fail(f'{label}:{req["line"]}: {req["id"]} has no acceptance criterion '
                                 '(bullets under "Acceptance:")'))
    if not seen:
        findings.append(fail(f'{label}: defines no requirement (a heading "### {key or "KEY"}-1: <title>")'))
    return findings


def select_requirements(reqs, key):
    chosen, seen = [], set()
    for req in reqs:
        if (req['prefix'] == key if key else (req['criteria'] or req['verify_line'])) and req['id'] not in seen:
            seen.add(req['id'])
            chosen.append(req)
    return chosen


def parse_spec(text, label, key):
    """(stories, findings) for spec.md (the spec template): every template section present and filled; each
    top-level numbered item under ## User Stories is requirement <key>-<n>. An item may end with
    `(Verify: check — <command>)`, `(Verify: manual — <reason>)` or `(Verify: none — <reason>)` (not delivered here)."""
    lines, findings = strip_noise(text), []
    ranges = section_ranges(lines)
    items, current = [], None
    start, end = ranges.get('user stories', (0, 0))
    for i in range(start + 1, end):
        line = lines[i]
        match = STORY.match(line)
        if match:
            current = {'number': int(match.group(1)), 'text': match.group(2), 'line': i + 1}
            items.append(current)
        elif current and line.strip() and line[0] in ' \t':
            current['text'] += ' ' + line.strip()
        elif line.strip():
            current = None
    stories, seen = [], {}
    for item in items:
        rid = f'{key}-{item["number"]}'
        story = {'id': rid, 'prefix': key, 'line': item['line'], 'title': item['text'], 'criteria': [item['text']],
                 'verify': 'test', 'verify_detail': '', 'verify_line': None, 'priority': None}
        tag = STORY_VERIFY.search(item['text'])
        if tag:
            story['title'] = story['criteria'][0] = item['text'][:tag.start()].rstrip()
            story['verify_line'] = item['line']
            findings += _set_verify(story, tag.group(1).strip(), f'{label}:{item["line"]}')
        if rid in seen:
            findings.append(fail(f'{label}:{item["line"]}: duplicate user story {item["number"]} (also line {seen[rid]})'))
            continue
        seen[rid] = item['line']
        stories.append(story)
    return stories, findings


def spec_findings(text, label, stories):
    """The accepted gate on spec.md: every template section present and filled, at least one story."""
    lines, findings = strip_noise(text), []
    ranges = section_ranges(lines)
    for name in SPEC_SECTIONS:
        if name not in ranges:
            findings.append(fail(f'{label}: no "## {name.title()}" section (spec template)'))
            continue
        start, end = ranges[name]
        if not any(x.strip() and not x.lstrip().startswith('#') for x in lines[start + 1:end]):
            findings.append(fail(f'{label}:{start + 1}: "## {name.title()}" is empty'))
    if 'user stories' in ranges and not stories:
        findings.append(fail(f'{label}: "## User Stories" has no numbered story ("1. As a <actor>, I want …")'))
    return findings


def spec_security(text):
    """spec.md records security decisions: a `### Security` heading or a **Security** bullet in Implementation
    Decisions."""
    lines = strip_noise(text)
    start, end = section_ranges(lines).get('implementation decisions', (0, 0))
    return any(SECURITY_DECISION.match(x) for x in lines[start + 1:end])


def parse_spec_check(text, label):
    """(guesses, findings); a guess is any checkbox line, closed ones must say resolved: or accepted risk:."""
    guesses, findings = [], []
    for n, line in enumerate(strip_noise(text), 1):
        match = CHECKBOX.match(line.strip())
        if not match:
            continue
        body = match.group(3).strip()
        gid = re.match(r'^(G\d+)\b', body)
        guess = {'id': gid.group(1) if gid else None, 'open': match.group(2) == ' ', 'text': body, 'line': n}
        if not guess['open'] and not re.search(r'\b(resolved|accepted risk)\s*:', body, re.I):
            findings.append(fail(f'{label}:{n}: closed guess {guess["id"] or "(no ID)"} says neither "resolved:" '
                                 'nor "accepted risk:"'))
        guesses.append(guess)
    return guesses, findings


def spec_check_ran(text):
    """A check is recorded by at least one guess line or a `Checked:` line (the checker found nothing)."""
    return any(CHECKBOX.match(x.strip()) or re.match(r'^\s*checked\s*:', x, re.I) for x in strip_noise(text))


def parse_plan(text, label):
    """(tasks, findings): top-level `- [ ] T<n>: title` lines with indented `- field: value` bullets."""
    tasks, findings, current = [], [], None
    for n, line in enumerate(strip_noise(text), 1):
        box = CHECKBOX.match(line)
        if box:
            body = box.group(3).strip()
            token = (body.split() or [''])[0].rstrip(':.')
            current = None
            if TASK_ID.match(token):
                current = {'id': token, 'title': body[len(token):].strip(' :.—-'), 'done': box.group(2) != ' ',
                           'line': n, 'fields': {}}
                tasks.append(current)
            elif re.match(r'^T\S*\d', token):
                findings.append(fail(f'{label}:{n}: task ID {token!r} must be T<n>'))
            continue
        if current is None:
            continue
        field = FIELD.match(line)
        if field:
            current['fields'].setdefault(field.group(1).lower(), field.group(2).strip())
        elif line.strip() and line[0] not in ' \t':
            current = None
    return [_task(task) for task in tasks], findings


def parse_tickets(text, label):
    """(tickets, findings) for tickets.md: `## T<n>: <title>` sections with `Blocked by:`, `Covers:`, `Status:`
    (ready-for-agent | done), `What to build:`, acceptance checkboxes and optional `Test:`, `Files:`, `Owner:`."""
    tickets, findings, current = [], [], None
    for n, line in enumerate(strip_noise(text), 1):
        heading = HEADING.match(line)
        if heading:
            current = None
            if len(heading.group(1)) == 2:
                title = heading.group(2)
                token = (title.split() or [''])[0].rstrip(':.')
                if TASK_ID.match(token):
                    current = {'id': token, 'title': title[len(token):].strip(' :.—-'), 'line': n, 'fields': {},
                               'criteria': [], 'status_line': None}
                    tickets.append(current)
                elif re.match(r'^T\S*\d', token):
                    findings.append(fail(f'{label}:{n}: ticket ID {token!r} must be T<n>'))
            continue
        if current is None:
            continue
        box = CHECKBOX.match(line.strip())
        if box:
            current['criteria'].append({'done': box.group(2) != ' ', 'text': box.group(3).strip(), 'line': n})
            continue
        field = TICKET_FIELD.match(line.strip())
        if field:
            name = {'blocked by': 'depends', 'blocked-by': 'depends', 'what to build': 'what'}.get(
                field.group(1).lower(), field.group(1).lower())
            current['fields'].setdefault(name, field.group(2).strip())
            if name == 'status' and current['status_line'] is None:
                current['status_line'] = n
    result = []
    for raw in tickets:
        status = raw['fields'].get('status', 'ready-for-agent').strip().lower()
        criteria = raw.pop('criteria')
        status_line = raw.pop('status_line')
        raw['done'] = status.startswith('done')
        raw['fields'].setdefault('owner', 'main')
        if not raw['fields'].get('exit'):
            raw['fields']['exit'] = '; '.join(c['text'] for c in criteria)
        what = raw['fields'].pop('what', '')
        ticket = _task(raw)
        ticket.update(criteria=criteria, status_line=status_line, what=what, ticket=True)
        result.append(ticket)
    return result, findings


def _task(raw):
    fields = raw.pop('fields')
    covers = fields.get('covers')
    none = re.match(r'^none\b' + DASH + r'(.*)$', covers or '', re.I)
    files, new = [], []
    for part in (fields.get('files') or '').split(','):
        is_new = bool(re.search(r'\(new\)\s*$', part))
        part = re.sub(r'\(new\)\s*$', '', part).strip().strip('`\'"').strip()
        if part and part.lower() != 'none':
            part = re.sub(r'^\./', '', part)
            files.append(part + '**' if part.endswith('/') else part)
            if is_new:
                new.append(files[-1])
    raw.update({'covers': [] if none or covers is None else _covers(covers),
                'covers_given': covers is not None, 'covers_none': none.group(1).strip() if none else None,
                'depends': re.findall(r'\bT\d+\b', fields.get('depends') or ''),
                'owner': fields.get('owner', ''), 'files': files, 'new_files': new,
                'exit': fields.get('exit', ''), 'test': fields.get('test', '')})
    return raw


def _covers(value):
    """Requirement IDs in a covers list; `RFD-3..RFD-6` and `RFD-3..6` are inclusive ranges."""
    ids = []
    for prefix, first, second in re.findall(r'\b([A-Z][A-Z0-9]*)-(\d+)(?:\s*(?:\.\.|–|—)\s*(?:\1-)?(\d+))?\b', value):
        last = int(second) if second else int(first)
        ids += [f'{prefix}-{n}' for n in range(int(first), max(int(first), last) + 1)]
    return list(dict.fromkeys(ids))


def parse_ledger(text, label):
    """(events, findings): one `- <UTC time> <event> …` line per event."""
    events, findings = [], []
    for n, line in enumerate(text.split('\n'), 1):
        if not re.match(r'^[-*]\s', line):
            continue
        match = LEDGER_LINE.match(line.rstrip())
        if not match:
            findings.append(fail(f'{label}:{n}: not a ledger event ("- <UTC time> <event> …")'))
            continue
        ts, kind, rest = match.groups()
        event, problem = _event(kind, rest)
        if problem:
            findings.append((problem[0], f'{label}:{n}: {problem[1]}'))
        if event is not None:
            event.update(kind=kind, ts=ts, line=n)
            events.append(event)
    return events, findings


def _kv(rest):
    data = {}
    junit = JUNIT.search(rest)
    if junit:
        data['junit'] = ({'passed': int(junit.group(1)), 'failed': int(junit.group(2))} if junit.group(1)
                         else junit.group(3))
        rest = rest[:junit.start()] + rest[junit.end():]
    for key, value in KV.findall(rest):
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value[1:-1]
        data[key.replace('-', '_')] = value
    return data


def _event(kind, rest):
    if kind == 'ruling':
        match = RULING.match(rest)
        if not match:
            return None, fail('ruling needs "<decision> — why: <why> — if wrong: <cost>"')
        return dict(zip(('task', 'decision', 'why', 'if_wrong'), match.groups())), None
    if kind == 'advance':
        match = ADVANCE.match(rest)
        if not match:
            return None, fail('advance needs "<from>→<to>"')
        data = _kv(match.group(3))
        return {'from': match.group(1), 'to': match.group(2), 'back': bool(re.match(r'back\b', match.group(3))),
                'reason': data.get('reason')}, None
    head = rest.split(None, 1)
    if kind == 'revert-check':
        skipped = bool(head) and head[0] == 'skipped'
        data = _kv((head[1] if len(head) > 1 else '') if skipped else rest)
        event = {'skipped': skipped, 'reason': data.get('reason'), 'base': data.get('base', ''),
                 'files': data.get('files'), 'junit': data.get('junit'),
                 'still_green': [x for x in str(data.get('still_green', '')).split(',') if x],
                 'fingerprint': str(data.get('fingerprint', '')).rstrip('…')}
        if not re.match(r'^[0-9a-f]+$', event['fingerprint']):
            return None, fail('revert-check needs fingerprint=<hex>')
        if not skipped:
            try:
                event['exit'] = int(data.get('exit'))
            except (TypeError, ValueError):
                return None, fail('revert-check needs exit=<code>')
        return event, None
    if kind == 'approve':
        data = _kv(rest)
        event = {'spec': str(data.get('spec', '')), 'by': str(data.get('by', '')), 'how': str(data.get('how', ''))}
        if not re.match(r'^[0-9a-f]{64}$', event['spec']) or event['how'] not in ('approved', 'delegated'):
            return None, fail('approve needs spec=<sha256> by="<name>" how=approved|delegated')
        return event, None
    if kind not in ('task-done', 'verify', 'stamp'):
        return {'text': rest}, warn(f'unknown ledger event {kind!r}')
    event = {}
    if kind == 'task-done':
        if not head or not TASK_ID.match(head[0]):
            return None, fail('task-done needs a task ID')
        event['task'], rest = head[0], (head[1] if len(head) > 1 else '')
    if kind == 'stamp':
        if not head or head[0] != 'review':
            return None, fail('stamp needs "review"')
        rest = head[1] if len(head) > 1 else ''
    data = _kv(rest)
    event.update(data)
    event['fingerprint'] = str(data.get('fingerprint', '')).rstrip('…')
    if not re.match(r'^[0-9a-f]+$', event['fingerprint']):
        return None, fail(f'{kind} needs fingerprint=<hex>')
    if kind != 'stamp':
        try:
            event['exit'] = int(data.get('exit'))
        except (TypeError, ValueError):
            return None, fail(f'{kind} needs exit=<code>')
    if kind == 'verify':
        event['before'] = str(data.get('before', '')).rstrip('…')
        event.setdefault('junit', None)
        for name in ('req_pass', 'req_fail'):
            event[name] = [x for x in str(data.get(name, '')).split(',') if x]
    return event, None


def parse_review(text, label):
    meta, start = parse_frontmatter(text)
    lines = strip_noise(text)
    review = {'fingerprint': (meta or {}).get('fingerprint', '').rstrip('…'), 'reviewers': (meta or {}).get('reviewers', ''),
              'axes': {}, 'findings': [], 'qa': None, 'qa_line': None}
    problems = []
    for name, (head, end) in section_ranges(lines, start).items():
        if name not in ('spec', 'standards', 'qa'):
            continue
        review['axes'][name] = {'line': head + 1, 'empty': not any(x.strip() for x in lines[head + 1:end])}
        for i in range(head + 1, end):
            if name == 'qa':
                verdict = re.match(r'^\s*(?:[-*+]\s+)?[*_]*verdict[*_]*\s*:[*_]*\s*(.*)$', lines[i], re.I)
                if verdict and review['qa'] is None:
                    review['qa'], review['qa_line'] = verdict.group(1).strip(), i + 1
                continue
            plain = PLAIN_FINDING.match(lines[i])
            if plain:
                problems.append(fail(f'{label}:{i + 1}: {plain.group(1)} is a finding but not a checkbox '
                                     f'("- [ ] {plain.group(1)} (must): …"): an untracked finding counts as open'))
            box = CHECKBOX.match(lines[i].strip())
            if box:
                match = FINDING.match(box.group(3).strip())
                review['findings'].append({
                    'axis': name, 'id': match.group(1) if match else None, 'open': box.group(2) == ' ',
                    'severity': (match.group(2) or '').strip().lower() if match else '', 'text': box.group(3).strip(),
                    'line': i + 1})
    return review, problems


def verdict_kind(text):
    """NO-GO | CONDITIONAL GO | GO, or None when the text is none of them."""
    for kind in ('NO-GO', 'CONDITIONAL GO', 'GO'):
        if re.match(r'^' + re.escape(kind) + r'\b', (text or '').strip(), re.I):
            return kind
    return None


def parse_return(text, label):
    """(return, findings) for one stored reviewer return: frontmatter (agent, axis, fingerprint, sha256, recorded) and
    the reviewer's words. `findings`: (ID, severity) of every S<n>/Q<n> line; `verdict`: the first Verdict: line."""
    meta, start = parse_frontmatter(text)
    body = '\n'.join(text.split('\n')[start:])
    item = {'agent': (meta or {}).get('agent', ''), 'axis': (meta or {}).get('axis', ''),
            'fingerprint': (meta or {}).get('fingerprint', ''), 'recorded': (meta or {}).get('recorded', ''),
            'label': label, 'findings': [], 'verdict': None}
    problems = []
    if meta is None or item['axis'] not in ('spec', 'standards', 'both', 'qa'):
        return item, [fail(f'{label}: not a stored reviewer return (frontmatter with agent, axis, sha256)')]
    if hashlib.sha256(body.encode('utf-8')).hexdigest() != meta.get('sha256'):
        problems.append(fail(f'{label}: was changed after it was recorded (the text no longer matches its sha256): '
                             'a return is the reviewer\'s account, not the implementer\'s'))
    for line in body.split('\n'):
        found = RETURNED_FINDING.match(line)
        if found:
            item['findings'].append((found.group(1), (found.group(2) or '').strip().lower()))
        verdict = VERDICT.match(line)
        if verdict and item['verdict'] is None:
            item['verdict'] = re.sub(r'\*\*|__|`', '', verdict.group(1)).strip()  # emphasis is not part of the verdict
    return item, problems


def review_findings(review, label, qa_waived=False):
    """Structure checks of review.md: both axes, a QA verdict (unless waived), every finding closed with evidence."""
    findings = []
    axes = [('spec', 'Spec'), ('standards', 'Standards')] + ([] if qa_waived else [('qa', 'QA')])
    for axis, title in axes:
        if axis not in review['axes']:
            findings.append(fail(f'{label}: no "## {title}" section'))
        elif review['axes'][axis]['empty']:
            findings.append(fail(f'{label}:{review["axes"][axis]["line"]}: ## {title} is empty '
                                 '(list findings or write "No findings.")'))
    for item in review['findings']:
        where, name = f'{label}:{item["line"]}', item['id'] or 'finding'
        if item['open']:
            findings.append(fail(f'{where}: open finding {name}: {item["text"][:100]}'))
        elif not re.search(r'\b(fixed|cleared)\s*:', item['text'], re.I):
            findings.append(fail(f'{where}: {name} is closed but says neither "fixed:" nor "cleared:"'))
        if item['severity'] not in ('must', 'should', 'nit'):
            findings.append(warn(f'{where}: {name} has no severity (must, should or nit)'))
    if not qa_waived and 'qa' in review['axes'] and not review['axes']['qa']['empty']:
        findings += _qa_findings(review, label)
    return findings


def _qa_findings(review, label):
    verdict = review['qa']
    if verdict is None:
        return [fail(f'{label}: ## QA has no "Verdict:" line (GO, CONDITIONAL GO — <conditions> or NO-GO — <reason>)')]
    where = f'{label}:{review["qa_line"]}'
    if re.match(r'^NO-GO\b', verdict, re.I):
        return [fail(f'{where}: QA verdict is NO-GO')]
    conditional = re.match(r'^CONDITIONAL GO\b' + DASH + r'(.*)$', verdict, re.I)
    if conditional:
        return [] if conditional.group(1).strip() else [fail(f'{where}: CONDITIONAL GO needs "— <conditions>"')]
    if re.match(r'^GO\b', verdict, re.I):
        return []
    return [fail(f'{where}: QA verdict {verdict!r} is not GO, CONDITIONAL GO or NO-GO')]


def parse_ship(text, label):
    meta, start = parse_frontmatter(text)
    raw, lines = strip_noise(text, fences=False), strip_noise(text)
    ship = {'decision': (meta or {}).get('decision', ''), 'version': (meta or {}).get('version', ''),
            'frontmatter': meta is not None, 'sections': {}, 'ci': None, 'ci_line': None}
    for name, (head, end) in section_ranges(lines, start).items():
        ship['sections'][name] = any(x.strip() for x in raw[head + 1:end])
        if name == 'checks':
            for i in range(head + 1, end):
                match = re.match(r'^\s*(?:[-*+]\s+)?[*_]*CI[*_]*\s*:\s*(.*)$', raw[i])
                if match and ship['ci'] is None:
                    ship['ci'], ship['ci_line'] = match.group(1).strip(), i + 1
    return ship, []


def ship_findings(ship, label):
    """Structure checks of ship.md (CI, changelog and fingerprint are checked by the gate)."""
    findings = []
    if not ship['frontmatter']:
        findings.append(fail(f'{label}:1: no frontmatter (decision: GO, version: …)'))
    if ship['decision'] != 'GO':
        findings.append(fail(f'{label}: decision is {ship["decision"] or "missing"!s}, not GO'))
    for title in ('Rollback', 'Post-release verification'):
        if not ship['sections'].get(title.lower()):
            findings.append(fail(f'{label}: "## {title}" is missing or empty'))
    return findings


def _switch(value, name, label, findings):
    """The reason of a `none — <reason>` waiver, or None for `required` (the default)."""
    if value is None or (isinstance(value, str) and value.strip().lower() == 'required'):
        return None
    waiver = WAIVER.match(value.strip()) if isinstance(value, str) else None
    if not waiver:
        findings.append(fail(f'{label}: {name} must be "required" or "none — <reason>"'))
    elif not waiver.group(1).strip():
        findings.append(fail(f'{label}: {name}: "none" needs a reason ("none — <reason>")'))
    else:
        return waiver.group(1).strip()
    return None


def parse_config(text, label):
    """(config, findings) for the repository config, schema 1:

      {"schema": 1,
       "verify": {"cmd": "<the full test suite>",
                  "junit": "<glob of the reports it writes>" | "none — <reason>",
                  "revert_check": true},                          optional, default true
       "ci": "required" | "none — <reason>",                      optional, default required
       "review": {"returns": "required" | "none — <reason>"}}     optional, default required

    config: cmd, junit (glob or None), junit_waiver, revert_check, ci_waiver, returns_waiver. Waivers hold the reason."""
    try:
        data = json.loads(text)
    except ValueError as err:
        return {}, [fail(f'{label}: not valid JSON ({err})')]
    if not isinstance(data, dict):
        return {}, [fail(f'{label}: must be a JSON object')]
    findings = []
    schema = data.get('schema')
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        findings.append(fail(f'{label}: "schema": {SCHEMA} is required'))
    elif schema > SCHEMA:
        findings.append(fail(f'{label}: schema {schema} is newer than this plugin reads ({SCHEMA}): update the plugin'))
    verify = data.get('verify')
    if not isinstance(verify, dict):
        verify = {}
    cmd = verify.get('cmd')
    if not isinstance(cmd, str) or not cmd.strip():
        findings.append(fail(f'{label}: "verify.cmd" must be the command that runs the full test suite'))
        cmd = ''
    junit, glob, junit_waiver = verify.get('junit'), None, None
    if not isinstance(junit, str) or not junit.strip():
        findings.append(fail(f'{label}: "verify.junit" must be the glob of the JUnit reports the command writes, or '
                             '"none — <reason>"'))
    else:
        waiver = WAIVER.match(junit.strip())
        if waiver and not waiver.group(1).strip():
            findings.append(fail(f'{label}: "verify.junit": "none" needs a reason ("none — <reason>")'))
        elif waiver:
            junit_waiver = waiver.group(1).strip()
        else:
            glob = junit.strip()
    revert = verify.get('revert_check', True)
    if not isinstance(revert, bool):
        findings.append(fail(f'{label}: "verify.revert_check" must be true or false'))
        revert = True
    review = data.get('review', {})
    if not isinstance(review, dict):
        findings.append(fail(f'{label}: "review" must be an object'))
        review = {}
    return {'cmd': cmd.strip(), 'junit': glob, 'junit_waiver': junit_waiver, 'revert_check': revert,
            'ci_waiver': _switch(data.get('ci'), '"ci"', label, findings),
            'returns_waiver': _switch(review.get('returns'), '"review.returns"', label, findings)}, findings


def _canonical(text):
    try:
        return json.dumps(json.loads(text), sort_keys=True)
    except ValueError:
        return text.strip()


def load_config(repo, folders):
    """The repository config for the first of `folders` that has one, or None.

    The gates read it from the trusted ref (the default branch; `--base` in CI): the command that verifies a branch
    is not the branch's to choose. A config that exists only on this branch is `onboarding` (trust on first use, with
    a warning a person is meant to read). Adds: source ('base' | 'onboarding'), ref, dir (where the command runs),
    label, findings."""
    trusted = repo.trusted_ref
    found = []
    for folder in folders:
        rel = repo.rel(folder / CONFIG_NAME)
        base = repo.show(trusted, rel) if trusted else None
        local, _ = read_text(folder / CONFIG_NAME, rel)
        if base is not None or local is not None:
            found.append((folder, rel, base, local))
    if not found:
        return None
    # A config that is on the trusted ref wins, wherever it is: a branch that adds a nearer one (a service folder)
    # does not choose its own command. Onboarding is for a repository that has none there.
    first = next((item for item in found if item[2] is not None), found[0])
    folder, rel, base, local = first
    ignored = [item[1] for item in found if item[2] is None and first[2] is not None]
    if base is not None:
        text = base.decode('utf-8', 'replace').replace('\r\n', '\n')
        config, findings = parse_config(text, f'{rel} on {trusted}')
        if local is None:
            findings.append(warn(f'{rel} is missing here: the gates use the version on {trusted}'))
        elif _canonical(local) != _canonical(text):
            findings.append(warn(f'{rel} differs from {trusted}: the gates use the version on {trusted} until this '
                                 'change is merged (a branch does not choose the command that verifies it)'))
        findings += [warn(f'{name} exists only on this branch and is ignored: the gates use {rel} on {trusted}')
                     for name in ignored]
        source = 'base'
    else:
        config, findings = parse_config(local, rel)
        where = f'not on {trusted} yet' if trusted else 'no default branch was found to read it from'
        findings.append(warn(f'onboarding: {rel} exists only on this branch ({where}). A person must read it '
                             'before the merge: it names the command every later gate trusts'))
        if not trusted and repo.has_origin():
            findings.append(fail('the default branch of origin was not found (no origin/HEAD, and no main, master or '
                                 'init.defaultBranch there): run `git remote set-head origin -a` so that the config '
                                 'is read from it, not from this branch'))
        source = 'onboarding'
    config.update(source=source, ref=trusted, dir=folder, label=rel, findings=findings)
    return config


def same_command(a, b):
    return ' '.join(str(a).split()) == ' '.join(str(b).split())


def says_green(value):
    value = (value or '').lower()
    return bool(re.search(r'\b(green|pass(ed|es|ing)?)\b', value)) and \
        not re.search(r'\b(not|no|red|fail\w*|pending|cancel\w*)\b', value)


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
