---
description: Score, upgrade and A/B-duel Claude Code assets (agents, commands, rules, skills) of a .claude directory or a plugin checkout with the bundled eval-upgrade tool — static checks with a 0-100 score, LLM upgrade proposals, and champion/challenger arena duels with guarded promotion.
disable-model-invocation: true
argument-hint: "[eval | dashboard | arena <challenger|duel|status|promote|discard> <artifact-id> [rounds] | config] [--target <dir>] [--types agents,commands,rules,skills] [--llm]"
---

# /aegisops-harness:eval-upgrade

Run the bundled tool for `$ARGUMENTS` and report what it printed. With no arguments, run a static evaluation. The tool needs Node ≥20. For anything beyond this page, read `${CLAUDE_PLUGIN_ROOT}/tools/eval-upgrade/README.md`. Hooks are out of scope.

```bash
T="${CLAUDE_PLUGIN_ROOT}/tools/eval-upgrade"
node "$T/bin/run.mjs" [--target <dir>] [--types agents,commands,rules,skills] [--llm] [--json]   # evaluate
node "$T/bin/arena.mjs" challenger <artifact-id>   # generate challenger + task bank
node "$T/bin/arena.mjs" duel <artifact-id> [N]     # N rounds (default 1)
node "$T/bin/arena.mjs" status | promote <artifact-id> | discard <artifact-id>
node "$T/bin/run.mjs" --show-config               # effective settings, state location
node "$T/server.mjs" --open                       # dashboard: start as a background Bash task
```

Artifact IDs are `<type>/<name>` as the evaluation lists them (e.g. `skills/spec`, `agents/code-reviewer`).

## Target
- The target is any directory with `agents/`, `commands/`, `rules/` or `skills/` subfolders.
- With no target, the tool uses `~/.claude`; say which directory was evaluated.
- For a project, use `--target <project>/.claude`. For a plugin, use its source checkout.
- Upgrades and promotions overwrite files in the target. An installed plugin's cache is replaced on every update, so evaluate it if you like, but duel and promote only against the source checkout.
- An arena works on the latest evaluation: evaluate the same target first, and the artifact ID must appear in that run.

## Cost
Every model call is a separate, billed `claude -p` run.

| Action | Model calls |
|---|---|
| evaluate | 0 |
| evaluate with `--llm` | 1 per artifact scoring under 100, capped at `llmReview.maxArtifacts` (10) |
| `arena challenger` | 2 |
| `arena duel` | 3 per round |

At the default thresholds an arena settles within 13 rounds (about 39 calls). If the user named the action and its size, run it. If you are the one adding `--llm`, a challenger or rounds, state the call count first and wait for a yes.

## Promotion
- Promotion is automatic only if the challenger reaches `arena.pointsToWin` (10) before the champion reaches `arena.pointsToDefend` (4). Otherwise the challenger is retired and the file stays unchanged.
- A promotion overwrites the artifact and leaves a timestamped `.bak` beside it. Report the artifact, the final score and the backup path. To undo, copy the `.bak` back. Never commit the `.bak`.
- `arena promote` skips the threshold; run it only when the user explicitly asks.

## Reading results
- Score = `100 − 25·errors − 8·warnings`, and it never falls below 60 when there are no errors. Report the findings behind the number.
- The checks are heuristics. Call out false positives; never reword an asset only to satisfy a check.
- An arena win is evidence of better single-turn answers on a generated task bank, judged by a model. It does not prove better behavior in real sessions. Present it that way, and show the judge's reasoning for the deciding rounds.

## State and dashboard
- State, results, proposals, ledgers and the optional `config.json` (only keys the user changed) live in `~/.claude/state/eval-upgrade`, or `$EVAL_UPGRADE_STATE_DIR`. Change settings through `config.json` or the dashboard; never hand-edit the generated files.
- Dashboard: tell the user it runs at `http://127.0.0.1:4600`, and stop the background task when they are done. With no browser (a remote or headless session), give the user the printed URL exactly; its token authorizes the buttons.
- The auto-trigger hook advances an existing arena by at most one round per artifact per day when that artifact is used. It never creates challengers, and it runs only with `autoTrigger.enabled: true`. It spends tokens unprompted, so enable it only at the user's request. Its log is `arena/auto-trigger.log`.

## Failures
- `node` missing or older than 20: report it and stop.
- `claude` not on PATH: the static evaluation still works, and `--llm` and the arena fail. Report the tool's error as printed.
