---
name: database-patterns
description: |
  Database query and design patterns: CTE-first query approach for MySQL/PostgreSQL, indexing strategies,
  zero-downtime migrations, DynamoDB single-table access pattern design, and Redis caching/data structures.
  Use when: writing SQL queries, designing database indexes, planning migrations, modeling DynamoDB access patterns,
  implementing Redis caching, or optimizing query performance.
  Triggers on: SQL, CTE, common table expression, query, index, migration, DynamoDB access pattern,
  single-table design, Redis, cache, PostgreSQL, MySQL, database performance.
---

# Database Patterns

## Queries (MySQL 8+ / PostgreSQL)
- CTE-first: multi-step logic and nested subqueries become named CTEs, one step per CTE. Skip CTEs for single-table lookups. On a hot path, profile first and use a subquery if the planner does better. MySQL < 8.0 has no CTEs.
- Recursive CTEs carry a depth guard (`WHERE depth < 10`). MySQL has no arrays: build the path as `CONCAT` of `LPAD(id, 20, '0')` and size the base `CAST(... AS CHAR(n))` for max depth (strict mode errors on overflow).
- Postgres upsert: `INSERT … ON CONFLICT (…) DO UPDATE SET …, updated_at = NOW() RETURNING *`.
- No `SELECT *` in production; no N+1 (JOIN or batch fetch); window functions for running totals/moving averages.

## Indexes
- Index columns used in WHERE/JOIN/ORDER BY, and every FK column. Skip low-cardinality booleans. Index actual query patterns only (each index slows writes).
- Composite indexes follow the leftmost prefix. Use partial indexes (Postgres) for queried subsets, expression indexes for `LOWER(email)`, covering indexes to avoid table lookups. MySQL prefix indexes for long strings. `FORCE INDEX` is a last resort.
- `EXPLAIN ANALYZE` before and after; the index must actually be used.

## Zero-downtime migrations (expand-contract)
1. Expand: add the new column nullable; deploy code writing both.
2. Backfill in batches by key range (`WHERE new IS NULL AND id BETWEEN $1 AND $2`).
3. Switch reads to the new column; verify.
4. Contract: drop the old column in a later deploy. Keep the new name — renaming back breaks running instances (needs a second expand-contract).

Rules:
- Never drop a column in the same deploy as the code change.
- New columns are nullable or have a server-side DEFAULT (no `NOT NULL` without default).
- Postgres: `CREATE INDEX CONCURRENTLY`; set a `lock_timeout`; prefer metadata-only changes (nullable `ADD COLUMN`, non-volatile DEFAULT on PG 11+); `ADD CONSTRAINT … NOT VALID` then `VALIDATE CONSTRAINT`; type changes and other table rewrites go through expand-contract. `pg_repack` only removes bloat.
- MySQL tables > 1M rows: `gh-ost` or `pt-online-schema-change`.
- Test migrations on a production-size dataset.
- Flyway naming: `V<n>__<snake_description>.sql`; repeatable `R__<description>.sql`.

## DynamoDB (single-table)
- List access patterns first, then design PK/SK and GSIs, and document them as an access-pattern table (pattern → PK, SK, GSI).
- Keys are typed prefixes: `CUSTOMER#<id>` / `ORDER#<ts>#<id>`. Query with `begins_with(SK, …)`, `ScanIndexForward=false` for newest first, and a `Limit`.
- Each extra access pattern on the same items needs its own GSI (GSI1, GSI2 …), not a second value on GSI1.
- No constant partition keys (`ALL_ORDERS`): write-shard as `ORDERS#<yyyy-mm-dd>#<shard 0..N-1>`, query shards in parallel and merge. Shard a dominant `STATUS#<status>` the same way.
- No Scans (a scan means a missing index/GSI).
- Items ≤ 400 KB; store blobs in S3 by key.
- Eventually consistent reads (half the cost) unless strong consistency is required.

## Redis
- Types: STRING cache/`INCR`+`EXPIRE` rate limit; HASH object/session; ZSET ranking; LIST+`LTRIM` feeds; SET/HyperLogLog uniques. Locks use `SET lock:<res> <owner> NX EX 30`.
- Keys: `<entity>:<id>`, `<entity>:<id>:<field>`, `<entity>:list:<filter>:<page>`, `rate:<scope>:<window>`, `lock:<resource>`.
- Cache-aside; every key has a TTL (e.g. 30 min) even with active invalidation.
- Invalidate only after commit (`@TransactionalEventListener(phase = AFTER_COMMIT)` or an outbox/CDC consumer), never inside the transaction.
- Protect hot keys from stampedes (lock or probabilistic early expiry). Never cache errors.
