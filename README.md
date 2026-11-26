# AegisOps-Harness

> The backend engineering lifecycle for Claude Code: **spec → plan → build → verify → review → ship**, started only by slash commands and held by gates.

[How it works (one page)](HOW-IT-WORKS.md) · [Changelog](CHANGELOG.md) (the version is in `.claude-plugin/plugin.json`) · MIT

No workflow starts until you run one of its commands. No keyword in a prompt starts one and the model cannot load an AegisOps-Harness skill on its own (every skill has `disable-model-invocation: true`, and `check-setup.py` fails if one does not). Inside a command each stage is a fixed file, support skills are chosen from the repository's files, business questions go to Atlassian Rovo before a person, and every stage ends at an `aidlc` gate. The hook gates (secret scan, TDD reminder, PR and merge gates, evidence guard) are on in every session.

**What enforces what.** Prompts advise. Hooks and local gates are a guard rail for the default path: they read files the session itself can write. Enforcement is `aidlc ci` as a required status check on a protected branch: it re-runs the pinned suite on the pull request head, proves the suite goes red without the change, and ignores the ledger's verify and revert-check lines. See [Enforce it in CI](#-enforce-it-in-ci).

---

## 🚀 Install

### From the marketplace (recommended)

```text
/plugin marketplace add TeaSui/aegisops-harness
/plugin install aegisops-harness@AegisOps-Harness
```

### From a local clone (development)

```bash
claude --plugin-dir /path/to/aegisops-harness
```

### Updating

Releases are driven by `version` in `.claude-plugin/plugin.json`; pushing commits without bumping it does not reach installed users. Third-party marketplaces do not auto-update by default:

```text
/plugin marketplace update AegisOps-Harness
/reload-plugins
```

### Requirements

| Tool | Used by |
|---|---|
| `python3` | All hooks and `scripts/` |
| [`gitleaks`](https://github.com/gitleaks/gitleaks) | Secret gate on `git commit` / `git push` (fails closed when missing) |
| `gh` (GitHub) or Bitbucket Cloud credentials | Opening, checking and merging PRs (`scripts/pr.py`), the PR and ship gates |
| `.aidlc.json` in the target repository | Pins the verify command the gates trust (`aidlc config init`); without it `aidlc verify` stops |
| `ruby` (optional) | Full YAML parsing in `scripts/check-setup.py` and `scripts/check-contract.py` (when PyYAML is absent) |

### Bitbucket Cloud

`scripts/pr.py` picks Bitbucket when `origin` is on `bitbucket.org` (SSH or HTTPS). Pushing uses your git credentials, as today. The API calls (create, checks, merge, comments) read these from the environment, for example in `~/.claude/settings.json` under `env` or your shell profile:

| Variable | Value |
|---|---|
| `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` | your Atlassian account email and an [API token](https://support.atlassian.com/bitbucket-cloud/docs/using-api-tokens/) with the scopes `read:repository:bitbucket`, `read:pullrequest:bitbucket`, `write:pullrequest:bitbucket` |
| or `BITBUCKET_ACCESS_TOKEN` | a repository, project or workspace access token (sent as Bearer) |

Check with `python3 <plugin>/scripts/pr.py auth` in the repository: exit 0 means PRs can be opened. CI status comes from the build statuses your CI posts to the PR (Bitbucket Pipelines, Jenkins, CodeBuild…).

---

## ⌨️ Which command, when

| Situation | Command |
|---|---|
| Turn a rough idea into an input that meets the AIDLC standard | `/aegisops-harness:prompt-builder <idea>` |
| New backend feature or behaviour change (request or pasted to-spec spec) | `/aegisops-harness:aidlc <request or spec>` |
| Interview me first on open decisions | `/aegisops-harness:grilling <topic>` |
| The lifecycle stopped for my approval of a spec | `/aegisops-harness:approve <slug>` |
| One stage at a time | `/aegisops-harness:spec` · `/aegisops-harness:plan` · `/aegisops-harness:build` · `/aegisops-harness:verify` · `/aegisops-harness:review` · `/aegisops-harness:ship` |
| Where is every spec, and what next | `/aegisops-harness:aidlc` (no argument) |
| Resume after `/clear` or a new session | `/aegisops-harness:aidlc <slug>` |
| Bug fix or small change, no new decision | `/aegisops-harness:fix <bug>` |
| Review comments arrived | `/aegisops-harness:receiving-code-review <PR or comments>` |
| After the merge | `/aegisops-harness:upgrade-service-docs` |
| Service has no living docs | `/aegisops-harness:generate-service-docs` |
| A second opinion | `/aegisops-harness:reframe` · `/aegisops-harness:expert-lens` |
| Score, upgrade or A/B-duel part of the plugin | `/aegisops-harness:eval-upgrade` |

What each command loads, which gate stops it and which files it leaves: [HOW-IT-WORKS.md](HOW-IT-WORKS.md).

## 🔎 Questions during the lifecycle

Files first (spec, `GLOSSARY.md`, ADRs, code, tests), then **Atlassian Rovo MCP** (`search`, then `fetch` / `getConfluencePage` / `getJiraIssue`), then a recorded assumption. A person is asked only for a security or compliance risk, money or regulatory behaviour with no source, an irreversible or production action, or sources that contradict each other (`references/aidlc.md` §0), and never when the input says "do not ask", "end to end" or `Status: ready-for-agent`: then the decision is recorded (`RISK-ACCEPTANCE NEEDED:` when it accepts a risk) and listed first in the final report. `hooks/question-gate.py` enforces both: inside an AegisOps-Harness command, a question in delegated input is blocked, and the first question asked before any Rovo search is sent back. Every source and assumption is listed in the spec and the final report.

## 🔒 Enforce it in CI

Once per repository, by a person:

1. **Pin the verify command.** `python3 <plugin>/scripts/aidlc.py config init --cmd "<full test suite>" --junit "<report glob>"` writes `.aidlc.json`. Keep the reports git-ignored and merge the file to the default branch: the gates read it from there, so a branch cannot swap its own exam.
2. **Run the gate on pull requests.** After your own toolchain setup:
   ```yaml
   - uses: actions/checkout@v4
     with:
       ref: ${{ github.event.pull_request.head.sha }}
       fetch-depth: 0
   - uses: TeaSui/aegisops-harness/.github/actions/aidlc-gate@<tag-or-sha>  # not @main: the gate is the trust anchor
   ```
   Bitbucket Pipelines: a ready `bitbucket-pipelines.yml` step is in [references/aidlc.md](references/aidlc.md) §5 (fetch the destination branch with its history first).
3. **Require it.** Branch protection: the gate job as a required status check, a required review, and CODEOWNERS on `.aidlc.json`, `docs/specs/` and the scripts and workflow the gate runs. `aidlc ci` judges the specs bound to the branch; a change that unbinds a spec gets the suite only, so read the diff of `docs/specs/`.

The job summary lists what it cannot check (who is said to have approved and reviewed, every waiver). Details and the limits of each layer: `references/aidlc.md` §4, §5 and "Trust model".

## 🤖 Agents

| Agent | Used in | Model |
|---|---|---|
| `aegisops-harness:security-engineer-subagent` | spec: the `### Security` section of a trust-boundary spec | sonnet |
| `aegisops-harness:backend-engineer-subagent` | build: tickets of a parallel batch (a lone ticket is built in the main session) | sonnet |
| `aegisops-harness:code-reviewer` | build and review: Spec and Standards axes | sonnet |
| `aegisops-harness:qa-subagent` | review: QA verdict against the stories | sonnet |

## ✅ Validating changes

```bash
python3 scripts/check-setup.py                 # manifests, frontmatter, references, no model-invocable skill, map freshness, version drift
python3 -m unittest discover -s tests          # node and gitleaks on PATH run the eval-fixture and secret-gate tests too
python3 scripts/aidlc.py ci --base origin/main # this repository's own lifecycle gate (docs/specs/, .aidlc.json)
python3 scripts/map.py                         # regenerate HOW-IT-WORKS.md after changing skills, agents or hooks
python3 evals/descriptions/run.py              # description lint, free
python3 evals/headless/run.py --suite lifecycle,tdd --runs 2 --model claude-opus-5-5   # real sessions, paid
```

CI runs the unit tests, `check-setup.py` and the free evals on Python 3.9 and 3.12, and on pull requests the lifecycle gate on the plugin's own spec. `scripts/validate.sh` starts a headless session that validates pending work in a target project (`skills/verify/SKILL.md` §2–§3).

---

## 📄 License

MIT © [Tea Nguyen](https://github.com/TeaSui)
