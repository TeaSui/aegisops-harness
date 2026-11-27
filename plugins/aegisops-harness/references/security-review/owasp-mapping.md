# OWASP edition and finding mapping

Use the project's required OWASP Top 10 edition, else **2025** (`checklist.md`). State the edition in the report and qualify every ID (`A01:2025`, `A01:2021`, `A1:2017`).

2025 index: A01 Broken Access Control · A02 Security Misconfiguration · A03 Software Supply Chain Failures · A04 Cryptographic Failures · A05 Injection · A06 Insecure Design · A07 Authentication Failures · A08 Software or Data Integrity Failures · A09 Security Logging and Alerting Failures · A10 Mishandling of Exceptional Conditions. (SSRF moved into A01:2025; `A10:2021` is SSRF — numbers do not carry across editions.)

## Procedure
1. Identify the concrete weakness, affected asset/boundary and STRIDE finding before choosing a category.
2. Verify the category description at the official source for the selected edition; a label or position alone is not enough.
3. Record finding ID, edition-qualified category, source link, rationale, rule IDs and verification evidence; explain the primary cause when several categories apply.
4. Record risks outside the edition's Top 10 as such; for each category with no finding, state non-applicability or the coverage limit.
5. Keep historical mappings with their original edition; never silently rename old IDs or claim a one-to-one crosswalk.

Older editions: 2021 → top10.owasp.org/2021; 2017 → owasp.github.io/www-project-top-ten/2017 (XXE, XSS, deserialization separate). Build coverage from that edition. Unverifiable edition → state the gap, mark the mapping unverified; never substitute recall.
