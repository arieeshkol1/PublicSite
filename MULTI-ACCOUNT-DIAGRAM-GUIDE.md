# Multi-Account Architecture Diagram Guide

## 🎨 Updated Diagram Structure

The architecture diagram should be restructured to show the proper multi-account AWS Organizations setup.

---

## 📊 Diagram Layout (Top to Bottom)

```
┌─────────────────────────────────────────────────────────────────┐
│                    AWS ORGANIZATIONS                            │
│                    (Management Account)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   SECURITY    │   │  OPERATIONS   │   │  PRODUCTION   │
│   ACCOUNT     │   │   ACCOUNT     │   │   ACCOUNT     │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────────────────────────────────────────────────┐
│              CROSS-ACCOUNT MONITORING                     │
└───────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  OUTPOSTS     │   │  OUTPOSTS     │   │  DR ACCOUNT   │
│  ACCOUNT #1   │   │  ACCOUNT #2   │   │  (us-west-2)  │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## 🔐 Security Account (Top Left)

### Visual Elements

**Account Box (Purple/Pink)**
```
┌─────────────────────────────────────┐
│  SECURITY ACCOUNT                   │
│  (Centralized Security & Compliance)│
├─────────────────────────────────────┤
│                                     │
│  [GuardDuty]  Threat Detection      │
│  [Config]     Compliance Monitoring │
│  [Security Hub] Security Posture    │
│  [CloudTrail] Audit Logs            │
│  [IAM Identity Center] SSO          │
│                                     │
│  Monitors: ALL ACCOUNTS             │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- AWS GuardDuty icon
- AWS Config icon
- AWS Security Hub icon
- AWS CloudTrail icon
- AWS IAM Identity Center icon

### Connections
- Dashed purple lines to all other accounts (monitoring)
- Label: "Security Monitoring & Compliance"

---

## 🔧 Operations Account (Top Middle)

### Visual Elements

**Account Box (Blue)**
```
┌─────────────────────────────────────┐
│  OPERATIONS ACCOUNT                 │
│  (Centralized Operations & Monitoring)│
├─────────────────────────────────────┤
│                                     │
│  [Systems Manager] Fleet Management │
│  [CloudWatch] Unified Monitoring    │
│  [X-Ray] Distributed Tracing        │
│  [Backup] Centralized Backup        │
│  [Health] AWS Health Dashboard      │
│                                     │
│  Manages: ALL WORKLOAD ACCOUNTS     │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- AWS Systems Manager icon
- Amazon CloudWatch icon
- AWS X-Ray icon
- AWS Backup icon
- AWS Health icon

### Connections
- Dashed blue lines to all workload accounts (management)
- Label: "Operational Management"

---

## 🏭 Production Account (Top Right)

### Visual Elements

**Account Box (Green)**
```
┌─────────────────────────────────────┐
│  PRODUCTION ACCOUNT                 │
│  (Main Workload - us-east-1)        │
├─────────────────────────────────────┤
│                                     │
│  VPC: Made4Net Production           │
│  ┌─────────────────────────────┐   │
│  │ [Transit Gateway]           │   │
│  │ [ALB] [API Gateway]         │   │
│  │ [EC2 ASG] [Lambda]          │   │
│  │ [RDS] [DynamoDB] [S3]       │   │
│  │ [CloudFront] [Cognito]      │   │
│  └─────────────────────────────┘   │
│                                     │
│  Connected to:                      │
│  • Standard Warehouses (VPN)        │
│  • Outposts Accounts (Service Link) │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- Transit Gateway (hub)
- ALB, API Gateway
- EC2 Auto Scaling Group
- RDS, DynamoDB, S3
- Lambda, CloudFront, Cognito

### Connections
- Solid green lines to Outposts Accounts
- Dashed green lines to DR Account (replication)
- Blue dashed lines from Operations Account
- Purple dashed lines from Security Account

---

## 🟧 Outposts Account #1 (Bottom Left)

### Visual Elements

**Account Box (Orange)**
```
┌─────────────────────────────────────┐
│  OUTPOSTS ACCOUNT #1                │
│  (Warehouse Group A: NY, Boston, PA)│
├─────────────────────────────────────┤
│                                     │
│  [Outposts Rack]                    │
│  [EC2 on Outposts]                  │
│  [EBS on Outposts]                  │
│                                     │
│  Service Link Status: Connected ●   │
│  Capacity: 75% (30/40 instances)    │
│                                     │
│  Connected to:                      │
│  Production Account (Transit GW)    │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- AWS Outposts Rack icon
- EC2 on Outposts icon
- EBS on Outposts icon
- AWS Health icon (for hardware events)

### Connections
- Orange solid line to Production Account Transit Gateway
- Label: "Service Link (Monitored)"
- Blue dashed line from Operations Account (management)
- Purple dashed line from Security Account (monitoring)

---

## 🟧 Outposts Account #2 (Bottom Middle)

### Visual Elements

**Account Box (Orange)**
```
┌─────────────────────────────────────┐
│  OUTPOSTS ACCOUNT #2                │
│  (Warehouse Group B: Chicago, etc.) │
├─────────────────────────────────────┤
│                                     │
│  [Outposts Rack]                    │
│  [EC2 on Outposts]                  │
│  [EBS on Outposts]                  │
│                                     │
│  Service Link Status: Connected ●   │
│  Capacity: 80% (32/40 instances)    │
│                                     │
│  Connected to:                      │
│  Production Account (Transit GW)    │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- AWS Outposts Rack icon
- EC2 on Outposts icon
- EBS on Outposts icon
- AWS Health icon

### Connections
- Orange solid line to Production Account Transit Gateway
- Label: "Service Link (Monitored)"
- Blue dashed line from Operations Account (management)
- Purple dashed line from Security Account (monitoring)

---

## 🔄 DR Account (Bottom Right)

### Visual Elements

**Account Box (Gray/Standby)**
```
┌─────────────────────────────────────┐
│  DR ACCOUNT                         │
│  (Disaster Recovery - us-west-2)    │
├─────────────────────────────────────┤
│                                     │
│  [RDS Read Replica] (Standby)       │
│  [S3 Replica] (Cross-Region)        │
│  [AMIs] (Copied)                    │
│  [CloudFormation] (Templates)       │
│                                     │
│  Status: Standby (Pilot Light)      │
│  Failover: Route 53 Health Check    │
│                                     │
└─────────────────────────────────────┘
```

### Services to Show
- RDS icon (with "Replica" label)
- S3 icon (with "CRR" label)
- EC2 AMI icon

### Connections
- Dashed gray line from Production Account
- Label: "Cross-Region Replication"

---

## 🏢 Warehouse Examples (Outside All Accounts)

### Warehouse #1 (Standard VPN)

**Location:** Far left, outside AWS Organizations box

```
┌─────────────────────┐
│ Warehouse #1        │
│ (Chicago)           │
│ Standard Deployment │
├─────────────────────┤
│ [Server Icon]       │
│ • WMS Application   │
│ • Barcode Scanners  │
│ • Wi-Fi Network     │
└─────────────────────┘
         │
         │ Site-to-Site VPN
         │ (Blue Dashed Line)
         ▼
   Production Account
   (Transit Gateway)
```

### Warehouse #2 (Outposts)

**Location:** Far left, below Warehouse #1

```
┌─────────────────────┐
│ Warehouse #2        │
│ (New York)          │
│ Outposts Deployment │
├─────────────────────┤
│ [Outposts Icon]     │
│ • Outposts Rack     │
│ • Local Compute     │
│ • Data Residency    │
└─────────────────────┘
         │
         │ Service Link
         │ (Orange Dashed Line)
         ▼
   Outposts Account #1
         │
         ▼
   Production Account
   (Transit Gateway)
```

---

## 🎨 Color Coding

| Account/Component | Color | Purpose |
|-------------------|-------|---------|
| **Security Account** | Purple/Pink (#C925D1) | Security services |
| **Operations Account** | Blue (#1976D2) | Operational services |
| **Production Account** | Green (#248814) | Workload resources |
| **Outposts Accounts** | Orange (#FF6F00) | On-premises hybrid |
| **DR Account** | Gray (#757575) | Standby/replica |
| **Warehouse #1** | Light Blue (#E3F2FD) | Standard VPN |
| **Warehouse #2** | Light Orange (#FFF3E0) | Outposts deployment |

---

## 🔗 Connection Types

### Solid Lines (Data Flow)
- **Green:** Production workload traffic
- **Orange:** Outposts service link
- **Blue:** Standard VPN connection

### Dashed Lines (Management/Monitoring)
- **Purple:** Security monitoring (from Security Account)
- **Blue:** Operational management (from Operations Account)
- **Gray:** Replication (to DR Account)

---

## 📋 Legend for Diagram

```
┌─────────────────────────────────────────────────────────┐
│  LEGEND                                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Account Types:                                         │
│  🟣 Security Account (Centralized Security)            │
│  🔵 Operations Account (Centralized Operations)        │
│  🟢 Production Account (Main Workload)                 │
│  🟧 Outposts Accounts (On-Premises Hybrid)             │
│  ⚪ DR Account (Disaster Recovery)                     │
│                                                         │
│  Connection Types:                                      │
│  ━━━ Solid Line: Data/Workload Traffic                │
│  ┈┈┈ Dashed Line: Management/Monitoring                │
│                                                         │
│  Deployment Models:                                     │
│  🔷 Standard Warehouse (VPN)                           │
│  🟧 Outposts Warehouse (Service Link)                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🎯 Key Messages for Diagram

### Multi-Account Benefits

**Security Isolation**
"Each account has its own security boundary. A breach in one account doesn't compromise others."

**Centralized Security**
"The Security Account monitors all accounts with GuardDuty, Config, and Security Hub."

**Centralized Operations**
"The Operations Account manages all workloads through Systems Manager and CloudWatch."

**Outposts Isolation**
"Outposts are in separate accounts for billing isolation and compliance. They connect to Production via service links."

**Cost Allocation**
"Each account tracks its own costs. We can charge back to business units accurately."

---

## 📊 Metrics to Show

### Per-Account Metrics

**Security Account**
- GuardDuty Findings: 0 high, 2 medium
- Config Compliance: 98%
- Security Hub Score: 95/100

**Operations Account**
- Managed Instances: 250 across all accounts
- Backup Success Rate: 99.5%
- Patch Compliance: 95%+

**Production Account**
- EC2 Instances: 150 running
- RDS: 45% CPU, Healthy
- ALB: 5,000 req/min

**Outposts Account #1**
- Service Link: Connected ●
- EC2 Capacity: 75% (30/40)
- EBS Capacity: 60% (6TB/10TB)

**Outposts Account #2**
- Service Link: Connected ●
- EC2 Capacity: 80% (32/40)
- EBS Capacity: 55% (5.5TB/10TB)

---

## 🚀 Implementation Notes

### For draw.io

1. **Create Account Boxes**
   - Use rounded rectangles
   - Color-code by account type
   - Add account name and purpose

2. **Add Service Icons**
   - Use AWS icon library
   - Group services by account
   - Label each service

3. **Draw Connections**
   - Solid lines for data flow
   - Dashed lines for management
   - Color-code by purpose
   - Add labels to connections

4. **Add Warehouse Examples**
   - Place outside AWS Organizations box
   - Show connection to appropriate account
   - Label connection type

5. **Add Legend**
   - Bottom of diagram
   - Explain colors and line types
   - Show account types

---

**This multi-account structure follows AWS best practices and demonstrates enterprise-grade architecture!** 🏢
