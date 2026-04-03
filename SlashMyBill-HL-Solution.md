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
| CI/CD | GitHub Actions + OIDC | Automated deployment on push to main |

### 2.2 Cross-Account Access Model

Members deploy a CloudFormation template in their AWS account that creates:
- IAM Role: `SlashMyBill-{AccountID}` with `ReadOnlyAccess` managed policy
- Inline policy: Cost Explorer, Budgets, Pricing, Trusted Advisor, stack self-management
- Trust policy: Platform account (991105135552) with ExternalId = SHA-256(member_email)

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
- Fetches on-demand and 1-year No Upfront RI pricing for top spending services
- Calculates exact monthly savings per instance type
- Supports EC2, RDS, ElastiCache pricing comparisons

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

### 5.5 Knowledge Base (RAG)
- DynamoDB table: ViewMyBill-CostOptimizationTips (32+ tips by service)
- Queried by service keyword matching from the question
- AI-generated tips auto-saved back to the knowledge base

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

### 8.1 Lambda Functions (6)
| Function | Memory | Timeout | Purpose |
|----------|--------|---------|---------|
| aws-bill-analyzer-viewmybill | 1024 MB | 900s | Bill PDF analysis |
| aws-bill-analyzer-upload-handler | 256 MB | 30s | PDF upload + validation |
| aws-bill-analyzer-otp-handler | 128 MB | 30s | OTP send/verify |
| aws-bill-analyzer-admin-api | 128 MB | 30s | Admin CRUD |
| aws-bill-analyzer-member-api | 256 MB | 120s | Member portal + AI agent |
| SlashMyBill-AgentAction | 256 MB | 120s | Bedrock Agent actions |

### 8.2 DynamoDB Tables (6)
| Table | Partition Key | Sort Key | Purpose |
|-------|--------------|----------|---------|
| ViewMyBill-Leads | email | timestamp | Contact leads |
| ViewMyBill-CostOptimizationTips | service | tipId | RAG knowledge base |
| ViewMyBill-OTP | email | — | OTP codes (TTL 5min) |
| MemberPortal-Members | email | — | Member accounts |
| MemberPortal-Accounts | memberEmail | accountId | Connected AWS accounts |

### 8.3 Other Resources
- API Gateway HTTP v2 (15+ routes, auto-deploy)
- SES Email Identity (eshkolai.com, DKIM verified)
- IAM Roles (per Lambda, with least-privilege policies)
- Lambda Permissions (API Gateway + Bedrock invoke)

---

## 9. CI/CD Pipeline

**Trigger:** Push to `main` branch (or manual dispatch)
**Platform:** GitHub Actions with AWS OIDC authentication

### Pipeline Steps:
1. Package 6 Lambda functions with dependencies → S3
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
