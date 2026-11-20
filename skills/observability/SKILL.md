---
name: observability
description: |
  DataDog: APM instrumentation, custom metrics (StatsD/DogStatsD), log correlation with traces,
  dashboard design, monitor/alert configuration, and DataBricks pipeline monitoring.
  Use only when the project uses DataDog: instrumenting services with DataDog, DataDog dashboards or monitors,
  DataDog log pipelines and trace correlation, or monitoring DataBricks jobs in DataDog.
  Triggers on: DataDog, DD, dd-trace, dd-java-agent, DogStatsD, DataDog monitors/SLOs, DataBricks monitoring in DataDog.
  General standards (log format, metric naming, alert severity) live in the plugin's references/observability-patterns.md.
---

# DataDog Observability

General standards (log format, metric naming `<service>.<entity>.<action>[.<outcome>]`, severities, SLO targets, dashboards, runbooks) are in `${CLAUDE_PLUGIN_ROOT}/references/observability-patterns.md`; it wins on conflict. Data levels: `${CLAUDE_PLUGIN_ROOT}/references/data-privacy-patterns.md`. This skill is the DataDog-specific layer.

## APM

- Unified Service Tagging on every service: `DD_SERVICE`, `DD_ENV`, `DD_VERSION`.
- Java: `dd-java-agent` with `dd.logs.injection=true`, `dd.trace.db.client.split-by-instance=true`. One tracer only: no Micrometer Tracing bridge or OTel agent beside it. If the project standardizes on Micrometer/OTel, export via OTLP instead of the agent.
- Java custom spans: OTel API only (`opentelemetry-api` + `-instrumentation-annotations`, `@WithSpan`, no OTel SDK) with `dd.trace.otel.enabled=true` (agent ≥ 1.24.0). Legacy `@Trace`/OpenTracing still works; never mix both in one service.
- Go: `dd-trace-go` v2 (`github.com/DataDog/dd-trace-go/v2`, contrib under `.../contrib/<pkg>/v2`); v1 is EOL (2025-12-31) — keep only as a documented migration exception. Check `go.mod` before use. `tracer.Start` with service/env/version, explicit startup-failure policy, `defer tracer.Stop()`.
- Span tags: categories only (currency, method type, provider, sanitized `error.type`). Never amounts, account numbers, raw provider errors or other Level 2+ data.

## Metrics

- Java: Micrometer DataDog registry with common tags `service`, `env`. Go: `datadog-go/v5` statsd with `WithNamespace("<service>.")` and `env` tag.
- Types: Count (events), Gauge (point value: queue depth, pool), Histogram (per-host distribution), Distribution (globally aggregated — use for percentiles across hosts), Rate.
- Instrument per operation: duration timer, success count, failure count tagged `error_type`.
- Tags must be bounded (status, endpoint, error type). Never `user_id`, account, order ID or PII.

## Log correlation

- Logs carry `dd.trace_id`, `dd.span_id`, `dd.service`, `dd.env`, `dd.version`.
- Go v2 manual injection: `TraceID()` is a 128-bit hex **string**, `TraceIDLower()` is `uint64`. Emit decimal lower-64 for a 64-bit pipeline, or the full 128-bit string only if the DataDog pipeline accepts it; never truncate implicitly. Log only allowlisted attributes.
- Log pipeline: JSON parser; remap `level` → `status`; `correlationId` as facet; `service`/`env`/`version` from attributes or agent tags; exclude DEBUG in prod.

## Monitors and SLOs

- Manage as code (Terraform `datadog_monitor`, `datadog_service_level_objective`).
- Alert on error *rate* (failed / total `.as_rate()`), not individual errors. Default example: critical 5 %, warning 2 % over `last_5m`.
- Evaluation window ≥ 5 min (1 min flaps). `notify_no_data` with `no_data_timeframe`, `renotify_interval`, recovery message. Tags `service`, `env`, `team`.
- Every P1/P2 monitor message links a runbook and the on-call handles.
- Group-by only bounded tags (`endpoint`, `error_type`), never `user_id`.
- Types: metric, APM (p99 latency, per-endpoint error rate), log, composite (error AND latency → P1), anomaly, SLO burn rate.
- SLO: metric-based good/total over 30 d, e.g. target 99.9 / warning 99.95.

## Dashboards

Sections in order: overview (rate, errors, p50/p95/p99 always visible) → endpoints → dependencies (downstream, DB, cache hit) → infrastructure (CPU, memory, JVM heap / goroutines) → business metrics.

## DataBricks

| Metric | Emit | Alert |
|---|---|---|
| Job success/failure | DD integration or webhook | Any failure (P2) |
| Duration | Job wrapper | > 2× historical average (P3) |
| Records processed | Spark job | Drop > 50 % vs expected (P2) |
| Data-quality checks | Pass/fail counts | Any critical fail (P1) |
| Cluster utilization | DD–DataBricks integration | Sustained > 80 % or < 20 % |
| Cost per job | Billing API | Over budget (P3) |

Job wrapper emits status, records and duration under `databricks.` with `job` and `env` tags in `try/except/finally`; API key from `dbutils.secrets`, never inline.

## Scope

Always instrument: endpoints, DB queries, outbound HTTP (latency, errors, timeouts), consumers (processing time, failures, DLQ sends), business events, cache (hit/miss/eviction). Never: per-user metrics, debug-level ops in prod, PII in tags or log attributes.
