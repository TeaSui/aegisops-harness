# AI integration rules

Numbers below are starting defaults; project values win.

## Sources of truth
Never answer Claude API shapes, model IDs, prices or limits from memory. In order: Claude Code's `/claude-api` skill; live docs (append `.md` to any platform.claude.com page; index `platform.claude.com/llms.txt`; Context7 `/websites/platform_claude_en`); the installed SDK's source and changelog.

## Models
- Unspecified substantial workload: latest Opus at `medium`; bounded implementation: Sonnet; measured mechanical/volume work: Haiku; hard reasoning or long autonomous runs: Fable. Validate quality, latency and cost on representative cases.
- API model IDs are fixed snapshots with no `-latest` alias: resolve via `GET /v1/models?lifecycle=active` (`client.models.list()`), take the first entry whose `line` matches the family (read `line`/`capabilities`, never parse the ID), then pin it in config (env var or config file), never as scattered literals.
- Upgrade deliberately (migration guide, evals, cost/latency); monitor `deprecated_at`/`retires_at` on a schedule; never invent IDs or assume Bedrock/Vertex/Foundry share first-party IDs.
- Control depth with effort (fixed thinking budgets are rejected; Opus/Fable cannot turn thinking off); size `max_tokens` for thinking plus answer.

## Prompts
Versioned named constants (e.g. `TRANSACTION_ANALYSIS_PROMPT_V2`), never inline template strings; XML-tagged sections; system prompt = behaviour, user prompt = data; each prompt has a golden test set.

## Cost
- Explicit `max_tokens` on every call; per-user and per-service token budgets; log input/output tokens and cost per request.
- Daily cost alert: $10 dev, $50 staging, $200 prod.
- Prompt caching (`cache_control: {"type": "ephemeral"}`) for repeated system prompts and RAG documents above the minimum cacheable length; cache hit rate target > 80%. Batch API where latency allows.

## Evals
Golden dataset ≥ 20 pairs per AI feature; metrics defined before implementation; evals run in CI on every prompt change; pass = no regression vs baseline and accuracy ≥ 85%.

## Security and privacy
- Sanitize user input before it enters a prompt; never execute model output — parse and validate (type, range, business rules); structured outputs or tool use for action-bearing responses.
- Never send raw PII to an external LLM API; pseudonymize (`[USER_A]`) or use a VPC-hosted model.
- Log interactions for audit with PII redacted; rate limit LLM endpoints at 60 requests/min per user.

## Errors and agents
- Bounded SDK retries (`maxRetries: 3`) instead of manual retry loops; after exhaustion degrade to a fallback on rate-limit and 5xx; rethrow unknown errors.
- Agents: clear tool descriptions, max 10 turns, token budget per run, JSON tool outputs, tolerate tool failures; log tool name, status, latency, usage with sensitive arguments redacted.

## Observability
Correlation ID on every LLM call; metrics: latency P50/P95/P99, tokens, cost, cache hit rate, error rate. Alerts: error rate > 5%, P99 > 10 s, daily cost threshold. Use the project's telemetry stack.
