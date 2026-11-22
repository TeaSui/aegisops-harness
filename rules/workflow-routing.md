# Workflow routing

AegisOps-Harness starts only from a command (`skills/session-bootstrap/SKILL.md` lists them). This file decides what runs inside one.

## /aegisops-harness:fix or /aegisops-harness:aidlc
`/aegisops-harness:fix` takes a bug fix or small change with no new decision. It stops and names `/aegisops-harness:aidlc` (one line, why) when the change: adds an endpoint, event, schema or migration, or a dependency; needs more than one user story; or crosses a trust boundary with a new decision (fails the escape hatch below).

## Trust-boundary check
Any YES or unsure → trust boundary.
1. Reads, writes or logs PII or sensitive data (identity, contact, ID numbers, financial, health, credentials).
2. Creates, validates or changes authN, session or authZ rules (login, tokens, permissions, roles).
3. Processes money, billing or third-party payments.
4. Exposes a new URL, endpoint, webhook or other surface reachable from outside the trust domain.
5. Integrates a new external vendor, partner API or third-party script.
6. Changes a security-relevant dependency, config key or secret-handling path (TLS, JWT keys, IAM, encryption).

## Escape hatch (trust boundary inside /aegisops-harness:fix)
All must hold, else `/aegisops-harness:aidlc`:
1. ≤ 30 lines of production code across ≤ 3 files (tests excluded).
2. No new endpoint, external surface, dependency, schema or migration.
3. A touch, not a new decision (renaming a field already classified as PII, not adding one).
4. An existing security decision covers the path; cite it (a spec's `### Security`, `docs/security.md`).

Then the security pass: before the first edit, 3-6 lines of assets touched, threats (STRIDE / OWASP), controls kept; tests for the security behaviour; the PR lists the threats checked. Commit message: `Escape hatch applied: <cite>`.

## Stack skills (chosen from repository files, never from prompt words)
Before the first edit in that area, Read the matching `skills/<name>/SKILL.md`:

| The repository has | Read |
|---|---|
| `build.gradle*`, `pom.xml`, `go.mod`, `Cargo.toml`, `pyproject.toml`/`requirements*.txt` with a web framework | `backend-languages` |
| SQL migrations (`db/migration`, `*.sql`, Flyway, Liquibase), ORM entities, DynamoDB or Redis clients | `database-patterns` |
| Kafka, RabbitMQ, SQS, SNS or EventBridge clients, an outbox table | `messaging-patterns` |
| OpenAPI, AsyncAPI or proto files, Pact | `api-contract-testing` |
| `*.feature` files, Cucumber or godog | `bdd-cucumber` |
| `cdk.json` | `cdk-testing` |
| `dd-trace`, `dd-java-agent` or DogStatsD dependencies | `observability` |
| a trust boundary (check above) | `fintech-security` |

Always, in every stage: `test-driven-development` before production code, `systematic-debugging` when a test fails for a reason you cannot explain or a fix fails twice, `grounding-claims` for every factual claim, `find-docs` before relying on a library or cloud-service detail you have not seen in this session.

## Design-decision quality
A non-trivial design decision (architecture, API contract, data model): look for flaws and counter-arguments in your draft before presenting; resolve material ones in ≤ 2 rounds, report the rest. Skip for implementation, bug fixes, single-file changes.
