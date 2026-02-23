# Made4Net "Fortress & Factory" POC Requirements

## Overview
Demonstrate operational excellence and security posture for 24/7 warehouse management platform hosting.

## Target Audience
Sagi Van - Made4Net Leadership
Role: Global Hosting Team Manager

## Core Components to Demonstrate

### 1. Security Posture Dashboard
- Real-time threat detection status (GuardDuty simulation)
- WAF rule effectiveness metrics
- Encryption status (KMS, TLS)
- Compliance audit trail (Config changes)

### 2. Operational Excellence Dashboard
- System health monitoring (CloudWatch Canaries simulation)
- Patch compliance status (SSM Patch Manager simulation)
- Cost optimization metrics (Trusted Advisor findings)
- Multi-region availability status

### 3. Incident Response Simulator
- Simulate security events (unauthorized access, DDoS)
- Demonstrate automated response
- Show observability (X-Ray trace simulation)

### 4. Architecture Visualization
- Interactive diagram showing:
  - Zero Trust perimeter (WAF, Transit Gateway)
  - Compute layer (SSM, Golden AMIs)
  - Data layer (Encryption, Backup, DR)
  - Monitoring layer (GuardDuty, Canaries)

## Technical Stack
- **Frontend**: HTML5 + JavaScript (Chart.js for metrics)
- **Backend**: AWS Lambda (Node.js)
- **API**: API Gateway REST API
- **Storage**: DynamoDB (operational metrics)
- **Hosting**: S3 + CloudFront
- **Auth**: Cognito (simulating enterprise SSO)

## Key Metrics to Display

### Security Metrics
1. Threat Detection Events (last 24h)
2. WAF Blocked Requests (by rule type)
3. Failed Authentication Attempts
4. Encryption Coverage (% of resources)
5. Config Compliance Score

### Operational Metrics
1. System Availability (99.99% target)
2. Patch Compliance (% up-to-date)
3. Cost Optimization Savings ($)
4. Canary Success Rate
5. Mean Time to Resolution (MTTR)

### Multi-Region Status
- Primary Region: us-east-1 (Active)
- DR Region: us-west-2 (Standby)
- Cross-region replication lag

## User Stories

### US-1: Security Operations Center View
**As a** Security Operations Manager  
**I want to** see real-time security posture across all hosted environments  
**So that** I can respond to threats before they impact customers

**Acceptance Criteria:**
- Dashboard shows GuardDuty findings count
- WAF metrics display blocked attacks by type
- Compliance score is visible (0-100)
- Alert status for critical security events

### US-2: Operational Health Monitoring
**As a** Hosting Team Manager  
**I want to** monitor system health and patch compliance  
**So that** I can ensure 24/7 availability for 800+ warehouses

**Acceptance Criteria:**
- Canary health checks display per region
- Patch compliance shows % compliant servers
- Auto Scaling Group status visible
- Maintenance window schedule displayed

### US-3: Cost Optimization Tracking
**As a** Global Hosting Team Manager  
**I want to** track cost savings from automation  
**So that** I can demonstrate ROI to leadership

**Acceptance Criteria:**
- Monthly cost savings displayed
- Idle resource count shown
- Instance Scheduler savings calculated
- Trusted Advisor recommendations listed

### US-4: Incident Response Simulation
**As a** Operations Engineer  
**I want to** simulate security incidents  
**So that** I can demonstrate automated response capabilities

**Acceptance Criteria:**
- Trigger simulated DDoS attack
- Show WAF auto-blocking response
- Display GuardDuty alert generation
- Show automated remediation action

## Interview Talking Points Integration

### Patching Strategy
- Display SSM Patch Manager compliance dashboard
- Show rolling patch schedule (Dev → Test → Prod)
- Demonstrate zero-downtime patching

### Cost Efficiency
- Show 30% cost reduction metrics
- Display Instance Scheduler savings
- List Trusted Advisor recommendations

### Incident Resolution
- X-Ray trace visualization for slow requests
- Root cause analysis dashboard
- MTTR metrics

### Security Compliance
- AWS Config change history
- Audit trail for security group changes
- Compliance report generation

## Success Criteria
1. Dashboard loads in < 2 seconds
2. Real-time metrics update every 5 seconds
3. Mobile-responsive design
4. Professional Made4Net branding
5. Clear demonstration of all 4 architecture layers
