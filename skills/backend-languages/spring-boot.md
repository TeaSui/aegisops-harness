---
name: backend-languages-spring-boot
description: >
  Spring Boot patterns: layered architecture (Controller/Service/Repository), profile management,
  constructor injection, @ControllerAdvice exception handling, test slicing, @ConfigurationProperties,
  Spring Security filter chain.
---

# Spring Boot Patterns

## Layout
- `com.example.<svc>`: `<App>Application` (only `@SpringBootApplication`), `config/`, `controller/` + `controller/dto/`, `service/` (`impl/` only if an interface is needed), `repository/`, `entity/`, `exception/`, `mapper/` (MapStruct or manual), `client/` (`RestClient`/`WebClient`).
- Resources: `application.yml` + `application-{local,test,prod}.yml`; Flyway in `db/migration/`.
- Controllers validate (`@Valid`, `@Validated`) and delegate; services own logic and `@Transactional`; repositories extend `JpaRepository` (`@Query` for complex queries); entities never appear in API responses (map to DTOs). No circular deps; services never call controllers.
- Constructor injection only (single constructor, no `@Autowired`; no field injection).
- Typed config via `@ConfigurationProperties` records (registered with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`), not scattered `@Value`; prod values from env vars / Secrets Manager.

## Errors
- One `@RestControllerAdvice` emitting the canonical envelope (records `ApiErrorResponse(ApiError(code, message, List<FieldErrorDetail(field, message)>))`, one public type per file) unless a project contract overrides it. Never catch in controllers.
- Map at least: `ResourceNotFoundException` → 404 `RESOURCE_NOT_FOUND`; `MethodArgumentNotValidException` → 400 `VALIDATION_ERROR` with field names and a generic "Invalid value" (no rejected values or exception messages); `Exception` → 500 `INTERNAL_ERROR`, logging only the exception class name.
- Exceptions: `BusinessException extends RuntimeException` carrying `code`; subclasses per case.
- Advice does not cover filter-chain errors: map Spring Security authentication/access-denied handlers to the envelope too. Verify status + `$.error.code|message|details` in MVC tests.
- RFC 9457 `ProblemDetail` only when the project selected it (its properties serialize top-level; it is not the envelope).

## Transactions and async
- `@Transactional` on service methods, `readOnly = true` for reads; rolls back on unchecked exceptions only; ignored on `private` methods and self-invocation (extract a bean or use `TransactionTemplate`).
- `@Async("taskExecutor")` needs `@EnableAsync` + a `ThreadPoolTaskExecutor` bean; transactions do not propagate into `@Async` methods.
- WebFlux: no blocking JPA calls inside `Mono`/`Flux` pipelines.

## Tests (use slices, not `@SpringBootTest` everywhere)
| Target | Annotation |
|---|---|
| Controller routing/validation/JSON | `@WebMvcTest(X.class)` + `@MockitoBean` |
| JPA queries | `@DataJpaTest` + `@AutoConfigureTestDatabase(replace = NONE)` + Testcontainers `postgres:16` via `@DynamicPropertySource` |
| Full flow | `@SpringBootTest` + `@AutoConfigureMockMvc` |
| Service | plain JUnit + Mockito |
| HTTP client | `@RestClientTest` + `MockRestServiceServer` |

## Spring Security 6+ (header-only bearer API)
- `@EnableWebSecurity` + `@EnableMethodSecurity`. Chain `@Order(1)` with `securityMatcher("/api/**")`: STATELESS, `httpBasic`/`formLogin` disabled, `oauth2ResourceServer(jwt)`, `/api/public/**` permitAll, `/api/admin/**` `hasRole("ADMIN")`, `anyRequest().authenticated()`.
- Disable CSRF on that chain only because it accepts nothing but a caller-supplied `Authorization` header — no JWT/session cookies, Basic or form login. Any chain accepting cookie or browser-automatic credentials (login/refresh/logout) keeps CSRF on, even when STATELESS.
- Final chain at `Ordered.LOWEST_PRECEDENCE` with no `securityMatcher`: CSRF on, Basic/form/logout disabled, `anyRequest().denyAll()`. Add other browser flows as scoped chains before it; never leave requests unmatched (first matching chain wins; an unmatched request is unprotected).
- Integration-test: unauthenticated API request, non-admin on admin path, non-API paths with and without auth (must stay denied — a valid token never bypasses the catch-all), unsafe non-API requests with/without CSRF.
