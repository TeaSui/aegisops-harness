#!/usr/bin/env python3
"""Contract gate: deterministic structure + compatibility check for a spec's `contracts/` folder.

Usage: python3 scripts/check-contract.py <spec-dir> [--base <authoritative-openapi-file>] [--repo <repo-root>]
       python3 scripts/check-contract.py --scan <repo-root>   # every active spec (proposed/accepted) with contract: external

The spec's README.md frontmatter decides whether the gate applies:
  contract: external | none     (default: external when contracts/ exists, otherwise none)
  contract_source: <path>       authoritative OpenAPI file, relative to the repo root (else auto-detected)
  breaking: approved            a breaking change against the authoritative source was explicitly approved

Checks (stdlib only; YAML is parsed with PyYAML when installed, else with ruby, else a WARN says it was not parsed):
  - external contract => contracts/ exists and is non-empty, files parse
  - OpenAPI (full document or delta): operationId present and unique, a 2xx response, an error response that uses the
    {error:{code,message}} envelope or a *Error* component, every local $ref resolves
  - compatibility vs the authoritative source for operations present in both: removed success response,
    removed/retyped response property, new required request property or parameter => breaking
Exit 0 = pass (warnings allowed), 1 = findings, 2 = usage error. It checks structure, not design quality.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

try:
    import yaml  # optional
except ImportError:
    yaml = None

METHODS = ('get', 'put', 'post', 'delete', 'patch', 'head', 'options')
BASE_GUESSES = ('api/openapi.yaml', 'api/openapi.yml', 'api/openapi.json', 'openapi.yaml', 'openapi.yml',
                'openapi.json', 'src/main/resources/openapi.yaml', 'src/main/resources/api/openapi.yaml')


def frontmatter(readme):
    try:
        text = readme.read_text()
    except OSError:
        return {}
    match = re.match(r'---\s*\n(.*?)\n---', text, re.S)
    data = {}
    for line in (match.group(1).split('\n') if match else []):
        if ':' in line and not line.startswith((' ', '\t', '#')):
            key, _, value = line.partition(':')
            data[key.strip()] = value.split('#')[0].strip()
    return data


RUBY_YAML = ("require 'yaml'; require 'json'; require 'date'; s = File.read(ARGV[0]); "
             "begin; d = YAML.safe_load(s, permitted_classes: [Date, Time], aliases: true); "
             "rescue ArgumentError; d = YAML.safe_load(s, [Date, Time], [], true); end; puts JSON.generate(d)")


def load(path):
    text = path.read_text()
    if path.suffix == '.json':
        return json.loads(text), None
    if yaml is not None:
        return yaml.safe_load(text), None
    ruby = shutil.which('ruby')
    if ruby:  # no PyYAML: ruby ships with macOS and most CI images
        proc = subprocess.run([ruby, '-e', RUBY_YAML, str(path)], capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            lines = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
            raise ValueError(lines[0][:300] if lines else 'YAML parse error')
        return json.loads(proc.stdout), None
    return None, 'neither PyYAML nor ruby is available: YAML not parsed in depth'


def resolve(doc, node, depth=0):
    while isinstance(node, dict) and '$ref' in node and depth < 8:
        ref = node['$ref']
        if not ref.startswith('#/'):
            return {}
        cur = doc
        for part in ref[2:].split('/'):
            cur = cur.get(part.replace('~1', '/').replace('~0', '~'), {}) if isinstance(cur, dict) else {}
        node, depth = cur, depth + 1
    return node


def refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == '$ref' and isinstance(value, str):
                yield value
            else:
                yield from refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from refs(value)


def operations(doc):
    out = {}
    for path, item in (doc.get('paths') or {}).items():
        for method in METHODS:
            if isinstance(item, dict) and isinstance(item.get(method), dict):
                out[(method, path)] = item[method]
    return out


def props(doc, schema, depth=0):
    """{name: (type, required)} for the top-level object properties of a schema (allOf merged)."""
    schema = resolve(doc, schema)
    if not isinstance(schema, dict) or depth > 4:
        return {}
    result = {}
    for part in schema.get('allOf', []):
        result.update(props(doc, part, depth + 1))
    required = set(schema.get('required', []))
    for name, sub in (schema.get('properties') or {}).items():
        sub = resolve(doc, sub)
        result[name] = (sub.get('type') if isinstance(sub, dict) else None, name in required)
    return result


def json_schema(content):
    for media in (content or {}).values():
        if isinstance(media, dict) and 'schema' in media:
            return media['schema']
    return None


def is_error_response(doc, response):
    response = resolve(doc, response)
    schema = json_schema(response.get('content')) if isinstance(response, dict) else None
    if schema is None:
        return False
    if isinstance(schema, dict) and '$ref' in schema and 'error' in schema['$ref'].lower():
        return True
    p = props(doc, schema)
    if 'error' in p:
        inner = resolve(doc, (resolve(doc, schema).get('properties') or {}).get('error', {}))
        return {'code', 'message'} <= set(props(doc, inner))
    return {'code', 'message'} <= set(p)


def check_openapi(doc, label, findings):
    full = 'openapi' in doc
    if full:
        if not str(doc.get('openapi', '')).startswith('3'):
            findings.append(('FAIL', f'{label}: openapi version must be 3.x'))
        if not (doc.get('info') or {}).get('title') or not (doc.get('info') or {}).get('version'):
            findings.append(('FAIL', f'{label}: info.title and info.version are required'))
    if not doc.get('paths') and not doc.get('components'):
        findings.append(('FAIL', f'{label}: no paths or components'))
    seen = {}
    for (method, path), op in operations(doc).items():
        where = f'{label}: {method.upper()} {path}'
        oid = op.get('operationId')
        if not oid:
            findings.append(('FAIL', f'{where}: operationId is missing'))
        elif oid in seen:
            findings.append(('FAIL', f'{where}: operationId {oid!r} duplicates {seen[oid]}'))
        else:
            seen[oid] = f'{method.upper()} {path}'
        responses = op.get('responses') or {}
        codes = [str(c) for c in responses]
        if not any(c.startswith('2') for c in codes):
            findings.append(('FAIL', f'{where}: no 2xx response'))
        errors = [r for c, r in responses.items() if str(c)[:1] in '45' or str(c) == 'default']
        if not errors or not any(is_error_response(doc, r) for r in errors):
            findings.append(('FAIL', f'{where}: no error response using the {{error:{{code,message}}}} envelope'))
    for ref in set(refs(doc)):
        if ref.startswith('#/') and not resolve(doc, {'$ref': ref}):
            findings.append(('FAIL', f'{label}: unresolved $ref {ref}'))


def breaking(new, base):
    out = []
    base_ops = operations(base)
    for key, op in operations(new).items():
        old = base_ops.get(key)
        if old is None:
            continue
        name = f'{key[0].upper()} {key[1]}'
        old_resp, new_resp = old.get('responses') or {}, op.get('responses') or {}
        for code, response in old_resp.items():
            if str(code).startswith('2') and code not in new_resp:
                out.append(f'{name}: success response {code} removed')
            elif code in new_resp:
                before = props(base, json_schema(resolve(base, response).get('content')) or {})
                after = props(new, json_schema(resolve(new, new_resp[code]).get('content')) or {})
                for field, (typ, _) in before.items():
                    if after and field not in after:
                        out.append(f'{name} {code}: response property {field!r} removed')
                    elif field in after and typ and after[field][0] and after[field][0] != typ:
                        out.append(f'{name} {code}: response property {field!r} changed type {typ} -> {after[field][0]}')
        before = props(base, json_schema(resolve(base, old.get('requestBody') or {}).get('content')) or {})
        after = props(new, json_schema(resolve(new, op.get('requestBody') or {}).get('content')) or {})
        for field, (_, required) in after.items():
            if required and field not in before:
                out.append(f'{name}: new required request property {field!r}')
        old_params = {p.get('name') for p in old.get('parameters', []) if isinstance(p, dict)}
        for param in op.get('parameters', []):
            if isinstance(param, dict) and param.get('required') and param.get('name') not in old_params:
                out.append(f'{name}: new required parameter {param.get("name")!r}')
    return out


def repo_root(spec_dir, given):
    if given:
        return pathlib.Path(given)
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=spec_dir, capture_output=True, text=True)
    return pathlib.Path(top.stdout.strip()) if top.returncode == 0 and top.stdout.strip() else spec_dir


def run(spec_dir, base_arg=None, repo_arg=None):
    spec_dir = pathlib.Path(spec_dir)
    findings = []
    unparsed = False
    meta = frontmatter(spec_dir / 'README.md')
    contracts = spec_dir / 'contracts'
    mode = meta.get('contract') or ('external' if contracts.is_dir() else 'none')
    if mode == 'none':
        return [('OK', f'{spec_dir}: no external contract (contract: none)')]
    files = sorted(p for p in contracts.rglob('*') if p.is_file()) if contracts.is_dir() else []
    if not files:
        return [('FAIL', f'{spec_dir}: contract is external but contracts/ is missing or empty')]
    root = repo_root(spec_dir, repo_arg)
    base_doc = None
    base_path = pathlib.Path(base_arg) if base_arg else None
    if base_path is None and meta.get('contract_source'):
        base_path = root / meta['contract_source']
    if base_path is None:
        base_path = next((root / g for g in BASE_GUESSES if (root / g).is_file()), None)
    if base_path is not None and base_path.is_file():
        try:
            base_doc, warn = load(base_path)
            if warn:
                findings.append(('WARN', f'{base_path}: {warn}'))
        except (ValueError, OSError) as err:
            findings.append(('FAIL', f'{base_path}: authoritative contract does not parse ({err})'))
    for path in files:
        label = str(path.relative_to(spec_dir))
        if path.stat().st_size == 0:
            findings.append(('FAIL', f'{label}: empty file'))
            continue
        if path.suffix not in ('.json', '.yaml', '.yml'):
            findings.append(('OK', f'{label}: non-OpenAPI contract (non-empty); structure not checked'))
            continue
        try:
            doc, warn = load(path)
        except (ValueError, OSError, getattr(yaml, 'YAMLError', ValueError)) as err:
            findings.append(('FAIL', f'{label}: does not parse ({err})'))
            continue
        if warn:
            unparsed = True
            findings.append(('WARN', f'{label}: {warn}'))
            continue
        if not isinstance(doc, dict):
            findings.append(('FAIL', f'{label}: not a mapping'))
            continue
        if 'paths' in doc or 'openapi' in doc or 'components' in doc:
            check_openapi(doc, label, findings)
            if isinstance(base_doc, dict):
                for problem in breaking(doc, base_doc):
                    level = 'WARN' if meta.get('breaking') == 'approved' else 'FAIL'
                    findings.append((level, f'{label}: breaking change vs {base_path.name}: {problem}'
                                     + (' (approved)' if level == 'WARN' else '')))
        else:
            findings.append(('OK', f'{label}: JSON/YAML contract parsed (no OpenAPI structure to check)'))
    if not any(level == 'FAIL' for level, _ in findings):
        findings.append(('OK', f'{spec_dir}: contract gate passed'
                         + (' WITH WARNINGS: some files were not parsed in depth' if unparsed else '')))
    return findings


def active_specs(root):
    """Spec folders under <root>/docs/specs and <root>/*/docs/specs that are active and declare an external contract."""
    root = pathlib.Path(root)
    found = []
    for pattern in ('docs/specs/*/README.md', '*/docs/specs/*/README.md'):
        for readme in sorted(root.glob(pattern)):
            meta = frontmatter(readme)
            if meta.get('contract') == 'external' and meta.get('status', 'proposed') in ('proposed', 'accepted'):
                found.append(readme.parent)
    return found


def scan(root):
    findings = []
    for spec_dir in active_specs(root):
        findings.extend(run(spec_dir, repo_arg=root))
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('spec_dir', nargs='?')
    parser.add_argument('--base')
    parser.add_argument('--repo')
    parser.add_argument('--scan', metavar='REPO_ROOT')
    args = parser.parse_args(argv)
    if args.scan:
        findings = scan(args.scan)
        for level, message in findings:
            print(f'{level} {message}')
        return 1 if any(level == 'FAIL' for level, _ in findings) else 0
    if not args.spec_dir:
        parser.print_usage(sys.stderr)
        return 2
    if not pathlib.Path(args.spec_dir).is_dir():
        print(f'check-contract: {args.spec_dir} is not a directory', file=sys.stderr)
        return 2
    findings = run(args.spec_dir, args.base, args.repo)
    for level, message in findings:
        print(f'{level} {message}')
    return 1 if any(level == 'FAIL' for level, _ in findings) else 0


if __name__ == '__main__':
    sys.exit(main())
