# SlashMyBill — High-Level Solution Document

## 1. Executive Summary

SlashMyBill is an AI-powered AWS FinOps platform that helps organizations analyze, optimize, and reduce their cloud spending. Members connect their AWS accounts via a secure cross-account IAM role, then use a conversational AI agent to ask natural language questions about their costs, get real-time pricing comparisons, detect anomalies, and receive actionable savings recommendations — all backed by live AWS API data.

**Platform URL:** https://www.eshkolai.com/members/
**AWS Account:** 991105135552 (us-east-1)

---

## 2. Architecture Overview

### 2.1 Core Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | HTML/CSS/JS + Chart.js | Member Portal with AI Agent, tables, charts |
| API Gateway | HTTP API v2 (15+ routes) | Request routing to Lambda handlers |
| Member Handler | Python 3.12 Lambda | Auth, accounts, AI queries, data gathering |
| Agent Action | Python 3.12 Lambda | Bedrock Agent action group (cross-account) |
| Bill Analyzer | Python 3.12 Lambda | PDF bill parsing + Bedrock analysis |
| AI Engine | Amazon Bedrock (Nova Lite v1) | Natural language analysis + recommendations |
| Bedrock Agent | SlashMyBill-FinOps-Agent | Orchestrated multi-step FinOps analysis |
| Storage | DynamoDB (6 tables) + S3 | Members, accounts, tips, OTP, leads, bills |
| Email | Amazon SES | OTP verification emails |
| CDN | CloudFront + Route 53 | HTTPS delivery, DNS |
| Scheduler Executor | Python 3.12 Lambda (slashmybill-scheduler-executor, 512 MB / 300s) | Cross-account stop/start/scale execution for automated schedules |
| EventBridge Scheduler | Amazon EventBridge Scheduler | Recurring schedule triggers for automated resource management |
| CI/CD | GitHub Actions + OIDC | Automated deployment on push to main |

### 2.2 Cross-Account Access Model

Members deploy a CloudFormation template in their AWS account that creates:
- IAM Role: `SlashMyBill-{AccountID}` with `ReadOnlyAccess` managed policy
- Inline policy: Cost Explorer, Budgets, Pricing, Trusted Advisor, stack self-management
- Trust policy: Platform account (991105135552) with ExternalId = SHA-256(member_email)
- Write permissions (for Scheduler): `ec2:StartInstances`, `rds:StopDBInstance`, `rds:StartDBInstance`, `eks:UpdateNodegroupConfig`, `eks:DescribeNodegroup`, `sagemaker:StopNotebookInstance`, `sagemaker:StartNotebookInstance`, `redshift:PauseCluster`, `redshift:ResumeCluster`, `workspaces:ModifyWorkspaceProperties`, `ec2:ModifyVolume`

---

## 3. AI Agent Data Flow

```
User Question → JWT Auth → Route Dispatch
                              ↓
                    ┌─────────┴──────────┐
                    │ Bedrock Agent?      │
                    │ (if configured)     │
                    └─────────┬──────────┘
                         Yes  │  No (fallback)
                              ↓
                    ┌─────────┴──────────┐
                    │ _invoke_direct_model│
                    └─────────┬──────────┘
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
        Search Tips     Assume Role     Gather Data
        (DynamoDB)      (STS)           (10+ APIs)
              ↓               ↓               ↓
              └───────────────┼───────────────┘
                              ↓
                    ┌─────────┴──────────┐
                    │ Bedrock Nova Lite   │
                    │ (prompt + data)     │
                    └─────────┬──────────┘
                              ↓
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
         AI Answer      Chart Data      Save Tip
              ↓               ↓          (DynamoDB)
              └───────┬───────┘
                      ↓
              Frontend Rendering
              (text + drill-downs + tables + charts)
```

---

## 4. Data Gathering Pipeline

The `_gather_account_data()` function collects data from the customer's AWS account via cross-account role assumption:

### 4.1 Always Fetched
| API Call | Data Collected |
|----------|---------------|
| `ce:GetCostAndUsage` (monthly) | Cost by service (last 30 days) |
| `ce:GetCostAndUsage` (daily) | Daily cost trend (last 7 days) |
| `ce:GetCostAndUsage` (usage type) | VPC + EC2-Other breakdown |

### 4.2 Conditionally Fetched (based on top costs or question keywords)
| API Call | Trigger | Data Collected |
|----------|---------|---------------|
| `ec2:DescribeInstances` | Question mentions EC2/instances | Instance inventory |
| `ec2:DescribeNatGateways` | VPC or EC2-Other in top costs | NAT Gateway count |
| `ec2:DescribeAddresses` | VPC or EC2-Other in top costs | Elastic IPs (idle) |
| `ec2:DescribeVpcEndpoints` | VPC or EC2-Other in top costs | VPC endpoint inventory |
| `ec2:DescribeVolumes` | VPC or EC2-Other in top costs | EBS volumes (unattached) |
| `rds:DescribeDBInstances` | RDS in top costs or question | RDS instance details |
| `kms:ListKeys` | KMS in top costs or question | Customer-managed key count |
| `lambda:ListFunctions` | Question mentions Lambda | Function configs |
| `cloudwatch:GetMetricStatistics` | Question mentions usage/invocations | Lambda invocations, EC2 CPU |
| `route53:ListHostedZones` | Route 53 in top costs | Hosted zone count |
| `pricing:GetProducts` | Top spending services | On-demand vs RI pricing |
| `eks:ListClusters` + `eks:DescribeCluster` | EKS/ECS in top costs or question mentions Kubernetes/containers | EKS cluster inventory, status, version |
| `ecs:ListClusters` + `ecs:DescribeClusters` | EKS/ECS in top costs or question mentions containers | ECS cluster inventory, running tasks, registered instances |
| `s3:GetBucketLifecycleConfiguration` | S3 in top costs or question mentions storage | Lifecycle policy presence per bucket |
| `s3:ListBucketIntelligentTieringConfigurations` | S3 in top costs or question mentions storage | Intelligent-Tiering enablement per bucket |
| `compute-optimizer:GetEC2InstanceRecommendations` | EC2 Compute in top costs or question mentions rightsizing | Rightsizing recommendations with estimated monthly savings |

### 4.3 Month Comparison (triggered by comparison keywords)
| Pattern | Action |
|---------|--------|
| "compare Feb and March" | Fetch both months separately from CE |
| "last 3 months" / "past quarter" | Fetch MONTHLY granularity for N months |
| Hebrew: "תשווה 3 חודשים" | Same as above (Hebrew keyword detection) |

---

## 5. FinOps Intelligence Features

### 5.1 Cost Efficiency Score
- Formula: `[1 - (Potential Savings / Total Spend)] × 100%`
- Aggregates savings from: unattached EBS, idle EIPs, deleted VPC endpoints, KMS keys, gp2→gp3 migration
- Rating scale: Excellent (≥90%), Good (≥75%), Needs Improvement (≥50%), Critical (<50%)
- Includes savings breakdown showing each component with dollar amounts

### 5.2 Cost Anomaly Detection
- Compares each day's cost to the 7-day average
- Flags days with cost > 2× the average as anomalies
- Reports spike percentage and date

### 5.3 Real-Time Pricing Engine
- Fetches on-demand pricing for top spending services via AWS Pricing API
- Calculates three pricing tiers per instance type:
  - On-Demand: full price (baseline reference)
  - Compute Savings Plan: ~30% discount (recommended default commitment)
  - Spot Instances: ~70% discount (for fault-tolerant/stateless workloads)
- Generates capacity mix recommendation per instance type:
  - 30% Savings Plan (baseline stability) + 70% Spot (cost optimization)
  - Shows blended monthly cost and total savings vs pure on-demand
- Reserved Instances kept as fallback only for rigid, high-commitment scenarios
- Enforces "Rightsize Before You Commit" workflow:
  1. Analyze utilization via Compute Optimizer
  2. Recommend rightsizing for OVER_PROVISIONED instances
  3. Calculate Savings Plan discount on the RIGHT-SIZED instance type
  4. Never recommend commitments on oversized instances

### 5.4 Waste Detection
- Unattached EBS volumes (with volume IDs and per-volume cost)
- Idle Elastic IPs ($3.65/month each)
- Lambda functions with 0 invocations (deletion candidates)
- Functions hitting timeout limits or with 100% error rates
- VPC endpoints deleted mid-month (charges explained)
- KMS customer-managed keys ($1/month each)
- EKS/ECS clusters with 0 running tasks (deletion candidates)
- ECS clusters with low task-to-instance ratio (over-provisioned nodes)
- S3 buckets without lifecycle policies (missing data tiering)
- S3 buckets without Intelligent-Tiering (paying Standard rates for infrequent data)
- EC2 instances flagged as OVER_PROVISIONED by AWS Compute Optimizer

### 5.5 AWS Compute Optimizer Integration
- Fetches `compute-optimizer:GetEC2InstanceRecommendations` for rightsizing
- Shows current instance type, recommended type, finding classification
- Calculates estimated monthly savings per instance
- Findings: OVER_PROVISIONED, UNDER_PROVISIONED, OPTIMIZED
- Savings automatically included in Cost Efficiency Score

### 5.6 Kubernetes/Container Cost Analysis
- EKS: cluster count, status, version, platform version
- ECS: cluster count, running tasks, pending tasks, registered instances, active services
- Flags clusters with 0 running tasks as deletion candidates
- Identifies over-provisioned ECS clusters (many instances, few tasks)

### 5.7 S3 Storage Optimization
- Checks each bucket for lifecycle policy presence
- Checks each bucket for Intelligent-Tiering configuration
- Reports buckets needing lifecycle policies (data not being tiered)
- Reports buckets needing Intelligent-Tiering (paying Standard rates unnecessarily)
- Recommends S3-IA for 30-90 day data, Glacier for 90+ day data

### 5.8 Automated Scheduler

SlashMyBill's Automated Scheduler lets members create recurring schedules to stop, start, and scale AWS resources automatically.

- **EventBridge Scheduler** in the platform account (991105135552) triggers a dedicated **Scheduler Executor Lambda** (`slashmybill-scheduler-executor`) at the configured times.
- The executor assumes the cross-account role (`SlashMyBill-{accountId}`) into the customer's account and performs the actual stop/start/scale actions.
- **12 schedule types**: EC2 stop/start, RDS stop/start, ASG scale-to-zero, EKS scale-to-zero, SageMaker stop, Redshift pause, WorkSpaces auto-stop, ELB teardown, plus 4 review types (waste scan, snapshot cleanup, gp2→gp3 migration, SP/RI review).
- **Schedule pair pattern**: Stop/start types create two EventBridge schedules (e.g., `smb-{id}-stop` and `smb-{id}-start`). Review types create a single schedule.
- **Lifecycle management**: Create, pause (disables without deleting), resume, and delete — all backed by real EventBridge Scheduler schedules.
- **Execution history tracking**: Each run records success/partial/failure with per-resource details. The frontend shows the last 10 runs per schedule.
- **Frontend**: Real schedule cards with Active/Paused status, next execution time, Pause/Resume/Delete buttons, and expandable execution history.
- **Admin visibility**: Admin panel Schedules tab shows all schedules across all members with stats and failure drill-down.
- **API endpoints**: `PUT /members/schedules/pause`, `PUT /members/schedules/resume`, `DELETE /members/schedules/delete`, `GET /admin/schedules`.

### 5.9 Knowledge Base (RAG)
- DynamoDB table: ViewMyBill-CostOptimizationTips (32+ tips by service)
- Queried by service keyword matching from the question
- AI-generated tips auto-saved back to the knowledge base

### 5.10 SQL Platform Comparator (Act > SQL Compare)

A side-by-side cost comparison wizard for SQL Server workloads that helps members find the cheapest deployment option and migrate with step-by-step guidance.

- **Discovery**: Scans EC2 Windows+SQL instances (via AMI description detection) and RDS SQL Server instances across all charged regions
- **4 deployment options compared per workload**:
  - EC2 Windows + SQL License Included (self-managed, license bundled)
  - EC2 Windows only + BYOL SQL (self-managed, bring your own license)
  - RDS SQL Server Standard (managed)
  - RDS SQL Server Enterprise (managed)
- **Pricing**: Queries AWS Pricing API (us-east-1) for all 4 options per instance type
- **Comparison table**: Shows monthly cost, savings vs current, highlights cheapest option
- **Migrate button**: Generates step-by-step migration plan for each cheaper alternative
- **7 migration templates**: EC2→BYOL, EC2→RDS Std, EC2→RDS Ent, RDS Std→EC2, RDS Std→BYOL, RDS Ent→BYOL, RDS Ent→RDS Std
- **API endpoints**: `POST /members/sql/compare`, `POST /members/sql/migration-plan`

### 5.11 Windows/SQL Licensing Optimizer (Act > Optimize > Optimize Licensing)

Dedicated licensing scan that discovers all Windows Server and SQL Server workloads, analyzes 30-day utilization, and generates a ranked report card of savings strategies:
- **5 strategies**: BYOL, Optimize CPUs, Memory-Optimized Swap, Edition Downgrade, Dedicated Host
- **Compute Optimizer integration**: ML-based rightsizing recommendations
- **SQL Edition Downgrade assessment**: Enterprise-only feature checklist
- **API endpoint**: `POST /members/licensing/scan`

---

## 6. Frontend Visualization Pipeline

### 6.1 Answer Flow
```
AI Answer (text) → Drill-down buttons → "Show as Table" buttons
                                              ↓
                                    Click table button
                                              ↓
                                    Render sortable table
                                    (with totals row)
                                              ↓
                                    Chart format toggles
                                    (Bar / Line / Doughnut / Pie)
                                              ↓
                                    Render Chart.js visualization
```

### 6.2 Chart Types Generated
| Chart ID | Type | Data Source |
|----------|------|------------|
| service-costs | Horizontal Bar | Cost by service (30 days) |
| daily-trend | Line | Daily cost trend (7 days) |
| vpc-breakdown | Doughnut | VPC usage type breakdown |
| ec2other-breakdown | Doughnut | EC2-Other usage type breakdown |
| month-comparison | Grouped Bar | Two-month comparison |
| monthly-total-trend | Line | Multi-month total cost |
| monthly-service-trend | Grouped Bar | Top services by month |
| lambda-invocations | Horizontal Bar | Lambda invocation counts |
| efficiency-score | Doughnut | Cost efficiency gauge |

### 6.3 Smart Chart Type Suggestions
- Time series data → Line + Bar
- Breakdown data → Doughnut + Pie + Bar
- Multi-month data → Grouped Bar + Line
- General data → Bar + Doughnut + Line

### 6.4 Context-Aware Drill-Downs
- Comparison questions → "What caused the biggest increase?", "Which services trending up?"
- Efficiency questions → Resource-specific drill-downs (EBS, VPC, KMS, Lambda)
- General questions → Answer-content-based suggestions

---

## 7. Security Model

| Layer | Mechanism |
|-------|-----------|
| Authentication | JWT tokens (HS256, 24h expiry) |
| Registration | 3-step OTP flow via SES (5-min TTL, rate-limited) |
| Password | bcrypt hashing with salt |
| Cross-Account | STS AssumeRole with ExternalId (SHA-256 of email) |
| API Security | CORS restricted to eshkolai.com |
| Data Encryption | DynamoDB SSE, S3 default encryption |
| IAM | ReadOnlyAccess + minimal billing inline policy |
| Deployment | GitHub OIDC → IAM Role (no stored credentials) |

---

## 8. Infrastructure (CloudFormation Stack)

**Stack Name:** aws-bill-analyzer-viewmybill

### 8.1 Lambda Functions (7)
| Function | Memory | Timeout | Purpose |
|----------|--------|---------|---------|
| aws-bill-analyzer-viewmybill | 1024 MB | 900s | Bill PDF analysis |
| aws-bill-analyzer-upload-handler | 256 MB | 30s | PDF upload + validation |
| aws-bill-analyzer-otp-handler | 128 MB | 30s | OTP send/verify |
| aws-bill-analyzer-admin-api | 128 MB | 30s | Admin CRUD |
| aws-bill-analyzer-member-api | 256 MB | 120s | Member portal + AI agent |
| SlashMyBill-AgentAction | 256 MB | 120s | Bedrock Agent actions |
| slashmybill-scheduler-executor | 512 MB | 300s | Cross-account scheduled actions (stop/start/scale) |

### 8.2 DynamoDB Tables (8)
| Table | Partition Key | Sort Key | Purpose |
|-------|--------------|----------|---------|
| ViewMyBill-Leads | email | timestamp | Contact leads |
| ViewMyBill-CostOptimizationTips | service | tipId | RAG knowledge base |
| ViewMyBill-OTP | email | — | OTP codes (TTL 5min) |
| MemberPortal-Members | email | — | Member accounts |
| MemberPortal-Accounts | memberEmail | accountId | Connected AWS accounts |
| Audit_Transaction_Log | transaction_id | start_timestamp | AI query audit trail + evaluations + healed answers |
| Cost_Cache_Table | pk (email#accountId) | sk (VENDOR#accountId#date) | Cached daily cost data from CE (avoids repeated API charges) |
| SpotSavingsLedger | accountId | timestamp | Spot instance savings tracking |

### 8.3 Other Resources
- API Gateway HTTP v2 (15+ routes, auto-deploy)
- SES Email Identity (eshkolai.com, DKIM verified)
- IAM Roles (per Lambda, with least-privilege policies)
- Lambda Permissions (API Gateway + Bedrock invoke)
- SlashMyBill-EventBridge-Scheduler-Role (trusted by `scheduler.amazonaws.com`, invokes Scheduler Executor Lambda)
- slashmybill-scheduler-executor-role (STS AssumeRole to customer accounts, DynamoDB write for execution history)

---

## 9. CI/CD Pipeline

**Trigger:** Push to `main` branch (or manual dispatch)
**Platform:** GitHub Actions with AWS OIDC authentication

### Pipeline Steps:
1. Package 7 Lambda functions with dependencies → S3 (includes scheduler-executor packaging step)
2. Deploy CloudFormation stack (IAM capabilities)
3. Update Lambda function code from S3
4. Seed DynamoDB knowledge base
5. Deploy website files to S3 (www.eshkolai.com)
6. Inject API Gateway URL into frontend JS
7. Sync to eshkolai.com bucket
8. Invalidate CloudFront cache

---

## 10. Prompt Engineering Summary

The AI prompt includes 20+ rules governing response quality:
- Strict cost-descending ranking
- Tax excluded from analysis
- Services < $0.50 grouped as "Minor costs"
- Deleted-mid-month resources explained (not "review non-existent resources")
- Real pricing data required (no generic percentages)
- Specific resource IDs in recommendations
- Context-aware responses (comparison vs efficiency vs specific questions)
- Hebrew language support for comparisons
- Cost Efficiency Score shown prominently
- Savings breakdown with per-component dollar amounts
