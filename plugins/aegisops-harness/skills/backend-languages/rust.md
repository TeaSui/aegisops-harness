---
name: backend-languages-rust
description: >
  Idiomatic Rust (2024 edition, stable since Rust 1.85) backend patterns: cargo workspaces, Result+thiserror/anyhow,
  trait design, table-driven tests with rstest, tokio async, axum handler patterns, error propagation.
---

# Rust Backend Patterns

## Layout
- Cargo workspace: `crates/api` (axum router, handlers, `AppError: IntoResponse`), `crates/service` (no HTTP), `crates/repository` (sqlx/diesel), `crates/domain` (types, traits, error enums; no I/O deps); `src/main.rs` wires runtime, config, router.
- Commit `Cargo.lock` for application binaries (not library crates).

## Errors
- `thiserror` enums for domain/library errors; `anyhow` only for application glue.
- `AppError { Domain(DomainError), Internal(anyhow::Error) }` with `From` impls so handlers use `?`; `IntoResponse` maps variants to status + error envelope (`Internal` → 500 `INTERNAL_ERROR`, generic message).
- No `unwrap()`/`expect()` on production paths (tests and compile-time invariants only).
- Log with `tracing::error!` before converting; never `println!`/`eprintln!`; never log tokens or PII. `#[tracing::instrument]` on service methods.

## Money
- Never `f32`/`f64`: `rust_decimal::Decimal` (`dec!`) or `i64` minor units; assert exact equality.

## axum (0.8)
- Handlers: `async fn` → `Result<impl IntoResponse, AppError>`; shared state via `State<AppState>` where `AppState` wraps `Arc<Inner>`.
- Path params use `/{id}` (0.7 used `/:id`).
- `Json<T>` rejects 400 (syntax) / 422 (shape) / 415 (content type); take `Result<Json<T>, JsonRejection>` to map rejections into the envelope.
- Always add `tower_http::catch_panic::CatchPanicLayer` (axum drops the connection on panic) and `TraceLayer`; stack layers with `ServiceBuilder`.
- Typed `Serialize`/`Deserialize` structs, not `serde_json::Value`.

## Async
- `tokio::join!` for fixed parallel calls; `JoinSet` to collect a dynamic fan-out; `tokio::spawn` for fire-and-forget.
- Never block the runtime (`std::thread::sleep`, blocking I/O, heavy CPU) — use `spawn_blocking`.
- Use `tokio::sync::Mutex` when a guard crosses `.await`; spawned futures must be `Send` (no `Rc`/`RefCell` across `.await`).

## Tests
- `#[cfg(test)]` unit modules; `rstest` `#[case]` tables; `#[tokio::test]` for async; integration tests in crate `tests/`.
- Repository tests use `#[sqlx::test]` against a real DB; do not mock the DB layer. Coverage ≥ 80% (`cargo llvm-cov` or `cargo tarpaulin --out Lcov`).

## Dependencies (checked 2026-11; verify against `Cargo.lock`)
- Workspace `resolver = "3"`, `edition = "2024"` (keep 2021 only on toolchains < 1.85); all versions in `[workspace.dependencies]`, crates use `{ workspace = true }`.
- `axum 0.8` (macros), `tokio 1` (full), `serde 1`, `serde_json 1`, `thiserror 2`, `anyhow 1`, `tracing 1`, `tracing-subscriber 0.3` (env-filter), `sqlx 0.9` (postgres, runtime-tokio, tls-rustls, macros), `tower-http 0.7` (trace, cors, catch-panic), `rust_decimal 1`, `rstest 0.28`.
- CI: `cargo clippy -- -D warnings`, `cargo fmt --check`, `cargo audit`.
