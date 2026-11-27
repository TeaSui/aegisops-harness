---
name: backend-languages-golang
description: >
  Go backend patterns: standard layout (cmd/internal/pkg), error handling (%w wrapping, sentinel errors),
  consumer-side interfaces, table-driven tests, errgroup, context cancellation, HTTP handler/middleware patterns.
---

# Go Backend Patterns

## Layout
- `cmd/<binary>/main.go`: parse config, wire deps, start server; no business logic, no `init()` (wire in `main`).
- `internal/{handler,service,repository,model,client,middleware}` by default; `pkg/` only for code other repos must import (usually none).
- No `utils/` or `helpers/` packages.

## Errors
- Handle or return; never discard (`_, _ = f()`). Wrap with `fmt.Errorf("doing X: %w", err)`; no naked `return nil, err`; don't wrap twice.
- Sentinel errors (`ErrOrderNotFound`, returned unwrapped) for expected conditions; error types for errors carrying data; check with `errors.Is`/`errors.As`.
- `panic` only for programmer bugs, never in library code or for expected conditions.

## Money
- Never `float64`: `int64` minor units, rates in basis points (1000 = 10%); `github.com/shopspring/decimal` for arbitrary precision or FX.

## Context and concurrency
- `ctx context.Context` is the first parameter of every I/O function and is threaded through every layer; never stored in a struct.
- Check `ctx.Done()` in long loops.
- Parallel calls: `golang.org/x/sync/errgroup` with `errgroup.WithContext`.
- Every goroutine has an exit path (buffered result channel + `select` on `ctx.Done()`).
- Pass loop variables explicitly to goroutines even on Go 1.22+.

## HTTP
- Handlers are constructors returning `http.HandlerFunc` with deps captured by closure; middleware is `func(http.Handler) http.Handler` and must call `next.ServeHTTP`.
- Request logging via `log/slog` with method, path, status, `duration_ms`.

## Interfaces
- Define interfaces in the consumer package, not next to the implementation.

## Tests
- Table-driven with `t.Run`; `foo_test.go` beside `foo.go` (same package = white-box, `_test` package = black-box); `t.Helper()` in helpers; `t.Parallel()` for independent tests.
- `testify/assert|require` only if the project already uses it; else stdlib.

## Modules
- Pin major versions via the `/vN` path; `go mod tidy` before committing; always commit `go.sum`; `go mod vendor` only if CI requires it.
