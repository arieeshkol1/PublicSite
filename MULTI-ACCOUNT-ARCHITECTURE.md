# Multi-Account AWS Architecture for Made4Net

## 🏢 AWS Organizations Structure

Following AWS best practices, the Made4Net architecture uses a **multi-account strategy** for security, compliance, and operational isolation.

---

## 📊 Account Structure

```
AWS Organizations (Root)
│
├── Management Account (Org Root)
│   └── AWS Organizations, Control Tower, Billing
│
├── Security Account
│   ├── AWS GuardDuty (Threat Detection)
│   ├── AWS Config (Compliance Monitoring)
│   ├── AWS Security Hub (Centralized Security)
│   ├── AWS CloudTrail (Audit Logs - Organization Trail)
│   └── AWS IAM Identity Center (SSO)
│
├── Operations Account
│   ├── AWS Systems Manager (Fleet Management)
│   ├── Amazon CloudWatch (Centralized Monitoring)
│   ├── AWS X-Ray (Distributed Tracing)
│   ├── AWS Backup (Centralized Backup)
│   └── AWS Health Dashboard
│
├── Production Account (Workload)
│   ├── VPC (Production Network)
│   ├── Transit Gateway
│   ├── EC2 Auto Scaling Groups
│   ├── RDS Multi-AZ
│   ├── DynamoDB
│   ├── S3 Buckets
│   ├── Lambda Functions
│   ├── ALB / API Gateway
│   └── CloudFront
│
├── Outposts Account #1 (Warehouse Group A)
│   ├── AWS Outposts Rack
│   ├── EC2 on Outposts
│   ├── EBS on Outposts
│   └── VPN/Service Link to Production
│
├── Outposts Account #2 (Warehouse Group B)
│   ├── AWS Outposts Rack
│   ├── EC2 on Outposts
│   ├── EBS on Outposts
│   └── VPN/Service Link to Production
│
└── DR Account (us-west-2)
    ├── RDS Read Replica
    ├── S3 Cross-Region Replication
    └── Standby Resources
```

---

## 🔐 Security Account Details

### Purpose
Centralized security monitoring, compliance, and audit logging for all accounts.

### Services

**AWS GuardDuty**
- Threat detection across all accounts
- Monitors VPC Flow Logs, CloudTrail, DNS logs
- **Monitors Outposts instances** via VPC Flow Logs
- Detects threats: SSH brute force, port scanning, malicious IPs
- Alerts on suspicious activity
- Delegated administrator for organization

**Amazon Inspector**
- **Vulnerability scanning across all accounts** (including Outposts)
- Uses SSM Agent to collect software inventory
- Continuous CVE scanning
- Network exposure detection
- Tracks configuration changes
- Automated rescanning when new CVEs published

**AWS Config**
- Compliance monitoring across all accounts
- Tracks configuration changes
- Compliance rules enforcement
- Aggregated view of all resources

**AWS Security Hub**
- Centralized security findings
- Aggregates from GuardDuty, Inspector, Config
- Security standards compliance (CIS, PCI-DSS)
- Automated remediation workflows

**AWS CloudTrail**
- Organization trail (logs all accounts)
- Immutable audit log
- Stored in dedicated S3 bucket
- Encrypted with KMS

**AWS IAM Identity Center (SSO)**
- Single sign-on for all accounts
- MFA enforcement
- Role-based access control
- Integration with corporate directory

### Cross-Account Access
```
Security Account
    ↓ (Read-Only Access)
Production Account
Operations Account
Outposts Accounts
DR Account
```

---

## 🔧 Operations Account Details

### Purpose
Centralized operational monitoring, management, and automation for all accounts.

### Services

**AWS Systems Manager**
- Fleet Manager (unified view of all EC2 instances)
- Session Manager (secure remote access)
- Patch Manager (automated patching)
- Run Command (bulk operations)
- State Manager (configuration management)
- Cross-account access to all workload accounts

**Amazon CloudWatch**
- Centralized monitoring dashboard
- Cross-account observability
- Metrics from all accounts
- Unified alarms and notifications
- Log aggregation (CloudWatch Logs Insights)

**AWS X-Ray**
- Distributed tracing across accounts
- Application performance monitoring
- Service map visualization
- Cross-account trace aggregation

**AWS Backup**
- Centralized backup management
- Cross-account backup policies
- Cross-region backup replication
- Compliance reporting

**AWS Health Dashboard**
- Organization-wide health events
- Outposts hardware alerts
- Service disruption notifications
- Proactive notifications

### Cross-Account Access
```
Operations Account
    ↓ (Management Access)
Production Account (EC2, RDS, etc.)
Outposts Accounts (EC2 on Outposts)
DR Account (Standby resources)
```

---

## 🏭 Production Account Details

### Purpose
Main workload account hosting customer-facing applications and data.

### Services

**Networking**
- VPC (Production Network)
- Transit Gateway (hub for all connections)
- Site-to-Site VPN (warehouse connections)
- Direct Connect (high-volume warehouses)

**Compute**
- EC2 Auto Scaling Groups
- Lambda Functions
- ECS/EKS (if containerized)

**Data**
- RDS Multi-AZ (encrypted)
- DynamoDB (point-in-time recovery)
- S3 Buckets (versioned, encrypted)
- ElastiCache (if needed)

**Application**
- Application Load Balancer
- API Gateway
- CloudFront (CDN)
- Cognito (user authentication)

**Monitoring (Local)**
- CloudWatch Logs (sent to Operations Account)
- CloudWatch Metrics (sent to Operations Account)
- VPC Flow Logs (sent to Security Account)

### Cross-Account Connections
```
Production Account
    ↑ Monitored by Operations Account
    ↑ Secured by Security Account
    ↓ Replicates to DR Account
    ↔ Connects to Outposts Accounts
```

---

## 🟧 Outposts Accounts Details

### Purpose
Separate accounts for Outposts deployments at warehouse locations.

### Why Separate Accounts?

1. **Billing Isolation:** Track Outposts costs per warehouse group
2. **Security Boundary:** Isolate on-premises resources
3. **Compliance:** Meet data residency requirements
4. **Blast Radius:** Limit impact of security incidents
5. **Multi-Tenancy:** Support different customers/divisions

### Account Structure

**Outposts Account #1 (Warehouse Group A)**
- Warehouses: New York, Boston, Philadelphia
- AWS Outposts Rack
- EC2 on Outposts (local compute)
- EBS on Outposts (local storage)
- Service Link to Production Account (via Transit Gateway)

**Outposts Account #2 (Warehouse Group B)**
- Warehouses: Chicago, Detroit, Milwaukee
- AWS Outposts Rack
- EC2 on Outposts (local compute)
- EBS on Outposts (local storage)
- Service Link to Production Account (via Transit Gateway)

### Connectivity

**Service Link (Outposts → AWS Region)**
```
Outposts Account
    ↓ Service Link (monitored)
    │ • Minimum: 500 Mbps
    │ • Recommended: 1 Gbps+
    │ • Redundant connections
    │ • Via Direct Connect or Internet
Production Account (Transit Gateway)
    ↓
Production VPC Resources
```

**VPC Extension Model**
```
Production Account VPC (10.0.0.0/16)
    ├── Region Subnets: 10.0.1.0/24, 10.0.2.0/24
    └── Extended to Outpost
        └── Outpost Subnet: 10.0.10.0/24
            └── EC2 on Outposts: 10.0.10.x
```

**VPC Endpoints (PrivateLink)**
- com.amazonaws.region.ssm (Systems Manager)
- com.amazonaws.region.ec2messages (SSM Agent communication)
- com.amazonaws.region.ssmmessages (Session Manager)
- com.amazonaws.region.ec2 (EC2 API)
- com.amazonaws.region.s3 (S3 access)
- com.amazonaws.region.inspector2 (Inspector scanning)

**Local Gateway (LGW)**
- Connectivity to on-premises network
- BGP peering with customer routers
- Enables local traffic routing
- Monitored via CloudWatch metrics

**Cross-Account Access**
```
Operations Account
    ↓ (Management via Systems Manager)
Outposts Account
    ↓ (Workload traffic)
Production Account
```

**Security Monitoring**
```
Security Account
    ↓ (GuardDuty, Inspector, Config)
Outposts Account
    ├── VPC Flow Logs → GuardDuty
    ├── SSM Agent → Inspector
    └── Config Rules → Config
```

---

## 🔄 DR Account Details

### Purpose
Disaster recovery resources in secondary region (us-west-2).

### Services

**Data Replication**
- RDS Read Replica (cross-region)
- S3 Cross-Region Replication
- DynamoDB Global Tables (if needed)

**Standby Resources**
- AMIs (copied from Production)
- Launch Templates
- CloudFormation templates
- Pilot Light architecture

### Failover Process
```
Production Account (us-east-1) FAILS
    ↓
Route 53 Health Check Detects Failure
    ↓
Route 53 Failover to DR Account (us-west-2)
    ↓
DR Account Scales Up Resources
    ↓
Traffic Served from DR Region
```

---

## 🌐 Network Architecture

### Transit Gateway (Hub-and-Spoke)

```
                    Transit Gateway
                    (Production Account)
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   Production VPC    Outposts Account   Outposts Account
   (us-east-1)            #1                 #2
                     (via Service Link) (via Service Link)
```

### VPN Connections

**Standard Warehouses → Production Account**
```
Warehouse (Chicago)
    ↓ Site-to-Site VPN
Transit Gateway (Production Account)
    ↓
Production VPC
```

**Outposts → Production Account**
```
Outposts Account
    ↓ Service Link (dedicated connection)
Transit Gateway (Production Account)
    ↓
Production VPC
```

---

## 🔐 Cross-Account IAM Roles

### Security Account Roles

**SecurityAuditor Role**
- Read-only access to all accounts
- Used by: Security team, compliance auditors
- Permissions: View logs, configurations, security findings

**SecurityAdmin Role**
- Administrative access to security services
- Used by: Security operations team
- Permissions: Manage GuardDuty, Config, Security Hub

### Operations Account Roles

**OperationsAdmin Role**
- Management access to operational services
- Used by: Operations team, SREs
- Permissions: Systems Manager, CloudWatch, Backup

**OperationsReadOnly Role**
- Read-only access to monitoring data
- Used by: Developers, support team
- Permissions: View metrics, logs, traces

### Production Account Roles

**ApplicationAdmin Role**
- Administrative access to application resources
- Used by: DevOps team
- Permissions: Manage EC2, RDS, Lambda, etc.

**ApplicationDeveloper Role**
- Limited access for development tasks
- Used by: Developers
- Permissions: Deploy code, view logs, limited resource access

### Outposts Account Roles

**OutpostsAdmin Role**
- Administrative access to Outposts resources
- Used by: Outposts operations team
- Permissions: Manage EC2 on Outposts, EBS, networking

**OutpostsReadOnly Role**
- Read-only access to Outposts resources
- Used by: Warehouse managers, support team
- Permissions: View resources, metrics, status

---

## 📊 Monitoring & Observability

### Centralized Monitoring (Operations Account)

**CloudWatch Dashboard**
```
┌─────────────────────────────────────────────────────┐
│  Made4Net Unified Operations Dashboard              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Production Account (us-east-1)                    │
│    • EC2 Instances: 150 running                    │
│    • RDS: Healthy, 45% CPU                         │
│    • ALB: 5,000 req/min                            │
│                                                     │
│  Outposts Account #1 (Warehouse Group A)           │
│    • Service Link: Connected ●                     │
│    • EC2 Capacity: 75% (30/40 instances)           │
│    • EBS Capacity: 60% (6TB/10TB)                  │
│                                                     │
│  Outposts Account #2 (Warehouse Group B)           │
│    • Service Link: Connected ●                     │
│    • EC2 Capacity: 80% (32/40 instances)           │
│    • EBS Capacity: 55% (5.5TB/10TB)                │
│                                                     │
│  Security Account                                   │
│    • GuardDuty Findings: 0 high, 2 medium          │
│    • Config Compliance: 98%                        │
│    • Security Hub Score: 95/100                    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Cross-Account Observability

**CloudWatch Cross-Account Setup**
```
Operations Account (Monitoring Account)
    ↓ (Cross-Account IAM Role)
Production Account (Source Account)
Outposts Account #1 (Source Account)
Outposts Account #2 (Source Account)
DR Account (Source Account)
```

---

## 🚨 Alerting Strategy

### Alert Routing by Account

**Security Account Alerts**
- GuardDuty findings → Security team (PagerDuty)
- Config non-compliance → Compliance team (Email)
- Security Hub critical → Security operations (Slack + PagerDuty)

**Operations Account Alerts**
- High CPU/Memory → Operations team (Slack)
- Backup failures → Backup team (Email)
- Health events → On-call engineer (PagerDuty)

**Production Account Alerts**
- Application errors → Development team (Slack)
- Database issues → DBA team (PagerDuty)
- ALB 5xx errors → Operations team (Slack)

**Outposts Account Alerts**
- Service link down → Network team (PagerDuty - P1)
- Capacity >80% → Capacity planning team (Email)
- Hardware failure → AWS support + Operations (PagerDuty - P1)

---

## 💰 Cost Management

### Cost Allocation by Account

**Production Account**
- Application workloads
- Data storage
- Network transfer
- ~60% of total AWS spend

**Outposts Accounts**
- Outposts hardware subscription
- Local compute and storage
- ~30% of total AWS spend

**Operations Account**
- Monitoring and management tools
- ~5% of total AWS spend

**Security Account**
- Security services
- Audit logging storage
- ~3% of total AWS spend

**DR Account**
- Standby resources
- Cross-region replication
- ~2% of total AWS spend

### Cost Optimization

**AWS Cost Explorer**
- Per-account cost tracking
- Tag-based cost allocation
- Anomaly detection

**AWS Budgets**
- Per-account budgets
- Alerts at 80%, 90%, 100%
- Automated actions (optional)

---

## 📋 Compliance & Governance

### AWS Control Tower

**Guardrails (Preventive)**
- Disallow public S3 buckets
- Require encryption at rest
- Enforce MFA for root accounts
- Restrict regions (us-east-1, us-west-2 only)

**Guardrails (Detective)**
- Detect unencrypted EBS volumes
- Detect public RDS instances
- Detect IAM users without MFA
- Detect non-compliant resources

### AWS Config Rules

**Organization-Wide Rules**
- encrypted-volumes
- rds-multi-az-support
- s3-bucket-versioning-enabled
- cloudtrail-enabled
- iam-password-policy
- vpc-flow-logs-enabled

### Compliance Reporting

**Automated Reports**
- Weekly compliance summary (all accounts)
- Monthly security posture report
- Quarterly audit readiness report
- Real-time non-compliance alerts

---

## 🎯 Benefits of Multi-Account Architecture

### Security
✅ **Blast Radius Containment:** Security incident in one account doesn't affect others
✅ **Least Privilege:** Fine-grained access control per account
✅ **Audit Trail:** Clear separation of responsibilities
✅ **Compliance:** Meet regulatory requirements for data isolation

### Operations
✅ **Centralized Management:** Operations Account manages all workloads
✅ **Unified Monitoring:** Single dashboard for all accounts
✅ **Automated Remediation:** Cross-account automation
✅ **Simplified Troubleshooting:** Clear account boundaries

### Cost
✅ **Cost Allocation:** Track costs per account/business unit
✅ **Budget Control:** Per-account budgets and alerts
✅ **Chargeback:** Bill internal teams accurately
✅ **Optimization:** Identify cost drivers per account

### Compliance
✅ **Data Residency:** Outposts accounts for on-premises data
✅ **Audit Readiness:** Centralized audit logs in Security Account
✅ **Regulatory Compliance:** Meet industry-specific requirements
✅ **Change Tracking:** AWS Config across all accounts

---

## 🚀 Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- [ ] Set up AWS Organizations
- [ ] Create Management Account
- [ ] Deploy AWS Control Tower
- [ ] Create Security Account
- [ ] Create Operations Account

### Phase 2: Workload Accounts (Week 3-4)
- [ ] Create Production Account
- [ ] Create DR Account
- [ ] Set up Transit Gateway
- [ ] Configure VPN connections

### Phase 3: Outposts Integration (Week 5-6)
- [ ] Create Outposts Account #1
- [ ] Create Outposts Account #2
- [ ] Configure Service Links
- [ ] Test cross-account connectivity

### Phase 4: Monitoring & Security (Week 7-8)
- [ ] Configure CloudWatch cross-account observability
- [ ] Set up GuardDuty organization-wide
- [ ] Deploy AWS Config rules
- [ ] Configure Security Hub
- [ ] Set up centralized logging

### Phase 5: Operations & Automation (Week 9-10)
- [ ] Configure Systems Manager cross-account
- [ ] Set up automated patching
- [ ] Deploy backup policies
- [ ] Configure alerting workflows
- [ ] Test disaster recovery procedures

---

**This multi-account architecture provides enterprise-grade security, compliance, and operational excellence for Made4Net's 800+ warehouse infrastructure.** 🏢
