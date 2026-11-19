"""Passive suite judge: pass when the session invoked any expected skill or agent."""
import harness


def judge(case, stream, repo=None, plugin_dir=None):
    expect = set(case.get('expect') or [])
    invoked = stream['skills'] + stream['agents']
    hit = [name for name in invoked if harness.bare(name) in expect]
    first_tools = [call['name'] for call in stream['calls'][:8]]
    summary = ('hit ' + ', '.join(hit)) if hit else ('missed; invoked: ' + (', '.join(invoked) or 'nothing'))
    return {'pass': bool(hit), 'score': 1.0 if hit else 0.0, 'hit': hit, 'skills': stream['skills'],
            'agents': stream['agents'], 'first_tools': first_tools, 'summary': summary}
