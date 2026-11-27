#!/usr/bin/env python3
"""AIDLC lifecycle engine: the stages, artifacts and gates of references/aidlc.md (stdlib only, Python 3.9+).

CLI: python3 scripts/aidlc.py <command> [--json] [--repo DIR]   exit 0 pass, 1 gate findings, 2 usage or input error
  status [--fast]                          every spec: stage, next stage, whether its gate passes, blockers
  check SPEC [--to STAGE]                  run a gate (default: the next stage's), also for a stage already reached
  advance SPEC STAGE [--back] [--reason T] move forward one stage when its gate passes; --back --reason moves back;
                                           abandoned (--reason), superseded (README superseded_by:), partially-implemented
  next SPEC                                ready tasks in conflict-free parallel batches
  task-done SPEC T<n> [--cmd CMD]          run CMD (default: the task's `test:` field); on exit 0 tick it and log it
  verify SPEC                              run the command pinned in .aidlc.json (revert check first); log exit code,
                                           code fingerprint and JUnit totals. --cmd/--junit only if equal to the pin
  approve SPEC [--by NAME] [--delegated]   log the SHA-256 of spec.md as approved (a person's act; see hooks/evidence-guard.py)
  attest SPEC --agent A --axis AXIS [--file F]  store a review done elsewhere in <spec>/returns/
  config init|show                         write .aidlc.json (never overwrites) / show the config the gates use
  ci [--base REF] [--branch B] [--require reviewed|verified|none]  recompute the evidence on the checked-out head
  ruling SPEC --decision T --why T --if-wrong T [--task T<n>]
  stamp SPEC review                        write the code fingerprint into review.md and log it
  trace SPEC [--write]                     requirement -> tasks -> tests -> result; --write fills README ## Traceability
  init SPEC --key KEY                      create the spec folder with skeletons
  lint FILE [--key KEY] [--no-security]    check a standalone spec.md (a drafted prompt) against the spec rules
SPEC is a folder path (contains '/') or a slug found under any docs/specs/ folder (init: <repo>/docs/specs/<slug>).
--repo may be any folder of the repository (normalized to the git top level). task-done, verify and ci accept
--timeout SECONDS (default 1800). JSON: `exit` is always the CLI exit code; `command_exit` is the run command's.
Writers of tickets.md (or plan.md), README.md and ledger.md hold an exclusive flock on the spec folder (no-op without fcntl).

Python API (load with importlib.util.spec_from_file_location; hooks call it; names and signatures are stable):
  find_spec(repo, ref) -> Path | None          spec folder for a path or slug; None when missing or ambiguous
  load_spec(path) -> dict                      path, slug, repo, stage, readme (frontmatter), requirements, guesses,
                                               tasks, ledger, review, ship (None when the file is missing),
                                               errors [(level, message)] from parsing
  stage(path) -> str                           README status: (default proposed)
  check(path, target=None) -> [(level, msg)]   level FAIL | WARN | OK; target defaults to the next stage
  fingerprint(repo, rev=None) -> str | None    SHA-256 over sorted (path, git blob ID) of every non-ignored file except
                                               docs/**, **/docs/specs/**, *.md, CHANGELOG*, LICENSE*; rev = a commit
                                               (None when unknown or outside git). A clean tree equals 'HEAD'.
  code_dirty(repo) -> bool                     the working tree's code differs from HEAD
  evidence_findings(path, rev=None) -> [...]   latest verify green and current; review stamp == verified code;
                                               with rev, that commit holds the verified code
  active_specs(repo) -> [Path]                 specs whose status is proposed..shipped
  specs_for_branch(repo, branch) -> [Path]     specs of ANY status whose README branch: is `branch`
  status(repo, fast=False) -> [dict]           path (repo-relative), slug, stage, next, passes (None = not evaluated),
                                               blockers [str], legacy (no key:, not evaluated); fast=True runs no gh
                                               and no contract gate, only cheap git (session-start snapshot)
  next_batches(path) -> [[task dict]]          the frontier; tasks in one batch share no file
Environment: AIDLC_GH = the gh executable for the shipped gate's CI check (tests point it at a fake).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))  # aidlc_lib/ sits next to this file
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403
from aidlc_lib.graph import *  # noqa: F401,F403
from aidlc_lib.model import *  # noqa: F401,F403
from aidlc_lib.gates import *  # noqa: F401,F403
from aidlc_lib.api import *  # noqa: F401,F403
from aidlc_lib.commands import *  # noqa: F401,F403

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--json', action='store_true', help='print one JSON object')
    common.add_argument('--repo', help='repository root (default: the git top level of the current folder)')
    parser = argparse.ArgumentParser(prog='aidlc', description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)

    def add(name, func, *spec_args):
        command = sub.add_parser(name, parents=[common])
        command.set_defaults(func=func)
        for arg in spec_args:
            command.add_argument(arg)
        return command

    add('status', cmd_status).add_argument('--fast', action='store_true', help='no gh, no contract gate')
    add('check', cmd_check, 'spec').add_argument('--to', choices=list(GATES))
    advance = add('advance', cmd_advance, 'spec')
    advance.add_argument('stage', choices=list(STAGES + SIDE))
    advance.add_argument('--back', action='store_true')
    advance.add_argument('--reason')
    add('next', cmd_next, 'spec')
    task_done = add('task-done', cmd_task_done, 'spec', 'task')
    task_done.add_argument('--cmd')
    task_done.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    verify = add('verify', cmd_verify, 'spec')
    verify.add_argument('--cmd', help='accepted only when it is the pinned command')
    verify.add_argument('--junit', help='accepted only when it is the pinned glob')
    verify.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    ci = add('ci', cmd_ci)
    ci.add_argument('--base', help='the ref the config is read from and the head is compared with (default: '
                                   'origin/$GITHUB_BASE_REF, origin/$BITBUCKET_PR_DESTINATION_BRANCH, else the default branch)')
    ci.add_argument('--branch', help='the branch the specs are bound to (default: $GITHUB_HEAD_REF, $BITBUCKET_BRANCH, '
                                     'else the checked-out branch)')
    ci.add_argument('--require', choices=['reviewed', 'verified', 'none'], default='reviewed',
                    help='the stage a bound spec must have reached (default: reviewed)')
    ci.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT)
    ci.add_argument('--summary', help='append a Markdown summary to this file (default: $GITHUB_STEP_SUMMARY)')
    config = add('config', cmd_config)
    config.add_argument('action', choices=['init', 'show'])
    config.add_argument('--cmd')
    config.add_argument('--junit')
    config.add_argument('--no-revert-check', action='store_true')
    config.add_argument('--dir', help='a service folder with its own docs/specs/ (default: the repository root)')
    ruling = add('ruling', cmd_ruling, 'spec')
    for name in ('--decision', '--why', '--if-wrong'):
        ruling.add_argument(name, required=True)
    ruling.add_argument('--task')
    add('stamp', cmd_stamp, 'spec').add_argument('what', choices=['review'])
    attest = add('attest', cmd_attest, 'spec')
    attest.add_argument('--agent', required=True, help='who returned it, e.g. aegisops-harness:code-reviewer')
    attest.add_argument('--axis', required=True, choices=['spec', 'standards', 'both', 'qa'])
    attest.add_argument('--file', help='the return as a file (default: standard input)')
    approve = add('approve', cmd_approve, 'spec')
    approve.add_argument('--by', help='the approver (default: git user.name)')
    approve.add_argument('--delegated', action='store_true', help='the request handed the decisions over: nobody read the spec')
    add('trace', cmd_trace, 'spec').add_argument('--write', action='store_true')
    add('init', cmd_init, 'spec').add_argument('--key', required=True)
    lint = add('lint', cmd_lint, 'file')
    lint.add_argument('--key', default='KEY')
    lint.add_argument('--no-security', action='store_true', help='the change crosses no trust boundary')
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # command output may not be UTF-8; never crash printing it
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(errors='replace')
            except (ValueError, OSError):
                pass
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:  # argparse already printed the usage error (or --help)
        return exit_.code if isinstance(exit_.code, int) else 2
    try:  # a revert check that was killed left production files at their base version: put them back first
        note = heal_revert(repo_root(pathlib.Path(getattr(args, 'repo', None) or pathlib.Path.cwd())))
        if note:
            print(note, file=sys.stderr)
    except Exception:
        pass
    try:
        code, payload, lines = args.func(args)
    except UsageError as err:
        code, payload, lines = 2, {'error': str(err)}, [f'aidlc: {err}']
    except Exception as err:  # never a traceback
        code, payload, lines = 2, {'error': f'internal error: {err.__class__.__name__}: {err}'}, \
            [f'aidlc: internal error: {err.__class__.__name__}: {err}']
    if args.json:
        print(json.dumps({'command': args.command, 'exit': code, **payload}, indent=2, default=list, ensure_ascii=False))
    else:
        print('\n'.join(lines), file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main())
