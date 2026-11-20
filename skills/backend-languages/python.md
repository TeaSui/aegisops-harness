---
name: backend-languages-python
description: >
  Idiomatic Python 3.12+ backend patterns: src layout, pyproject.toml, typing, pytest,
  asyncio, FastAPI/Starlette handlers, exception hierarchies, dependency injection, uv/poetry.
---

# Python Backend Patterns

## Layout
- `src/<pkg>/`: `main.py` (app factory, lifespan, routers), `config.py`, `api/routers/` (one router per resource) + `api/deps.py`, `service/`, `repository/`, `models/` (SQLAlchemy ORM), `schemas/` (Pydantic), `exceptions.py`; `tests/{unit,integration}` + `conftest.py`.
- ORM models never leave the repository layer; responses are Pydantic schemas (`Schema.model_validate(orm_obj)`).

## Config
- `pydantic-settings` `Settings`; expose `get_settings()` wrapped in `@lru_cache` and inject via `Depends` (tests override with `app.dependency_overrides` or `get_settings.cache_clear()`). No module-level `settings = Settings()`.

## Errors
- `AppError(Exception)` hierarchy with class-level `status_code` and `code` (`NotFoundError` 404 `NOT_FOUND`, `ValidationError` 422 `VALIDATION_ERROR` + `details`); raise from the service layer.
- Register `@app.exception_handler` once for `AppError` and for `RequestValidationError` (→ 422, `details` = `[{field: "a.b", message}]`) producing the error envelope.
- No catch-and-swallow in routes, no bare `except Exception` (catch specific types; re-raise or convert to `AppError`). Never return tracebacks or ORM details; log the full exception server-side first.

## Handlers and DI
- Routers are thin: Pydantic in, service call, response model out. Always set `response_model`.
- DI via `Annotated[T, Depends(...)]`.
- Avoid `from __future__ import annotations` in Pydantic v2 model modules.
- No mutable default arguments.

## Async
- `async def` for I/O-bound handlers; CPU-bound sync work via `run_in_executor`.
- Never block the loop: no `requests`, `time.sleep`, sync `open()` in `async def` — use `httpx.AsyncClient`, `asyncio.sleep`, `aiofiles`.
- Parallel awaits: `asyncio.TaskGroup` (3.11+) preferred, else `asyncio.gather`. Never drop an `await`.

## Tests
- `pytest` + `pytest-asyncio` with `asyncio_mode = "auto"`; HTTP tests through `httpx.AsyncClient(transport=ASGITransport(app=app))`; `@pytest.mark.parametrize` over copy-pasted tests.
- Integration tests use a real DB (Testcontainers, or in-process SQLite where appropriate). Coverage ≥ 80% (`pytest --cov=src/<pkg>`).

## Dependencies
- Python ≥ 3.12; `fastapi>=0.115`, `pydantic>=2`, `pydantic-settings>=2`, `sqlalchemy[asyncio]>=2`, `asyncpg>=0.29`, `uvicorn[standard]>=0.30`; dev: `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `mypy`, `ruff`.
- `uv` (`uv sync`, `uv add`); `poetry` only if the project already uses it. Commit the lock file.
- CI runs `mypy --strict` and `ruff check`.
