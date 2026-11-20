---
name: data-pipeline-patterns
description: |
  Data pipeline and ETL patterns: PySpark/DataBricks pipeline structure, Delta Lake operations,
  incremental processing (watermarks, CDC), data quality frameworks (Great Expectations, dbt tests),
  SCD Type 2, star schema modeling, and pipeline orchestration patterns.
  Use when: building ETL/ELT pipelines, designing data warehouse models, implementing data quality checks,
  working with DataBricks/Spark, designing incremental loads, or implementing slowly changing dimensions.
  Triggers on: ETL, ELT, data pipeline, DataBricks, Spark, PySpark, Delta Lake, data warehouse,
  star schema, SCD, data quality, Great Expectations, dbt, incremental load, CDC.
---

# Data Pipeline Patterns

## Structure
- `src/pipelines/<name>/{extract,transform,load,schema}.py`; `src/common/{spark_session,delta_utils,quality,observability}.py`; `src/config/{dev,prod}.yaml`; `tests/{unit,fixtures}`; optional `dbt/`.
- Production pipelines are tested, version-controlled Python modules, never notebooks (exploration only).
- Config from YAML + environment variables; no hardcoded connection strings.
- `transform` is a pure function. Add `_loaded_at`.
- Validate the expected schema at extract (fail fast on missing columns, cast to the declared `StructType`).
- Dedupe before load (`row_number()` over business key ordered by `updated_at desc`, keep 1).

## Extract
- JDBC has no bind parameters: filter the DataFrame on the watermark and rely on predicate pushdown (confirm `PushedFilters` in `.explain()`), or pass `predicates=[…]`. `fetchsize` 10000.

## Load (idempotent: a rerun yields the same result)
- Default load is a Delta `MERGE` on business keys (`whenMatchedUpdateAll` guarded by `s._loaded_at > t._loaded_at`, `whenNotMatchedInsertAll`); create the table with `overwrite` + `partitionBy` only when it doesn't exist. Never blind INSERT/append for keyed data.
- Partition by date, never by high-cardinality columns.
- Maintenance: `OPTIMIZE … ZORDER BY (<non-partition cols>)` daily/weekly (Z-ordering a partition column errors); `VACUUM … RETAIN 168 HOURS` weekly.
- Schema evolution only via explicit `mergeSchema=true`.

## Incremental
- Prefer watermark or CDC over full reloads.
- Watermark stored in a Delta control table keyed by pipeline (default `1970-01-01T00:00:00Z`). Extract `updated_at > watermark`, load, then advance the watermark (via MERGE) only after the load succeeds.
- CDC: one MERGE with `whenMatchedDelete(_cdc_op='DELETE')`, `whenMatchedUpdateAll(_cdc_op='UPDATE')`, `whenNotMatchedInsertAll(_cdc_op='INSERT')`.

## Data quality (between transform and load)
- Required checks: not-null + unique on keys, not-null on every mandatory field (range/regex do not imply non-null), value ranges (amount 0–1,000,000), formats. Failure raises with check names only.
- Great Expectations: read the project's pinned version first. GX Core 1.x on Spark DataFrames: Data Source → `add_dataframe_asset` → `add_batch_definition_whole_dataframe` → `batch.validate(expectation, result_format={"result_format": "BOOLEAN_ONLY"})`; ephemeral context only for CI/disposable runs.
  - Durable jobs reuse configured assets (re-adding by name is not an update) and use a Validation Definition/Checkpoint when results must persist.
  - Never `toPandas()` the dataset; execution/config errors propagate (never become a pass).
  - Never print raw results, exception text or Data Docs containing PII.
  - Pre-1.0 pins: follow that version's Validator docs and existing tests.
  - Don't upgrade GX or start Spark sessions on this guidance alone.
- dbt: `not_null` + `unique` on keys, `relationships` to dimensions, `dbt_utils.accepted_range` on amounts.

## Modeling
- Star schema: facts hold surrogate FKs (`*_sk`) to dimensions plus measures; money is `DECIMAL(19,4)`, never float. Surrogate keys `BIGINT GENERATED ALWAYS AS IDENTITY`.
- SCD Type 2 dimensions: business key, tracked attributes, `effective_from NOT NULL`, `effective_to` default `9999-12-31`, `is_current` default true, partial index on business key `WHERE is_current`.
- SCD2 load: detect changes null-safely (`NOT (t.c <=> s.c)`, never `!=`), expire current rows (`is_current=false`, `effective_to=now`), then append new versions; no-op when nothing changed.

## Tests and observability
- Unit-test transforms with 10–100-row DataFrames on `local[2]` and `spark.sql.shuffle.partitions=2`; never full datasets.
- Emit records processed, duration, quality pass/fail and cost per run (`tea-sdlc:observability`).
