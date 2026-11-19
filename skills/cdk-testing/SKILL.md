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

# CDK Testing Patterns

## Test Types Decision Table

| What to test | Approach | Speed | When |
|---|---|---|---|
| Resource created with correct properties | Fine-grained assertions | Fast | Every resource |
| Resource count (no extra resources) | resourceCountIs | Fast | Security-sensitive stacks |
| No regressions in template | Snapshot test | Fast | Stable stacks |
| Custom construct outputs correct resources | Unit test construct in isolation | Fast | Every L3 construct |
| Compliance rules (tags, encryption) | Aspects + assertions | Fast | Every stack |
| Stack deploys and resources work | Integration test (`integ-runner` + `@aws-cdk/integ-tests-alpha` `IntegTest`) | Slow | Pre-release |

## Project Test Structure

```
lib/
├── stacks/
│   ├── database-stack.ts
│   ├── compute-stack.ts
│   └── api-stack.ts
├── constructs/                   # Reusable L3 constructs
│   ├── secure-bucket.ts
│   └── monitored-lambda.ts
test/
├── stacks/
│   ├── database-stack.test.ts
│   ├── compute-stack.test.ts
│   └── api-stack.test.ts
├── constructs/
│   ├── secure-bucket.test.ts
│   └── monitored-lambda.test.ts
├── aspects/
│   └── compliance.test.ts
└── helpers/
    └── test-app.ts               # Shared test setup
```

## Fine-Grained Assertions

```typescript
import { Template, Match, Capture } from 'aws-cdk-lib/assertions';
import * as cdk from 'aws-cdk-lib';
import { DatabaseStack } from '../lib/stacks/database-stack';

describe('DatabaseStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new DatabaseStack(app, 'TestDatabase', {
      env: { account: '123456789012', region: 'ap-southeast-1' },
      envName: 'test',
    });
    template = Template.fromStack(stack);
  });

  test('creates DynamoDB table with correct key schema', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [
        { AttributeName: 'PK', KeyType: 'HASH' },
        { AttributeName: 'SK', KeyType: 'RANGE' },
      ],
      BillingMode: 'PAY_PER_REQUEST',
      PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
    });
  });

  test('DynamoDB table has encryption enabled', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      SSESpecification: {
        SSEEnabled: true,
        SSEType: 'KMS',
      },
    });
  });

  test('creates exactly one DynamoDB table', () => {
    template.resourceCountIs('AWS::DynamoDB::Table', 1);
  });

  test('table has deletion protection in production', () => {
    const app = new cdk.App();
    const stack = new DatabaseStack(app, 'ProdDatabase', {
      env: { account: '123456789012', region: 'ap-southeast-1' },
      envName: 'prod',
    });
    const prodTemplate = Template.fromStack(stack);

    prodTemplate.hasResourceProperties('AWS::DynamoDB::Table', {
      DeletionProtectionEnabled: true,
    });
  });
});
```

## Testing Lambda Functions

```typescript
describe('ComputeStack', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new ComputeStack(app, 'TestCompute', {
      env: { account: '123456789012', region: 'ap-southeast-1' },
      envName: 'test',
      tableName: 'test-main',
      tableArn: 'arn:aws:dynamodb:ap-southeast-1:123456789012:table/test-main',
    });
    template = Template.fromStack(stack);
  });

  test('Lambda uses ARM64 architecture', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      Architectures: ['arm64'],
      Runtime: 'nodejs22.x',
    });
  });

  test('Lambda has X-Ray tracing enabled', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      TracingConfig: { Mode: 'Active' },
    });
  });

  test('Lambda has dead letter queue configured', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      DeadLetterConfig: {
        TargetArn: Match.anyValue(),
      },
    });
  });

  test('Lambda timeout is explicitly set (not default 3s)', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      Timeout: Match.not(3),
    });
  });

  test('Lambda does not have wildcard IAM permissions', () => {
    // X-Ray tracing grants xray:PutTraceSegments/PutTelemetryRecords on '*' (no resource-level
    // permissions exist for them), so statements whose actions are all xray:* are exempt.
    // Only an exact '*' Resource fails: scoped ARNs ending in '/*' (DynamoDB GSI '.../index/*',
    // S3 'bucket/*') are legitimate. Resource may be a string, token object or array.
    const actionsOf = (s: any): string[] => [].concat(s.Action ?? []);
    const resourcesOf = (s: any): unknown[] => [].concat(s.Resource ?? []);
    const policies = template.findResources('AWS::IAM::Policy');
    for (const [, policy] of Object.entries(policies)) {
      const statements = policy.Properties?.PolicyDocument?.Statement ?? [];
      for (const statement of statements) {
        if (statement.Effect !== 'Allow') continue;
        if (actionsOf(statement).every((a) => a.startsWith('xray:'))) continue;
        expect(resourcesOf(statement).filter((r) => r === '*')).toEqual([]);
      }
    }
  });
});
```

## Testing IAM Permissions (Capture)

```typescript
test('Lambda has scoped DynamoDB permissions', () => {
  const capture = new Capture();

  template.hasResourceProperties('AWS::IAM::Policy', {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Action: capture,
          Effect: 'Allow',
        }),
      ]),
    },
  });

  const actions = capture.asArray();
  // Should have specific actions, not dynamodb:*
  expect(actions).not.toContain('dynamodb:*');
  // Should include only needed actions
  expect(actions).toEqual(
    expect.arrayContaining([
      'dynamodb:GetItem',
      'dynamodb:PutItem',
      'dynamodb:Query',
    ])
  );
});
```

## Testing API Gateway

```typescript
describe('ApiStack', () => {
  test('API Gateway has authorization on all methods', () => {
    const methods = template.findResources('AWS::ApiGateway::Method');

    for (const [logicalId, method] of Object.entries(methods)) {
      // OPTIONS (CORS preflight) can be unauthenticated
      if (method.Properties?.HttpMethod === 'OPTIONS') continue;

      expect(method.Properties?.AuthorizationType).not.toBe('NONE');
      expect(method.Properties?.AuthorizationType).toBeDefined();
    }
  });

  test('API Gateway has throttling configured', () => {
    template.hasResourceProperties('AWS::ApiGateway::Stage', {
      MethodSettings: Match.arrayWith([
        Match.objectLike({
          ThrottlingRateLimit: Match.anyValue(),
          ThrottlingBurstLimit: Match.anyValue(),
        }),
      ]),
    });
  });

  test('CORS does not allow all origins', () => {
    // Ensure no wildcard CORS in non-dev environments
    const methods = template.findResources('AWS::ApiGateway::Method', {
      Properties: { HttpMethod: 'OPTIONS' },
    });

    for (const [, method] of Object.entries(methods)) {
      const integration = method.Properties?.Integration;
      const responseParams = integration?.IntegrationResponses?.[0]?.ResponseParameters;
      const allowOrigin = responseParams?.['method.response.header.Access-Control-Allow-Origin'];
      expect(allowOrigin).not.toBe("'*'");
    }
  });
});
```

## Snapshot Tests

```typescript
// Use for STABLE stacks only — snapshot churn on active development is noise

test('database stack matches snapshot', () => {
  const app = new cdk.App();
  const stack = new DatabaseStack(app, 'SnapshotTest', {
    env: { account: '123456789012', region: 'ap-southeast-1' },
    envName: 'prod',
  });
  const template = Template.fromStack(stack);
  expect(template.toJSON()).toMatchSnapshot();
});

// Update snapshots: npx jest --updateSnapshot
// Review snapshot diffs carefully in PRs — they show infrastructure changes
```

## Custom Aspects for Compliance

```typescript
// lib/aspects/compliance-aspect.ts

import { IAspect, Annotations } from 'aws-cdk-lib';
import { CfnBucket } from 'aws-cdk-lib/aws-s3';
import { CfnTable } from 'aws-cdk-lib/aws-dynamodb';
import { CfnFunction } from 'aws-cdk-lib/aws-lambda';
import { IConstruct } from 'constructs';

export class FintechComplianceAspect implements IAspect {
  visit(node: IConstruct): void {
    this.checkS3Encryption(node);
    this.checkDynamoDBBackup(node);
    this.checkLambdaTracing(node);
    this.checkTags(node);
  }

  private checkS3Encryption(node: IConstruct): void {
    if (node instanceof CfnBucket) {
      if (!node.bucketEncryption) {
        Annotations.of(node).addError(
          'S3 bucket must have encryption enabled (MAS TRM requirement)'
        );
      }
      const publicAccess = node.publicAccessBlockConfiguration;
      if (!publicAccess) {
        Annotations.of(node).addError(
          'S3 bucket must have BlockPublicAccess enabled'
        );
      }
    }
  }

  private checkDynamoDBBackup(node: IConstruct): void {
    if (node instanceof CfnTable) {
      const pitr = node.pointInTimeRecoverySpecification;
      if (!pitr || !(pitr as any).pointInTimeRecoveryEnabled) {
        Annotations.of(node).addError(
          'DynamoDB table must have point-in-time recovery enabled'
        );
      }
    }
  }

  private checkLambdaTracing(node: IConstruct): void {
    if (node instanceof CfnFunction) {
      if (!node.tracingConfig || (node.tracingConfig as any).mode !== 'Active') {
        Annotations.of(node).addWarning(
          'Lambda function should have X-Ray tracing enabled'
        );
      }
    }
  }

  private checkTags(node: IConstruct): void {
    if (node instanceof CfnBucket || node instanceof CfnTable || node instanceof CfnFunction) {
      const tags = (node as any).tags?.renderedTags ?? [];
      const hasProject = tags.some((t: any) => t.key === 'Project');
      const hasEnvironment = tags.some((t: any) => t.key === 'Environment');
      if (!hasProject || !hasEnvironment) {
        Annotations.of(node).addWarning(
          'Resource should have Project and Environment tags'
        );
      }
    }
  }
}
```

### Testing the Aspect
```typescript
// test/aspects/compliance.test.ts

describe('FintechComplianceAspect', () => {
  test('flags S3 bucket without encryption', () => {
    const app = new cdk.App();
    const stack = new cdk.Stack(app, 'TestStack');

    // Create non-compliant bucket
    new s3.CfnBucket(stack, 'BadBucket', {});

    cdk.Aspects.of(stack).add(new FintechComplianceAspect());

    const messages = Annotations.fromStack(stack);
    messages.hasError('/TestStack/BadBucket', Match.stringLikeRegexp('encryption'));
  });

  // Current CDK v2 L2 TableProps syntax; see version note below.
  test('passes compliant DynamoDB table', () => {
    const app = new cdk.App();
    const stack = new cdk.Stack(app, 'TestStack');

    new dynamodb.Table(stack, 'GoodTable', {
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
    });

    cdk.Aspects.of(stack).add(new FintechComplianceAspect());

    const messages = Annotations.fromStack(stack);
    messages.hasNoError('/TestStack/GoodTable', Match.anyValue());
  });
});
```

**CDK version gate:** inspect `aws-cdk-lib` in the project lockfile. Current CDK v2 `TableProps` uses `pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true }`; the older boolean `pointInTimeRecovery` is deprecated. Keep that legacy form only when the pinned library lacks the specification property, and verify synthesized `PointInTimeRecoverySpecification.PointInTimeRecoveryEnabled` in either case. L1 `CfnTable` still uses `pointInTimeRecoverySpecification`; do not rename the aspect's field to the legacy L2 boolean. See [TableProps](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_dynamodb.TableProps.html) and [PITR specification](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_dynamodb.PointInTimeRecoverySpecification.html). This instructional edit has not executed CDK synthesis or the embedded Jest tests.


### Applying Aspects
```typescript
// bin/app.ts — apply to entire app
const app = new cdk.App();

// ... create stacks ...

// Apply compliance checks to all stacks
cdk.Aspects.of(app).add(new FintechComplianceAspect());
```

## Reusable L3 Construct with Tests

```typescript
// lib/constructs/monitored-lambda.ts

export interface MonitoredLambdaProps {
  functionName: string;
  handler: string;
  code: lambda.Code;
  environment?: Record<string, string>;
  timeout?: cdk.Duration;
  memorySize?: number;
  alarmThreshold?: number;
}

export class MonitoredLambda extends Construct {
  public readonly function: lambda.Function;
  public readonly errorAlarm: cloudwatch.Alarm;

  constructor(scope: Construct, id: string, props: MonitoredLambdaProps) {
    super(scope, id);

    const dlq = new sqs.Queue(this, 'DLQ', {
      retentionPeriod: cdk.Duration.days(14),
    });

    const logGroup = new logs.LogGroup(this, 'LogGroup', {
      retention: logs.RetentionDays.ONE_MONTH,
    });

    this.function = new lambda.Function(this, 'Function', {
      functionName: props.functionName,
      runtime: lambda.Runtime.NODEJS_22_X,
      architecture: lambda.Architecture.ARM_64,
      handler: props.handler,
      code: props.code,
      environment: props.environment,
      timeout: props.timeout ?? cdk.Duration.seconds(30),
      memorySize: props.memorySize ?? 512,
      tracing: lambda.Tracing.ACTIVE,
      deadLetterQueue: dlq,
      logGroup, // `logRetention` is the legacy custom-resource approach
    });

    this.errorAlarm = this.function
      .metricErrors({ period: cdk.Duration.minutes(5) })
      .createAlarm(this, 'ErrorAlarm', {
        threshold: props.alarmThreshold ?? 5,
        evaluationPeriods: 2,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
  }
}
```

```typescript
// test/constructs/monitored-lambda.test.ts

describe('MonitoredLambda', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new cdk.Stack(app, 'TestStack');
    new MonitoredLambda(stack, 'TestLambda', {
      functionName: 'test-handler',
      handler: 'index.handler',
      code: lambda.Code.fromInline('exports.handler = async () => {}'),
    });
    template = Template.fromStack(stack);
  });

  test('creates Lambda with required defaults', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      Architectures: ['arm64'],
      Runtime: 'nodejs22.x',
      TracingConfig: { Mode: 'Active' },
    });
  });

  test('creates DLQ', () => {
    template.resourceCountIs('AWS::SQS::Queue', 1);
    template.hasResourceProperties('AWS::SQS::Queue', {
      MessageRetentionPeriod: 1209600, // 14 days
    });
  });

  test('creates CloudWatch alarm', () => {
    template.hasResourceProperties('AWS::CloudWatch::Alarm', {
      EvaluationPeriods: 2,
      Threshold: 5,
      TreatMissingData: 'notBreaching',
    });
  });

  test('connects DLQ to Lambda', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      DeadLetterConfig: {
        TargetArn: Match.anyValue(),
      },
    });
  });
});
```

## Common Mistakes to Avoid

1. **Testing CDK internals** — test the CloudFormation output (Template), not CDK construct tree.
2. **Snapshot tests on active stacks** — snapshot diffs are noise during development. Use fine-grained assertions.
3. **Missing env in test stacks** — some constructs need account/region. Always provide `env` in tests.
4. **Not testing prod vs dev differences** — conditional logic (retention policies, deletion protection) needs separate test cases per environment.
5. **Forgetting to test IAM** — IAM is the most common security misconfiguration. Always assert permission scope.
6. **Testing with `cdk deploy`** — unit tests should never deploy. Use `Template.fromStack()` for all fast tests.
