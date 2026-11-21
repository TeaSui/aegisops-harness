---
name: messaging-patterns
description: Broker selection and cross-broker patterns (idempotency, DLQ, retry backoff, outbox, schema versioning) with Kafka, RabbitMQ and SQS references; Read before the first edit in that area when the repository has Kafka, RabbitMQ, SQS, SNS or EventBridge clients or an outbox table.
disable-model-invocation: true
user-invocable: false
---

# Messaging Patterns

## Broker selection
Pick in order; stop at the first match:
1. Event replay, audit log, event sourcing/CQRS, >100k msg/s streaming, or Kafka already in use → **Kafka** (avoid running two brokers).
2. Complex routing (topic/headers/fanout), task distribution to workers, request-reply, per-message TTL/priority → **RabbitMQ**.
3. Simple queue on an AWS-native/serverless (Lambda) stack → **SQS** (fan-out via SNS filter policies).

Don't use Kafka for simple task queues; SQS/RabbitMQ give no replay (SQS retention ≤ 14 days).

Then read only the matching reference:

| Broker | Reference | Triggers |
|--------|-----------|----------|
| Kafka | `${CLAUDE_PLUGIN_ROOT}/skills/messaging-patterns/references/kafka.md` | `kafka`, `segmentio/kafka-go`, `spring-kafka`, `KafkaListener`, `KRaft` |
| RabbitMQ | `${CLAUDE_PLUGIN_ROOT}/skills/messaging-patterns/references/rabbitmq.md` | `rabbitmq`, `amqp`, `@RabbitListener`, `quorum queue`, `DLX` |
| AWS SQS | `${CLAUDE_PLUGIN_ROOT}/skills/messaging-patterns/references/sqs.md` | `SQS`, `FIFO`, `visibility timeout`, `redrive`, Lambda + SQS |

## Cross-broker rules (references do not repeat these)

### Idempotent consumer — transactional inbox
Delivery is at-least-once on all three brokers (Kafka EOS and SQS FIFO dedup do not cover DB/HTTP effects). Every consumer:
- In ONE transaction on the same DB/connection as the business effects: atomically insert `(consumer_name, event_id)` under a unique constraint (Postgres: `INSERT … ON CONFLICT DO NOTHING RETURNING event_id`); if it already exists, skip effects without touching it; else apply DB effects plus any new outbox rows.
- Ack / delete / commit offset only after that commit succeeds; a committed duplicate is also acked.
- Never catch a uniqueness error and continue in the aborted transaction.
- Spring: the transaction lives in a separate proxied service or `TransactionTemplate`, never in the listener method itself.
- `applyOnce` / `inboxHandler.applyOnce` in the references = this contract (application-owned, not a library API).
- Keep inbox rows for the full replay/redrive window, which can exceed broker retention (don't expire Kafka protection at 7 days).
- Redis `SET NX` is a lease, not completion. External effects (payments, HTTP) need a stable vendor idempotency key or a recoverable state machine/outbox worker.
- Test rollback, concurrent duplicates and crash-after-commit/before-ack against the real store.

### Transactional outbox
Required wherever losing the event is a business failure (orders, payments, inventory). Write the event in the same transaction as the state change; a relay publishes only committed rows (or committed CDC), marks published only after broker confirmation, retries on failure, deletes after retention. Republish keeps the same `eventId`; preserve per-entity order. Never create the outbox row in a send callback; rolled-back work never publishes. Fire-and-forget publishing is not allowed for critical events.

### Retry and DLQ
- Exponential backoff with jitter, never immediate: 1 s, 2 s, 4 s, 8 s, then DLQ (5th failure). Non-retryable errors and poison pills go straight to DLQ.
- Every queue/subscription has a DLQ/DLT; no hot requeue loops.
- DLQ processor: log only allowlisted metadata (safe event/correlation id, error category, attempt count, partition/offset or delivery tag) — never raw bodies, exception messages or headers; alert P2 on DLQ depth over threshold; store payloads only in an access-controlled, encrypted quarantine with retention limits; admin replay endpoint for after the fix.

### Event schema
- Envelope: `eventId` (UUID v4, stable across retries and republish), `eventType`, `version` (int), `timestamp` (ISO-8601 UTC), `source`, `correlationId`, `data`.
- Names: `<domain>.<entity>.<event>` (e.g. `payments.payment.authorized`).
- Evolution: add fields only if consumers tolerate unknowns and compatibility rules allow (verify old/new producer–consumer pairs); remove only after deprecation and all consumers updated; never rename or change a type — publish a versioned event (`OrderCreated.v2`).
- Enforce with a schema registry (Confluent/Glue for Kafka) or JSON Schema validation (RabbitMQ/SQS).
- Ordering: partition / group by entity ID, never a single partition or group.
