"""Passive suite judge. tea-sdlc starts only from slash commands, so a natural prompt must load nothing of it:
a case with "silent": true passes when the session invoked no tea-sdlc skill, command or agent. A case with
"expect" passes when the session invoked any expected skill or agent (kept for command cases)."""
import harness


def judge(case, stream, repo=None, plugin_dir=None):
    invoked = stream['skills'] + stream['agents']
    first_tools = [call['name'] for call in stream['calls'][:8]]
    if case.get('silent'):
        ours = [name for name in invoked if str(name).startswith('tea-sdlc:')]
        summary = ('silent' if not ours else 'activated: ' + ', '.join(ours))
        return {'pass': not ours, 'score': 0.0 if ours else 1.0, 'hit': ours, 'skills': stream['skills'],
                'agents': stream['agents'], 'first_tools': first_tools, 'summary': summary}
    expect = set(case.get('expect') or [])
    hit = [name for name in invoked if harness.bare(name) in expect]
    summary = ('hit ' + ', '.join(hit)) if hit else ('missed; invoked: ' + (', '.join(invoked) or 'nothing'))
    return {'pass': bool(hit), 'score': 1.0 if hit else 0.0, 'hit': hit, 'skills': stream['skills'],
            'agents': stream['agents'], 'first_tools': first_tools, 'summary': summary}
