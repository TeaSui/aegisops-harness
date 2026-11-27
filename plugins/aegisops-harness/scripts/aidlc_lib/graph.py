"""The ticket graph: dependencies, conflict-free batches and `files:` globs."""
from aidlc_lib.core import *  # noqa: F401,F403
from aidlc_lib.parsers import *  # noqa: F401,F403

# --------------------------------------------------------------------------------------------- plan graph and globs

def _glob_regex(pattern):
    out, i = '', 0
    while i < len(pattern):
        if pattern.startswith('**/', i):
            out, i = out + '(?:.*/)?', i + 3
        elif pattern.startswith('**', i):
            out, i = out + '.*', i + 2
        else:
            out += {'*': '[^/]*', '?': '[^/]'}.get(pattern[i], re.escape(pattern[i]))
            i += 1
    return re.compile(out + r'\Z')


def overlaps(a, b):
    """Whether two plan `files` entries can name the same file (two globs: conservative, by literal prefix)."""
    if a == b or b.startswith(a.rstrip('/') + '/') or a.startswith(b.rstrip('/') + '/'):
        return True
    glob_a, glob_b = ('*' in a or '?' in a), ('*' in b or '?' in b)
    if glob_a and glob_b:
        pa, pb = re.split(r'[*?]', a, maxsplit=1)[0], re.split(r'[*?]', b, maxsplit=1)[0]
        return pa.startswith(pb) or pb.startswith(pa)
    if glob_a or glob_b:
        pattern, path = (a, b) if glob_a else (b, a)
        return bool(_glob_regex(pattern).match(path))
    return False


def _graph(tasks):
    ids = {t['id'] for t in tasks}
    graph = {}
    for task in tasks:
        graph.setdefault(task['id'], [d for d in task['depends'] if d in ids])
    return graph


def _cycles(graph):
    state, stack, found = {}, [], []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for dep in graph[node]:
            if state.get(dep) == 1:
                cycle = stack[stack.index(dep):] + [dep]
                if not any(set(cycle) == set(c) for c in found):
                    found.append(cycle)
            elif dep not in state:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in graph:
        if node not in state:
            visit(node)
    return found


def _ancestors(graph):
    result = {}
    for node in graph:
        seen, todo = set(), list(graph[node])
        while todo:
            dep = todo.pop()
            if dep not in seen:
                seen.add(dep)
                todo.extend(graph.get(dep, []))
        result[node] = seen
    return result


def plan_findings(tasks, req_ids, label):
    """The planned gate on parsed tasks; req_ids None skips the coverage checks."""
    findings, seen = [], {}
    if not tasks:
        if label.endswith('plan.md'):
            return [fail(f'{label}: defines no task ("- [ ] T1: <title>" with indented fields)')]
        return [fail(f'{label}: defines no ticket ("## T1: <title>" with Blocked by:, Covers:, criteria)')]
    for task in tasks:
        where, tid = f'{label}:{task["line"]}', task['id']
        if tid in seen:
            findings.append(fail(f'{where}: duplicate task {tid} (also line {seen[tid]})'))
        seen.setdefault(tid, task['line'])
        if not task.get('ticket'):  # legacy plan.md: every task names its owner and files
            if not task['owner']:
                findings.append(fail(f'{where}: {tid} has no owner'))
            if not task['files']:
                findings.append(fail(f'{where}: {tid} has no files'))
        if not task['covers_given']:
            findings.append(fail(f'{where}: {tid} covers nothing (add "covers: <IDs>" or "covers: none — <reason>")'))
        elif task['covers_none'] == '':
            findings.append(fail(f'{where}: {tid} "covers: none" needs a reason'))
        elif task['covers_none'] is None and not task['covers']:
            findings.append(fail(f'{where}: {tid} covers lists no requirement ID'))
        for rid in task['covers']:
            if req_ids is not None and rid not in req_ids:
                findings.append(fail(f'{where}: {tid} covers unknown requirement {rid}'))
        for dep in task['depends']:
            if dep not in seen and dep not in {t['id'] for t in tasks}:
                findings.append(fail(f'{where}: {tid} depends on unknown {dep}'))
    covered = {rid for task in tasks for rid in task['covers']}
    for rid in req_ids or []:
        if rid not in covered:
            findings.append(fail(f'{label}: requirement {rid} is not covered by any task'))
    graph = _graph(tasks)
    for cycle in _cycles(graph):
        findings.append(fail(f'{label}: dependency cycle {" → ".join(cycle)}'))
    findings += _conflicts(tasks, graph, label)
    return findings


def _conflicts(tasks, graph, label):
    findings, ancestors = [], _ancestors(graph)
    unique, seen = [], set()
    for task in tasks:  # a duplicate ID is reported elsewhere; compare its first definition only
        if task['id'] not in seen:
            seen.add(task['id'])
            unique.append(task)
    for i, first in enumerate(unique):
        for second in unique[i + 1:]:
            if first['id'] in ancestors[second['id']] or second['id'] in ancestors[first['id']]:
                continue
            shared = sorted({f'{a}' if a == b else f'{a} ~ {b}'
                             for a in first['files'] for b in second['files'] if overlaps(a, b)})
            if shared:
                findings.append(fail(f'{label}:{second["line"]}: {first["id"]} and {second["id"]} may run at the same '
                                     f'time but share {", ".join(shared)} (add a dependency or split the files)'))
    return findings


def batches(tasks):
    """Open tasks whose dependencies are done, greedily grouped so that a batch shares no file."""
    done = {t['id'] for t in tasks if t['done']}
    ready = [t for t in tasks if not t['done'] and all(d in done for d in t['depends'])]
    groups = []
    for task in ready:
        if not task['files']:  # no declared files: nothing proves it conflict-free, so it runs alone
            groups.append([task])
            continue
        for group in groups:
            if all(other['files'] for other in group) and not any(
                    overlaps(a, b) for other in group for a in other['files'] for b in task['files']):
                group.append(task)
                break
        else:
            groups.append([task])
    return groups


__all__ = [name for name in dir() if not name.startswith('__')]  # private names too: the layers above use them
