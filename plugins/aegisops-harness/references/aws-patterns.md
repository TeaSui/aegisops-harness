# AWS patterns (CDK TypeScript, serverless-first)

The project's stack, account, region, deploy process and security rules come first; these are defaults for open choices (CDK TypeScript, `ap-southeast-1`, profile `ai-driven`). Never upgrade CDK or migrate a stack to match this file; check props against the installed `aws-cdk-lib`.

## Conventions
- Stacks `Project-<Purpose>` with `envName: 'dev' | 'staging' | 'prod'` props; resource names `${envName}-<name>`; region from `CDK_DEFAULT_REGION` (project/CLI target first).
- Tags (mandatory): app `Project`, `ManagedBy=cdk`; stack `Environment`, `Stack`.
- Least privilege via `grant*` methods; custom statements scoped to exact actions and ARNs built with `this.partition/region/account` (e.g. `parameter/${envName}/<service>/*`).
- Secrets: never in env vars or logs. Pass the secret identifier (`API_SECRET_ID`), fetch and cache at runtime via the SDK/extension with scoped read + KMS access. `Secret.fromSecretNameV2` imports a reference, not a value.

## Lambda
`NODEJS_22_X`, `ARM_64` (verify dependency compatibility), 512 MB, 30 s timeout, `Tracing.ACTIVE`, DLQ, explicit `logGroup` (`logs.LogGroup`, 1-month retention) instead of legacy `logRetention` when the installed CDK supports it.

## DynamoDB
Single-table `PK`/`SK`, GSIs `GSI1PK`/`GSI1SK` (projection ALL), `PAY_PER_REQUEST`, `AWS_MANAGED` encryption, PITR via `pointInTimeRecoverySpecification`, `RETAIN` in prod / `DESTROY` elsewhere, streams `NEW_AND_OLD_IMAGES` when used. Keys: `<ENTITY>#<id>` + `METADATA`; one-to-many `USER#<id>` / `ORDER#<id>`; GSI by status `STATUS#<s>` / `ORDER#<ts>#<id>`. No PII in keys.

## Step Functions
- Retry Lambda `TooManyRequestsException`/`ServiceException` (2 s, max 3, backoff 2) only when effects tolerate replay; Catch to a Fail/recovery state with `resultPath: '$.error'`.
- Prefer SDK integrations (e.g. `DynamoPutItem`) over Lambda wrappers. EXPRESS vs STANDARD by duration/delivery semantics.
- `tracingEnabled: true`; logs level `ERROR`, `includeExecutionData: false` (payloads may hold PII).

## SQS → Lambda
FIFO: `batchSize` ≤ 10, no `maxBatchingWindow`; FIFO DLQ for a FIFO queue. Visibility timeout = 6 × Lambda timeout; redrive `maxReceiveCount: 3`; `reportBatchItemFailures: true` with partial batch responses (FIFO: return the failed and all later messages); idempotent business effects.

## API Gateway
Explicit approved CORS origins and only the needed methods; stage tracing + metrics + `INFO` logging; throttling 1000 rps / burst 500; Cognito (or JWT) authorizer; integration timeout 29 s (verify quota for the API type).

## EventBridge
Domain bus `${envName}-domain`; event `source` `com.tyme.<domain>`, `detailType` past-tense (`OrderCreated`); schedules target Step Functions directly.

## Observability
- Lambda Powertools Logger (`addContext`) and Metrics (EMF); metric names `<service>.<entity>.<action>[.<outcome>]` in snake_case; never log raw records.
- Alarms (starting defaults, description prefixed `[P<n>] ${envName}`): Lambda errors ≥ 5 per 5 min for 2 periods [P2]; p99 duration > 5 s for 3 periods [P3]; any DLQ message ≥ 1 [P2]; `treatMissingData: NOT_BREACHING`.

## Cost
Estimate from current regional pricing and measured usage; no assumed savings (Layers save nothing at runtime; no universal on-demand/provisioned crossover; API caching needs tenant/auth isolation).

## Deploy
Credentials/account/region via the project process, never a personal profile in place of CI roles or SSO. `cdk diff` before `cdk deploy`, only with authorization for that target, native approvals kept. Diagnostics: status, IDs, counts; never payloads or secrets.
