#!/usr/bin/env python3
"""tea-sdlc autopilot: the user never has to remember a slash command or a skill name.

  prompt  UserPromptSubmit  keyword-match the prompt (English) and add a short note naming the skills,
                            routing tier signals and commands that fit, so the session loads them on its own.
  post    PostToolUse       Edit|Write|MultiEdit|Bash: remember code edited since the last test run, and add a
                            follow-up note after three failing test runs in a row (systematic-debugging), a
                            `git revert` (incident-to-eval) or a merge while a spec is still accepted
                            (upgrade-service-docs).
  stop    Stop              before the session finishes a turn with code changed since the last test run, ask once
                            per change set (max 3 per session) for a test run or a stated reason.

Every note is a hint the session may ignore; nothing here blocks a tool call. Any internal error is silent.
Off with TEA_SDLC_AUTOPILOT=off (prompt + post notes) and TEA_SDLC_VERIFY_GATE=off (stop).
State: ~/.claude/state/tea-sdlc/autopilot/<session>.json
"""
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
STATE_DIR = pathlib.Path.home() / '.claude' / 'state' / 'tea-sdlc' / 'autopilot'
NOTE_LIMIT = 1500
MAX_STOP_REMINDERS = 3
FAIL_STREAK = 3


def _load_tdd():
    spec = importlib.util.spec_from_file_location('tdd_gate', HERE / 'tdd-gate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tdd = _load_tdd()


def skill(name):
    return 'tea-sdlc:' + name


# ---------------------------------------------------------------------------------------------------------------
# Prompt router
# ---------------------------------------------------------------------------------------------------------------

def rx(pattern):
    return re.compile(pattern, re.I | re.U)


# A change verb counts only outside command names (`/eval-upgrade`, `create-pr`).
CHANGE = rx(r'(?<![\w/-])(add|adding|implement\w*|build|create|fix|fixing|refactor\w*|change|modify|update|remove|'
            r'delete|migrate|rename|integrate|upgrade|introduce|rewrite|port|bump|wire up|optimi[sz]e|reduce|'
            r'improve|write|store|persist|validate)(?![\w-])')
# What the change is about. Strong nouns mean code; weak ones mean code unless the prompt is about prose or git/ops.
STRONG_CODE = rx(r'\b(functions?|methods?|class(es)?|endpoints?|api|apis|unit tests?|migrations?|schemas?|quer(y|ies)|'
                 r'handlers?|controllers?|components?|hooks?|regex)\b'
                 r'|\.(py|ts|tsx|js|jsx|java|kt|go|rs|cs|rb|php|swift|dart|c|cpp|h)\b')
WEAK_CODE = rx(r'\b(code|feature|services?|modules?|logic|retry|retries|validation|checks?|cache|tests?|ui|bug|screen|button|alarms?|lambdas?|stacks?|infra\w*)\b')
PROSE = rx(r'(?<![\w/<])/[a-z][\w-]+|\b(prompts?|rules?|readme|docs?|documentation|documents?|guidelines?|changelog|skills?|commands?|wording|'
           r'spec)\b|\.md\b')
OPS = rx(r'\b(branch(es)?|worktrees?|repo(sitory|s)?|version|commits?|remote|credentials?|aws profiles?|publish|tags?|'
         r'release|author)\b')
DEBUG = rx(r'\b(bugs?|errors?|exceptions?|stack ?trace|traceback|crash\w*|fail(s|ing|ed|ure)?|broken|regression|'
           r'flaky|not working|does ?n[o\']t work|panic|segfault|npe|nullpointer\w*|timeouts?|5\d\d)\b'
           r'|\b(is|are|went|turned|goes|going) red\b|\bred (builds?|tests?|ci|pipelines?)\b')
# "an alarm for Lambda errors" defines monitoring; it is not a bug report.
MONITORED = rx(r'\b(alarms?|alerts?|monitors?|metrics?|dashboards?)\b[^.\n]{0,40}\b(errors?|failures?|timeouts?|5\d\d)\b')
QUESTION_START = rx(r'^\s*(does|do|did|is|are|was|were|can|could|should|would|will|what|why|how|which|where|when|'
                    r'who)\b')
MULTI_SERVICE = rx(r'\b(between|across) (the )?(micro)?services\b|\bservices? \S+ (and|->|→) \S+ services?\b')
# Workflow mode. `lean` (the default) keeps every change in the main session: subagent fan-out costs several times
# the tokens. `full` runs the AIDLC lifecycle with specialist subagents; set TEA_SDLC_WORKFLOW=full, or ask for it.
FULL_REQUEST = rx(r'\b(full|complete) (aidlc |sdlc )?(workflow|process|lifecycle)\b|\baidlc\b|'
                  r'\b(use|with|dispatch) (the )?(specialist )?(sub-?agents?|agents in parallel)\b')

TRUST = (
    ('PII', rx(r'\b(pii|personal data|e-?mails?|phone( numbers?)?|home address|date of birth|dob|ssn|passports?|'
               r'national id|kyc|gdpr|pdpa|health data)\b')),
    ('auth', rx(r'\b(auth|authn|authz|authenticat\w*|authoriz\w*|log ?ins?|log ?outs?|sign ?(in|up)|'
                r'session (tokens?|cookies?|fixation|hijack\w*|management|timeouts?)|(user|login) sessions?|'
                r'(access|refresh|auth|bearer|id|jwt|csrf|api) tokens?|tokens? (expir\w*|refresh\w*|validation|rotation)|'
                r'jwt|oauth\w*|oidc|sso|permissions?|role[- ]based|user roles?|rbac|acl|passwords?|mfa|2fa|otp)\b')),
    ('money', rx(r'\b(payments?|pay|billing|invoices?|refunds?|charges?|wallets?|transfers?|payouts?|ledgers?|'
                 r'checkout|subscriptions?|pricing|credit cards?)\b|(?<!load )\bbalances?\b')),
    ('new public surface', rx(r'\b(endpoints?|webhooks?|public api|new api|new routes?|expose[sd]?)\b')),
    ('external vendor', rx(r'\b(third[- ]party|vendors?|partner api|stripe|paypal|twilio|sendgrid|adyen|plaid|'
                           r'external api)\b')),
    ('secrets/crypto config', rx(r'\b(secrets?|tls|ssl|certificates?|iam|encrypt\w*|decrypt\w*|kms|hsm|'
                                 r'private keys?|api keys?|signing keys?|key rotation|cors)\b')),
)

DOMAINS = (
    # Security first: it is the one the [:3] cap must never drop.
    ('fintech-security', rx(r'\b(threat model\w*|stride|owasp|mas trm|security review)\b')),
    ('backend-languages', rx(r'\b(golang|go\.mod|spring[- ]boot|fastapi|pydantic|django|flask|axum|tokio|actix)\b')),
    ('database-patterns', rx(r'\b(sql|postgres\w*|mysql|dynamodb|redis|cte|databases?|indexes|indices|'
                             r'(db|database|sql|schema) (tables?|index|migrations?|quer(y|ies))|an index)\b')),
    ('messaging-patterns', rx(r'\b(kafka|rabbitmq|sqs|sns|eventbridge|dlq|dead[- ]letter|pub/?sub|outbox|'
                              r'event[- ]driven|message (queues?|brokers?))\b')),
    ('cdk-testing', rx(r'\bcdk\b')),
    ('data-pipeline-patterns', rx(r'\b(etl|elt|spark|pyspark|databricks|delta lake|dbt|data warehouse|scd|cdc|'
                                  r'airflow)\b')),
    ('frontend-react', rx(r'\b(react(?! native)|next\.?js|jsx|tsx|frontend|front-end|vitest)\b')),
    ('fintech-mobile', rx(r'\b(flutter|dart|ios(?! safari)|android|swiftui|react native|mobile (app|banking)s?)\b')),
    ('observability', rx(r'\b(datadog|dogstatsd|dd-trace|dd-java-agent|apm)\b')),
    ('api-contract-testing', rx(r'\b(pact|openapi|swagger|contract tests?|consumer[- ]driven)\b')),
    ('bdd-cucumber', rx(r'\b(cucumber|gherkin|bdd|godog)\b|\.feature\b')),
)

# Process skills and commands, in the order they should run when several match.
INTENTS = (
    ('goal', rx(r'(^|\s)/goal\b|\bend[- ]to[- ]end\b|\bhandle (it|everything|the whole)\b|\buntil (it\'?s )?done\b|'
                r'\bautonomous(ly)?\b')),
    ('clarify', rx(r'\bask me (\w+ )?(questions )?first\b|\bclarifying questions\b')),
    ('grilling', rx(r'\bgrill(ing)? (me|it|this|the \w+)\b|\bgrill-?me\b|\binterview me\b')),
    ('expert-lens', rx(r'\bwhat would (an? )?(expert|senior|staff|principal|top \w+)\b|\bhow do the best\b')),
    ('reframe', rx(r'\b(devil\'?s advocate|challenge (this|my)|what am i missing|poke holes|second opinion)\b')),
    ('writing-software-docs', rx(r'\b(write|draft|create|prepare)\b[^.\n→]{0,25}'
                                 r'\b(prd|brd|frd|rfc|adr|user stor(y|ies)|acceptance criteria)\b')),
    ('measurement-planning', rx(r'\b(north star|funnel|a/b test\w*|ab test\w*|experiment design|event taxonomy|'
                                r'go[- ]to[- ]market|gtm)\b')),
    ('generate-service-docs', rx(r'\b(generate|write|create|build) (the )?(service |living )?(docs|documentation)\b'
                                 r'|\bdocument (this|the) (service|codebase|repo\w*)\b')),
    ('upgrade-service-docs', rx(r'\b(update|refresh|sync|promote) (the )?(living |service )?(docs|documentation)\b'
                                r'|\bdocs? (is|are) (outdated|stale)\b')),
    ('incident-to-eval', rx(r'\b(revert(ed)?|roll ?back|rolled back|incident|post-?mortem|outage)\b')),
    ('find-docs', rx(r'\b(give me|cite|show me|with) (the |a )?(sources?|docs|documentation)\b'
                     r'|\b(does|do|is) (the )?[\w.\-/ ]{1,40}\bsupport\b|\bwhich version\b'
                     r'|\bis (it|this) (deprecated|still supported)\b')),
    ('validate-feature', rx(r'\bready (for|before) (a |the )?(pr|merge|review|release)\b'
                            r'|\bbefore I open a (pr|pull request)\b'
                            r'|\bvalidate (the |my |this |these )?(pending )?(changes?|branch|work|diff|feature|pr)\b'
                            r'|\bcheck (that )?(the|my|this) (pending )?(changes?|work|diff)\b')),
    ('receiving-code-review', rx(r'\b(reviewer|review comments?|review feedback|pr comments?)\b[^.\n]{0,40}'
                                 r'\b(left|said|says|asks?|wants?|suggests?|flagged|commented)\b'
                                 r'|\b(deal with|address|apply|handle) (the |this |their )?(review|review comments?|'
                                 r'feedback|pr comments?)\b')),
    ('review', rx(r'\b(get|have) (it|this|them|these|the \w+(?: \w+)?) reviewed\b|'r'\breview (my|the|this|these) (code|changes?|diff|pr|branch)\b|\bcode review\b')),
    ('ship', rx(r'\bship (it|this|the \w+)\b|\b(cut|make|do) (a |the )?release\b|\brelease (it|this|v?\d[\w.]*)\b'
                    r'|\bdeploy (it|this)\b|\bdeploy (the \w+ )?to (prod\w*|staging|production)\b|\bgo live\b')),
    ('finishing-a-development-branch', rx(r'(?<!→ )(?<!-> )(?<!auto )\b(open|create|raise|make|send) (a |the )?'
                                          r'(pr|pull request)\b'
                                          r'|\bmerge (it|this|the branch)\b')),
    ('prove-it', rx(r'\b(are you sure|really (done|fixed|working)|prove it|double[- ]check)\b')),
)
# A spec in the to-spec template pasted into the prompt (references/aidlc.md §2 spec.md).
HANDED_SPEC = re.compile(r'^\W{0,4}problem statement\W*$(?s:.*)^\W{0,4}user stories\W*$', re.I | re.M)
LIFECYCLE_STATUS = rx(r'\b(where are we|what\'?s next|what is next|which stage|status of (the|this) (feature|spec|change))\b')

# Intents that frame the whole task run before spec; the others follow the change workflow.
OPENERS = ('goal', 'clarify', 'grilling', 'expert-lens', 'reframe')
# Intents that still apply when the prompt is a question; the rest ask for work to be done.
CONVERSATIONAL = OPENERS + ('prove-it', 'find-docs')


# Every skill or command name this hook can emit; scripts/check-setup.py verifies each one exists in the plugin.
CHAIN = ('spec', 'systematic-debugging', 'debug-parallel', 'test-driven-development')
FOLLOW_UPS = ('verification-before-completion', 'build')
SKILL_NAMES = frozenset(CHAIN + FOLLOW_UPS + OPENERS + tuple(name for name, _ in DOMAINS + INTENTS))


def match_word(pattern, text):
    found = pattern.search(text)
    return found.group(0).strip() if found else None


def is_code_work(text, debug):
    if debug or STRONG_CODE.search(text):
        return True
    return bool(WEAK_CODE.search(text)) and not PROSE.search(text) and not OPS.search(text)


def workflow_mode():
    return 'full' if os.environ.get('TEA_SDLC_WORKFLOW', '').strip().lower() == 'full' else 'lean'


def route(prompt, rules_dir):
    text = (prompt or '')[:6000]
    if not text.strip() or text.lstrip().startswith('/'):
        return ''
    full = workflow_mode() == 'full' or bool(FULL_REQUEST.search(text))
    intents = [name for name, pattern in INTENTS if pattern.search(text)]
    change, debug, trust = None, None, []
    # A question gets an answer, not a workflow; a change to prose, git or ops is not gated as code.
    domains = [(name, hit) for name, pattern in DOMAINS if (hit := match_word(pattern, text))][:3]
    question = text.rstrip().endswith('?') or ('?' in text and QUESTION_START.match(text))
    if question:
        intents = [name for name in intents if name in CONVERSATIONAL]
    else:
        debug = match_word(DEBUG, MONITORED.sub(' ', text))
        change = match_word(CHANGE, text)
        if not is_code_work(text, debug):
            change = None
        if not change and HANDED_SPEC.search(text):
            change = 'a spec to build'
        if change or debug:
            trust = [(label, hit) for label, pattern in TRUST if (hit := match_word(pattern, text))]
    status_question = bool(LIFECYCLE_STATUS.search(text))
    if not (change or debug or intents or domains or status_question):
        return ''
    chain = [i for i in intents if i in OPENERS]
    if change or debug:
        chain.append('spec')  # the bootstrap's first action for any fix, so the order matches it
    if debug:
        chain.append('systematic-debugging')
        if MULTI_SERVICE.search(text) and full:
            chain.append('debug-parallel')
    if change or debug:
        chain.append('test-driven-development')
    chain += [i for i in intents if i not in chain]

    signals = []
    if change:
        signals.append(f'code change ("{change}")')
    if debug:
        signals.append(f'bug/error ("{debug}")')
    if trust:
        signals.append('trust boundary: ' + ', '.join(f'{label} ("{hit}")' for label, hit in trust))
    lines = ['Signals: ' + '; '.join(signals) + '.' if signals else None,
             'Load in this order, without waiting for the user to name them: '
             + ' → '.join(skill(name) for name in chain) + '.' if chain else None]
    if change or debug:
        if trust and full:
            lines.append(f'Routing: trust-boundary signal → walk the six-item check in {rules_dir}/workflow-routing.md;'
                         ' any YES (or unsure) → Full workflow (Security first).')
        elif trust:
            lines.append(f'Routing: trust-boundary signal, workflow mode lean (default) → Fast path with a security pass '
                         f'({rules_dir}/workflow-routing.md § Lean mode), no subagents: check the threats and the '
                         'security rules yourself and list them in the PR description. The full AIDLC workflow with '
                         'subagents runs only when the user asks for it.')
        else:
            lines.append('Routing: no trust-boundary keyword → Fast path, unless the six-item check says otherwise.')
    if full and any(name == 'fintech-security' for name, _ in domains):
        lines.append('Threat models are produced by tea-sdlc:security-engineer-subagent (Full workflow); the skill is its '
                     'rule catalogue, not a replacement for that dispatch.')
    if (change or debug) and HANDED_SPEC.search(text):
        ready = 'ready-for-agent' in text.lower()
        lines.append('Spec handed over (to-spec template): it is the spec. '
                     + ('Full mode: save it verbatim as docs/specs/<feature>/spec.md, change only what the accepted '
                        'gate rejects, no rewrite into other files. ' if full else
                        'Lean: save it verbatim as docs/specs/<feature>/spec.md (no README, ledger or gates) and '
                        'build from it. ')
                     + 'Slice tickets from its stories, test at its Testing Decisions seams, do not re-ask what it '
                       'decides' + ('; Status ready-for-agent: no grilling.' if ready else '.'))
    if 'finishing-a-development-branch' in chain:
        lines.append(f'Before the PR: the single pass in {rules_dir}/pre-pr-review.md, recorded with '
                     f'{PLUGIN_ROOT}/scripts/mark-pr-review.py.')
    if status_question:
        lines.append(f'Lifecycle state: run python3 "{PLUGIN_ROOT}/scripts/aidlc.py" status (and `next <feature>`) '
                     'and answer from its output.')
    if domains:
        lines.append('Domain skill, load before answering or coding: '
                     + ', '.join(f'{skill(name)} ("{hit}")' for name, hit in domains) + '.')
    lines.append('These are keyword hints: skip any that do not fit. Run commands yourself; never ask the user to type one.')
    return '\n'.join(line for line in lines if line)


# ---------------------------------------------------------------------------------------------------------------
# Session state, PostToolUse tracking and follow-up notes
# ---------------------------------------------------------------------------------------------------------------

def state_path(session):
    return STATE_DIR / (re.sub(r'[^A-Za-z0-9_-]', '_', session) + '.json')


def load_state(session):
    try:
        return json.loads(state_path(session).read_text())
    except (OSError, ValueError):
        return {}


def save_state(session, state):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        target = state_path(session)
        temp = target.with_suffix(f'.{os.getpid()}.tmp')
        temp.write_text(json.dumps(state))
        os.replace(temp, target)  # atomic: concurrent hooks never read a half-written file
    except OSError:
        pass


def is_code(path):
    path = path.replace('\\', '/')
    return path.endswith(tdd.CODE_EXT) and not tdd.SKIP_DIRS.search(path)


def display_path(path, cwd):
    try:
        return str(pathlib.Path(path).resolve().relative_to(pathlib.Path(cwd).resolve()))
    except (ValueError, OSError):
        return path


def spec_status(readme):
    try:
        head = readme.read_text(errors='replace')[:2000]
    except OSError:
        return {}
    match = re.match(r'---\s*\n(.*?)\n---', head, re.S)
    meta = {}
    for line in (match.group(1).splitlines() if match else []):
        if ':' in line and not line.startswith((' ', '\t', '#')):
            key, _, value = line.partition(':')
            meta[key.strip()] = value.split('#')[0].strip()
    return meta


def repo_root(cwd):
    here = pathlib.Path(cwd or '.').resolve()
    for folder in [here, *here.parents]:
        if (folder / '.git').exists():
            return folder
        if folder == pathlib.Path.home():
            break
    return here


def active_specs(root, statuses=('proposed', 'accepted')):
    found = []
    for pattern in ('docs/specs/*/README.md', '*/docs/specs/*/README.md'):
        for readme in sorted(root.glob(pattern)):
            meta = spec_status(readme)
            if meta.get('status', 'proposed') in statuses:
                found.append((readme.parent, meta))
    return found[:8]


REVERT = rx(r'(^|[;&|\s])git\s+revert\b(?!.*--abort)')
MERGE = rx(r'(^|[;&|\s])(gh\s+pr\s+merge|git\s+merge)\b(?!.*--abort)')


def post(payload, session, cwd):
    tool, tin = payload.get('tool_name'), payload.get('tool_input') or {}
    state = load_state(session)
    before = json.loads(json.dumps(state))
    notes = []
    if tool in ('Edit', 'Write', 'MultiEdit'):
        target = str(tin.get('file_path', ''))
        if is_code(target):
            dirty = state.setdefault('dirty', [])
            shown = display_path(target, cwd)
            if shown not in dirty:
                dirty.append(shown)
                del dirty[:-20]
    elif tool == 'Bash':
        command = str(tin.get('command', ''))
        parts = tdd.segments(command)
        runs = [index for index, part in enumerate(parts) if tdd.RUNNER.match(part)]
        if runs:
            state['dirty'] = []
            red = bool(tdd.RED.search(tdd.result_text(payload)))
            state['fail_streak'] = state.get('fail_streak', 0) + 1 if red else 0
            if state['fail_streak'] == FAIL_STREAK:
                notes.append(f'{FAIL_STREAK} failing test runs in a row. Stop patching symptoms: load '
                             f'{skill("systematic-debugging")}, reproduce, and find the root cause before the next fix.')
        # Only writes after the last test run in the same command leave code untested.
        written = tdd.bash_writes_prod('\n'.join(parts[runs[-1] + 1:]) if runs else command)
        if written:
            dirty = state.setdefault('dirty', [])
            if written not in dirty:
                dirty.append(written)
        if not runs:
            if REVERT.search(command) and not state.get('incident_nudged'):
                state['incident_nudged'] = True
                notes.append(f'A commit was just reverted. Load {skill("incident-to-eval")} to turn the defect into '
                             'a regression case for review quality (ask the user only for facts you cannot find).')
            if MERGE.search(command):
                pending = [(spec, meta) for spec, meta in active_specs(repo_root(cwd), ('accepted', 'shipped'))
                           if str(spec) not in state.get('promote_nudged', [])]
                if pending:
                    state.setdefault('promote_nudged', []).extend(str(spec) for spec, _ in pending)
                    names = ', '.join(display_path(str(spec), cwd) for spec, _ in pending)
                    notes.append(f'A merge just ran and these specs are not promoted yet: {names}. When the change '
                                 f'is merged on the target branch, run {skill("upgrade-service-docs")} yourself to '
                                 'promote it into the living docs and close the spec.')
    if state != before:
        save_state(session, state)
    return '\n'.join(notes)


def stop(payload, session, cwd):
    if payload.get('stop_hook_active'):
        return None
    state = load_state(session)
    dirty = state.get('dirty') or []
    if not dirty or not tdd.has_test_setup(cwd):
        return None
    fingerprint = hashlib.sha256('\n'.join(sorted(dirty)).encode()).hexdigest()[:16]
    if fingerprint in state.get('reminded', []) or len(state.get('reminded', [])) >= MAX_STOP_REMINDERS:
        return None
    state.setdefault('reminded', []).append(fingerprint)
    save_state(session, state)
    shown = ', '.join(dirty[:6]) + (f' and {len(dirty) - 6} more' if len(dirty) > 6 else '')
    return (f'tea-sdlc verification: code changed since the last test run in this session ({shown}). Before you '
            f'finish, run the relevant tests and show the result ({skill("verification-before-completion")}), or say '
            'in your reply why no test applies to this change. This reminder appears once per change set.')


# ---------------------------------------------------------------------------------------------------------------
# Session snapshot (called by hooks/session-start)
# ---------------------------------------------------------------------------------------------------------------

def plan_progress(path):
    """(done, total) tickets in tickets.md (`Status: done`), or ticked tasks in a legacy plan.md."""
    tickets = path.parent / 'tickets.md' if path.name == 'plan.md' else path
    try:
        text = tickets.read_text(errors='replace')
        total = len(re.findall(r'^##\s+T\d+\b', text, re.M))
        done = len(re.findall(r'^\s*\**Status\**\s*:\**\s*done\b', text, re.M | re.I))
        if total:
            return min(done, total), total
    except OSError:
        pass
    try:
        text = path.read_text(errors='replace')
    except OSError:
        return None
    done = len(re.findall(r'^\s*[-*] \[[xX]\]', text, re.M))
    total = done + len(re.findall(r'^\s*[-*] \[ \]', text, re.M))
    return (done, total) if total else None


# What each stage needs next, and the skill that does it (references/aidlc.md).
NEXT_STEP = {
    'proposed': 'finish spec.md (the template: stories, decisions incl. Security, testing seams), get the one '
                'approval, then `aidlc advance <spec> accepted`',
    'accepted': 'slice tickets.md with tea-sdlc:plan, then `aidlc advance <spec> planned`',
    'planned': '`aidlc advance <spec> building` on a feature branch, then build the `aidlc next` batches '
               '(tea-sdlc:build)',
    'building': 'build the `aidlc next` batches; finish tickets with `aidlc task-done`; then `aidlc verify` and advance',
    'verified': 'two-axis review + QA into review.md (tea-sdlc:review), `aidlc stamp <spec> review`, '
                'then advance',
    'reviewed': 'ship stage (tea-sdlc:ship): PR, CI, ship.md, `aidlc advance <spec> shipped`, merge',
    'shipped': 'promote with upgrade-service-docs, then `aidlc advance <spec> implemented`',
}


# Skills that the superpowers plugin also ships under the same name.
SUPERPOWERS_TWINS = ('test-driven-development', 'systematic-debugging', 'verification-before-completion',
                     'dispatching-parallel-agents', 'finishing-a-development-branch', 'receiving-code-review')
STATE_ROOTS = ('tdd', 'contract-gate', 'tea-sdlc/autopilot')
STATE_MAX_AGE_DAYS = 30


def enabled_plugins(root):
    """enabledPlugins merged from user, project and local settings (later files win)."""
    merged = {}
    for path in (pathlib.Path.home() / '.claude' / 'settings.json', root / '.claude' / 'settings.json',
                 root / '.claude' / 'settings.local.json'):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get('enabledPlugins'), dict):
            merged.update(data['enabledPlugins'])
    return merged


def prune_state(now=None):
    """Delete per-session gate state older than STATE_MAX_AGE_DAYS; sessions that old are not resumed."""
    import time
    cutoff = (now or time.time()) - STATE_MAX_AGE_DAYS * 86400
    base = pathlib.Path.home() / '.claude' / 'state'
    for folder in STATE_ROOTS:
        for path in (base / folder).glob('*.json'):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


def load_aidlc():
    spec = importlib.util.spec_from_file_location('tea_sdlc_aidlc', PLUGIN_ROOT / 'scripts' / 'aidlc.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def spec_lines(root):
    """One line per active spec: stage, what the next gate still needs, and the next parallel batch."""
    cli = f'python3 "{PLUGIN_ROOT}/scripts/aidlc.py"'
    try:
        aidlc = load_aidlc()
        try:  # fast: no network or slow subprocesses inside the 10 s session-start budget
            rows = aidlc.status(str(root), fast=True)
        except TypeError:
            rows = aidlc.status(str(root))
        rows = [row for row in rows if row.get('stage') in NEXT_STEP]
    except Exception:  # engine missing or broken: fall back to the README status alone
        aidlc, rows = None, [{'path': str(spec), 'stage': meta.get('status', 'proposed'), 'blockers': []}
                             for spec, meta in active_specs(root)]
    lines = []
    for row in rows[:6]:
        path = pathlib.Path(row['path'])
        path = path if path.is_absolute() else root / path  # status() reports repo-relative paths
        rel = display_path(str(path), root)
        stage = row['stage']
        progress = plan_progress(path / 'plan.md')
        detail = f', {progress[0]}/{progress[1]} tickets done' if progress else ''
        if row.get('legacy'):
            detail += ' (legacy: no key, not gated)'
        elif row.get('blockers'):
            detail += f'; next gate blocked by: {"; ".join(str(b) for b in row["blockers"][:3])}'
        elif row.get('passes'):
            detail += f'; the {row.get("next")} gate already passes — advance it'
        if aidlc and stage == 'building':
            try:
                batch = (aidlc.next_batches(path) or [[]])[0]
                if batch:
                    detail += f'; next parallel batch: {", ".join(str(task.get("id")) for task in batch)}'
            except Exception:
                pass
        lines.append(f'Spec {rel} at stage `{stage}`{detail}. Next: {NEXT_STEP[stage].replace("<spec>", rel)}.')
    if rows:
        lines.append(f'Lifecycle CLI: {cli} status | next <spec> | check <spec> (references/aidlc.md).')
    return lines


def snapshot(cwd, which=None):
    """Return (context lines for Claude, message for the user or None)."""
    which = which or __import__('shutil').which
    root = repo_root(cwd)
    lines, user = [], None
    if workflow_mode() == 'full':
        lines.append('Workflow mode: full (TEA_SDLC_WORKFLOW=full): trust-boundary changes run the AIDLC lifecycle '
                     'with specialist subagents.')
    else:
        lines.append('Workflow mode: lean (default): every change stays in this session, no subagent dispatch; a '
                     'trust boundary gets a security pass, not the full workflow. Run the full workflow only when the '
                     'user asks for it or a spec bound to this branch is already in progress.')
    goal = root / '.goal' / 'state.md'
    if goal.is_file():
        lines.append('Resumable goal: read .goal/state.md first and continue from it (skill tea-sdlc:goal).')
    lines.extend(spec_lines(root))
    plans = sorted((root / 'docs' / 'plans').glob('*.md'), reverse=True)[:2] if (root / 'docs' / 'plans').is_dir() else []
    for plan in plans:
        progress = plan_progress(plan)
        if progress and progress[0] < progress[1]:
            lines.append(f'Open plan {display_path(str(plan), root)} ({progress[0]}/{progress[1]} tasks done); resume it with tea-sdlc:build '
                         'when the user continues that work.')
    has_code = any((root / name).exists() for name in tdd.INFRA)
    if has_code and not (root / 'docs').is_dir():
        lines.append('This repository has no docs/ yet: when a task needs architecture context, offer once to run '
                     'tea-sdlc:generate-service-docs (you run it, not the user).')
    if any(name.split('@')[0] == 'superpowers' and on for name, on in enabled_plugins(root).items()):
        twins = [name for name in SUPERPOWERS_TWINS if (PLUGIN_ROOT / 'skills' / name / 'SKILL.md').is_file()]
        lines.append('The superpowers plugin is also enabled and ships skills with the same names. Where both exist, '
                     'load the tea-sdlc one (' + ', '.join(skill(name) for name in twins[:4]) + ', …): they follow this '
                     "plugin's routing tiers and gates; do not run both versions of a step.")
    if not which('gitleaks'):
        lines.append('gitleaks is not installed: the security gate will block git commit/push until it is.')
        user = 'tea-sdlc: gitleaks is not installed, so git commit/push will be blocked. Install: brew install gitleaks'
    return lines, user


# Subagents never see the SessionStart bootstrap, so the rules they must follow travel with each dispatch.
READ_ONLY_AGENTS = ('explore', 'claude-code-guide', 'statusline-setup', 'web-fetch', 'plan')


def subagent_rules(agent_type):
    if str(agent_type).split(':')[-1].lower() in READ_ONLY_AGENTS:
        return ''
    rules = PLUGIN_ROOT / 'rules'
    return '\n'.join((
        'tea-sdlc rules for this subagent (the main session dispatched you; its bootstrap does not reach you):',
        '- You are a leaf: do not dispatch further agents. If the task needs more, return the dispatch plan and stop.',
        f'- Return a status (DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT or BLOCKED), evidence paths the dispatcher can '
        f'Read, and a check of each exit criterion ({rules}/subagent-return-format.md).',
        '- Evidence before claims: cite file:line or command output; never invent paths, flags or results.',
        '- TDD: the tdd-gate hook blocks the first production edit without a recorded failing test run. Write the '
        'test, run it, see it fail, then change the code. Name each test with the requirement ID it covers '
        '(for example "RFD-1 rejects over-capture") so the trace gate finds it.',
        '- Stay inside the files your task owns. Do not edit docs/specs/**, contracts/ or another task\'s files unless '
        'the dispatch says so; others work in the same checkout, never revert their changes.',
        '- A contract-gate finding means the contract must change: return NEEDS_CONTEXT with it instead of editing '
        'contracts/.',
    ))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    session = str(payload.get('session_id') or '')
    cwd = payload.get('cwd') or os.getcwd()
    autopilot_on = os.environ.get('TEA_SDLC_AUTOPILOT', '').lower() != 'off'
    if mode == 'prompt' and autopilot_on:
        note = route(str(payload.get('prompt', '')), PLUGIN_ROOT / 'rules')
        if note:
            emit('UserPromptSubmit', note)
    elif mode == 'post' and session:
        note = post(payload, session, cwd)
        if note and autopilot_on:
            emit('PostToolUse', note)
    elif mode == 'subagent' and autopilot_on:
        rules = subagent_rules(payload.get('agent_type', ''))
        if rules:
            emit('SubagentStart', rules)
    elif mode == 'stop' and session and os.environ.get('TEA_SDLC_VERIFY_GATE', '').lower() != 'off':
        reason = stop(payload, session, cwd)
        if reason:
            print(json.dumps({'decision': 'block', 'reason': reason}))
    return 0


def emit(event, note):
    note = '<tea-sdlc-autopilot>\n' + note[:NOTE_LIMIT - 60] + '\n</tea-sdlc-autopilot>'
    print(json.dumps({'hookSpecificOutput': {'hookEventName': event, 'additionalContext': note}}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # autopilot is advisory: never break the session
        sys.exit(0)
