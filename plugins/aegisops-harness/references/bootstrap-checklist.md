# Greenfield service checklist

In order:
1. Project skeleton: source layout, config, dependency manifest.
2. Deploy "hello world" to production first (only with deployment authorization) to prove the pipeline.
3. CI/CD: test → build → deploy on push.
4. Observability: structured logging, error alerting, basic dashboard.
5. Data store: primary table/schema, migrations, backups on.
6. One integration test against the deployed endpoint.
7. First endpoint in the authoritative contract source (schema folder the build consumes, or generated from code); `api-contracts.md` links it.

Defaults when the project leaves the choice open: AWS CDK (TypeScript), `ap-southeast-1`; Lambda Node.js 22.x ARM64 512 MB; DynamoDB single-table, PAY_PER_REQUEST, PITR, RETAIN; GitHub Actions; Lambda Powertools + CloudWatch + X-Ray; `AWS_PROFILE=ai-driven`.
