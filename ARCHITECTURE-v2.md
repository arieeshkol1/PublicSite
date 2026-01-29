# TAG Video Systems - Architecture v2 (with Cognito & CI/CD)

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          GITHUB ACTIONS CI/CD PIPELINE                       │
│                                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐         │
│  │  Code    │───▶│  Build   │───▶│   CDK    │───▶│   Deploy to  │         │
│  │  Push    │    │  & Test  │    │  Synth   │    │     AWS      │         │
│  └──────────┘    └──────────┘    └──────────┘    └──────────────┘         │
│                                                            │                 │
└────────────────────────────────────────────────────────────┼─────────────────┘
                                                             │
                                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD (Account: 991105135552)               │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    AUTHENTICATION LAYER                              │   │
│  │                                                                       │   │
│  │   ┌──────────────────────────────────────────────────────────┐      │   │
│  │   │  Amazon Cognito User Pool                                │      │   │
│  │   │  - User Pool ID: us-east-1_TQ4bIPoxz                    │      │   │
│  │   │  - Client ID: 7o3rdacnp8fkfkuqt878e2f6eg               │      │   │
│  │   │  - Users: admin, operator, viewer                       │      │   │
│  │   │  - Authentication: Username/Password + SRP              │      │   │
│  │   └──────────────────────────────────────────────────────────┘      │   │
│  │                              │                                        │   │
│  │                              │ JWT Tokens                             │   │
│  │                              ▼                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PRESENTATION LAYER                                │   │
│  │                                                                       │   │
│  │   ┌────────────────────────────────────────────────────────┐        │   │
│  │   │  Amazon S3 (Static Website Hosting)                    │        │   │
│  │   │                                                         │        │   │
│  │   │  ┌──────────────┐         ┌──────────────────┐        │        │   │
│  │   │  │ login.html   │         │  index.html      │        │        │   │
│  │   │  │              │         │  (Dashboard)     │        │        │   │
│  │   │  │ - Cognito    │────────▶│  - Auth Check    │        │        │   │
│  │   │  │   Login Form │         │  - Probe Monitor │        │        │   │
│  │   │  │ - JWT Tokens │         │  - Real-time     │        │        │   │
│  │   │  └──────────────┘         │    Graphs        │        │        │   │
│  │   │                           └──────────────────┘        │        │   │
│  │   └────────────────────────────────────────────────────────┘        │   │
│  │                              │                                        │   │
│  │                              │ HTTPS                                  │   │
│  │                              ▼                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    API & INGESTION LAYER                             │   │
│  │                                                                       │   │
│  │   ┌────────────────────────────────────────────────────────┐        │   │
│  │   │  Amazon API Gateway (REST API)                         │        │   │
│  │   │                                                         │        │   │
│  │   │  POST /telemetry  ────────────┐                        │        │   │
│  │   │  (Edge Probes)                │                        │        │   │
│  │   │                               │                        │        │   │
│  │   │  GET /probes      ────────────┼───────────┐           │        │   │
│  │   │  (Dashboard)                  │           │           │        │   │
│  │   └────────────────────────────────────────────────────────┘        │   │
│  │                              │           │                            │   │
│  │                              ▼           ▼                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    MESSAGE QUEUE LAYER                               │   │
│  │                                                                       │   │
│  │   ┌────────────────────────────────────────────────────────┐        │   │
│  │   │  Amazon SQS (Telemetry Queue)                          │        │   │
│  │   │  - Decouples ingestion from processing                 │        │   │
│  │   │  - Handles "Thundering Herd" scenarios                 │        │   │
│  │   │  - Retention: 1 day                                    │        │   │
│  │   └────────────────────────────────────────────────────────┘        │   │
│  │                              │                                        │   │
│  │                              │ Batch (10 messages)                    │   │
│  │                              ▼                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    COMPUTE LAYER                                     │   │
│  │                                                                       │   │
│  │   ┌────────────────────────────────────────────────────────┐        │   │
│  │   │  AWS Lambda (Node.js 18)                               │        │   │
│  │   │                                                         │        │   │
│  │   │  ┌──────────────────┐      ┌──────────────────┐       │        │   │
│  │   │  │ Processor Lambda │      │  Reader Lambda   │       │        │   │
│  │   │  │                  │      │                  │       │        │   │
│  │   │  │ - Parse JSON     │      │ - Scan DynamoDB  │       │        │   │
│  │   │  │ - Evaluate FPS   │      │ - Return probes  │       │        │   │
│  │   │  │ - Set Status     │      │ - CORS enabled   │       │        │   │
│  │   │  │ - Write to DB    │      │                  │       │        │   │
│  │   │  └──────────────────┘      └──────────────────┘       │        │   │
│  │   └────────────────────────────────────────────────────────┘        │   │
│  │                              │                                        │   │
│  │                              │ Put/Scan                               │   │
│  │                              ▼                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    DATA LAYER                                        │   │
│  │                                                                       │   │
│  │   ┌────────────────────────────────────────────────────────┐        │   │
│  │   │  Amazon DynamoDB (Hot Store)                           │        │   │
│  │   │                                                         │        │   │
│  │   │  Table: ProbeStatusTable                               │        │   │
│  │   │  Partition Key: ProbeID                                │        │   │
│  │   │  Attributes:                                           │        │   │
│  │   │    - Status (HEALTHY / NOT_HEALTHY)                   │        │   │
│  │   │    - FPS (Float)                                       │        │   │
│  │   │    - Resolution (String)                               │        │   │
│  │   │    - Timestamp (ISO 8601)                              │        │   │
│  │   │    - Color (green / red)                               │        │   │
│  │   │  Billing: Pay-per-request                              │        │   │
│  │   └────────────────────────────────────────────────────────┘        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          EDGE LAYER (Simulated)                              │
│                                                                              │
│  ┌──────────────────┐                    ┌──────────────────┐              │
│  │  Probe-A-Encoder │                    │  Probe-B-CDN     │              │
│  │                  │                    │                  │              │
│  │  Python Script   │                    │  Python Script   │              │
│  │  - FPS: 30       │                    │  - FPS: 28       │              │
│  │  - Chaos Mode    │                    │  - Chaos Mode    │              │
│  │  - Jitter        │                    │  - Packet Loss   │              │
│  │  - Interval: 1s  │                    │  - Interval: 1s  │              │
│  └──────────────────┘                    └──────────────────┘              │
│           │                                       │                          │
│           │ POST /telemetry                       │ POST /telemetry          │
│           └───────────────────┬───────────────────┘                          │
│                               │                                              │
│                               ▼                                              │
│                    API Gateway (Public Endpoint)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Authentication Flow

```
┌──────────┐                                                    ┌──────────┐
│          │  1. Access Dashboard URL                           │          │
│  User    │───────────────────────────────────────────────────▶│  S3      │
│          │                                                    │  Bucket  │
└──────────┘                                                    └──────────┘
     │                                                                │
     │  2. Redirect to login.html                                    │
     │◀──────────────────────────────────────────────────────────────┘
     │
     │  3. Enter credentials (admin / TagVideo2024!)
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  login.html (Client-side)                                            │
│  - Cognito Identity SDK                                              │
│  - User Pool ID: us-east-1_TQ4bIPoxz                                │
│  - Client ID: 7o3rdacnp8fkfkuqt878e2f6eg                           │
└──────────────────────────────────────────────────────────────────────┘
     │
     │  4. AuthenticateUser API call
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Amazon Cognito User Pool                                            │
│  - Validate credentials                                              │
│  - Generate JWT tokens                                               │
└──────────────────────────────────────────────────────────────────────┘
     │
     │  5. Return JWT tokens (Access, ID, Refresh)
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  login.html                                                          │
│  - Store tokens in sessionStorage                                    │
│  - Redirect to index.html                                            │
└──────────────────────────────────────────────────────────────────────┘
     │
     │  6. Load dashboard
     │
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│  index.html (Dashboard)                                              │
│  - Check for accessToken in sessionStorage                           │
│  - If missing → redirect to login.html                               │
│  - If present → show dashboard + logout button                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
Edge Probe → API Gateway → SQS → Lambda Processor → DynamoDB
                                                          │
Dashboard ← API Gateway ← Lambda Reader ←─────────────────┘
```

### Telemetry Ingestion Flow

1. **Edge Probe** sends JSON payload via HTTP POST
2. **API Gateway** validates request and forwards to SQS
3. **SQS** buffers messages (decoupling)
4. **Lambda Processor** polls SQS in batches of 10
5. **Lambda** evaluates FPS threshold (25 FPS)
6. **Lambda** writes status to DynamoDB
7. **DynamoDB** stores latest probe state

### Dashboard Read Flow

1. **User** authenticated via Cognito
2. **Dashboard** polls `/probes` endpoint every 2 seconds
3. **API Gateway** invokes Reader Lambda
4. **Lambda Reader** scans DynamoDB
5. **Lambda** returns all probe statuses
6. **Dashboard** updates UI with real-time data

## CI/CD Pipeline (GitHub Actions)

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Repository: arieeshkol1/TAG-SYSTEM-POC                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  .github/workflows/deploy.yml                          │    │
│  │                                                         │    │
│  │  Triggers:                                             │    │
│  │    - push to main branch                               │    │
│  │    - manual workflow_dispatch                          │    │
│  │                                                         │    │
│  │  Steps:                                                │    │
│  │    1. Checkout code                                    │    │
│  │    2. Setup Node.js 18                                 │    │
│  │    3. Setup Python 3.11                                │    │
│  │    4. Install CDK CLI                                  │    │
│  │    5. Install Lambda dependencies                      │    │
│  │    6. Install CDK dependencies                         │    │
│  │    7. Configure AWS credentials (OIDC)                 │    │
│  │    8. CDK synth                                        │    │
│  │    9. CDK deploy                                       │    │
│  └────────────────────────────────────────────────────────┘    │
│                                                                  │
│  AWS Credentials:                                               │
│    - OIDC Provider: GitHub                                      │
│    - IAM Role: GitHubDeployRole                                 │
│    - Account: 991105135552                                      │
│    - Region: us-east-1                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Authentication (NEW)
- **Amazon Cognito User Pool**: Manages user authentication
- **User Pool Client**: Enables username/password + SRP authentication
- **JWT Tokens**: Stored in browser sessionStorage
- **Login Page**: Client-side authentication with Cognito SDK

### 2. Presentation Layer
- **S3 Static Website**: Hosts login.html and index.html
- **login.html**: Cognito authentication form
- **index.html**: Real-time monitoring dashboard with auth check

### 3. API Layer
- **API Gateway**: REST API with CORS enabled
- **POST /telemetry**: Direct SQS integration (no Lambda)
- **GET /probes**: Lambda integration for reading data

### 4. Processing Layer
- **SQS Queue**: Decouples ingestion from processing
- **Lambda Processor**: Evaluates FPS and writes to DynamoDB
- **Lambda Reader**: Reads probe status from DynamoDB

### 5. Data Layer
- **DynamoDB**: NoSQL database for probe status
- **Pay-per-request billing**: Cost-effective for variable load

### 6. CI/CD (NEW)
- **GitHub Actions**: Automated deployment pipeline
- **AWS CDK**: Infrastructure as Code
- **OIDC Authentication**: Secure, keyless AWS access

## Security Features

1. **Authentication**: Cognito User Pool with password policy
2. **Authorization**: JWT tokens for API access
3. **HTTPS**: All communication encrypted
4. **CORS**: Configured for dashboard origin
5. **IAM Roles**: Least privilege access
6. **Session Management**: Tokens stored in sessionStorage (cleared on logout)

## Scalability Features

1. **SQS Buffering**: Handles traffic spikes
2. **Lambda Auto-scaling**: Scales with load
3. **DynamoDB On-demand**: Scales automatically
4. **API Gateway**: Handles millions of requests
5. **S3 Static Hosting**: Unlimited scalability

## Cost Optimization

1. **Serverless**: Pay only for usage
2. **No idle costs**: Zero cost when not in use
3. **Direct SQS integration**: Saves Lambda invocations
4. **On-demand billing**: No provisioned capacity
5. **S3 static hosting**: Cheapest hosting option

## Monitoring & Observability

1. **CloudWatch Logs**: Lambda execution logs
2. **CloudWatch Metrics**: API Gateway, SQS, Lambda metrics
3. **DynamoDB Metrics**: Read/write capacity usage
4. **Cognito Metrics**: Authentication attempts
5. **Dashboard**: Real-time probe status visualization

## Deployment Process

1. **Code Push**: Developer pushes to GitHub
2. **GitHub Actions**: Triggers deployment workflow
3. **CDK Synth**: Generates CloudFormation template
4. **CDK Deploy**: Deploys to AWS account 991105135552
5. **S3 Upload**: Dashboard files uploaded to S3
6. **Stack Update**: CloudFormation updates resources
7. **Verification**: Automated health checks

## Future Enhancements

1. **Multi-factor Authentication (MFA)**: Add to Cognito
2. **API Gateway Authorizer**: Validate JWT tokens
3. **CloudWatch Alarms**: Alert on probe failures
4. **SNS Notifications**: Email/SMS alerts
5. **Historical Data**: Store probe history in S3
6. **Advanced Analytics**: QuickSight dashboards
7. **Multi-region**: Deploy to multiple regions
8. **Custom Domain**: Route53 + CloudFront
