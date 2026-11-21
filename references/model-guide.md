# Claude models and effort

Starting policy, checked 2026-11-10 against the Claude model docs; recheck on upgrade. Use family aliases (resolve to the newest release); never pin a versioned ID in frontmatter or plugin guidance. Snapshot 2026-11-09: Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.2.

| Alias | $/MTok in/out (2026-11-09) | Start effort | Choose for |
|---|---|---|---|
| `haiku` | 0.10/0.50 ≤100K prompt; 0.50/2.50 above | `medium` | Classification, routing, extraction; file search, log reading, summaries; checkable volume work. Not long agentic loops |
| `sonnet` | 2/10 | `medium` → `high` | Well-scoped spec-driven coding; repeated review/investigation/drafting; documents |
| `opus` | 4/20 | `medium` → `high` | Default when unsure; debugging, multi-PR features, judgment calls, computer use, vision |
| `fable` | 8/40 | `medium` → `high` | Major refactors/migrations, architecture, leading many subagents, deep research, long unattended runs, or Opus `high` still short |

## Choosing
- Escalate: (1) let the model verify its own work; (2) one effort level up; (3) one model up at a lower effort. Effort buys thinking, not capability.
- Checkable tasks: `low`, re-run only failures at `high`. Switching model mid-session loses the prompt cache.
- Never enable paid fast mode or extra-usage modes automatically.

## tea-sdlc subagent defaults
Frontmatter sets the normal job; a dispatcher overrides only when a task differs.

| Agent | Model | Effort | Override up when |
|---|---|---|---|
| tea-sdlc:security-engineer-subagent | sonnet | high | `opus` or `fable` for novel auth/crypto/payment designs or large trust-boundary diffs |
| tea-sdlc:code-reviewer | sonnet | medium | `high` effort, or `opus`, for large or trust-boundary diffs |
| tea-sdlc:backend-engineer-subagent | sonnet | high | `opus` for ambiguous bugs, cross-cutting refactors, or when `high` still fails |
| tea-sdlc:qa-subagent | sonnet | medium | `high` for large release scopes |

## Facts that are not obvious
- `modelSettings.effortLevel` accepts `low`–`xhigh`; `max` is per session. Code defaults to `medium` for every family.
- Subagent model resolution: provider/host override → dispatch `model` → agent frontmatter → parent model (`CLAUDE_CODE_SUBAGENT_MODEL` sets the default). Omitting a model never guarantees Sonnet. On Bedrock, Google Cloud, Microsoft Foundry and Claude Platform on AWS, `haiku` may still resolve to Haiku 4.5 (`ANTHROPIC_DEFAULT_HAIKU_MODEL` pins it); never infer a version from an alias on a gateway.
- API code is separate: request-level `output_config.effort`, adaptive reasoning, adequate `max_tokens`; every API model ID is a fixed snapshot (no `-latest` alias), so resolve the newest via the Models API and pin it in config. Use the `/claude-api` skill.
