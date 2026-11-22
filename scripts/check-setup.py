#!/usr/bin/env python3
"""Structural checks for the AegisOps-Harness plugin: manifests, frontmatter, bundled path
references and the SessionStart hook. No model, network or plugin-runtime calls.
When --project (default: the current directory) is a git repository other than the
plugin, also warns about repository setup that hides instructions or docs from
worktrees and agents. Those warnings never change the status."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

MODELS = {'haiku', 'sonnet', 'opus', 'fable', 'inherit'}
EFFORTS = {'low', 'medium', 'high', 'xhigh', 'max'}
BUNDLED_DIRS = ('rules', 'references', 'skills', 'templates', 'scripts', 'hooks', 'commands', 'agents', 'tools')
# Prose that the plugin authors and loads; vendored/synced skill docs are excluded.
SCANNED = ('agents', 'commands', 'rules', 'references', 'skills', 'hooks', 'scripts')
EXCLUDED = ('skills/synced/',)
# ~/.claude paths that legitimately belong to the user's install, not the plugin.
USER_PATHS = ('settings.json', 'CLAUDE.md', 'state/', 'projects/', 'agent-memory/')
BUNDLED_REF = re.compile(r'(?<![\w./~-])(\$\{CLAUDE_PLUGIN_ROOT\}/)?((?:%s)/[A-Za-z0-9_./-]+\.(?:md|py|sh|json|mjs))'
                         % '|'.join(BUNDLED_DIRS))
USER_REF = re.compile(r'~/\.claude/([A-Za-z0-9_./-]+)')
FRONTMATTER = re.compile(r'\A---\r?\n(.*?)\r?\n---', re.S)
INSTRUCTION_FILES = ('CLAUDE.md', '.claude/CLAUDE.md')
DOC_PROBES = ('docs/README.md', 'docs/specs/x/README.md', 'docs/plans/x.md')


def git(args, cwd):
    try:
        return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, '', '')


def project_warnings(project):
    """Return (repo top-level or None, warnings) for the git repository containing `project`."""
    top = git(['rev-parse', '--show-toplevel'], project)
    if top.returncode:
        return None, []
    top = Path(top.stdout.strip()).resolve()
    warnings = []
    for name in INSTRUCTION_FILES:
        blob = git(['show', 'HEAD:' + name], top)
        if blob.returncode == 0 and not blob.stdout.strip():
            warnings.append('%s is tracked but empty at HEAD; worktrees and fresh checkouts get no project '
                            'instructions. Commit its content.' % name)
    rules = [p for p in (top / '.claude' / 'rules').rglob('*') if p.is_file()]
    if rules and not git(['ls-files', '--', '.claude/rules'], top).stdout.strip():
        probe = rules[0].relative_to(top).as_posix()
        state = 'ignored' if git(['check-ignore', '-q', '--', probe], top).returncode == 0 else 'untracked'
        warnings.append('.claude/rules/ is %s; its rules exist only in this checkout, not in worktrees or '
                        'clones. Track them, or cite their absolute paths in dispatch prompts.' % state)
    ignored = git(['check-ignore', '--', *DOC_PROBES], top).stdout.split()
    if ignored:
        warnings.append('docs/ paths are ignored by git (%s), e.g. by core.excludesFile; specs and living docs '
                        'will not be tracked. Add !/docs/ and !/docs/** to the repo .gitignore.' % ', '.join(ignored))
    return top, warnings


def scanned_files(root):
    for directory in SCANNED:
        for path in (root / directory).rglob('*'):
            rel = path.relative_to(root).as_posix()
            if path.is_file() and path.suffix in {'.md', '.py', '.sh', ''} and not rel.startswith(EXCLUDED) \
                    and '__pycache__' not in rel:
                yield path, rel
    yield root / 'README.md', 'README.md'


def frontmatter(path):
    match = FRONTMATTER.match(path.read_text())
    return match.group(1) if match else None


def simple_fields(block):
    return {k.strip(): v.strip().strip('"\'') for k, v in
            (line.split(':', 1) for line in block.splitlines() if ':' in line and not line.startswith((' ', '-')))}


def yaml_errors(paths):
    ruby = shutil.which('ruby')
    if not ruby:
        return None
    script = r'''
require 'yaml'; require 'json'
errors = []
JSON.parse(STDIN.read).each do |path|
  begin
    m = File.read(path).match(/\A---\r?\n(.*?)\r?\n---/m)
    raise 'missing frontmatter' unless m
    data = YAML.safe_load(m[1])
    raise 'expected mapping' unless data.is_a?(Hash)
    raise 'skills must be a YAML list' if data.key?('skills') && !data['skills'].is_a?(Array)
  rescue => e
    errors << path + ': ' + e.message.lines.first.strip
  end
end
puts JSON.generate(errors)
'''
    result = subprocess.run([ruby, '-e', script], input=json.dumps([str(p) for p in paths]),
                            capture_output=True, text=True, timeout=30)
    return ['YAML diagnostics failed: exit %d' % result.returncode] if result.returncode else json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--project', type=Path, default=Path.cwd(),
                        help='target project whose git setup is checked (warnings only)')
    args = parser.parse_args()
    root = args.root.resolve()
    errors, warnings = [], []

    # Target project git setup (warnings only; skipped for the plugin's own repository)
    project, project_warn = project_warnings(args.project)
    if project == root:
        project = None
    elif project:
        warnings.extend(project_warn)

    # Manifests
    manifests = {}
    for name in ('plugin.json', 'marketplace.json'):
        try:
            manifests[name] = json.loads((root / '.claude-plugin' / name).read_text())
        except (OSError, ValueError) as error:
            errors.append('.claude-plugin/%s unreadable: %s' % (name, type(error).__name__))
    map_script = root / 'scripts' / 'map.py'
    if map_script.is_file():  # HOW-IT-WORKS.md is generated; stale or a skill in no phase is an error
        result = subprocess.run([sys.executable, str(map_script), '--check'], capture_output=True, text=True,
                                timeout=60, cwd=str(root))
        if result.returncode != 0:
            errors.append((result.stderr.strip() or 'scripts/map.py --check failed').splitlines()[-1])
    plugin = manifests.get('plugin.json', {})
    if plugin and not re.fullmatch(r'\d+\.\d+\.\d+', str(plugin.get('version', ''))):
        errors.append('plugin.json version must be semver')
    for entry in manifests.get('marketplace.json', {}).get('plugins', []):
        if 'version' in entry and entry['version'] != plugin.get('version'):
            errors.append('marketplace.json version differs from plugin.json')
    try:
        hooks = json.loads((root / 'hooks/hooks.json').read_text())
        for command in re.findall(r'\$\{CLAUDE_PLUGIN_ROOT\}/([^"\s]+)', json.dumps(hooks)):
            if not (root / command.replace('\\', '')).exists():
                errors.append('hooks.json references missing ' + command)
    except (OSError, ValueError) as error:
        errors.append('hooks/hooks.json unreadable: ' + type(error).__name__)

    # Frontmatter
    agents = sorted((root / 'agents').glob('*.md'))
    skills = sorted((root / 'skills').glob('*/SKILL.md'))
    commands = sorted((root / 'commands').glob('*.md'))
    for path in agents + skills + commands:
        block = frontmatter(path)
        rel = path.relative_to(root).as_posix()
        if block is None:
            errors.append(rel + ': missing frontmatter')
            continue
        fields = simple_fields(block)
        if 'description' not in fields:
            errors.append(rel + ': missing description')
        if path in agents + skills and 'name' not in fields:
            errors.append(rel + ': missing name')
        if path in agents:
            if fields.get('model') not in MODELS:
                errors.append(rel + ': model must be a family alias (latest release), got %r' % fields.get('model'))
            if fields.get('effort', 'high') not in EFFORTS:
                errors.append(rel + ': unsupported effort %r' % fields.get('effort'))
    parsed = yaml_errors(agents + skills + commands)
    if parsed is None:
        warnings.append('Ruby unavailable; full YAML parsing skipped.')
    else:
        errors.extend(e.replace(str(root) + '/', '') for e in parsed)

    # Path references
    checked = 0
    for path, rel in scanned_files(root):
        text = path.read_text(errors='replace')
        for match in USER_REF.finditer(text):
            target = match[1].rstrip('.')
            if not target.startswith(USER_PATHS):
                errors.append('%s: user-home path ~/.claude/%s — bundled files must be plugin-relative' % (rel, target))
        # ${CLAUDE_PLUGIN_ROOT} is substituted only in agent/command bodies and SKILL.md files.
        substituted = rel.startswith(('agents/', 'commands/')) or path.name == 'SKILL.md'
        if '${CLAUDE_PLUGIN_ROOT}' in text and not substituted and rel.endswith('.md') and rel != 'README.md':
            errors.append('%s: ${CLAUDE_PLUGIN_ROOT} is not substituted in Read-loaded files; use plugin-relative paths' % rel)
        for match in BUNDLED_REF.finditer(text):
            prefixed, target = bool(match[1]), match[2].rstrip('.')
            if re.search(r'[<>{}*]|YYYY|NNNN', target):
                continue
            checked += 1
            if prefixed:
                if not (root / target).exists():
                    errors.append('%s: ${CLAUDE_PLUGIN_ROOT}/%s does not exist at the plugin root' % (rel, target))
            elif not (root / target).exists() and not (path.parent / target).exists():
                errors.append('%s: missing bundled reference %s' % (rel, target))

    # Every bundled file must ship: a personal core.excludesFile pattern (e.g. `cdk*`) can keep one out of every
    # release while it still works in the author's checkout. Only meaningful when the root is its own repository.
    top = git(['rev-parse', '--show-toplevel'], root)
    if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root:
        shipped = [p.relative_to(root).as_posix() for d in SCANNED + ('.claude-plugin',) for p in (root / d).rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts and p.name != '.DS_Store'
                   and not p.relative_to(root).as_posix().startswith(EXCLUDED)]
        ignored = git(['check-ignore', '--no-index', '--', *shipped], root).stdout.split() if shipped else []
        for rel in ignored:
            errors.append('%s is ignored by git (check `git check-ignore -v %s`), so it never ships; add a `!` '
                          'exception to the repository .gitignore' % (rel, rel))

    # Hooks compile, and every skill/command name the autopilot can point the session to exists in the plugin.
    for path in sorted((root / 'hooks').glob('*.py')):
        try:
            compile(path.read_text(), str(path), 'exec')
        except (SyntaxError, ValueError, OSError) as error:
            errors.append('%s does not compile: %s' % (path.relative_to(root).as_posix(), error))
    invocable = {p.parent.name for p in skills} | {p.stem for p in commands}
    referenced = set()
    for path, rel in scanned_files(root):
        for name in re.findall(r'(?<![\w-])aegisops-harness:([a-z0-9][a-z0-9-]*[a-z0-9])', path.read_text(errors='replace')):
            referenced.add((name, rel))
    # No passive activation: the model may never load an AegisOps-Harness skill or command on its own.
    for path in list(skills) + list(commands):
        head = path.read_text(errors='replace')[:1500]
        if not re.search(r'^disable-model-invocation:\s*true\s*$', head, re.M):
            errors.append('%s: needs disable-model-invocation: true (AegisOps-Harness runs only from slash commands)'
                          % path.relative_to(root).as_posix())
    agent_names = {p.stem for p in agents}
    for name, rel in sorted(referenced):
        if name not in invocable | agent_names and name != 'aegisops-harness':
            errors.append('%s: aegisops-harness:%s is not a skill, command or agent of this plugin' % (rel, name))

    # Plugin agents are registered as `aegisops-harness:<name>`: a bare name sent as subagent_type fails with
    # "Agent type '<name>' not found". Text the model reads must name them with the prefix.
    if agent_names:
        bare = re.compile(r'(?<![:\w/.-])(%s)(?![\w-]|\.md)' % '|'.join(map(re.escape, sorted(agent_names))))
        for path, rel in scanned_files(root):
            if not (rel.endswith('.md') or rel == 'hooks/autopilot.py'):
                continue
            for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
                if rel.startswith('agents/') and line.startswith('name:'):
                    continue
                for match in bare.finditer(line):
                    errors.append('%s:%d: agent %s must be named aegisops-harness:%s (plugin agents are namespaced)'
                                  % (rel, number, match[1], match[1]))

    # SessionStart hook contract
    hook = root / 'hooks/session-start'
    try:
        # A scratch HOME: the hook prunes old gate state in the user state directory, which a check must never touch.
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run(['/bin/bash', str(hook)], input='{}', capture_output=True, text=True, timeout=5,
                                    cwd=root, env={**os.environ, 'HOME': home})
        payload = json.loads(result.stdout)
        context = payload['hookSpecificOutput']
        if result.returncode or context['hookEventName'] != 'SessionStart' or not isinstance(context['additionalContext'], str):
            errors.append('SessionStart output contract failed.')
        if len(result.stdout.encode('utf-8')) > 49152:
            errors.append('SessionStart exceeded the 48 KiB output budget.')
        if 'systemMessage' in payload:
            warnings.append(payload['systemMessage'])
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
        errors.append('SessionStart could not emit valid bounded JSON within five seconds.')

    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'version': plugin.get('version'),
                      'agents': len(agents), 'skills': len(skills), 'commands': len(commands),
                      'bundled_references_checked': checked, 'project': str(project) if project else None,
                      # Always-on cost: the bootstrap injected into every session (rules/ is only read on demand).
                      'bootstrap_bytes': (root / 'skills/session-bootstrap/SKILL.md').stat().st_size,
                      'errors': errors, 'warnings': warnings,
                      'limits': 'Structure only; no model/API run or behavioral review.'}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
