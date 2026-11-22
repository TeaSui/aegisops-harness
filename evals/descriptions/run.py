#!/usr/bin/env python3
"""Description lint for skills/*/SKILL.md and commands/*.md: the menu text a person reads when choosing a command.

Deterministic and free. Per file:
  - frontmatter present and valid YAML (the same Ruby YAML check as scripts/check-setup.py; skipped with a warning
    when Ruby is missing), a `description`, and for skills a `name` equal to the folder name;
  - `disable-model-invocation: true` (AegisOps-Harness runs only from slash commands; the description is menu text, not a
    trigger), with a warning when it still reads like a model trigger ("when the user says …");
  - its length is within bounds (too short cannot carry triggers; too long is truncated in the skill listing).
Across files, a collision check: TF-IDF cosine similarity between every pair of descriptions (stdlib implementation).
Pairs above the threshold are collisions; accepted ones live in allowlist.json with a reason. Exit 1 on any lint
error or on a collision that is not allowlisted. Allowlisted pairs more than STALE_MARGIN below the threshold are
reported as stale (a warning).
"""
import argparse
import collections
import importlib.util
import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MIN_LEN = 80
MAX_LEN = 1024          # the Agent Skills limit for `description`
WARN_LEN = 700          # long descriptions crowd the skill listing every session pays for
THRESHOLD = 0.25
STALE_MARGIN = 0.05     # an allowlisted pair is stale only below threshold - margin
TRIGGER = re.compile(r'\b(use|load|run|invoke)\b(?:\s+[\w/-]+){0,3}?\s+(when|whenever|before|after|for|if|in|first|to|'
                     r'once|only|right)\b|\btriggers? on\b', re.I)
STOPWORDS = frozenset('''a an and are as at be before by can do does for from has have how i if in into is it its
of on or that the their them then this to use used uses using when whenever which with without you your not no
only each any all also one so than what who will while via per e g eg etc aegisops harness follows routing tiers hook gates
triggers'''.split())
TOKEN = re.compile(r'[a-z][a-z0-9+#.-]*[a-z0-9+#]|[a-z]')


def load_check_setup(root):
    """scripts/check-setup.py as a module (its file name has a hyphen); None when it cannot be loaded."""
    try:
        spec = importlib.util.spec_from_file_location('aegisops_harness_check_setup_eval', root / 'scripts' / 'check-setup.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


FRONTMATTER = re.compile(r'\A---\r?\n(.*?)\r?\n---', re.S)


def frontmatter_block(text):
    match = FRONTMATTER.match(text)
    return match.group(1) if match else None


def parse_fields(block):
    """Top-level scalar fields of a frontmatter block: plain, quoted, and | or > block scalars."""
    fields, lines, index = {}, block.splitlines(), 0
    while index < len(lines):
        line = lines[index]
        index += 1
        match = re.match(r'^([A-Za-z_][\w-]*):\s*(.*)$', line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value[:1] in ('|', '>'):
            body = []
            while index < len(lines) and (not lines[index].strip() or lines[index][:1] in (' ', '\t')):
                body.append(lines[index].strip())
                index += 1
            joiner = '\n' if value[0] == '|' else ' '
            value = joiner.join(body).strip()
            if value and joiner == ' ':
                value = re.sub(r'\s+', ' ', value)
        elif value[:1] in ('"', "'") and value[-1:] == value[:1] and len(value) > 1:
            value = value[1:-1]
        else:
            value = value.split(' #')[0].strip()
        fields[key] = value
    return fields


def collect(root):
    items = []
    for path in sorted((root / 'skills').glob('*/SKILL.md')):
        items.append(('skill', path.parent.name, path))
    for path in sorted((root / 'commands').glob('*.md')):
        items.append(('command', path.stem, path))
    return items


def lint(root, items, check_setup=None):
    errors, warnings, descriptions = [], [], {}
    for kind, name, path in items:
        rel = path.relative_to(root).as_posix()
        block = frontmatter_block(path.read_text(errors='replace'))
        if block is None:
            errors.append(rel + ': missing frontmatter')
            continue
        fields = parse_fields(block)
        description = fields.get('description', '').strip()
        if not description:
            errors.append(rel + ': missing description')
            continue
        if kind == 'skill' and fields.get('name') != name:
            errors.append('%s: name %r does not match the folder %r' % (rel, fields.get('name'), name))
        flat = re.sub(r'\s+', ' ', description)
        if len(flat) < MIN_LEN:
            errors.append('%s: description is %d chars (min %d)' % (rel, len(flat), MIN_LEN))
        if len(flat) > MAX_LEN:
            errors.append('%s: description is %d chars (max %d)' % (rel, len(flat), MAX_LEN))
        elif len(flat) > WARN_LEN:
            warnings.append('%s: description is %d chars (over %d)' % (rel, len(flat), WARN_LEN))
        if not re.search(r'(?m)^disable-model-invocation:\s*true\s*$', block):
            errors.append(rel + ': needs disable-model-invocation: true (AegisOps-Harness runs only from slash commands)')
        if TRIGGER.search(flat) and re.search(r'\b(user says|user asks|when the user)\b', flat, re.I):
            warnings.append(rel + ': description reads as a model trigger; say what it does and which command runs it')
        descriptions[name] = flat
    if check_setup is not None and hasattr(check_setup, 'yaml_errors'):
        parsed = check_setup.yaml_errors([path for _, _, path in items])
        if parsed is None:
            warnings.append('Ruby unavailable; full YAML parsing skipped.')
        else:
            errors.extend(e.replace(str(root) + '/', '') for e in parsed)
    else:
        warnings.append('scripts/check-setup.py could not be loaded; full YAML parsing skipped.')
    return errors, warnings, descriptions


def tokens(text):
    words = []
    for word in TOKEN.findall(text.lower()):
        word = word.strip('.-')
        if len(word) < 2 or word in STOPWORDS:
            continue
        if len(word) > 4 and word.endswith('ies'):
            word = word[:-3] + 'y'
        elif len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
            word = word[:-1]
        words.append(word)
    return words


def tfidf_vectors(texts):
    """Sublinear TF times smoothed IDF, L2-normalised. `texts` maps name -> text."""
    docs = {name: collections.Counter(tokens(text)) for name, text in texts.items()}
    df = collections.Counter(term for counts in docs.values() for term in counts)
    n = len(docs)
    vectors = {}
    for name, counts in docs.items():
        vec = {term: (1 + math.log(tf)) * (math.log((1 + n) / (1 + df[term])) + 1) for term, tf in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors[name] = {term: v / norm for term, v in vec.items()}
    return vectors


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(term, 0.0) for term, v in a.items())


def similar_pairs(texts, threshold):
    vectors = tfidf_vectors(texts)
    names = sorted(vectors)
    pairs = []
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            score = cosine(vectors[left], vectors[right])
            if score >= threshold:
                shared = sorted(set(vectors[left]) & set(vectors[right]),
                                key=lambda t: -(vectors[left][t] * vectors[right][t]))[:6]
                pairs.append({'pair': [left, right], 'score': round(score, 3), 'shared_terms': shared})
    return sorted(pairs, key=lambda p: -p['score'])


def load_allowlist(path):
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except OSError:
        return {}
    return {tuple(sorted(entry['pair'])): entry.get('reason', '') for entry in data.get('pairs', [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=pathlib.Path, default=ROOT)
    parser.add_argument('--allowlist', type=pathlib.Path, default=HERE / 'allowlist.json')
    parser.add_argument('--threshold', type=float, default=THRESHOLD)
    parser.add_argument('--top', type=int, default=0, help='also print the N most similar pairs, collisions or not')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    items = collect(root)
    errors, warnings, texts = lint(root, items, load_check_setup(root))
    pairs = similar_pairs(texts, args.threshold)
    allow = load_allowlist(args.allowlist)
    collisions = [p for p in pairs if tuple(sorted(p['pair'])) not in allow]
    accepted = [dict(p, reason=allow[tuple(sorted(p['pair']))]) for p in pairs if tuple(sorted(p['pair'])) in allow]
    # Hysteresis: an accepted pair hovering just under the threshold is not stale (descriptions get small edits).
    near = {tuple(sorted(p['pair'])) for p in similar_pairs(texts, max(0.0, args.threshold - STALE_MARGIN))}
    stale = [list(pair) for pair in allow if pair not in near]
    result = {'status': 'PASS' if not errors and not collisions else 'FAIL', 'files': len(items),
              'threshold': args.threshold, 'errors': errors, 'warnings': warnings, 'collisions': collisions,
              'allowlisted': accepted, 'stale_allowlist': stale}
    if args.top:
        result['top'] = similar_pairs(texts, 0.0)[:args.top]
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('%d descriptions (%d skills, %d commands), collision threshold %.2f'
              % (len(items), sum(k == 'skill' for k, _, _ in items), sum(k == 'command' for k, _, _ in items),
                 args.threshold))
        for error in errors:
            print('ERROR     ' + error)
        for warning in warnings:
            print('warning   ' + warning)
        for p in collisions:
            print('COLLISION %.3f %s <> %s  shared: %s' % (p['score'], p['pair'][0], p['pair'][1],
                                                            ', '.join(p['shared_terms'])))
        for p in accepted:
            print('allowed   %.3f %s <> %s  (%s)' % (p['score'], p['pair'][0], p['pair'][1], p['reason']))
        for pair in stale:
            print('stale     allowlist entry %s <> %s no longer collides; remove it' % tuple(pair))
        for p in result.get('top', []):
            print('top       %.3f %s <> %s' % (p['score'], p['pair'][0], p['pair'][1]))
        if collisions:
            print('\nNew collisions: make the descriptions say what distinguishes them (when to use which), or add the '
                  'pair to %s with a reason.' % args.allowlist.name)
        print(result['status'])
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
