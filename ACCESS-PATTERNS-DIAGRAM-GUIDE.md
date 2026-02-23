# Made4Net Access Patterns - Complete Diagram Guide

## Overview

This guide shows how to create a comprehensive diagram depicting three access patterns:
1. **End User Access** (Warehouse Manager - Tenant Login)
2. **IoT Device Access** (Robots, Sensors, Smart Shelves)
3. **Hosting Engineer Access** (Troubleshooting & Support)

---

## 🎨 Color Coding

- **End User Flow:** Blue (#0066CC)
- **IoT Device Flow:** Green (#00AA00)
- **Hosting Engineer Flow:** Orange (#FF6600)
- **Security Services:** Purple (#9B59B6)
- **Data Services:** Teal (#00CED1)
- **Networking:** Gray (#7F8C8D)

---

## 📐 Diagram Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                  MADE4NET ACCESS PATTERNS                       │
│              End User | IoT Device | Hosting Engineer           │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┬──────────────────┬──────────────────────────┐
│   END USER       │   IoT DEVICE     │   HOSTING ENGINEER       │
│   (Blue)         │   (Green)        │   (Orange)               │
├──────────────────┼──────────────────┼──────────────────────────┤
│                  │                  │                          │
│ [User Icon]      │ [Robot Icon]     │ [Engineer Icon]          │
│      ↓           │      ↓           │      ↓                   │
│ Cloudflare       │ IoT Core         │ AWS Console              │
│      ↓           │      ↓           │      ↓                   │
│ ALB              │ Rules Engine     │ Systems Manager          │
│      ↓           │      ↓           │      ↓                   │
│ EC2 + Cognito    │ Kinesis/Lambda   │ Fleet Manager            │
│      ↓           │      ↓           │      ↓                   │
│ RDS              │ DynamoDB/S3      │ Session Manager          │
│                  │                  │      ↓                   │
│                  │                  │ EC2 Instance             │
│                  │                  │                          │
└──────────────────┴──────────────────┴──────────────────────────┘
```

---

## 🔵 ACCESS PATTERN 1: End User (Tenant Login)

### Components to Add

1. **User Icon** (Top Left)
   - Icon: Person/User symbol
   - Label: "Warehouse Manager"
   - Annotation: "Web Browser"
   - Color: Blue (#0066CC)

2. **Cloudflare**
   - Icon: AWS Cloudflare
   - Label: "Amazon Cloudflare"
   - Annotations:
     - "Global CDN"
     - "WAF Protection"
     - "DDoS Shield"
   - Color: Orange (#FF9900)

3. **Application Load Balancer**
   - Icon: AWS ALB
   - Label: "Application Load Balancer"
   - Annotations:
     - "SSL Termination"
     - "Multi-AZ"
   - Color: Pink (#FF69B4)

4. **EC2 Auto Scaling**
   - Icon: AWS EC2 Auto Scaling
   - Label: "EC2 Auto Scaling Group"
   - Annotation: "WMS Application"
   - Color: Orange (#FF9900)

5. **Amazon Cognito**
   - Icon: AWS Cognito
   - Label: "Amazon Cognito"
   - Annotation: "Multi-Tenant SSO"
   - Color: Red (#DC143C)

6. **Amazon RDS**
   - Icon: AWS RDS
   - Label: "Amazon RDS"
   - Annotation: "Tenant Database"
   - Color: Blue (#0066CC)

### Connection Flow

```
[Warehouse Manager]
    │
    │ ① HTTPS (443)
    │ https://customer-a.made4net.com
    ▼
[Amazon Cloudflare]
    │
    │ ② Origin Request
    │ SSL/TLS
    ▼
[Application Load Balancer]
    │
    │ ③ Load Balanced
    │ Health Checks
    ▼
[EC2 Auto Scaling Group]
    │
    ├─④─→ [Amazon Cognito]
    │      (Authentication)
    │
    └─⑤─→ [Amazon RDS]
           (Data Query)
```

### Labels for Arrows

- ① "HTTPS (443) - Web Request"
- ② "Origin Request - SSL/TLS"
- ③ "Load Balanced - Multi-AZ"
- ④ "Authentication - SSO + MFA"
- ⑤ "Database Query - Tenant Isolated"

### Text Box Annotation

```
┌─────────────────────────────────────┐
│ END USER ACCESS (Case 1)            │
├─────────────────────────────────────┤
│ • Protocol: HTTPS (443)             │
│ • Auth: Cognito SSO + MFA           │
│ • Latency: <200ms                   │
│ • Entry: Cloudflare → ALB           │
│ • Security: WAF + DDoS Shield       │
│ • Pattern: Request/Response         │
└─────────────────────────────────────┘
```

---

## 🟢 ACCESS PATTERN 2: IoT Device (Robots/Sensors)

### Components to Add

1. **IoT Device Icons** (Top Center)
   - Robot icon: "Autonomous Robot"
   - Sensor icon: "RFID Sensor"
   - Shelf icon: "Smart Shelf"
   - Scanner icon: "Barcode Scanner"
   - Group in container: "Warehouse Floor Devices"
   - Color: Green (#00AA00)

2. **AWS IoT Core**
   - Icon: AWS IoT Core
   - Label: "AWS IoT Core"
   - Annotation: "MQTT Broker"
   - Color: Green (#00AA00)

3. **IoT Rules Engine**
   - Icon: AWS IoT Rules
   - Label: "IoT Rules Engine"
   - Annotation: "Message Routing"
   - Color: Green (#00AA00)

4. **Kinesis Data Streams**
   - Icon: AWS Kinesis
   - Label: "Kinesis Data Streams"
   - Annotation: "Real-Time Path"
   - Color: Orange (#FF9900)

5. **AWS Lambda**
   - Icon: AWS Lambda
   - Label: "AWS Lambda"
   - Annotation: "Data Processing"
   - Color: Orange (#FF9900)

6. **Amazon DynamoDB**
   - Icon: AWS DynamoDB
   - Label: "Amazon DynamoDB"
   - Annotation: "Hot Storage"
   - Color: Blue (#0066CC)

7. **Kinesis Firehose**
   - Icon: AWS Kinesis Firehose
   - Label: "Kinesis Firehose"
   - Annotation: "Analytics Path"
   - Color: Orange (#FF9900)

8. **Amazon S3**
   - Icon: AWS S3
   - Label: "Amazon S3"
   - Annotation: "Cold Storage"
   - Color: Green (#00AA00)

9. **Amazon Athena**
   - Icon: AWS Athena
   - Label: "Amazon Athena"
   - Annotation: "SQL Analytics"
   - Color: Blue (#0066CC)

10. **IoT Events**
    - Icon: AWS IoT Events
    - Label: "AWS IoT Events"
    - Annotation: "Anomaly Detection"
    - Color: Red (#DC143C)

11. **Amazon SNS**
    - Icon: AWS SNS
    - Label: "Amazon SNS"
    - Annotation: "Alerts"
    - Color: Pink (#FF69B4)

### Connection Flow

```
[Warehouse Floor Devices]
    │
    │ ① MQTT/TLS (8883)
    │ X.509 Certificates
    ▼
[AWS IoT Core]
    │
    │ ② Message Routing
    ▼
[IoT Rules Engine]
    │
    ├─③─→ [Kinesis Data Streams] ─④─→ [Lambda] ─⑤─→ [DynamoDB]
    │      (Real-Time Hot Path)
    │
    ├─⑥─→ [Kinesis Firehose] ─⑦─→ [S3] ─⑧─→ [Athena]
    │      (Analytics Cold Path)
    │
    └─⑨─→ [IoT Events] ─⑩─→ [SNS] ─⑪─→ [Operations Team]
           (Anomaly Alerts)
```

### Labels for Arrows

- ① "MQTT/TLS (8883) - Telemetry"
- ② "Message Routing - Rules Engine"
- ③ "Real-Time Stream"
- ④ "Process Data"
- ⑤ "Store Hot Data"
- ⑥ "Analytics Stream"
- ⑦ "Archive to S3"
- ⑧ "SQL Queries"
- ⑨ "Anomaly Detection"
- ⑩ "Alert Notification"
- ⑪ "Ops Team Alert"

### Text Box Annotation

```
┌─────────────────────────────────────┐
│ IoT DEVICE ACCESS (Case 2)          │
├─────────────────────────────────────┤
│ • Protocol: MQTT/TLS (8883)         │
│ • Auth: X.509 Certificates          │
│ • Latency: <50ms                    │
│ • Entry: IoT Core → Rules Engine    │
│ • Devices: Robot, Sensor, Shelf     │
│ • Pattern: Persistent Connection    │
│                                     │
│ Data Paths:                         │
│ 1. Real-Time: Kinesis → DynamoDB    │
│ 2. Analytics: Firehose → S3         │
│ 3. Alerts: IoT Events → SNS         │
└─────────────────────────────────────┘
```

### Outposts Variant (Add Below Main Flow)

```
[IoT Device on Outpost]
    │
    │ Local Network
    ▼
[Local Gateway (LGW)]
    │
    ├─→ [AWS Lambda on Outpost]
    │    (Local Processing <10ms)
    │
    └─→ [Service Link]
         │
         ▼
    [AWS IoT Core in Region]
    (Aggregated Data Only)
```

---

## 🟠 ACCESS PATTERN 3: Hosting Engineer (Troubleshooting)

### Components to Add

1. **Engineer Icon** (Top Right)
   - Icon: Person with wrench/tools
   - Label: "Hosting Engineer"
   - Annotation: "Operations Team"
   - Color: Orange (#FF6600)

2. **AWS Console**
   - Icon: AWS Management Console
   - Label: "AWS Management Console"
   - Annotation: "Web Interface"
   - Color: Orange (#FF9900)

3. **AWS Systems Manager**
   - Icon: AWS Systems Manager
   - Label: "AWS Systems Manager"
   - Annotation: "Central Hub"
   - Color: Pink (#FF69B4)

4. **Fleet Manager**
   - Icon: Systems Manager Fleet
   - Label: "Fleet Manager"
   - Annotation: "Instance Inventory"
   - Color: Blue (#0066CC)

5. **Session Manager**
   - Icon: Systems Manager Session
   - Label: "Session Manager"
   - Annotation: "Secure Shell Access"
   - Color: Green (#00AA00)

6. **CloudWatch**
   - Icon: AWS CloudWatch
   - Label: "Amazon CloudWatch"
   - Annotation: "Monitoring & Logs"
   - Color: Red (#DC143C)

7. **AWS X-Ray**
   - Icon: AWS X-Ray
   - Label: "AWS X-Ray"
   - Annotation: "Distributed Tracing"
   - Color: Purple (#9B59B6)

8. **Target EC2 Instance**
   - Icon: AWS EC2
   - Label: "EC2 Instance"
   - Annotation: "Troubleshooting Target"
   - Color: Orange (#FF9900)

### Connection Flow

```
[Hosting Engineer]
    │
    │ ① HTTPS (443)
    │ IAM Credentials + MFA
    ▼
[AWS Management Console]
    │
    │ ② Navigate to Service
    ▼
[AWS Systems Manager]
    │
    ├─③─→ [Fleet Manager]
    │      │
    │      │ ④ View Instance Inventory
    │      │ • OS Version
    │      │ • Patch Status
    │      │ • Health Metrics
    │      │
    │      └─⑤─→ Select Target Instance
    │
    ├─⑥─→ [Session Manager]
    │      │
    │      │ ⑦ Initiate Secure Session
    │      │ • No SSH/RDP ports
    │      │ • IAM-based access
    │      │ • Session logging
    │      │
    │      └─⑧─→ [EC2 Instance]
    │             (Shell Access)
    │
    ├─⑨─→ [CloudWatch]
    │      │
    │      │ ⑩ View Metrics & Logs
    │      │ • CPU/Memory/Disk
    │      │ • Application Logs
    │      │ • Custom Metrics
    │      │
    │      └─⑪─→ Logs Insights Query
    │
    └─⑫─→ [AWS X-Ray]
           │
           │ ⑬ Trace Analysis
           │ • Service Map
           │ • Latency Breakdown
           │ • Error Detection
           │
           └─⑭─→ Identify Root Cause
```

### Labels for Arrows

- ① "HTTPS - IAM Auth + MFA"
- ② "Navigate to Systems Manager"
- ③ "Open Fleet Manager"
- ④ "View Inventory"
- ⑤ "Select Instance"
- ⑥ "Open Session Manager"
- ⑦ "Start Session (No SSH)"
- ⑧ "Shell Access"
- ⑨ "Open CloudWatch"
- ⑩ "View Metrics/Logs"
- ⑪ "Query Logs"
- ⑫ "Open X-Ray"
- ⑬ "Analyze Traces"
- ⑭ "Root Cause Found"

### Text Box Annotation

```
┌─────────────────────────────────────┐
│ HOSTING ENGINEER ACCESS (Case 3)    │
├─────────────────────────────────────┤
│ • Protocol: HTTPS (443)             │
│ • Auth: IAM Credentials + MFA       │
│ • Access: AWS Console               │
│ • Entry: Systems Manager            │
│ • Security: No SSH/RDP Ports        │
│ • Pattern: Interactive Session      │
│                                     │
│ Troubleshooting Tools:              │
│ 1. Fleet Manager - Inventory        │
│ 2. Session Manager - Shell Access   │
│ 3. CloudWatch - Metrics & Logs      │
│ 4. X-Ray - Distributed Tracing      │
│ 5. Run Command - Bulk Operations    │
└─────────────────────────────────────┘
```

### Additional Troubleshooting Tools (Add Below)

```
[Additional Tools]
    │
    ├─→ [Run Command]
    │    • Execute commands on multiple instances
    │    • Restart services
    │    • Collect diagnostics
    │
    ├─→ [Patch Manager]
    │    • View patch compliance
    │    • Apply patches
    │    • Schedule maintenance
    │
    ├─→ [State Manager]
    │    • Configuration management
    │    • Enforce desired state
    │    • Automated remediation
    │
    └─→ [Parameter Store]
         • Retrieve configuration
         • Secrets management
         • Version control
```

---

## 📊 Comparison Table (Add to Diagram)

Create a table showing all three access patterns:

| Aspect | End User | IoT Device | Hosting Engineer |
|--------|----------|------------|------------------|
| **Who** | Warehouse Manager | Robot/Sensor | Operations Team |
| **Protocol** | HTTPS (443) | MQTT/TLS (8883) | HTTPS (443) |
| **Auth** | Cognito SSO | X.509 Certs | IAM + MFA |
| **Entry** | Cloudflare | IoT Core | Systems Manager |
| **Latency** | <200ms | <50ms | <100ms |
| **Purpose** | Use Application | Send Telemetry | Troubleshoot |
| **Pattern** | Request/Response | Persistent | Interactive |
| **Security** | WAF + DDoS | Certificate Rotation | No SSH/RDP |

---

## 🔐 Security Overlay (Add as Separate Layer)

Show how security services monitor all three access patterns:

```
┌─────────────────────────────────────────────────────────┐
│              SECURITY MONITORING LAYER                  │
│                  (Security Account)                     │
└─────────────────────────────────────────────────────────┘

[AWS GuardDuty]
    │ Monitors VPC Flow Logs
    ├─→ End User Traffic
    ├─→ IoT Device Traffic
    └─→ Engineer Access

[Amazon Inspector]
    │ Vulnerability Scanning
    └─→ All EC2 Instances

[AWS Config]
    │ Compliance Monitoring
    └─→ All Resources

[AWS CloudTrail]
    │ API Call Auditing
    ├─→ User Actions
    ├─→ IoT Actions
    └─→ Engineer Actions

[AWS Security Hub]
    │ Unified Findings
    └─→ All Security Services
```

---

## 🎨 Step-by-Step Implementation

### Step 1: Open the Diagram
1. Open `Made4Net-Access-Patterns.drawio` in draw.io
2. Set canvas size: 1920x1080 (landscape)

### Step 2: Create Layout Structure
1. Add title at top: "Made4Net Access Patterns & User Flows"
2. Divide canvas into 3 vertical sections
3. Add section headers: "End User", "IoT Device", "Hosting Engineer"

### Step 3: Add End User Flow (Left Section)
1. Add user icon at top
2. Add Cloudflare below
3. Add ALB below Cloudflare
4. Add EC2 Auto Scaling
5. Add Cognito and RDS side-by-side
6. Connect with blue arrows
7. Add labels and annotations
8. Add text box with details

### Step 4: Add IoT Device Flow (Center Section)
1. Add device icons at top (robot, sensor, shelf, scanner)
2. Add IoT Core below
3. Add Rules Engine
4. Add three data paths:
   - Left: Kinesis → Lambda → DynamoDB
   - Center: Firehose → S3 → Athena
   - Right: IoT Events → SNS
5. Connect with green arrows
6. Add labels and annotations
7. Add text box with details
8. Add Outposts variant below

### Step 5: Add Hosting Engineer Flow (Right Section)
1. Add engineer icon at top
2. Add AWS Console below
3. Add Systems Manager
4. Add Fleet Manager, Session Manager, CloudWatch, X-Ray
5. Add target EC2 instance at bottom
6. Connect with orange arrows
7. Add labels and annotations
8. Add text box with details
9. Add additional tools section

### Step 6: Add Comparison Table
1. Insert table at bottom of diagram
2. Add 8 rows, 4 columns
3. Fill in comparison data
4. Style with colors

### Step 7: Add Security Overlay
1. Create new layer: "Security"
2. Add security services at top
3. Show monitoring connections to all three flows
4. Use dashed lines for monitoring
5. Use purple color for security

### Step 8: Final Touches
1. Align all elements
2. Ensure consistent spacing
3. Add legend for colors
4. Add footer with date and version
5. Review all labels and annotations

---

## 📤 Export Instructions

1. **Save the file:** `Made4Net-Access-Patterns.drawio`

2. **Export as PNG:**
   - File → Export as → PNG
   - Resolution: 300 DPI
   - Transparent background: No
   - Border width: 10px
   - Save as: `Made4Net-Access-Patterns.png`

3. **Export as PDF:**
   - File → Export as → PDF
   - Include: All pages
   - Fit to: 1 page
   - Save as: `Made4Net-Access-Patterns.pdf`

4. **Export as SVG:**
   - File → Export as → SVG
   - Save as: `Made4Net-Access-Patterns.svg`

---

## 🎤 Interview Talking Points

### Overview
"This diagram shows three distinct access patterns in our Made4Net architecture: end users accessing the WMS application, IoT devices sending telemetry data, and hosting engineers troubleshooting issues. Each pattern has different security, latency, and protocol requirements."

### End User Access
"Warehouse managers access the system through Cloudflare with WAF protection. Requests flow through an Application Load Balancer to tenant-specific EC2 instances. Cognito handles multi-tenant authentication with MFA, and each tenant has an isolated database schema. This gives us sub-200ms response times globally."

### IoT Device Access
"IoT devices like robots and sensors connect via MQTT to IoT Core using X.509 certificates. The Rules Engine routes data to three paths: real-time processing for immediate inventory updates, analytics for historical analysis, and anomaly detection for proactive alerts. For Outposts, we process data locally with AWS Lambda on Outpost for sub-10ms latency."

### Hosting Engineer Access
"Our hosting engineers use Systems Manager for all troubleshooting—no SSH or RDP ports exposed. Fleet Manager provides instance inventory, Session Manager gives secure shell access, CloudWatch shows metrics and logs, and X-Ray traces distributed requests. Everything is IAM-controlled with MFA and full audit logging."

### Security
"All three access patterns are monitored by our Security Account. GuardDuty analyzes VPC Flow Logs for threats, Inspector scans for vulnerabilities, Config tracks compliance, and CloudTrail logs all API calls. Security Hub aggregates findings from all sources into a unified dashboard."

---

**Estimated Time:** 60-90 minutes
**Complexity:** Medium-High
**Status:** Ready to implement

