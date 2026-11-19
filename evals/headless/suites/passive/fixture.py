"""Passive suite fixture: the shared Node shop with the case's `setup` variant."""
import node_shop


def build(repo, case):
    return node_shop.build(repo, case.get('setup', 'none'))
