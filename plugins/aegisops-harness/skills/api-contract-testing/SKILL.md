---
name: api-contract-testing
description: API contract testing for microservices — consumer-driven contracts (Pact for Spring Boot, Go), OpenAPI compliance, baseline regression comparison and structured test reports; Read before the first edit in that area when the repository has OpenAPI, AsyncAPI, proto files or Pact.
disable-model-invocation: true
user-invocable: false
---

# API Contract Testing

Static structure/compatibility of `docs/specs/<f>/contracts/` is the contract gate: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/check-contract.py <spec-dir>`. This skill covers runtime and consumer contract tests.

| Scenario | Approach |
|---|---|
| Client → backend, service → service | Consumer-driven contracts (Pact) |
| Public API with OpenAPI spec | Response validation against the spec + contract tests |
| Endpoint regression | Baseline comparison |
| Pre-release | Smoke + contract + baseline |

## Bind the installed validator

- Use the repo's installed validator matching its OpenAPI version and JSON Schema dialect (e.g. openapi-core with the adapter of the installed release). Never hand-roll key checks or install a tool to get a pass. Spec linting or a snapshot alone does not validate responses.
- From the task's service/module, find specs, contract/Pact tests, lockfiles, manifests and CI workflows. Record spec `openapi` version, SHA-256, commit, working-change scope and validator version from the lockfile.
- Run the repo's documented command/selector from its CI. Never invent a script or switch service when a selector is missing.
- Do not probe guessed localhost endpoints or execute operations found in a spec. No installs, service startup or mutating replay from discovery; in-process app or an explicitly authorized disposable target. A GET is not safe by method alone.

## Scenario gate

- Each scenario: real fixture IDs, full body/query/headers; cover success and intended error responses.
- Assert exact expected status first (a declared 401 does not pass a 200 scenario), then media type, JSON decode, full response schema incl. `$ref` and nested constraints.
- Missing tool/target, incompatible dialect, unresolved ref, parse error or zero tests executed = unsupported/failed, never PASS. Never mask the exit status (`|| true`, trailing success command, unguarded pipe). A skipped schema branch is not compliance.
- Resolve local refs under the spec root only; no remote refs without explicit scope.
- Before trusting the validator integration, record negative-fixture evidence:

| Fixture | Required outcome |
|---|---|
| Valid response with `$ref`/nested schema | Pass; nonzero tests ran |
| Expects 200, gets declared 401/500 | Fail on status |
| JSON media type, malformed body | Fail |
| Wrong nested type / missing nested required / bad array item via `$ref` | Fail |
| Unsupported dialect, unresolved ref, invalid spec | Fail or unsupported |
| Zero scenarios, runner/config failure | Gate fails, nonzero exit |
| Request with body/query | Server fixture confirms inputs arrived |

- Redact credentials and payload values from artifacts.

## Schemathesis (only if already installed)

- Check `st --version` / `st run --help`; use only flags the pinned release supports (`--include-operation-id`, `--phases examples`, `--checks status_code_conformance,content_type_conformance,response_schema_conformance`, `--report junit`).
- Sends real HTTP: authorized disposable target only; auth via the project's secret-safe fixture, never a raw token on the command line.
- Unresolved refs, unsupported schemas, missing examples or skipped operations block claims for those operations. Schema conformance accepts any declared status, so keep the scenario's exact-status assertion. Missing CLI or flags = unsupported; no auto-install.

## Pact

- Consumer (pact-js `PactV3` + `MatchersV3`, or the service's language): match shape and type, not environment values. Cover the error contract (e.g. 404 `RESOURCE_NOT_FOUND`) as well as success.
- Provider: Pact JVM `junit5spring` (`@Provider`, `@PactBroker`/`@PactFolder`, `@State`, `HttpTestTarget` on random port); Go `pact-go/v2` `VerifyProvider` with `StateHandlers`.
- Every consumer `given()` has a provider state handler.
- Publish pacts with the consumer version; gate releases with `can-i-deploy`.
- Contracts verify the interface, not business logic — integration tests are still required.
- Auth tokens from env/fixtures, never hardcoded.

## Baseline regression

- Same installed validator and deterministic tests (not `check-contract.py`), with sanitized version-controlled fixtures or the installed snapshot facility, bound to the same spec version, selectors and fixtures.
- Baseline stores method, resolved path, query, non-secret headers, body/encoding, fixture setup, expected status and media type, stable nested fields. Credentials come from fixtures at runtime.
- Normalize only named volatile fields; preserve array/type/null distinctions; re-run full schema validation in both runs. Never coerce malformed JSON to null or compare top-level keys only. Mismatch fails the command.
- Missing/empty baseline, zero cases or missing input reports = incomplete gate. Updating a baseline is a separate reviewed action. Schemathesis failure baselines suppress known findings; they are not snapshots or proof of fixes.
- Latency is separate: repeated samples against the project budget under controlled load; one timing ratio proves nothing.

## Report

- Source: the runner's JUnit/JSON output and exit status. Record exact command, runner version, spec hash, environment, target, scenario selectors, executed counts, sanitized report path. Per category mark `executed | failed | skipped | unsupported | static-only`; each failure as test / expected / actual / severity / category.
- Never synthesize empty passing categories. Zero executed contract scenarios or missing results cannot pass a required gate. Say "unsupported: no compatible installed validator" when that is the case.
