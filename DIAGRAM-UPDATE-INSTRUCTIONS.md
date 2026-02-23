# Architecture Diagram Update Instructions

## 🎯 Objective

Update `Made4Net-AWS-Architecture.drawio` to visually represent the multi-account architecture structure.

---

## 📋 Current Diagram Status

The current diagram shows:
- ✅ Warehouse examples (Standard VPN and Outposts)
- ✅ AWS services in a single cloud view
- ✅ Transit Gateway as the hub
- ✅ Outposts section
- ❌ Multi-account structure (needs to be added)

---

## 🎨 Recommended Diagram Updates

### Option 1: Add Multi-Account Layer (Recommended)

Add account boundaries to the existing diagram to show which services belong to which account:

**1. Add Account Boxes (Colored Borders)**

Create colored boxes around service groups:

**Security Account Box (Purple #C925D1)**
- Position: Right side of diagram
- Contains:
  - GuardDuty
  - Config
  - AWS Backup
  - (Add Security Hub icon if space allows)
- Label: "SECURITY ACCOUNT - Centralized Security"

**Operations Account Box (Blue #1976D2)**
- Position: Right side, below Security Account
- Contains:
  - CloudWatch
  - AWS X-Ray
  - Systems Manager
- Label: "OPERATIONS ACCOUNT - Centralized Management"

**Production Account Box (Green #248814)**
- Position: Main central area
- Contains:
  - VPC
  - Transit Gateway
  - ALB, API Gateway
  - EC2 Auto Scaling Group
  - RDS, DynamoDB, S3
  - Lambda
- Label: "PRODUCTION ACCOUNT - Main Workload"

**Outposts Account Boxes (Orange #FF6F00)**
- Position: Top section (existing Outposts area)
- Split into two boxes:
  - "OUTPOSTS ACCOUNT #1 - Warehouse Group A"
  - "OUTPOSTS ACCOUNT #2 - Warehouse Group B"

**2. Add Cross-Account Connection Lines**

Add dashed lines to show monitoring/management relationships:

**From Security Account:**
- Purple dashed lines to Production Account (monitoring)
- Purple dashed lines to Outposts Accounts (monitoring)
- Label: "Security Monitoring"

**From Operations Account:**
- Blue dashed lines to Production Account (management)
- Blue dashed lines to Outposts Accounts (management)
- Label: "Operational Management"

**3. Add AWS Organizations Box**

Add a large container box at the top:
- Label: "AWS ORGANIZATIONS"
- Contains all account boxes
- Style: Light gray border, no fill

---

### Option 2: Create Separate Multi-Account Diagram

Create a new diagram page in the same file showing the account structure:

**Page Name:** "Multi-Account Architecture"

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│              AWS ORGANIZATIONS                          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  SECURITY    │  │  OPERATIONS  │  │  PRODUCTION  │ │
│  │  ACCOUNT     │  │  ACCOUNT     │  │  ACCOUNT     │ │
│  │              │  │              │  │              │ │
│  │ • GuardDuty  │  │ • Systems    │  │ • VPC        │ │
│  │ • Inspector  │  │   Manager    │  │ • Transit GW │ │
│  │ • Config     │  │ • CloudWatch │  │ • EC2, RDS   │ │
│  │ • Sec Hub    │  │ • X-Ray      │  │ • Lambda     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  OUTPOSTS    │  │  OUTPOSTS    │  │  DR ACCOUNT  │ │
│  │  ACCOUNT #1  │  │  ACCOUNT #2  │  │  (us-west-2) │ │
│  │              │  │              │  │              │ │
│  │ • Outposts   │  │ • Outposts   │  │ • RDS        │ │
│  │   Rack       │  │   Rack       │  │   Replica    │ │
│  │ • EC2 Local  │  │ • EC2 Local  │  │ • S3 CRR     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Step-by-Step Instructions for draw.io

### Adding Account Boxes

1. **Open the diagram** in draw.io
2. **Select Rectangle tool** from the left toolbar
3. **Draw a rectangle** around the services for each account
4. **Set the style:**
   - Right-click → Edit Style
   - For Security Account: `strokeColor=#C925D1;fillColor=none;strokeWidth=3;dashed=1`
   - For Operations Account: `strokeColor=#1976D2;fillColor=none;strokeWidth=3;dashed=1`
   - For Production Account: `strokeColor=#248814;fillColor=none;strokeWidth=3;dashed=1`
   - For Outposts Accounts: `strokeColor=#FF6F00;fillColor=none;strokeWidth=3;dashed=1`
5. **Add label:**
   - Double-click the rectangle
   - Type the account name
   - Set font size to 14, bold

### Adding Cross-Account Lines

1. **Select Connector tool** from the toolbar
2. **Draw line** from Security Account box to Production Account box
3. **Set style:**
   - Right-click → Edit Style
   - `strokeColor=#C925D1;strokeWidth=2;dashed=1;endArrow=classic`
4. **Add label:**
   - Double-click the line
   - Type "Security Monitoring"
5. **Repeat** for Operations Account connections

### Adding AWS Organizations Container

1. **Draw large rectangle** encompassing all accounts
2. **Set style:**
   - `strokeColor=#AAB7B8;fillColor=none;strokeWidth=2;dashed=0`
3. **Add label** at top: "AWS ORGANIZATIONS"
4. **Send to back:**
   - Right-click → To Back

---

## 📊 Color Coding Reference

| Account | Color Code | RGB | Usage |
|---------|-----------|-----|-------|
| Security Account | #C925D1 | Purple | Security services box |
| Operations Account | #1976D2 | Blue | Operations services box |
| Production Account | #248814 | Green | Production workload box |
| Outposts Accounts | #FF6F00 | Orange | Outposts boxes |
| AWS Organizations | #AAB7B8 | Gray | Container box |

---

## 🎯 Key Visual Elements to Add

### 1. Account Labels

Each account box should have a clear label:
- **Security Account**: "SECURITY ACCOUNT - Centralized Security & Compliance"
- **Operations Account**: "OPERATIONS ACCOUNT - Centralized Management"
- **Production Account**: "PRODUCTION ACCOUNT - Main Workload (us-east-1)"
- **Outposts Account #1**: "OUTPOSTS ACCOUNT #1 - Warehouse Group A"
- **Outposts Account #2**: "OUTPOSTS ACCOUNT #2 - Warehouse Group B"

### 2. Cross-Account Relationships

Show these relationships with dashed lines:
- Security Account → All other accounts (purple dashed)
- Operations Account → Production + Outposts (blue dashed)
- Production Account → Outposts Accounts (green solid - service link)

### 3. Legend Update

Add to the existing legend:
```
ACCOUNT TYPES:
🟣 Security Account (Centralized Security)
🔵 Operations Account (Centralized Operations)
🟢 Production Account (Main Workload)
🟧 Outposts Accounts (On-Premises Hybrid)
```

---

## 📝 Alternative: Text Annotation

If modifying the diagram structure is too complex, add a text box with the multi-account structure:

**Position:** Bottom of diagram or separate section

**Content:**
```
MULTI-ACCOUNT ARCHITECTURE

This architecture uses 6 AWS accounts under AWS Organizations:

1. SECURITY ACCOUNT (Purple)
   • GuardDuty, Inspector, Config, Security Hub, CloudTrail
   • Monitors all accounts for threats and compliance

2. OPERATIONS ACCOUNT (Blue)
   • Systems Manager, CloudWatch, X-Ray, Backup
   • Manages all workloads across accounts

3. PRODUCTION ACCOUNT (Green)
   • VPC, Transit Gateway, EC2, RDS, Lambda
   • Main application workload

4. OUTPOSTS ACCOUNT #1 (Orange)
   • Warehouse Group A (NY, Boston, Philadelphia)
   • AWS Outposts Rack, EC2 on Outposts

5. OUTPOSTS ACCOUNT #2 (Orange)
   • Warehouse Group B (Chicago, Detroit, Milwaukee)
   • AWS Outposts Rack, EC2 on Outposts

6. DR ACCOUNT (Gray)
   • Disaster Recovery (us-west-2)
   • RDS Read Replica, S3 Cross-Region Replication

CROSS-ACCOUNT MONITORING:
• Security Account monitors all accounts via GuardDuty, Inspector, Config
• Operations Account manages all instances via Systems Manager
• Unified dashboard shows all accounts in one view
```

---

## ✅ Verification Checklist

After updating the diagram, verify:

- [ ] All 6 accounts are clearly labeled
- [ ] Account boxes use correct colors (Security=Purple, Operations=Blue, Production=Green, Outposts=Orange)
- [ ] Cross-account monitoring lines are shown (dashed lines)
- [ ] AWS Organizations container encompasses all accounts
- [ ] Legend includes account types
- [ ] Warehouse examples still visible and connected correctly
- [ ] Transit Gateway shows connections to all accounts
- [ ] Outposts service links are clearly marked

---

## 🎨 Visual Design Tips

1. **Use consistent spacing** between account boxes
2. **Align boxes** horizontally or vertically for clean layout
3. **Use dashed lines** for monitoring/management relationships
4. **Use solid lines** for data flow (VPN, service links)
5. **Keep labels readable** - minimum font size 10pt
6. **Use color consistently** - same color for same account type
7. **Add whitespace** - don't overcrowd the diagram

---

## 📚 Reference Documents

For detailed multi-account architecture information, refer to:
- **MULTI-ACCOUNT-ARCHITECTURE.md** - Complete account structure
- **MULTI-ACCOUNT-DIAGRAM-GUIDE.md** - Detailed visual layout guide
- **FINAL-ARCHITECTURE-SUMMARY.md** - Complete solution overview

---

**Note:** The diagram update is optional but recommended for visual clarity. The HLD document already contains the complete multi-account architecture description in Section 7.
