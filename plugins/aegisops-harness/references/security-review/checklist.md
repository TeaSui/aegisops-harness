# Security review checklist

Default **OWASP Top 10:2025**; a project-required edition wins, every ID edition-qualified, mapped per `owasp-mapping.md` (never by position). Decide applicability from assets, boundaries and the threat model; record evidence, gaps and justified non-applicability; keep mobile, infra, AI and regulatory risks outside the web Top 10. A ticked box is not a verdict: each applicable control maps to a finding, rule or evidence.

House checks beyond standard OWASP guidance:
- **A01 Broken Access Control:** ownership checked at every boundary, default deny; tenant separation and privilege changes tested with authorized test identities; SSRF (in A01 since 2025): restrict server-side fetch destinations.
- **A02 Security Misconfiguration:** no prod debug or default credentials; XML external entities/DTDs off; storage, network, runtime permissions reviewed.
- **A03 Supply Chain:** dependencies scanned per project policy; build inputs and artifacts from approved origins; CI and signing credentials scoped.
- **A04 Cryptographic Failures:** project-approved algorithms and KMS; key access audited, rotation and recovery defined; retention and deletion per jurisdiction.
- **A05 Injection:** parameterized SQL, validated NoSQL operators, no untrusted text in OS commands, contextual output encoding (CSP is defence in depth only).
- **A06 Insecure Design:** abuse cases and business invariants in the threat model; idempotency keys and transaction boundaries preserve money/business effects across retries.
- **A07 Authentication Failures:** Argon2id (or approved bcrypt), unique salts; lockout that cannot lock victims out; session rotation on login/privilege change; expiry, revocation, logout tested; reset tokens scoped, time-limited, single-use; cookies Secure/HttpOnly/SameSite.
- **A08 Integrity Failures:** no untrusted deserialization into arbitrary types; signatures verified where the trust model needs it.
- **A09 Logging and Alerting:** security events with safe IDs and outcomes; no credentials, payloads or PII; tamper-protected; alerts tested with assigned responders.
- **A10 Exceptional Conditions:** fail closed, no stack traces to clients; timeouts, exhaustion and partial failure keep invariants; bounded retries; unexplained 5xx investigated with redacted evidence.
- **Cross-cutting:** allowlist validation, length/depth limits, upload and Content-Type checks; no secrets in source, images or diagnostics; secrets fetched at runtime from the approved store, identifiers never confused with values.
