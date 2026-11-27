"""Public API (hooks call it) and the helpers every command shares."""
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403
from aidlc_lib.graph import *  # noqa: F401,F403
from aidlc_lib.model import *  # noqa: F401,F403
from aidlc_lib.gates import *  # noqa: F401,F403

# ------------------------------------------------------------------------------------------------------ public API

def find_spec(repo, ref):
    path, _ = resolve_spec(repo, ref)
    return path


def resolve_spec(repo, ref):
    """(path, None) or (None, error): a path when ref contains '/', else a slug under any docs/specs/ folder."""
    repo = pathlib.Path(repo).resolve()
    ref = str(ref)
    if '/' in ref or os.sep in ref:
        for candidate in (pathlib.Path(ref), repo / ref):
            if candidate.is_dir():
                return candidate.resolve(), None
        return None, f'{ref} is not a folder'
    matches = [d for d in Repo(repo).spec_dirs() if d.name == ref]
    if len(matches) > 1:
        return None, f'{ref} is ambiguous: {", ".join(Repo(repo).rel(m) for m in matches)} (pass the path)'
    if not matches:
        return None, f'no spec named {ref} under a docs/specs/ folder in {repo}'
    return matches[0], None


def load_spec(path):
    """Every artifact parsed; `errors` holds parse problems only (gate checks are check()'s job)."""
    spec = Spec(path)
    artifacts, errors = {}, list(spec.readme[2])
    for name in ('parsed_requirements', 'guesses', 'tasks', 'ledger', 'review', 'ship'):
        data, findings = getattr(spec, name)
        artifacts[name] = data
        errors += findings
    reqs = artifacts.pop('parsed_requirements')
    return {'path': str(spec.dir), 'slug': spec.slug, 'repo': str(spec.repo.root), 'stage': spec.stage,
            'readme': spec.meta, 'requirements': None if reqs is None else select_requirements(reqs, spec.key),
            'errors': errors, **artifacts}


def stage(path):
    return Spec(path).stage


def check(path, target=None):
    return _check(Spec(path), target)


def fingerprint(repo, rev=None):
    return Repo(repo).fingerprint if rev is None else Repo(repo).fingerprint_at(rev)


def code_dirty(repo):
    return Repo(repo).code_dirty


def evidence_findings(path, rev=None):
    return _evidence(Spec(path), rev)


def active_specs(repo):
    root = Repo(repo)
    return [d for d in root.spec_dirs() if Spec(d, root).stage in ACTIVE]


def specs_for_branch(repo, branch):
    root = Repo(repo)
    return [d for d in root.spec_dirs() if branch and Spec(d, root).meta.get('branch') == branch]


def status(repo, fast=False):
    root, items = Repo(repo, fast=fast), []
    for folder in root.spec_dirs():
        spec = Spec(folder, root)
        nxt = next_stage(spec.stage)
        legacy = 'key' not in spec.meta
        item = {'path': root.rel(folder), 'slug': spec.slug, 'stage': spec.stage, 'next': nxt, 'passes': None,
                'blockers': [], 'legacy': legacy}
        if nxt and not legacy:
            findings = _check(spec, nxt)
            item['passes'] = not failed(findings)
            item['blockers'] = [m for level, m in findings if level == 'FAIL']
        items.append(item)
    return items


def next_batches(path):
    tasks, _ = Spec(path).tasks
    return batches(tasks) if tasks else []


# ------------------------------------------------------------------------------------------------------------- CLI

def repo_arg(args):
    """--repo (any folder inside the repository) or the current folder, normalized to the git top level."""
    return repo_root(pathlib.Path(args.repo) if args.repo else pathlib.Path.cwd())


def spec_arg(args):
    path, error = resolve_spec(repo_arg(args), args.spec)
    if error:
        raise UsageError(error)
    return Spec(path, Repo(repo_arg(args)) if args.repo else None)


def finding_result(findings, payload):
    payload['findings'] = [{'level': level, 'message': message} for level, message in findings]
    payload['passes'] = not failed(findings)
    return (1 if failed(findings) else 0), payload, [f'{level} {message}' for level, message in findings]


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
