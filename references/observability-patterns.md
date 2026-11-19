# Observability Standards

Platform-agnostic standards for structured logging, metrics, tracing, alerting, dashboards and health checks. Thresholds and targets are starting defaults; the project's telemetry stack, SLOs and on-call policy override them. Vendor implementations: `references/aws-patterns.md` (CloudWatch, Lambda Powertools), `skills/observability/SKILL.md` (Datadog).

## Structured Logging

All services emit structured JSON logs.

```json
{
  "timestamp": "2026-01-15T10:30:00.000Z",
  "level": "INFO",
  "service": "order-service",
  "env": "prod",
  "version": "1.2.3",
  "correlationId": "req-abc-123",
  "message": "Order created",
  "durationMs": 145,
  "orderId": "ord-456"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `timestamp` | yes | ISO 8601, always UTC |
| `level` | yes | `DEBUG` \| `INFO` \| `WARN` \| `ERROR` \| `FATAL` |
| `service` | yes | Matches the service registry name |
| `env` | yes | `dev` \| `staging` \| `prod` |
| `version` | yes | Matches the deployed artifact |
| `correlationId` | yes | Propagated across service calls (see Tracing) |
| `message` | yes | Human-readable; no PII |
| `requestId` | when available | Platform request ID |
| `durationMs` | for timed operations | |
| business IDs | as needed | Surrogate keys (`customerId`, `orderId`), never PII |

| Level | Use for |
|-------|---------|
| `DEBUG` | Detailed flow for local development; off in production by default |
| `INFO` | Key business events: request served, order created, job completed |
| `WARN` | Recoverable anomalies: retry, fallback, deprecated API, approaching a limit |
| `ERROR` | Operation failed or request could not be served; exception caught at a boundary |
| `FATAL` | Process-aborting condition; alerts immediately |

**Never log:**
- PII: names, emails, phone numbers, national IDs, addresses — mask or omit (`references/data-privacy-patterns.md`). When PII context is needed for debugging, log a surrogate key and join externally.
- Payment data: card numbers, CVV, bank account numbers (even partial).
- Credentials: passwords, PINs, OTPs, API keys, tokens, secrets.
- Stack traces in user-facing responses (server-side logs only).
- High-volume debug output in production.

## Metrics

**Naming:** `<service>.<entity>.<action>[.<outcome>]`, `snake_case` throughout.
- The service prefix is mandatory — never a bare `order.created`.
- An outcome suffix (`failed`, `timeout`, `rejected`) separates error counts from totals.
- Record the unit in the metric metadata (e.g. milliseconds), not only in the name.

```
order_service.order.created              # counter
order_service.order.create.duration      # histogram / timer
order_service.order.create.failed        # counter (error path)
payment_service.payment.authorize.duration
payment_service.payment.authorize.failed
```

**Standard signals for every service:** request count, request duration (histogram), failed requests by `error_type`, and success rate derived from them — e.g. `order_service.http.request`, `order_service.http.request.duration`, `order_service.http.request.failed`.

**Dimensions / tags** — keep cardinality bounded:

| Good (bounded) | Example values |
|----------------|----------------|
| `env` | `prod`, `staging`, `dev` |
| `service` | `order-service` |
| `version` | `1.2.3` |
| `region` | `ap-southeast-1` |
| `status` | `success`, `failed`, `timeout` |
| `error_type` | `ValidationError`, `TimeoutError` |
| `payment_method` | `card`, `wallet`, `bank_transfer` |

Forbidden (unbounded, and some are PII): `user_id`, `order_id`, `request_id` / `trace_id` (use logs for per-request correlation), `email`.

## Distributed Tracing

- Every request carries a correlation ID: `X-Correlation-Id`, or `traceparent` for W3C Trace Context. Inject it on outbound calls and extract it on inbound ones.
- Async messages (queues, streams, workflows): put the correlation ID in message attributes/headers.
- Generate a new ID only at the edge (API gateway or consumer entry point) when none arrived; never mid-flow.
- Spans include service name, operation, duration, status and key attributes (no PII).
- Sampling: choose a production success-trace rate (e.g. 5%). Keeping every error trace needs tail-based sampling or error-triggered retention; a head-based sampler decides before the outcome is known, so it cannot guarantee it.

```typescript
// Edge: reuse an incoming correlation ID, else create one
const correlationId = headers['x-correlation-id'] ?? crypto.randomUUID();
const log = logger.child({ correlationId });
```

## Alerting

| Severity | Page on-call? | Response | Use for |
|----------|---------------|----------|---------|
| **P1 — Critical** | Yes, immediately | 15 min | Service down, data loss risk, security breach, payment or auth broken, SLA breach |
| **P2 — High** | Yes, after 30 min if not auto-resolved | 1 hour | Elevated error rate, P99 latency over target, DLQ depth growing, connections exhausted |
| **P3 — Medium** | No (ticket) | Next business day | Non-critical degradation, warning threshold crossed, single-host anomaly |
| **P4 — Low** | No | 3 business days / digest | Informational, capacity signals, approaching (not breaching) limits |

**Alert naming:** `[<Severity>] <service> — <What> <Condition>`, e.g. `[P2] payment-service — P99 latency > 3s for 10 min`.

**Required for every production service:** error-rate alert, P99 latency alert, and a DLQ-depth alert for every dead-letter queue.

**Avoid alert fatigue:**
- No alert without a runbook.
- Alert on symptoms (user impact), not causes.
- Group related alerts.
- Set meaningful thresholds — not "alert on any error".

## SLO Targets (starting points)

| Signal | Target | Warning |
|--------|--------|---------|
| HTTP success rate | ≥ 99.5% (30-day window) | < 99.9% |
| P99 request latency | ≤ 500 ms | > 300 ms |
| P99 DB query time | ≤ 100 ms | > 50 ms |
| Queue consumer lag | < 1,000 messages | > 500 messages |
| Serverless cold start P95 | ≤ 3 s | > 2 s |

Payment and auth services start stricter: success rate ≥ 99.9%, P99 latency ≤ 200 ms. Override per service based on business criticality.

## Dashboards

Minimum per service, named `<env>-<service>-operations`:
1. Request rate and error rate, side by side
2. Latency P50 / P95 / P99
3. Compute saturation (duration and cold starts for serverless; CPU/memory for containers)
4. Data store capacity and throttling
5. Queue depth and DLQ depth
6. Cost per hour or per transaction, when the platform exposes it

## Health Checks

Every API service exposes a health endpoint (`GET /health` → 200):

```json
{
  "status": "healthy",
  "version": "1.2.3",
  "timestamp": "2026-01-15T10:30:00Z",
  "dependencies": { "database": "healthy", "queue": "healthy", "external-api": "degraded" }
}
```

- Liveness: is the process running? (simple ping)
- Readiness: can the service handle traffic? (checks dependencies)

## Runbooks

Every P1/P2 alert links to a runbook in the project's runbook location, covering:
1. What the alert means
2. Immediate triage steps
3. Common root causes
4. Remediation steps
5. Escalation path

## Cost Observability

- Tag all cloud resources with project, environment, service and team.
- Budget alerts: 80% of the monthly budget → notify, 100% → page.
- Review cost per service regularly; track cost per transaction over time.
