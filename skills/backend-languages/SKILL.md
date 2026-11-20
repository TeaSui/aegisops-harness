---
name: backend-languages
description: >
  Use when writing or reviewing backend service code in Go, Spring Boot (Java), Python/FastAPI
  or Rust/axum — by the main session on the fast path or by tea-sdlc:backend-engineer-subagent.
  Routes to the matching language reference.
---

# Backend Language References

Read only `${CLAUDE_PLUGIN_ROOT}/skills/backend-languages/<file>` for the detected language (plain files, not skills); load several only for a genuinely polyglot repo.

| Language | Triggers | File |
|----------|----------|------|
| **Go** | `.go` files, `go.mod`, `goroutine`, `channel`, `errgroup`, Go modules | `golang.md` |
| **Spring Boot** | `@SpringBootApplication`, `@RestController`, `build.gradle`, `pom.xml`, Spring MVC, JPA, Hibernate | `spring-boot.md` |
| **Python** | `.py` files, `pyproject.toml`, `requirements.txt`, FastAPI, Starlette, `asyncio`, Pydantic | `python.md` |
| **Rust** | `.rs` files, `Cargo.toml`, `cargo workspace`, `tokio`, `axum`, `actix`, `thiserror`, `anyhow` | `rust.md` |

## Shared conventions (all languages)

- Envelope: success `{ "data": {...}, "meta": { "timestamp": "..." } }`; error `{ "error": { "code": "...", "message": "...", "details": [] } }` with the correct HTTP status, mapped in one central handler.
- Errors: no stack traces, ORM/internal details, rejected values or PII in responses or logs; log the full error server-side with safe fields only.
- Money: never binary floating point. Integer minor units (rates in basis points) or an exact decimal type; compare exactly.
- Config from environment variables only; secrets from env/Secrets Manager.
- Layers: thin handler (validate DTO, call service) → service (business logic, transaction boundary) → repository. Never return persistence models from the API.
- Tests: mock only external HTTP APIs; query tests hit a real DB (Testcontainers) or in-memory DB.
- Commit lock files (`go.sum`, `uv.lock`/`poetry.lock`, `Cargo.lock` for binaries).
