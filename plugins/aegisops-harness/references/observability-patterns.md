# Observability standards

Starting defaults; the project's telemetry stack, SLOs and on-call policy override them.

## Logs
JSON. Required: `timestamp` (UTC ISO 8601), `level` (`DEBUG|INFO|WARN|ERROR|FATAL`), `service`, `env`, `version`, `correlationId`, `message` (no PII). Optional: `requestId`, `durationMs`, surrogate business IDs. `DEBUG` off in production.

Never log PII (use a surrogate key), payment data (card, CVV, bank account, even partial) or credentials (passwords, PINs, OTPs, keys, tokens); no stack traces in user-facing responses.

## Metrics
- Name `<service>.<entity>.<action>[.<outcome>]`, snake_case, service prefix mandatory (`order_service.order.create.failed`); unit in metadata.
- Every service: request count, duration histogram, failures by `error_type` (`<svc>.http.request`, `.duration`, `.failed`).
- Tags bounded only (`env`, `service`, `version`, `region`, `status`, `error_type`, small enums). Forbidden: `user_id`, `order_id`, `request_id`, `trace_id`, `email`.

## Tracing
- `X-Correlation-Id` or W3C `traceparent`, propagated through calls and message attributes; generated only at the edge when absent. Spans carry no PII.
- Sample ~5% of successful traces; keeping every error trace needs tail-based sampling.

## Alerts
| Severity | Page | Response | For |
|---|---|---|---|
| P1 | immediately | 15 min | service down, data-loss risk, breach, payment/auth broken, SLA breach |
| P2 | after 30 min unresolved | 1 h | elevated errors, P99 over target, growing DLQ, exhausted connections |
| P3 | ticket | next business day | non-critical degradation, warning threshold |
| P4 | no | 3 business days / digest | informational, capacity, approaching limits |

- Name `[<Severity>] <service> — <What> <Condition>`.
- Every production service: error-rate alert, P99 latency alert, a depth alert per DLQ.
- Every alert links a runbook (meaning, triage, causes, remediation, escalation); alert on symptoms, not causes.

## SLOs
| Signal | Target | Warning |
|---|---|---|
| HTTP success rate (30 d) | ≥ 99.5% | < 99.9% |
| P99 request latency | ≤ 500 ms | > 300 ms |
| P99 DB query | ≤ 100 ms | > 50 ms |
| Queue consumer lag | < 1,000 msgs | > 500 |
| Serverless cold start P95 | ≤ 3 s | > 2 s |

Payment and auth services: success ≥ 99.9%, P99 ≤ 200 ms.

## Dashboards and health
- Dashboard `<env>-<service>-operations`: request + error rate; latency P50/P95/P99; saturation; data-store throttling; queue + DLQ depth; cost per transaction if available.
- `GET /health` → 200 with `status`, `version`, `timestamp`, per-dependency status; liveness separate from readiness.

## Cost
Tag every resource with project, environment, service, team. Budget alerts: 80% notify, 100% page. Track cost per transaction over time.
