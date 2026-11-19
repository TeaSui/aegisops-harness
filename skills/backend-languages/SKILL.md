---
name: backend-languages
description: >
  Use when writing or reviewing backend service code in Go, Spring Boot (Java), Python/FastAPI
  or Rust/axum — by the main session on the fast path or by backend-engineer-subagent.
  Routes to the matching language reference.
---

# Backend Language References

Used by the main session on the fast path and preloaded into `backend-engineer-subagent`. It routes to the language reference file matching the detected triggers. Read only the reference that matches your current task.

## Language Router

| Language | Triggers | Reference |
|----------|----------|-----------|
| **Go** | `.go` files, `go.mod`, `goroutine`, `channel`, `errgroup`, Go modules | `golang.md` |
| **Spring Boot** | `@SpringBootApplication`, `@RestController`, `build.gradle`, `pom.xml`, Spring MVC, JPA, Hibernate | `spring-boot.md` |
| **Python** | `.py` files, `pyproject.toml`, `requirements.txt`, FastAPI, Starlette, `asyncio`, Pydantic | `python.md` |
| **Rust** | `.rs` files, `Cargo.toml`, `cargo workspace`, `tokio`, `axum`, `actix`, `thiserror`, `anyhow` | `rust.md` |

## How to use

1. Detect the language from file extensions, build manifests, or imports.
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/backend-languages/<file>.md` for the matching file (e.g. `golang.md`); these files are not skills and cannot be invoked with the Skill tool.
3. Apply patterns from that reference. Do not load multiple language references unless the project is genuinely polyglot.

## Shared conventions (all languages)

- REST response envelope: `{ "data": {...}, "meta": { "timestamp": "..." } }` / `{ "error": { "code": "...", "message": "...", "details": [] } }`
- Config via environment variables only — no hardcoded values
- Repository pattern for data access; services own business logic
- DTOs validated at entry points; never expose raw persistence models in API responses
- Mock only external HTTP APIs in tests; use real or in-memory DB for query tests
