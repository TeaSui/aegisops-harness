# AegisOps-Harness evals

These suites measure whether a session picks the right skill, command and gate when the user describes the work without naming any of them. They are written for maintainers and are not loaded into agent sessions.

**The rule:** a change to a skill, a command, the hooks or the bootstrap (`skills/session-bootstrap/SKILL.md`) must not lower any suite's score. CI enforces this for the deterministic suites on every push. Run the paid suites before you merge a change to any of those files, and attach the report to the PR.

| Suite | Measures | Cost | Where it runs |
|---|---|---|---|
| `descriptions/` | Lint of every `skills/*/SKILL.md` and `commands/*.md` description, plus a collision check between descriptions | Free, under 1 s | CI, every push and PR |
| `headless/` `passive` | Real `claude -p` sessions: a natural prompt with no slash command must invoke no AegisOps-Harness skill, command or agent (no passive activation) | About $0.45 per case per run (18 cases) | Manual, weekly workflow |
| `headless/` `tdd` | Real sessions on code-change and bug prompts: a failing test run before the first production edit, and a test run after the last edit | About $0.50 per case per run (4 cases) | Manual, weekly workflow |
| `headless/` `lifecycle` | One real session asked for a trust-boundary feature end to end. Scores how far the AIDLC lifecycle got and whether its gates were passed through `aidlc advance` | Several dollars per run, up to 45 min | Manual |

Costs are what Claude Code reported (`total_cost_usd`) with Claude Code 2.1.319 on its default model. They change with the model and the plugin.

## Deterministic suites

```bash
python3 evals/descriptions/run.py       # --top 15 shows the most similar pairs, collisions or not
python3 -m unittest tests.test_evals    # unit tests for the eval code itself
```


### Descriptions (`descriptions/`)

Checks for each file:

- The frontmatter is valid YAML. This uses the same Ruby check as `scripts/check-setup.py`; when Ruby is missing it prints a warning and skips the check.
- There is a `description`. For a skill, `name` equals the folder name.
- `disable-model-invocation: true` is set (AegisOps-Harness runs only from slash commands); a description that still reads like a model trigger is a warning.
- The description is 80 to 1024 characters long. Over 700 characters gives a warning.

**Collision check.** Every pair of descriptions gets a TF-IDF cosine similarity (stdlib implementation, threshold 0.25). Two descriptions that read alike make Claude guess between the two files.

- **Exit 1** on any lint error, or on a pair at or above the threshold that is not in `descriptions/allowlist.json`.
- A pair belongs in the allowlist only when the two descriptions already say which one to use when. For example, one says "fast-path work goes to X" and the other says "full-workflow work goes to Y". Every entry needs a `reason`.
- An allowlisted pair whose score falls more than 0.05 below the threshold is reported as stale. Remove it.

## Headless suites (paid)

These suites need the `claude` CLI and an `ANTHROPIC_API_KEY` or a logged-in CLI. Each run builds its own fixture repository and starts one `claude -p --plugin-dir <plugin> --output-format stream-json --verbose` session in it. A judge then scores the recorded session. The runs use your normal user settings, so any other plugins you have enabled load too. In CI the machine is clean.

```bash
python3 evals/headless/run.py --suite passive --runs 1 --parallel 6
python3 evals/headless/run.py --suite passive,tdd --runs 3 --compare        # exit 1 on a regression
python3 evals/headless/run.py --suite tdd --cases T2-behavior,T4-red --runs 3
python3 evals/headless/run.py --suite lifecycle --runs 1 --model sonnet
python3 evals/headless/run.py --suite passive --rejudge evals/headless/results/<stamp>   # re-score, no model calls
```

Options:

| Option | Meaning |
|---|---|
| `--plugin-dir` | The plugin under test (default: this checkout) |
| `--model` | Passed to `claude --model` (default: the CLI default) |
| `--out DIR` | Output folder (default `evals/headless/results/<UTC stamp>`, git-ignored) |
| `--claude-bin` | The CLI to use, for example when `claude` is a shell function (default: `$CLAUDE_BIN` or `claude` on `PATH`) |
| `--extra-arg` | One extra CLI argument; repeat the option for more |
| `--tolerance` | Allowed pass-rate drop for `--compare` (default 0.10) |
| `--strict` | Turn off the noise guard described below |

Output:

- `results.json`: every run, the per-suite summaries and the comparison.
- `report.md`: one table per suite with each run's outcome, score, cost (`total_cost_usd` from the stream's result event), duration and the judge's one-line detail.
- Each run keeps its fixture repo, `out.jsonl`, `err.txt` and `judge.json` under `<out>/<suite>/<case>-r<n>/`.

### Suites

Each suite is a folder in `headless/suites/` with four files: `suite.json` (turn limit, timeout, permission mode, allowed tools), `cases.jsonl`, `fixture.py` (`build(repo, case)`) and `judge.py` (`judge(case, stream, repo, plugin_dir)`). `headless/fixtures/node_shop.py` is the shared fixture: a small Node repository with `src/math.js`, `src/wallet.js` (float balances, on purpose) and `node --test` tests.

- **passive.** A `silent` case passes when the session called neither the `Skill` tool with an AegisOps-Harness skill nor the `Agent`/`Task` tool with an AegisOps-Harness agent. Allowed tools are read-only, with a turn limit of 8. A tool call is counted even when permissions deny it.
- **tdd.** The judge orders the tool calls into test edits, production edits (`src/`, not test files, including shell writes), red test runs and green test runs. An edit that a gate blocked counts as nothing. A run passes when a red run comes before the first production edit and a test run comes after the last edit. `score` gives half a point for each of the two conditions.
- **lifecycle.** The judge scores six artifacts in the fixture's spec folder, one point each, against `references/aidlc.md`:
  1. spec: a README with `key:`, and `spec.md` (to-spec template, ≥1 numbered user story)
  2. no open guess: `spec-check.md` closed, or absent (optional for `spec.md`)
  3. `tickets.md` whose `## T<n>` tickets all have `Covers` and `Blocked by`
  4. `task-done` and `verify … exit=0` ledger events
  5. `review.md` with `## Spec` and `## Standards`
  6. `ship.md` with `decision: GO`, a rollback section and a post-release verification section
  Legacy `requirements.md`/`plan.md` specs score on the pre-3.3.0 rules.

  A run passes when its score reaches the case's `pass_score` (0.67). The judge also reports the stage from `python3 scripts/aidlc.py status --json --repo <fixture>`, the `advance` transitions in the ledger, and gate discipline, which is advances divided by the stages reached. When `scripts/aidlc.py` is missing or prints no JSON, the judge says so and scores from the files alone.

### Baseline and regressions

`headless/baseline.json` holds the last accepted score of each suite: passed/total, the cases, runs per case, model, Claude Code version and plugin version. It was seeded from the 2.9.0 measurements in `CHANGELOG.md`: tdd 12/12; passive now measures silence (4.0.0), so its old 16/18 is not comparable. Lifecycle has no baseline yet, so `--compare` reports `no-baseline` for it and does not fail.

`--compare` marks a suite as a **regression** (exit 1) when both of these hold:

1. Its pass rate is more than `--tolerance` below the baseline rate.
2. The baseline rate lies above the upper bound of the current Wilson 95% interval.

The second condition is the noise guard. At small N a drop can be pure chance. For example, 14/18 has the interval 55–91%, which still contains a 16/18 baseline (89%). The report shows such a drop as `drop-within-noise` without failing. `--strict` fails on the first condition alone. The report also notes when the case set differs from the baseline's, as it does in a smoke run on a few cases.

To accept new scores, run the full suite with at least as many runs as the baseline, with `--update-baseline`. Commit `baseline.json` with the change that moved it, and give the reason in the PR. Lower a baseline only for a deliberate tradeoff. If the drop comes from a description, router or bootstrap change, fix that change instead.

### CI

- `.github/workflows/ci.yml` runs on every push and pull request, on Python 3.9 and 3.12. It runs the unit tests, `scripts/check-setup.py` and the description lint.
- `.github/workflows/evals.yml` runs on manual dispatch (inputs: suites, runs, model) and every Monday. It needs the repository secret `ANTHROPIC_API_KEY`. It installs the Claude Code CLI and gitleaks (the security gate blocks commits without gitleaks), then runs the headless suites with `--compare`. It writes the report to the job summary and uploads `results.json`, `report.md` and each run's stream and verdict as artifacts.
