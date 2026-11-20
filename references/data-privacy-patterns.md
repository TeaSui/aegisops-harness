# Data privacy patterns

Defaults for a Singapore fintech; the project's verified jurisdiction and policy override. Cite the regulation before relying on any deadline or period.

## Classification
| Level | Data | Controls |
|---|---|---|
| 1 Highly sensitive | national ID/passport, account and card numbers, biometrics, full DOB + name, credentials (passwords, PINs, OTPs) | encrypt at rest (customer-managed KMS key) and in transit; audit every access |
| 2 Sensitive | email, phone, address, transaction amounts/history, KYC status and documents, user-linked device IDs | encrypt at rest (AWS-managed KMS minimum) and in transit |
| 3 Internal | anonymized aggregates, logs with user IDs only, per-segment flags | encrypt in transit |

## Rules
- Data minimization; explicit consent before Level 1/2 collection; purpose documented per data type.
- Never store full PAN or CVV: tokenize (e.g. PSP tokens). Encrypt Level 1 fields at the application layer; keep PII in a separate table, referenced by `userId`; no PII in keys.
- Retention defined and enforced (defaults): transactions 7 years; KYC 5 years after relationship end; sessions 90 days; logs with user data 1 year.
- Never log raw PII. Masks: email `us***@example.com`, phone `+65****1234`, account `****5678`.
- No PII in error messages, URLs or query strings; responses carry no more PII than the request scope needs.
- TLS 1.2 minimum, 1.3 preferred; queues holding PII encrypted at rest.
- Singapore residents' data stays in `ap-southeast-1` by default; cross-region replication needs a DPA; no PII to inadequate jurisdictions without legal approval; register every third-party processor.
- LLMs: never send raw PII to an external LLM API; pseudonymize (`[USER_A]`) or use a VPC-hosted model.
- Data subject rights: deletion = hard delete + backup purge for Level 1/2; export JSON/CSV; a tested `deleteUser(userId)`.
- Breach deadlines come from the incident policy and cited regulation; log detection time, scope, affected record count, remediation.
