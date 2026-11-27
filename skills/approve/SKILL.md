---
name: approve
description: Record your approval of a spec as it is written now (/aegisops-harness:approve <slug>). The approval is bound to the text of spec.md, so a later edit needs a new one, and only a command the user types can record it.
argument-hint: "<spec slug>"
disable-model-invocation: true
---

# Approve a spec

The user typed this command: that is their approval of the spec named in `$ARGUMENTS`, as its text is now. Nothing else approves a spec: not an "ok" to a question you asked, not your reading of the conversation.

1. No argument, or a slug `aidlc status` does not know → show the specs at `proposed` and stop. Never pick one.
2. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" approve <slug>`. The evidence guard lets it through because the user's own command is the latest in this session; run it now, not after other commands.
3. Report what was recorded: the approver, the first 12 characters of the spec hash, and that an edit to spec.md from now on needs a new approval.
4. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/aidlc.py" advance <slug> accepted`. Fix what the gate lists; a fix that changes spec.md needs the user to approve again. If a `/aegisops-harness:aidlc` run was waiting for this approval, continue it (`${CLAUDE_PLUGIN_ROOT}/skills/aidlc/SKILL.md`, at the spec's stage); otherwise stop and name the next command.

A delegated request ("do not ask", "end to end", `Status: ready-for-agent`) does not use this command: `/aegisops-harness:spec` records `aidlc approve <slug> --delegated`, which says that nobody read the spec.
