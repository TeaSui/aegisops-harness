---
name: messaging-patterns-rabbitmq
description: >
  RabbitMQ implementation reference: exchange types, quorum vs classic queues, publisher confirms,
  consumer acknowledgments, DLX patterns, Streams plugin, Spring AMQP, clustering basics.
type: reference
---

# RabbitMQ Reference

Inbox, outbox, backoff, DLQ handling and schema rules: parent `SKILL.md`.

## Topology
- Durable, non-auto-delete exchanges: topic for event filtering, direct for task queues/DLX, fanout for broadcast, headers for key-less routing.
- Quorum queues for all new production queues. Classic mirroring is removed in 4.0: migrate first (check with `rabbitmq-queues check_if_cluster_has_classic_queue_mirroring_policy`).
- Quorum limits: priority only since 4.0 (2 levels; 0–31 from 4.3; `x-max-priority` ignored); no non-durable/exclusive queues.
- ≥ 3 nodes. On Kubernetes, `rabbit_peer_discovery_k8s`.
- Every queue sets `x-dead-letter-exchange` + `x-dead-letter-routing-key` to a provisioned DLX → quorum DLQ. Without a DLX, `requeue=false` silently discards.
- `x-message-ttl` (e.g. 24 h = 86400000) on a queue dead-letters expired messages to its DLX.
- Replay needs: RabbitMQ Streams (offset `first`/`last`/N/timestamp).

## Publishing
- Publisher confirms mandatory: `publisher-confirm-type: correlated`, `publisher-returns: true`, `RabbitTemplate.setMandatory(true)`, with confirm and returns callbacks (NACK → outbox retry; unroutable → alert).
- A confirm means broker acceptance, not consumer completion. The relay marks outbox rows published only on a confirmed, routed publish, not from a callback log.
- Properties: `contentType: application/json`, `messageId = eventId`.
- No built-in registry: JSON Schema/Avro via a custom message converter, or Confluent Schema Registry over HTTP when strict compatibility is needed.

## Consuming
- `acknowledge-mode: manual`, `prefetch: 10` as the starting point (tune per workload; 1 = fairest, slowest).
- `channel.basicAck(tag, false)` only after `applyOnce` commits, outside the transaction.
- `basicNack(requeue=true)` only for transient failures with backoff; never on persistent errors.
- No exactly-once in AMQP 0-9-1.
- Retries: bounded container retry/backoff, or TTL retry queues (`x-message-ttl` = delay, DLX back to the main exchange, attempt-count header). After max attempts `basicNack(requeue=false)` to the DLQ. A thrown error is never acked.
- Confirm the dead-letter reliability strategy for the queue type and version in use.

## Alerts
- Queue depth (`messages_ready`, `messages_unacknowledged`).
- Consumer count = 0.
- `memory_alarm`, `disk_free_alarm`.
- Publish/ack rate baseline.
