---
name: fintech-security
description: Fintech security control catalogue (Spring Boot, Go, AWS serverless) — candidate controls for auth, payments, KYC documents, crypto and keys, logging, network, rate limits and secrets under the security rule prefixes; Read by tea-sdlc:security-engineer-subagent in /tea-sdlc:spec and by /tea-sdlc:fix for its security pass when the trust-boundary check says yes.
disable-model-invocation: true
user-invocable: false
---

# Fintech Security Control Catalogue

Candidate controls — cite one only when a STRIDE finding earns it; this is a lookup list, not a template.

- **`/tea-sdlc:fix` (escape hatch):** the main session uses it for the short security pass in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` — assets, threats, controls; no subagent.
- **`/tea-sdlc:spec`:** threat model, rule numbering and output format (the spec's `### Security`) belong to `tea-sdlc:security-engineer-subagent`. Copy the control into a numbered rule under its section prefix (`AUTH-NN`, `AUTHZ-NN`, `INPUT-NN`, `CRYPTO-NN`, `DATA-NN`, `LOG-NN`, `NET-NN`, `RATE-NN`, `DEP-NN`, `SECRET-NN`, `COMPLIANCE-NN`; payment controls under `DATA`), phrased as what must be true, citing the finding.

Numbers marked **(default — project must confirm)** are starting points, not regulatory facts; confirm with the compliance owner before they become rules. Name frameworks (MAS TRM Guidelines, MAS Notice on Cyber Hygiene, PCI DSS, PDPA) without clause numbers unless checked against the current text. Data levels (Level 1 highly sensitive … Level 3 internal): `${CLAUDE_PLUGIN_ROOT}/references/data-privacy-patterns.md`.

## AUTH

- MFA for customer financial transactions; step-up (separate factor) for high-value transfers and transaction signing. New device → step-up before financial operations.
- Idle timeout 15 min financial, 30 min otherwise **(default — project must confirm)**.
- Lockout after 5 failed logins with progressive delay **(default — project must confirm)**; no account enumeration or targeted-lockout DoS.
- JWT: verify signature, pinned algorithm (reject `none`/confusion), `exp`, `iss`, `aud`; asymmetric (RS256/ES256) when verifiers are separate services. Go: `golang-jwt/jwt/v5`, never abandoned `dgrijalva/jwt-go`.
- Spring `SecurityFilterChain` ends `.anyRequest().authenticated()`; specific matchers first.

## AUTHZ

- Object-level ownership check on every resource access.
- Spring `@PreAuthorize` on sensitive service methods, not URL matchers alone.
- DTOs never bind role, owner, balance or status (no mass assignment).
- Admin actions need a distinct role and are audit-logged.

## INPUT

- Validate at the boundary (Spring `@Valid` on every `@RequestBody`; Go in the handler before logic).
- Parameterized queries only; never string-built SQL.
- Body limits 1 MB JSON, 10 MB per upload **(default — project must confirm)** (`http.MaxBytesReader`, Spring multipart limits).
- No Jackson polymorphic default typing; Go `DisallowUnknownFields` for closed contracts; ReDoS-safe regex.
- Go `html/template` only; paths `filepath.Clean` + base-dir containment.
- Amounts positive, within limits, fraction digits ≤ ISO 4217 exponent (VND/KRW 0, SGD/USD 2, KWD/BHD 3).

## CRYPTO

- Level 1 data encrypted at rest with customer-managed KMS keys; field-level encryption for national ID and account numbers.
- KMS keys: KMS automatic rotation. Secrets: Secrets Manager rotation, ≤ 90 days **(default — project must confirm)**. KMS keys are not rotated by Secrets Manager.
- Passwords/PINs: memory-hard hash tuned to hardware; never reversible.
- Provider webhooks: signature (typically HMAC-SHA256), constant-time compare, timestamp replay window.
- Money: integer minor units or decimal (`BigDecimal`, `shopspring/decimal`, `math/big`); never float; guard Go integer overflow.

## DATA (incl. payments)

- No PII in logs, URLs, error responses, metric tags or queue metadata.
- Generic client errors; details server-side only. Spring prod: no `include-stacktrace=always`, no `show-sql=true`.
- PCI DSS: never store CVV or full PAN; provider tokenization.
- KYC documents: separate bucket, SSE-KMS (CMK), Block Public Access, pre-signed upload/view URLs with 5-min expiry **(default — project must confirm)**, server-side MIME check, malware scan before processing, no PII in object keys, OCR in memory only.
- Retention: transaction records 7 years, KYC documents 5 years after relationship end, then hard delete **(defaults from data-privacy-patterns.md — project must confirm with its compliance owner and jurisdiction)**.
- Payments: idempotency key on every payment-creating endpoint; double-entry ledger; optimistic locking on balances (version column / DynamoDB conditional write); forward-only state machine `INITIATED → PENDING → COMPLETED|FAILED`; daily provider reconciliation; 3DS2 for cards where applicable.

## LOG

- Every financial transaction: who, what, when, from where, result.
- Audit logs tamper-evident: S3 Object Lock (WORM) or hash chain; CloudTrail all regions with log file validation.
- Audit retention 7 years financial, 5 years access logs **(default — project must confirm)**.
- Real-time alerts: privilege escalation, bulk export, out-of-hours admin actions.

## NET

- TLS 1.2 minimum, 1.3 preferred (floor 1.3 only where all clients support it); Go `MinVersion: tls.VersionTLS12`.
- Go: HTTP clients set a timeout; `http.Server` sets `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout`.
- CORS explicit origins; never `*` with credentials or in production.
- CSRF stays on whenever the browser sends credentials automatically (session/JWT cookies, Basic); disable only on an Authorization-header-only chain with no cookie path — statelessness alone is not a defense.
- S3 policies deny non-TLS; Lambda in a VPC only when it needs VPC resources.
- Actuator: only `/health`, `/info` public. Go `pprof` on a separate non-public port.

## RATE

- Rate limits on auth and OTP endpoints (Bucket4j, API Gateway usage plans, WAF rate rules).
- Configurable per-transaction and daily limits; velocity checks.
- New-payee cool-down 12 hours **(default — project must confirm)**.
- Max page size on every list endpoint. Kill switch per transaction type, effective within minutes.
- Go: every goroutine has a context exit; no unbounded fan-out.

## DEP

- Dependency and image scanning in CI (Trivy, Grype, Snyk); SBOM per build (Syft or Trivy). No abandoned security-critical libraries.

## SECRET

- No secrets in Lambda env vars, IaC, images or committed `.env`: Secrets Manager or SSM SecureString at runtime. Spring config only `${ENV_VAR}` or a secrets backend.
- Review for `AKIA[0-9A-Z]{16}`, `-----BEGIN (RSA |EC )?PRIVATE KEY-----`, `eyJ…\.eyJ…\.`, passworded connection strings, hardcoded OTP seeds/HMAC keys.
- gitleaks pre-commit; trufflehog or detect-secrets (baseline) in CI.

## COMPLIANCE

- MAS TRM / Cyber Hygiene: MFA, session controls, audit trail, notification for every financial transaction, customer-configurable limits.
- PCI DSS: tokenization, no CVV/full PAN, scoped cardholder-data environment.
- PDPA: purpose limitation, consent before Level 1/2 collection, retention/deletion per data-privacy-patterns.md.
- Unclear compliance scope → escalate (in a spec: `tea-sdlc:security-engineer-subagent`; in `/tea-sdlc:fix`: stop and name `/tea-sdlc:aidlc`), never guess.

## AWS serverless checks

| Check | Prefix |
|---|---|
| Authorizer on every API Gateway method; WAF on public APIs | AUTH / RATE |
| DynamoDB with Level 1 data uses a CMK | CRYPTO |
| SQS encrypted (SSE-SQS minimum, SSE-KMS for PII) | CRYPTO |
| IAM scoped to ARNs; wildcards need written justification | AUTHZ |
| EventBridge consumers validate `source`, `detail-type`, payload schema | INPUT |
