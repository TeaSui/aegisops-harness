"""The repository and the spec folder: git reads, the code fingerprint and every artifact, parsed once."""
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403
from aidlc_lib.graph import *  # noqa: F401,F403

# ------------------------------------------------------------------------------------------------ repository and spec

def repo_root(path):
    path = pathlib.Path(path).resolve()
    probe = path
    while not probe.is_dir() and probe != probe.parent:
        probe = probe.parent
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=probe, capture_output=True, text=True,
                             timeout=30)
        if top.returncode == 0 and top.stdout.strip():
            return pathlib.Path(top.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    if path.parent.name == 'specs' and path.parent.parent.name == 'docs':
        return path.parents[2]
    return probe


def blob_id(path):
    """The git blob ID of a file (a symlink hashes its target path, as git does), or None when unreadable."""
    try:
        data = os.readlink(path).encode('utf-8', 'surrogateescape') if os.path.islink(path) else path.read_bytes()
    except OSError:
        return None
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _digest(entries):
    digest = hashlib.sha256()
    for path in sorted(entries):
        digest.update(f'{path}\0{entries[path]}\n'.encode('utf-8', 'surrogateescape'))
    return digest.hexdigest()


class Repo:
    """A repository root with cached file listing, fingerprint and test-file contents.

    fast=True (status for the session-start snapshot) skips gh and the contract gate; only cheap git runs.
    base: the ref the repository config is read from and the branch is compared with (CI passes the PR's base ref);
    default: the default branch."""

    def __init__(self, root, fast=False, base=None):
        self.root = pathlib.Path(root).resolve()
        self.fast = fast
        self.base = base

    def git(self, *args, stdin=None):
        try:
            return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True, timeout=30,
                                  encoding='utf-8', errors='surrogateescape', input=stdin)
        except (OSError, subprocess.SubprocessError):
            return None

    def _z(self, *args):
        """NUL-separated git output as a list, or None when git fails."""
        result = self.git(*args)
        if result is None or result.returncode != 0:
            return None
        return [x for x in result.stdout.split('\0') if x]

    @cached_property
    def is_git(self):
        result = self.git('rev-parse', '--is-inside-work-tree')
        return result is not None and result.returncode == 0 and result.stdout.strip() == 'true'

    def rel(self, path):
        try:
            return pathlib.Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    @cached_property
    def files(self):
        """Every tracked or untracked, not ignored file (repo-relative); a folder walk outside git."""
        listing = self._z('ls-files', '-z', '--cached', '--others', '--exclude-standard') if self.is_git else None
        if listing is not None:
            return sorted(set(listing))
        found = []
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not _tdd.SKIP_DIRS.search(d + '/'))
            found += [self.rel(os.path.join(folder, name)) for name in names]
        return sorted(found)

    # -- code fingerprint: sha256 over sorted (path, git blob ID) of every file not matched by NOT_CODE ------------
    def _hash_paths(self, paths):
        """{path: blob ID} for files whose content git has not recorded (modified or untracked)."""
        ids, batch = {}, [p for p in paths if '\n' not in p]
        result = self.git('hash-object', '--stdin-paths', stdin=''.join(f'{p}\n' for p in batch)) if batch else None
        hashed = result.stdout.split() if result is not None and result.returncode == 0 else []
        if len(hashed) == len(batch):
            ids.update(zip(batch, hashed))
        for path in paths:
            if path not in ids:
                ids[path] = blob_id(self.root / path)
        return {p: v for p, v in ids.items() if v}

    def _working_entries(self):
        if not self.is_git:
            return {rel: blob_id(self.root / rel) for rel in self.files if not NOT_CODE.search(rel)}
        staged = self._z('ls-files', '-s', '-z') or []
        entries, todo = {}, set()
        for line in staged:
            meta, _, path = line.partition('\t')
            mode, sha, stage = (meta.split() + ['', '', ''])[:3]
            if NOT_CODE.search(path):
                continue
            entries[path] = sha
            if stage != '0':  # merge conflict: hash what is on disk
                todo.add(path)
        changed = (self._z('ls-files', '-m', '-z') or []) + (self._z('ls-files', '-o', '--exclude-standard', '-z') or [])
        todo |= {p for p in changed if not NOT_CODE.search(p)}
        for path in todo:
            target = self.root / path
            if os.path.isdir(target) and not os.path.islink(target):
                continue  # a submodule keeps its recorded commit
            entries.pop(path, None)  # deleted files leave the fingerprint
        present = sorted(p for p in todo if os.path.lexists(self.root / p) and not
                         (os.path.isdir(self.root / p) and not os.path.islink(self.root / p)))
        entries.update(self._hash_paths(present))
        return entries

    @cached_property
    def fingerprint(self):
        return _digest(self._working_entries())

    def fingerprint_at(self, rev):
        """Fingerprint of a commit (same exclusions); None outside git or for an unknown revision."""
        if not self.is_git or not rev or str(rev).startswith('-'):
            return None
        resolved = self.git('rev-parse', '--verify', '--quiet', f'{rev}^{{commit}}')
        if resolved is None or resolved.returncode != 0:
            return None
        tree = self._z('ls-tree', '-r', '-z', '--full-tree', resolved.stdout.strip())
        if tree is None:
            return None
        entries = {}
        for line in tree:
            meta, _, path = line.partition('\t')
            if not NOT_CODE.search(path):
                entries[path] = meta.split()[2]
        return _digest(entries)

    @cached_property
    def code_dirty(self):
        """Whether the working tree's code differs from HEAD (staged, unstaged or untracked)."""
        if not self.is_git:
            return False
        head = self.fingerprint_at('HEAD')
        return self.fingerprint != head if head is not None else bool(self._working_entries())

    # -- tests and specs ---------------------------------------------------------------------------------------
    @cached_property
    def test_texts(self):
        texts = {}
        for rel in self.files:
            if rel.endswith(CODE_EXT) and (TEST_PATH.search(rel) or rel.endswith('.feature')) \
                    and not re.search(r'(^|/)docs/specs/', rel):
                try:
                    texts[rel] = (self.root / rel).read_text(encoding='utf-8', errors='replace')
                except OSError:
                    pass
        return texts

    def tests_referencing(self, req_id):
        pattern = id_pattern(req_id)
        return [rel for rel, text in self.test_texts.items() if pattern.search(text)]

    def branch(self):
        result = self.git('symbolic-ref', '--quiet', '--short', 'HEAD')
        return result.stdout.strip() if result is not None and result.returncode == 0 else None

    def default_branches(self):
        origin = self.git('symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD')
        if origin is not None and origin.returncode == 0 and origin.stdout.strip():
            return {origin.stdout.strip().split('/', 1)[-1]}
        configured = self.git('config', 'init.defaultBranch')
        extra = {configured.stdout.strip()} if configured is not None and configured.stdout.strip() else set()
        return {'main', 'master'} | extra

    @cached_property
    def trusted_ref(self):
        """`base` when given, else the default branch as the remote has it (a session can commit to its local default
        branch, not move the remote's without a push), else the local one. None outside git or when none resolves."""
        if not self.is_git:
            return None
        names = [self.base] if self.base else [ref for name in sorted(self.default_branches())
                                               for ref in (f'origin/{name}', name)]
        for ref in names:
            if not ref or str(ref).startswith('-'):
                continue
            found = self.git('rev-parse', '--verify', '--quiet', f'{ref}^{{commit}}')
            if found is None or found.returncode != 0:
                continue
            if str(ref).startswith('origin/'):  # a tag or a local branch named `origin/x` would shadow the short name
                full = self.git('rev-parse', '--verify', '--quiet', f'refs/remotes/{ref}^{{commit}}')
                if full is None or full.returncode != 0 or full.stdout.strip() != found.stdout.strip():
                    continue
            return ref
        return None

    def has_origin(self):
        remotes = self.git('remote')
        return remotes is not None and remotes.returncode == 0 and 'origin' in remotes.stdout.split()

    def show(self, ref, rel):
        """The bytes of `rel` at `ref`, or None when it is not there."""
        try:
            result = subprocess.run(['git', 'show', f'{ref}:{rel}'], cwd=self.root, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout if result.returncode == 0 else None

    @cached_property
    def spec_dirs_cached(self):
        dirs = {(self.root / rel).parent for rel in self.files if SPEC_README.search(rel)}
        return sorted((d for d in dirs if (d / 'README.md').is_file()), key=lambda d: self.rel(d))

    def spec_dirs(self):
        """Spec folders (with a README.md) under any `docs/specs/` in the repository, ignored files excluded."""
        return list(self.spec_dirs_cached)


class Spec:
    """One spec folder; every artifact is parsed once, on first use."""

    def __init__(self, path, repo=None):
        self.dir = pathlib.Path(path).resolve()
        self.repo = repo if repo is not None else Repo(repo_root(self.dir))
        self.slug = self.dir.name
        self.fresh = {}  # {kind: event} produced by this run (`aidlc ci`); read instead of the ledger's line

    def label(self, name):
        return self.repo.rel(self.dir / name)

    def _parse(self, name, parser):
        """(data, findings); data is None when the file is missing or unreadable."""
        text, error = read_text(self.dir / name, self.label(name))
        if text is None:
            return None, [fail(error)] if error else []
        try:
            return parser(text, self.label(name))
        except Exception as err:  # a parser bug must surface as a finding, never as a traceback
            return None, [fail(f'{self.label(name)}: cannot be parsed ({err.__class__.__name__}: {err})')]

    def missing(self, name):
        return [] if (self.dir / name).is_file() else [fail(f'{self.label(name)}: missing')]

    @cached_property
    def readme(self):
        label = self.label('README.md')
        text, error = read_text(self.dir / 'README.md', label)
        if text is None:
            return {}, '', [fail(error or f'{label}: missing')]
        meta, _ = parse_frontmatter(text)
        if meta is None:
            return {}, text, [fail(f'{label}:1: no frontmatter (--- block with status:, key:, …)')]
        findings = []
        status = meta.get('status') or 'proposed'
        if status not in STAGES + SIDE:
            findings.append(fail(f'{label}: status: {status} is not an AIDLC stage'))
        schema = meta.get('schema')
        if schema not in (None, ''):  # absent: schema 1, what every spec before the field looked like
            if not str(schema).isdigit() or int(schema) < 1:
                findings.append(fail(f'{label}: schema: {schema!r} is not a version number'))
            elif int(schema) > SCHEMA:
                findings.append(fail(f'{label}: schema {schema} is newer than this plugin reads ({SCHEMA}): update the '
                                     'plugin before working on this spec'))
        return meta, text, findings

    @property
    def meta(self):
        return self.readme[0]

    @property
    def stage(self):
        return self.meta.get('status') or 'proposed'

    @property
    def key(self):
        key = self.meta.get('key', '')
        return key if KEY.match(key) else ''

    @property
    def legacy_spec(self):
        """requirements.md (+ spec-check.md, security.md) instead of spec.md: specs written before 3.3.0."""
        return not (self.dir / 'spec.md').is_file() and (self.dir / 'requirements.md').is_file()

    @property
    def spec_name(self):
        return 'requirements.md' if self.legacy_spec else 'spec.md'

    @property
    def plan_name(self):
        if (self.dir / 'tickets.md').is_file():
            return 'tickets.md'
        return 'plan.md' if (self.dir / 'plan.md').is_file() or self.legacy_spec else 'tickets.md'

    @cached_property
    def parsed_requirements(self):
        if self.legacy_spec:
            return self._parse('requirements.md', parse_requirements)
        return self._parse('spec.md', lambda text, label: parse_spec(text, label, self.key or 'KEY'))

    @cached_property
    def requirements(self):
        """(requirements of this spec's key or None, parse findings + requirement_findings)."""
        reqs, findings = self.parsed_requirements
        if reqs is None:
            return None, findings or self.missing(self.spec_name)
        if not self.legacy_spec:
            text, _ = read_text(self.dir / 'spec.md', self.label('spec.md'))
            return reqs, findings + spec_findings(text or '', self.label('spec.md'), reqs)
        return (select_requirements(reqs, self.key),
                findings + requirement_findings(reqs, self.key, self.label('requirements.md')))

    @cached_property
    def guesses(self):
        return self._parse('spec-check.md', parse_spec_check)

    @cached_property
    def tasks(self):
        return self._parse(self.plan_name, parse_tickets if self.plan_name == 'tickets.md' else parse_plan)

    @cached_property
    def ledger(self):
        events, findings = self._parse('ledger.md', parse_ledger)
        return events or [], findings

    @cached_property
    def review(self):
        return self._parse('review.md', parse_review)

    @cached_property
    def ship(self):
        return self._parse('ship.md', parse_ship)

    @cached_property
    def returns(self):
        """(stored reviewer returns in the order they were recorded, findings)."""
        items, findings = [], []
        for path in sorted((self.dir / RETURNS).glob('*.md')) if (self.dir / RETURNS).is_dir() else []:
            item, problems = self._parse(f'{RETURNS}/{path.name}', parse_return)
            findings += problems
            if item is not None:
                items.append(item)
        return items, findings

    @property
    def service(self):
        """The folder that holds this spec's `docs/specs/` (a service root in a monorepo, else the repository)."""
        nested = self.dir.parent.name == 'specs' and self.dir.parent.parent.name == 'docs'
        return self.dir.parents[2] if nested else self.repo.root

    @cached_property
    def config(self):
        """The repository config that applies to this spec (load_config), the service's own before the root's."""
        folders = [self.service] if self.repo.root in self.service.parents else []
        return load_config(self.repo, folders + [self.repo.root])

    def last(self, kind):
        if kind in self.fresh:
            return self.fresh[kind]
        return next((e for e in reversed(self.ledger[0]) if e['kind'] == kind), None)

    def at(self, event):
        """Where a finding about `event` points: its ledger line, or this run."""
        return 'this run' if event.get('fresh') else f'{self.label("ledger.md")}:{event["line"]}'


def fp_matches(recorded, current):
    """A recorded fingerprint (or a prefix of at least FP_MIN hex characters) matches the current one."""
    return bool(recorded and current) and len(recorded) >= FP_MIN and current.startswith(recorded)


def short(fp):
    return (fp or '')[:12] or 'none'


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
