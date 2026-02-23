# Made4Net POC Architecture Diagram - Complete Guide

## Overview

This diagram depicts the POC/Demo system architecture with 2 Windows EC2 instances (free tier) including frontend, backend, database, and basic failover capabilities.

---

## 🎨 Diagram Structure

### External Layer
- **End Users** - Access inventory management UI
- **Admin Users** - RDP access for management

### AWS Cloud (Free Tier)
- **VPC:** 10.0.0.0/16
- **Public Subnet:** 10.0.1.0/24 (Frontend)
- **Private Subnet:** 10.0.2.0/24 (Backend)
- **Supporting Services:** S3, CloudWatch

---

## 🏗️ Architecture Components

### Frontend EC2 Instance (Public Subnet)

**Specifications:**
- **OS:** Windows Server 2022
- **Instance Type:** t2.micro (1 vCPU, 1GB RAM)
- **Storage:** 30GB EBS General Purpose SSD
- **Network:** Public subnet with Elastic IP
- **Web Server:** IIS 10.0

**Features:**
- Made4Net WMS Branded UI (Logo, Colors)
- Inventory Management Interface
- Internal Application Authentication (username/password stored in SQL Server)
- User Roles: Admin, Manager, Operator
- Responsive Design (Bootstrap)
- HTTPS Enabled
- Session Management (30 min timeout)

**Security:**
- **Security Group:**
  - Inbound HTTPS (443) from 0.0.0.0/0
  - Inbound RDP (3389) from admin IP only
  - Outbound: All traffic
- **Windows Firewall:** Enabled with IIS exceptions
- **SSL:** Self-signed certificate (demo) or Let's Encrypt
- **Application Authentication:** Separate from AWS/Windows authentication (username/password in SQL Server)

---

### Backend EC2 Instance (Private Subnet)

**Specifications:**
- **OS:** Windows Server 2022
- **Instance Type:** t2.micro (1 vCPU, 1GB RAM)
- **Storage:** 30GB EBS General Purpose SSD
- **Network:** Private subnet (10.0.2.x)
- **Runtime:** .NET Framework 4.8 or .NET 6

**Database:**
- **SQL Server Express 2019**
- **Database Name:** InventoryDB
- **Size Limit:** 10GB
- **Tables:** Users, Inventory, AuditLog
- **Backup:** Daily automated to S3

**API Endpoints:**
- `POST /api/auth/login` - Authentication
- `GET /api/inventory` - List items
- `POST /api/inventory` - Add item
- `PUT /api/inventory/{id}` - Update item
- `DELETE /api/inventory/{id}` - Delete item
- `GET /api/health` - Health check

**Security:**
- **Security Group:**
  - Inbound HTTPS (443) from Frontend-SG only
  - Inbound RDP (3389) from admin IP only
  - Outbound: All traffic
- **Authentication:** JWT tokens
- **Encryption:** TLS 1.2+ for all API calls

---

## 🔄 Failover & High Availability

### Automated Recovery
- **Method:** AWS Instance Recovery
- **RTO:** 5-10 minutes
- **Scope:** Same AZ recovery
- **Trigger:** Instance status check failure

### Manual Failover
- **Method:** Launch from AMI + Restore from S3
- **RTO:** 15-30 minutes
- **RPO:** 24 hours (daily backup)
- **Process:**
  1. Launch new instance from latest AMI
  2. Restore database from S3 backup
  3. Update Elastic IP association
  4. Verify application functionality

### Health Monitoring
- **Frontend:** HTTP GET /health every 60 seconds
- **Backend:** SQL Server connection test every 60 seconds
- **CloudWatch Alarms:** Alert on failures
- **Notifications:** Email/SMS to admin

### Backup Strategy
- **Database:** Daily automated backup to S3
- **AMI Snapshots:** Weekly automated snapshots
- **Retention:** 7 days for daily, 4 weeks for weekly
- **Storage:** S3 Standard (free tier: 5GB)

### Free Tier Limitations
⚠️ **Important Constraints:**
- No Multi-AZ deployment
- No Application Load Balancer
- No Auto Scaling
- Single point of failure per tier
- Manual intervention required for some scenarios

---

## 🌐 Network Architecture

### VPC Configuration
```
VPC: 10.0.0.0/16
├── Public Subnet: 10.0.1.0/24
│   ├── Frontend EC2 (Made4Net WMS)
│   └── Internet Gateway
└── Private Subnet: 10.0.2.0/24
    └── Backend EC2 (API + SQL Server)
```

### Traffic Flow

**End User Access (Application Users):**
```
Warehouse Manager/Operator
  ↓ ① HTTPS (443) - Made4Net Login
Internet Gateway
  ↓
Frontend EC2 (Public Subnet) - Made4Net WMS UI
  ↓ ② API Calls (HTTPS) - JWT Token
Backend EC2 (Private Subnet) - REST API
  ↓ ③ Database Queries
SQL Server Express (InventoryDB.Users table)
```

**Admin Access (System Administrators):**
```
Hosting Engineer
  ↓ RDP (3389) - AWS IAM + Windows Auth
Internet Gateway
  ↓
Frontend EC2 (Jump Box)
  ↓ RDP - Windows Auth
Backend EC2 (Infrastructure Management)
```

### Security Groups

**Frontend-SG:**
```
Inbound:
- HTTPS (443) from 0.0.0.0/0
- RDP (3389) from [Admin IP]

Outbound:
- All traffic
```

**Backend-SG:**
```
Inbound:
- HTTPS (443) from Frontend-SG
- RDP (3389) from [Admin IP]

Outbound:
- All traffic
```

---

## 💰 Cost Analysis

| Resource | Quantity | Free Tier | Monthly Cost |
|----------|----------|-----------|--------------|
| t2.micro EC2 | 2 instances | 750 hrs/month each | $0 |
| EBS Storage | 60GB total | 30GB free | $0 |
| S3 Storage | 5GB backups | 5GB free | $0 |
| Data Transfer | <15GB/month | 15GB free | $0 |
| Elastic IP | 1 (attached) | Free when attached | $0 |
| **Total** | | **12 months free** | **$0-5/month** |

**After Free Tier (12 months):**
- 2x t2.micro: ~$16/month
- 60GB EBS: ~$6/month
- S3 + Transfer: ~$2/month
- **Total:** ~$24/month

---

## 📋 Deployment Steps

### Prerequisites
- AWS Account (Free Tier eligible)
- Admin IP address for RDP access
- Basic Windows Server knowledge

### Step 1: VPC Setup (10 minutes)
1. Create VPC: 10.0.0.0/16
2. Create Internet Gateway and attach
3. Create Public Subnet: 10.0.1.0/24
4. Create Private Subnet: 10.0.2.0/24
5. Configure route tables:
   - Public: 0.0.0.0/0 → IGW
   - Private: Local only

### Step 2: Security Groups (5 minutes)
1. Create Frontend-SG:
   - Inbound: HTTPS (443), RDP (3389)
2. Create Backend-SG:
   - Inbound: HTTPS (443) from Frontend-SG, RDP (3389)

### Step 3: Launch Frontend EC2 (15 minutes)
1. Launch t2.micro with Windows Server 2022
2. Place in public subnet
3. Assign Frontend-SG
4. Allocate and attach Elastic IP
5. Connect via RDP
6. Install IIS via Server Manager
7. Configure Windows Firewall

### Step 4: Launch Backend EC2 (15 minutes)
1. Launch t2.micro with Windows Server 2022
2. Place in private subnet
3. Assign Backend-SG
4. Connect via RDP (through frontend as jump box)
5. Install SQL Server Express 2019
6. Install .NET Framework/Runtime

### Step 5: Deploy Application (30 minutes)
1. **Frontend:**
   - Copy web application files to IIS wwwroot
   - Configure IIS site bindings
   - Set up SSL certificate
   - Test web UI access

2. **Backend:**
   - Deploy API application
   - Create InventoryDB database
   - Run schema creation scripts
   - Seed initial data
   - Test API endpoints

### Step 6: Configure Backups (10 minutes)
1. Create S3 bucket for backups
2. Configure SQL Server backup job
3. Set up CloudWatch alarms
4. Create AMI snapshots
5. Test restore procedure

### Step 7: Testing (20 minutes)
1. Test end user login
2. Test inventory CRUD operations
3. Test API connectivity
4. Verify database operations
5. Test failover procedures
6. Verify monitoring alerts

**Total Deployment Time:** ~2 hours

---

## 🎯 Use Cases

### ✅ Suitable For:
- **Sales Demonstrations:** Show WMS capabilities to prospects
- **Training Environment:** Hands-on training for users
- **Development Testing:** Test features before production
- **Proof of Concept:** Validate architecture decisions
- **Customer Trials:** Temporary access for evaluation
- **Internal Demos:** Showcase to stakeholders

### ❌ Not Suitable For:
- Production workloads (no HA)
- Large databases (>10GB limit)
- High traffic (performance constraints)
- Mission-critical operations
- Compliance requirements (single AZ)
- Enterprise features (clustering, replication)

---

## 🎤 Interview Talking Points

### Architecture Overview

**Question:** "Walk me through the POC architecture."

**Answer:** "Our POC system is a cost-effective demonstration environment running entirely on AWS free tier. It consists of two Windows Server 2022 t2.micro instances. The frontend in the public subnet runs IIS hosting our Made4Net WMS branded inventory management web UI with internal application authentication. The backend in the private subnet runs .NET with SQL Server Express for the REST API and database. 

We have two distinct authentication layers: Layer 1 is internal application authentication where warehouse staff (managers, operators) log into the Made4Net WMS using username/password stored in SQL Server. Layer 2 is external system administration where hosting engineers use AWS IAM with MFA to access the AWS Console and Windows authentication for RDP access to manage the infrastructure.

Users access the system via HTTPS through an Internet Gateway, the frontend calls the backend API over HTTPS with JWT tokens, and the backend queries SQL Server. We have daily database backups to S3, CloudWatch monitoring, and both automated and manual failover capabilities. The entire system costs $0-5 per month during the 12-month free tier period."

### Failover Strategy

**Question:** "How does failover work?"

**Answer:** "We implement two levels of failover. First, AWS automated instance recovery monitors health checks and automatically recovers failed instances within 5-10 minutes in the same availability zone. Second, we maintain weekly AMI snapshots and daily database backups to S3, enabling manual failover by launching a new instance and restoring the database within 15-30 minutes. While this isn't enterprise-grade HA—we don't have Multi-AZ, load balancers, or auto-scaling due to free tier constraints—it provides adequate resilience for a demo environment and demonstrates the concepts."

### Security Model

**Question:** "How is the POC system secured?"

**Answer:** "Security is implemented in layers with two distinct authentication systems. For application users (warehouse staff), we have internal authentication using username/password stored in SQL Server with hashed passwords (bcrypt/PBKDF2). For system administrators, we use AWS IAM with MFA for AWS Console access and Windows Authentication for RDP access to EC2 instances—these are completely separate systems.

At the network level, the frontend is in a public subnet with security groups allowing only HTTPS from the internet and RDP from our admin IP. The backend is in a private subnet with no direct internet access, accepting only HTTPS from the frontend security group. All API communication uses TLS 1.2+ with JWT token authentication. The database uses Windows Authentication. We have CloudWatch monitoring for anomaly detection and all RDP sessions are logged. While it's not production-grade security, it demonstrates security best practices and proper separation of concerns between application users and system administrators."

---

## 📁 File Information

**Filename:** `Made4Net-POC-Architecture.drawio`
**Format:** draw.io XML
**Canvas Size:** 1920x1080
**Created:** $(date)
**Version:** 1.0

---

## 🚀 How to Use This Diagram

### Opening
1. Open draw.io (desktop or https://app.diagrams.net/)
2. File → Open → Select `Made4Net-POC-Architecture.drawio`

### Exporting
- **PNG:** File → Export as → PNG (300 DPI)
- **PDF:** File → Export as → PDF
- **SVG:** File → Export as → SVG

---

## ✅ Diagram Features

- [x] Frontend EC2 with IIS
- [x] Backend EC2 with .NET + SQL Server
- [x] VPC with public/private subnets
- [x] Security groups clearly labeled
- [x] Traffic flow arrows (numbered)
- [x] Failover strategy box
- [x] Cost analysis box
- [x] Health monitoring (CloudWatch)
- [x] Backup to S3
- [x] Legend and key features
- [x] Color-coded components

---

**Status:** ✅ DIAGRAM COMPLETE
**Components:** 2 EC2, VPC, S3, CloudWatch
**Cost:** $0-5/month (Free Tier)
**Ready for Use:** YES
