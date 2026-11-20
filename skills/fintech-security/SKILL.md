---
name: fintech-security
description: |
  Reference for drafting or reviewing security rules in fintech code (Spring Boot, Go, AWS serverless):
  candidate controls for auth, payments, KYC documents, crypto/keys, logging, network, rate limits and secrets,
  mapped onto the security agent's rule prefixes. In lean mode the main session uses it for its own security pass;
  in full mode threat models are produced by tea-sdlc:security-engineer-subagent.
  Triggers on: payment security, KYC document handling, MAS/PDPA control lookup, fintech security review.
---

# Fintech Security Control Catalogue

**Candidate controls — cite only when earned by a STRIDE finding.** This is a lookup list, not a template. In lean mode (the default) the main session uses this catalogue for the short security pass in `${CLAUDE_PLUGIN_ROOT}/rules/workflow-routing.md` (assets, threats, controls; no `security.md`). In full mode the threat model, rule numbering and output format belong to `tea-sdlc:security-engineer-subagent` (`${CLAUDE_PLUGIN_ROOT}/agents/security-engineer-subagent.md`, Phase 3–4). When a finding needs a control, copy the idea below into a numbered rule under the matching prefix (`AUTH-NN`, `DATA-NN`, …), phrase it as WHAT must be true, and cite the finding.

Numbers marked **(default — project must confirm)** are starting points, not regulatory facts. Confirm them against the project's compliance owner before they become rules. Compliance references name the framework (MAS TRM Guidelines, MAS Notice on Cyber Hygiene, PCI DSS, PDPA) without chapter numbers; cite a section only after checking the current published text.

Classification levels follow `${CLAUDE_PLUGIN_ROOT}/references/data-privacy-patterns.md` (Level 1 highly sensitive … Level 3 internal).

## AUTH — authentication & session

- MFA for customer-facing financial transactions; step-up (separate factor) for high-value transfers and transaction signing.
- Device binding: a new device requires step-up authentication before financial operations.
- Idle session timeout: 15 min for financial operations, 30 min otherwise **(default — project must confirm)**.
- Failed-login lockout after 5 attempts with progressive delays **(default — project must confirm)**; lockout must not enable account-enumeration or targeted lockout DoS.
- JWT validation checks signature, algorithm (pinned; reject `none` and algorithm confusion), `exp`, `iss`, `aud`. Prefer asymmetric signing (e.g. RS256/ES256) when verifiers are separate services.
- Spring: `SecurityFilterChain` ends in `.anyRequest().authenticated()`; more specific matchers before generic ones.
- Go: use a maintained JWT library (e.g. `github.com/golang-jwt/jwt/v5`; `dgrijalva/jwt-go` is abandoned).

## AUTHZ — authorization

- Object-level checks on every resource access (the caller owns or may act on the account/payment ID).
- Spring: method-level `@PreAuthorize` on sensitive service operations; do not rely on URL matchers alone.
- No mass assignment: request DTOs never bind role, owner, balance or status fields.
- Admin actions require a distinct role and are audit-logged (see LOG).

## INPUT — validation & output encoding

- Validate at the boundary: Spring `@Valid` + Bean Validation on every `@RequestBody`; Go validation in the handler before business logic.
- Parameterized queries only (`$1`, `?`, JPA parameters); never `fmt.Sprintf`/string concatenation into SQL.
- Request size limits: 1 MB JSON body, 10 MB per upload **(default — project must confirm)**; Go `http.MaxBytesReader`, Spring multipart limits.
- Untrusted JSON: no Jackson polymorphic default typing; Go `json.Decoder` with `DisallowUnknownFields` where the contract is closed.
- Regex in validators must be safe against catastrophic backtracking.
- Go HTML: `html/template`, never `text/template`; file paths: `filepath.Clean` + base-directory containment check.
- Payment amounts: positive, within limits, and no more fraction digits than the currency's ISO 4217 exponent (0 for VND/KRW, 2 for SGD/USD, 3 for KWD/BHD).

## CRYPTO — encryption, hashing, keys

- Level 1 data encrypted at rest with customer-managed KMS keys; field-level encryption for national ID and account numbers.
- Key rotation: KMS keys use **KMS automatic key rotation** (verify the rotation period options in current KMS docs); secrets (DB passwords, API keys) rotate via **Secrets Manager rotation**. Do not describe KMS keys as rotated by Secrets Manager. Rotation interval for secrets: ≤ 90 days **(default — project must confirm)**.
- Passwords/PINs hashed with a memory-hard algorithm tuned to the target hardware; never reversible encryption.
- Webhook callbacks from payment providers verified with the provider's signature scheme (typically HMAC-SHA256) using constant-time comparison and a timestamp/replay window.
- Money arithmetic: integer minor units or a decimal type (`shopspring/decimal`, `math/big`, `BigDecimal`); never floating point. Guard against silent integer overflow in Go.

## DATA — handling, PII, retention

- No PII in logs, URLs, error responses, metric tags or message-queue metadata/attributes.
- Error responses to clients are generic; details stay in server logs. Spring: no `server.error.include-stacktrace=always`, no `spring.jpa.show-sql=true` in production.
- PCI DSS: never store CVV or full PAN; use provider tokenization.
- KYC documents: separate bucket, SSE-KMS with a customer-managed key, Block Public Access, upload and view via pre-signed URLs with 5-minute expiry **(default — project must confirm)**, MIME type validated server-side, malware scan before processing, no PII in object keys, OCR results processed in memory (no temp files).
- Retention: financial transaction records 7 years, KYC documents 5 years after relationship end, then hard delete **(defaults from data-privacy-patterns.md — project must confirm with its compliance owner and jurisdiction)**.
- Payments: idempotency key on every payment-creating endpoint; double-entry ledger; optimistic locking on balances (version column or DynamoDB conditional write); forward-only state machine (`INITIATED → PENDING → COMPLETED|FAILED`); daily reconciliation against the provider; 3DS2 for card payments where applicable.

## LOG — logging & audit

- Every financial transaction records who, what, when, from where, and result.
- Audit logs are append-only/tamper-evident: S3 Object Lock (WORM) or a hash chain; CloudTrail in all regions with log file validation.
- Audit retention: 7 years for financial transactions, 5 years for access logs **(default — project must confirm)**.
- Real-time alerts on privilege escalation, bulk data export, and admin actions outside business hours.

## NET — network, TLS, CORS

- **TLS 1.2 minimum, TLS 1.3 preferred** for external and inter-service traffic; raise the floor to 1.3 only where every client supports it. Go: `tls.Config{MinVersion: tls.VersionTLS12}`.
- Go HTTP clients set an explicit timeout (the default client has none); `http.Server` sets `ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`, `IdleTimeout`.
- CORS: explicit allowed origins; never `*` with credentials or in production.
- CSRF: keep protection whenever the browser sends credentials automatically (session cookies, JWT cookies, HTTP Basic). Disable only on an Authorization-header-only resource-server chain with no cookie alternative; statelessness alone is not a CSRF defense ([Spring CSRF considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)).
- S3 bucket policies deny non-TLS requests; Lambda attaches to a VPC only when it needs VPC resources.
- Spring Actuator: only `/health` and `/info` public; `env`, `beans`, `configprops` require an admin role or stay unexposed. Go `pprof` on a separate, non-public port.

## RATE — rate limiting, quotas, DoS

- Rate limits on authentication and OTP endpoints (Bucket4j, API Gateway usage plans or WAF rate rules).
- Per-transaction and daily limits, configurable; velocity checks flag unusual frequency or amounts.
- Cool-down before a newly added payee can receive funds: 12 hours **(default — project must confirm)**.
- Pagination with a max page size on every list endpoint.
- Kill switch to disable a transaction type within minutes.
- Go: every goroutine has a context-based exit; no unbounded fan-out.

## DEP — dependencies & supply chain

- Dependency and image scanning in CI (e.g. Trivy, Grype, Snyk); SBOM per build (Syft or Trivy).
- No abandoned security-critical libraries (see the JWT note under AUTH).

## SECRET — secrets management

- No secrets in Lambda environment variables, IaC source, images or committed `.env` files: Secrets Manager or SSM SecureString, retrieved at runtime.
- Spring `application.yml`: secrets only via `${ENV_VAR}` placeholders or a secrets backend.
- Review patterns: AWS access keys (`AKIA[0-9A-Z]{16}`), private key headers (`-----BEGIN (RSA |EC )?PRIVATE KEY-----`), JWTs (`eyJ…\.eyJ…\.`), connection strings with passwords, hardcoded OTP seeds/HMAC keys.
- Tooling: gitleaks pre-commit; trufflehog or detect-secrets (baseline mode) in CI.

## COMPLIANCE — MAS, PCI DSS, PDPA

- MAS TRM / Cyber Hygiene: MFA, session controls, audit trail, transaction notifications (SMS/push for every financial transaction), customer-configurable limits. Map each to a specific clause only after checking the current text.
- PCI DSS: tokenization, no CVV/full PAN storage, scoped cardholder-data environment.
- PDPA: purpose limitation, consent before Level 1/2 collection, retention and deletion per `data-privacy-patterns.md`.
- Unclear compliance scope is an escalation for the security agent, not a guess.

## AWS serverless quick checks

| Check | Prefix |
|---|---|
| Authorizer on every API Gateway method; WAF on public APIs | AUTH / RATE |
| DynamoDB tables with Level 1 data use a customer-managed KMS key | CRYPTO |
| SQS encrypted at rest (SSE-SQS minimum, SSE-KMS for PII) | CRYPTO |
| IAM scoped to specific ARNs; wildcards need a written justification | AUTHZ |
| EventBridge consumers validate `source`/`detail-type` and the payload schema | INPUT |
