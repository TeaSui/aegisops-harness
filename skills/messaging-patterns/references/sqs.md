---
name: messaging-patterns-sqs
description: >
  AWS SQS implementation reference: standard vs FIFO queues, visibility timeout tuning, redrive policies,
  batching, long polling, partial batch failures in Lambda, message deduplication, cost model.
type: reference
---

# AWS SQS Reference

Inbox, outbox, backoff, DLQ handling and schema rules: parent `SKILL.md`.

## Queue choice
- Standard: at-least-once, unordered.
- FIFO: `MessageGroupId = entityId`, never one global group unless global order is truly required (it serializes everything). `MessageDeduplicationId = eventId` dedups sends for 5 min only — consumers still need the inbox (visibility expiry or a crash after commit redelivers).

## Limits and settings
- Message and batch total ≤ 1 MiB (1,048,576 bytes); batch ≤ 10 entries. Larger payloads go to S3 with a pointer (Extended Client Library).
- Long polling `WaitTimeSeconds=20`, never 0.
- Visibility timeout > max processing time + buffer. For Lambda: ≥ 6 × function timeout + batching window (30 s + 5 s → ≥ 185 s). Extend long jobs with `ChangeMessageVisibility` / sqs-consumer `heartbeatInterval`.
- Redrive: `maxReceiveCount = 5` (1 + 4 retries), never < 3 retries.
- Retention expiry deletes messages; it is not redrive.
- KMS encryption on queue and DLQ. DLQ retention 14 days.
- DLQ alarm on `ApproximateNumberOfMessagesVisible ≥ 1` (`NumberOfMessagesSent` misses automatic redrive); set the evaluation period and missing-data treatment per the alert policy.
- Lambda event source: `batchSize: 10`, `maxBatchingWindow: 5s`, `reportBatchItemFailures: true`.
- Schema version and event type in `MessageAttributes` (`schema-version`, `event-type`). Validate payloads with the project's schema validator.
- Verify pricing at aws.amazon.com/sqs/pricing before estimating cost.

## Producer
- `SendMessageBatch`: check `Failed` even on HTTP 200 and retry those entries with unchanged event IDs.
- Critical events are sent by the outbox relay and marked published only on success.

## Consumer
- Lambda: `ReportBatchItemFailures` always; return `batchItemFailures` with the `messageId`s of failed records.
- sqs-consumer (Standard queues): `handleMessageBatch` returns only committed successes/duplicates for deletion. Never enable unconditional deletion; match the installed release's ack semantics.
- Parallel processing (`Promise.all`/`allSettled`) is Standard-only. FIFO processes each group serially and stops at the first failure, returning the failed and all later unprocessed IDs.
