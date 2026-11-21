---
name: bdd-cucumber
description: |
  BDD with Cucumber: writing Gherkin feature files, step definitions for Java (Cucumber-JVM) and Go (godog),
  scenario outlines, data tables, hooks, and linking features to acceptance criteria.
  Use when: writing Cucumber tests, creating Gherkin feature files, implementing step definitions,
  setting up BDD test infrastructure, or converting acceptance criteria to scenarios.
  Triggers on: Cucumber, Gherkin, BDD, feature file, .feature, step definitions, scenario outline, godog.
---

# BDD Cucumber

## Gherkin rules

- Business language and declarative steps: no endpoints, status codes, JSON, DB ids or UI clicks in steps.
- One behaviour per scenario: exactly one When; at most two `And` under Then; split scenarios over ~10 steps.
- Background when 3+ scenarios share Givens. Scenario Outline only with 2+ example rows.
- Scenarios are independent: reset state in a `Before` hook.
- Feature header names the spec: `# See: docs/specs/<feature>/spec.md`.

## Tags

| Tag | Meaning |
|---|---|
| `@P0` | Critical path; must pass before any deployment |
| `@P1` | Must pass before release |
| `@P2` | Edge cases; non-blocking |
| `@wip` | Excluded from CI |
| `@slow` | Nightly only |
| `@<domain>` | Feature filter |
| `@<KEY>-<n>` | User story this scenario covers, from `docs/specs/<feature>/spec.md` (story 1 of key RFD = `@RFD-1`); the exact upper-case token counts as spec traceability |

Tag from the first commit.

## Java (Cucumber-JVM)

- Versions via `io.cucumber:cucumber-bom` (checked 2026-11; verify against the project): 8.x targets JUnit 6 / Spring Boot 4; on JUnit 5 / Spring Boot 3 use 7.34.9. Modules: `cucumber-java`, `cucumber-spring`, `cucumber-junit-platform-engine`, plus `junit-platform-suite` from the JUnit/Spring BOM.
- Runner: JUnit Platform `@Suite @IncludeEngines("cucumber") @SelectClasspathResource("features")` with `GLUE_PROPERTY_NAME`; report plugin `pretty,html:build/reports/cucumber.html`.
- One `@CucumberContextConfiguration` + `@SpringBootTest(RANDOM_PORT)` + `@ActiveProfiles("test")` class for all glue.
- Money parameters `{bigdecimal}`, compared with `isEqualByComparingTo`; never `{double}`/`{float}`.
- `@Before` truncates test tables (`TRUNCATE … RESTART IDENTITY CASCADE`); `@After` attaches the last response on failure.

## Go (godog)

- `godog.TestSuite` with `TestingT: t`, `Paths: ["features"]`; fail the test on non-zero status. `ctx.Before` resets per-scenario state.
- Money: capture as string, parse with `shopspring/decimal` (or int64 minor units), compare with `.Equal`; never `float64`.
- Steps return wrapped errors including status and body on mismatch.

## Step definitions

Glue only: delegate to helpers/clients, no business logic. Scenario state lives in a per-scenario holder, never shared statics.
