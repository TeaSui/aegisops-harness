# tea-sdlc

> The backend engineering lifecycle for Claude Code: **spec → plan → build → verify → review → ship**, started only by slash commands and held by gates.

**Version 4.0.0** · [How it works (one page)](HOW-IT-WORKS.md) · [Changelog](CHANGELOG.md) · MIT

tea-sdlc does nothing until you run one of its commands. No keyword in a prompt starts a workflow and the model cannot load a tea-sdlc skill on its own (every skill has `disable-model-invocation: true`, and `check-setup.py` fails if one does not). Inside a command each stage is a fixed file, support skills are chosen from the repository's files, business questions go to Atlassian Rovo before a person, and every stage ends at an `aidlc` gate.

---

## 🚀 Install

### From the marketplace (recommended)

```text
/plugin marketplace add TeaSui/tea-sdlc
/plugin install tea-sdlc@tea-sdlc
```

### From a local clone (development)

```bash
claude --plugin-dir /path/to/tea-sdlc
```

### Updating

Releases are driven by `version` in `.claude-plugin/plugin.json`; pushing commits without bumping it does not reach installed users. Third-party marketplaces do not auto-update by default:

```text
/plugin marketplace update tea-sdlc
/reload-plugins
```

### Requirements

| Tool | Used by |
|---|---|
| `python3` | All hooks and `scripts/` |
| [`gitleaks`](https://github.com/gitleaks/gitleaks) | Secret gate on `git commit` / `git push` (fails closed when missing) |
| `gh` (GitHub) or Bitbucket Cloud credentials | Opening, checking and merging PRs (`scripts/pr.py`), the PR and ship gates |
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
| Turn a rough idea into an input that meets the AIDLC standard | `/tea-sdlc:prompt-builder <idea>` |
| New backend feature or behaviour change (request or pasted to-spec spec) | `/tea-sdlc:aidlc <request or spec>` |
| Interview me first on open decisions | `/tea-sdlc:grilling <topic>` |
| One stage at a time | `/tea-sdlc:spec` · `/tea-sdlc:plan` · `/tea-sdlc:build` · `/tea-sdlc:verify` · `/tea-sdlc:review` · `/tea-sdlc:ship` |
| Where is every spec, and what next | `/tea-sdlc:aidlc` (no argument) |
| Resume after `/clear` or a new session | `/tea-sdlc:aidlc <slug>` |
| Bug fix or small change, no new decision | `/tea-sdlc:fix <bug>` |
| Review comments arrived | `/tea-sdlc:receiving-code-review <PR or comments>` |
| After the merge | `/tea-sdlc:upgrade-service-docs` |
| Service has no living docs | `/tea-sdlc:generate-service-docs` |
| A second opinion | `/tea-sdlc:reframe` · `/tea-sdlc:expert-lens` |
| Score, upgrade or A/B-duel part of the plugin | `/tea-sdlc:eval-upgrade` |

What each command loads, which gate stops it and which files it leaves: [HOW-IT-WORKS.md](HOW-IT-WORKS.md).

## 🔎 Questions during the lifecycle

Files first (spec, `GLOSSARY.md`, ADRs, code, tests), then **Atlassian Rovo MCP** (`search`, then `fetch` / `getConfluencePage` / `getJiraIssue`), then a recorded assumption. A person is asked only for a security or compliance risk, money or regulatory behaviour with no source, an irreversible or production action, or sources that contradict each other (`references/aidlc.md` §0), and never when the input says "do not ask", "end to end" or `Status: ready-for-agent`: then the decision is recorded (`RISK-ACCEPTANCE NEEDED:` when it accepts a risk) and listed first in the final report. `hooks/question-gate.py` enforces both: inside a tea-sdlc command, a question in delegated input is blocked, and the first question asked before any Rovo search is sent back. Every source and assumption is listed in the spec and the final report.

## 🤖 Agents

| Agent | Used in | Model |
|---|---|---|
| `tea-sdlc:security-engineer-subagent` | spec: the `### Security` section of a trust-boundary spec | sonnet |
| `tea-sdlc:backend-engineer-subagent` | build: tickets of a parallel batch (a lone ticket is built in the main session) | sonnet |
| `tea-sdlc:code-reviewer` | build and review: Spec and Standards axes | sonnet |
| `tea-sdlc:qa-subagent` | review: QA verdict against the stories | sonnet |

## ✅ Validating changes

```bash
python3 scripts/check-setup.py                 # manifests, frontmatter, references, no model-invocable skill, map freshness
python3 -m unittest discover -s tests
python3 scripts/map.py                         # regenerate HOW-IT-WORKS.md after changing skills, agents or hooks
python3 evals/descriptions/run.py              # description lint, free
python3 evals/headless/run.py --suite lifecycle,tdd --runs 2 --model claude-opus-5-5   # real sessions, paid
```

CI runs the unit tests, `check-setup.py` and the free evals on Python 3.9 and 3.12. `scripts/validate.sh` starts a headless session that validates pending work in a target project (`skills/verify/SKILL.md` §2–§3).

---

## 📄 License

MIT © [Tea Nguyen](https://github.com/TeaSui)
