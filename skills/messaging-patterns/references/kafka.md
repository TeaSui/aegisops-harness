---
name: messaging-patterns-kafka
description: >
  Apache Kafka implementation reference: producer idempotence + transactions, consumer groups,
  partition strategy, exactly-once semantics, schema registry, KRaft mode, Spring Kafka, kafka-go.
type: reference
---

# Kafka Reference

Inbox, outbox, backoff, DLQ handling and schema rules: parent `SKILL.md`.

## Cluster and topics
- KRaft only (ZooKeeper removed in 4.0). Migrate ZK clusters on 3.x (3.9 bridge: KRaft controller quorum, `zookeeper.metadata.migration.enable=true`, roll brokers, finalize) before upgrading to 4.0.
- Replication factor ≥ 3 in production.
- Partitions: start at `max(throughput_MB_s / 10, target_consumer_count)`, sized at creation (can increase, never decrease; increasing breaks key ordering for existing keys).
- Retention: broker default 168 h; set topic `retention.ms` to the replay window. `cleanup.policy=compact` for state topics, `delete` for event logs.

## Producer
- `acks=all`, `enable.idempotence=true`, `max.in.flight.requests.per.connection ≤ 5`, `retries=2147483647` bounded by `delivery.timeout.ms=120000`.
- Key = entity ID. Headers `event-type`, `event-id`. kafka-go: `Balancer: &kafka.Hash{}`, `RequiredAcks: kafka.RequireAll`, `Async: false`.
- Direct sends need an explicit failure policy; critical events go through the outbox relay.
- Transactions (`transactional.id`, `sendOffsetsToTransaction`, abort and rethrow on error) only for Kafka-to-Kafka read-process-write. Consumers of transactional topics set `isolation.level=read_committed`. EOS never covers DB, payment or HTTP effects.

## Consumer
- `enable.auto.commit=false`, `AckMode.MANUAL`; `ack.acknowledge()` only after `applyOnce` returns.
- Container concurrency ≤ partition count.
- `CooperativeStickyAssignor`. On `onPartitionsRevoked` commit only contiguous offsets whose effects have committed.
- Keep handling under `max.poll.interval.ms` (or raise it) to avoid rebalances.
- Errors: `DefaultErrorHandler(DeadLetterPublishingRecoverer, ExponentialBackOffWithMaxRetries(4))` with `setFailIfSendResultIsError(true)`. A failed DLT publish must leave the offset retryable — never catch-all, fire-and-forget to DLT and ack. Test it.
- DLT name `<topic>.DLT` (e.g. `orders.order.created.DLT`). Restrict DLT payload storage; sanitize exception headers.

## Schemas
- Registry (Confluent or Glue) with Avro/Protobuf/JSON Schema, `BACKWARD` compatibility by default.
- Without a registry: `version` in the envelope, consumers ignore unknown fields (Jackson `FAIL_ON_UNKNOWN_PROPERTIES=false`).

## Alerts
- Sustained consumer-lag growth per group/partition.
- `under_replicated_partitions > 0`.
- `request_handler_pool_idle_percent < 30%`.
