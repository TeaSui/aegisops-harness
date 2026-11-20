---
name: cdk-testing
description: |
  AWS CDK testing patterns: unit tests with assertions, fine-grained assertions,
  snapshot tests, integration tests, custom aspects for compliance, and reusable
  L3 construct patterns with testability.
  Use when: writing CDK unit tests, validating CloudFormation output, testing
  custom constructs, enforcing compliance via aspects, or setting up CDK test suites.
  Triggers on: CDK test, cdk synth, CloudFormation assertion, CDK aspect,
  infrastructure test, stack test.
---

# CDK Testing

| What | Approach | When |
|---|---|---|
| Resource properties | `Template.fromStack` + `hasResourceProperties` / `Match` / `Capture` | Every resource |
| No extra resources | `resourceCountIs` | Security-sensitive stacks |
| Template regressions | Snapshot (`toMatchSnapshot`) | Stable stacks only; review snapshot diffs in PRs |
| L3 construct output | Construct in an isolated `cdk.Stack` | Every L3 construct |
| Compliance | Aspect + `Annotations.fromStack` | Every stack |
| Deploys and works | `integ-runner` + `@aws-cdk/integ-tests-alpha` `IntegTest` | Pre-release only |

Layout: `test/{stacks,constructs,aspects,helpers}/` mirrors `lib/`. Unit tests never deploy.

## Rules

- Assert on the synthesized template, not the construct tree.
- Always pass `env` (account + region) to test stacks.
- Environment-conditional logic (deletion protection, retention, removal policy) gets one test per env (e.g. `test` and `prod`).
- Every stack's tests assert IAM scope.
- Check `aws-cdk-lib` in the lockfile before writing props: L2 `TableProps` uses `pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true }` (boolean `pointInTimeRecovery` is deprecated — keep only if the pinned lib lacks the spec); L1 `CfnTable` uses `pointInTimeRecoverySpecification`. Assert the synthesized `PointInTimeRecoverySpecification.PointInTimeRecoveryEnabled` either way.

## House assertions

| Resource | Assert |
|---|---|
| DynamoDB | PITR on; `SSESpecification` KMS; `PAY_PER_REQUEST` unless justified; `DeletionProtectionEnabled` in prod; exact table count |
| Lambda | `arm64`, current Node runtime (`nodejs22.x`), X-Ray `Active`, DLQ configured, timeout set explicitly (not default 3 s) |
| IAM | No `Allow` statement with an exact `*` Resource, except statements whose actions are all `xray:*`. Scoped ARNs ending `/*` (GSI `index/*`, S3 `bucket/*`) are fine; handle string, token and array forms. No service wildcards (`dynamodb:*`); capture actions and assert the needed set. |
| API Gateway | Every non-`OPTIONS` method has `AuthorizationType` defined and ≠ `NONE`; stage `MethodSettings` set throttling rate + burst; CORS `Access-Control-Allow-Origin` ≠ `'*'` outside dev |

## Compliance aspect

An `IAspect` applied at app level (`Aspects.of(app).add(...)`), tested with a deliberately non-compliant and a compliant resource (`hasError` / `hasNoError`):

| Check | Severity |
|---|---|
| S3 `CfnBucket` without encryption (MAS TRM) | error |
| S3 without `publicAccessBlockConfiguration` | error |
| `CfnTable` without PITR | error |
| `CfnFunction` tracing not `Active` | warning |
| Bucket/table/function missing `Project` or `Environment` tag | warning |

## MonitoredLambda L3 defaults

Node 22, ARM64, tracing active, timeout 30 s, memory 512 MB, SQS DLQ with 14-day retention, explicit `LogGroup` with one-month retention (not legacy `logRetention`), error alarm: 5-min period, threshold 5, 2 evaluation periods, missing data not breaching. Test each default (incl. `MessageRetentionPeriod: 1209600`, one queue).
