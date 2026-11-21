---
name: dispatching-parallel-agents
description: Use in the full workflow, or when the user asks for parallel investigation, to run 2+ independent investigations or tasks with disjoint files concurrently via subagents. In a full-workflow build the batches come from `aidlc next`, driven by build. Not for fast-path implementation (no dispatch). For an error crossing services use debug-parallel.
---

# Dispatching Parallel Agents

**Tier check first.** Dispatch only in full mode or when the user asked for parallel investigation; in lean mode (default) and on the fast path, work in this session. An error crossing services → the `debug-parallel` command. Executing a written plan → `tea-sdlc:build`.

## Full-workflow build: batches come from `aidlc next`

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" next <f> --json` returns the ready tickets already grouped into batches that share no file (only tickets declaring `Files:` share a batch). One message per batch, one Agent call per ticket: agent = the ticket's `Owner:` (else the domain agent for its files), owned files = its `Files:`, prompt = the implementer template of `tea-sdlc:build`. Never move a ticket to an earlier batch or merge batches; a ticket that needs another ticket's file is a plan change (edit `tickets.md`, rerun `aidlc check <f> --to planned`).

## Parallel investigation

Use when 2+ problems are independent: different subsystems or test files with different root causes, understandable without each other, no shared files or resources. Investigate together instead when failures may share a cause, the system state must be seen whole, or you do not yet know what is broken.

1. Group failures by independent domain; one agent per domain.
2. Each prompt is self-contained (non-fork subagents do not see this conversation): role; context with the pasted error messages and test names; one narrow scope (a test file or subsystem); the goal; constraints (files it may change, e.g. tests only, never just raise timeouts); return format (root cause, changes, evidence).
3. All Agent calls in ONE message so they run concurrently: a domain agent from `${CLAUDE_PLUGIN_ROOT}/rules/agents.md` as `tea-sdlc:<agent>`, or `general-purpose`. Set `model` (`haiku`/`sonnet`/`opus`/`fable`) only when a dispatch is materially lighter or heavier than the agent's normal job; say why when not obvious.
4. On return: read each summary, check the agents did not edit the same code, run the full suite, spot-check the changes (agents make systematic errors), then integrate.
