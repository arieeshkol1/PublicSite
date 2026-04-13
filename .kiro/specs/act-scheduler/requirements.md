# Act Tab — Scheduler Section: Requirements

## Overview
Add a "Scheduler" section to the Act tab (alongside Waste Cleanup and Tag Resources) that lets members create, manage, and monitor recurring FinOps automation tasks across their connected AWS accounts.

## User Stories

### US-1: Instance Scheduling (Office Hours)
**As a** Growth/Scale member  
**I want to** define business hours schedules for my dev/test EC2 and RDS instances  
**So that** they automatically stop outside working hours and save 60-70% on non-production compute  

**Acceptance Criteria:**
- Can create a schedule with: name, start time, end time, timezone, days of week
- Can assign schedule to specific EC2/RDS instances by tag (e.g., Environment=dev)
- Can assign by instance ID or by account-wide tag filter
- Schedule deploys an EventBridge rule + Lambda in the customer's account via CloudFormation
- Dashboard shows: instances covered, estimated monthly savings, schedule status (active/paused)
- Can pause/resume/delete schedules
- Tier: Growth and Scale only (Free sees "Upgrade to enable")

### US-2: Recurring Waste Scan
**As a** member  
**I want to** schedule automatic waste scans (weekly/monthly)  
**So that** I get notified when new idle resources appear without manually clicking "Scan"  

**Acceptance Criteria:**
- Can set scan frequency: weekly (pick day) or monthly (pick date)
- Scan runs automatically via EventBridge scheduled rule on the SlashMyBill platform
- Results stored in DynamoDB, visible in the Act > Waste section
- Email notification sent when new waste is found (via SES)
- Shows last scan date, next scan date, findings count
- Token cost: 10 tokens per scheduled scan (deducted from monthly allowance)
- Free tier: manual only. Growth/Scale: can schedule.

### US-3: Recurring Tag Compliance Check
**As a** member  
**I want to** schedule weekly tag compliance scans  
**So that** I'm alerted when new untagged resources are created  

**Acceptance Criteria:**
- Can enable/disable weekly tag compliance check
- Runs every Monday at 9am UTC (or configurable)
- Compares current tag coverage vs previous week
- Email alert if coverage drops below threshold (configurable, default 80%)
- Results visible in Act > Tag Resources section
- Token cost: 10 tokens per scheduled scan

### US-4: Cleanup Automation Rules
**As a** Growth/Scale member  
**I want to** create rules that automatically clean up specific resource types  
**So that** waste doesn't accumulate between manual scans  

**Acceptance Criteria:**
- Can create rules like: "Delete unattached EBS volumes older than 7 days"
- Rule types:
  - Delete unattached EBS volumes after N days
  - Release unassociated Elastic IPs after N days  
  - Delete EBS snapshots older than N days
  - Apply S3 lifecycle policy to buckets without one
- Each rule has: name, type, threshold (days), enabled/disabled, dry-run mode
- Dry-run mode: logs what would be deleted without actually deleting
- Execution log: shows what was cleaned, when, savings
- Safety: JIT check before every deletion (same as manual cleanup)
- Token cost: 50 tokens per automated cleanup execution

### US-5: FinOps Review Reminders
**As a** member  
**I want to** receive periodic FinOps review reminders  
**So that** I maintain a regular cadence of cost optimization  

**Acceptance Criteria:**
- Weekly email digest: top 3 savings opportunities, token usage, coverage changes
- Monthly summary: total spend trend, savings achieved, commitment utilization
- Can configure: enable/disable, email frequency (weekly/monthly/both)
- Email includes direct links to relevant dashboard sections

## Data Model

### Schedule (stored in MemberPortal-Members as `schedules` array)
```json
{
  "schedules": [
    {
      "id": "sched-uuid",
      "type": "instance-hours|waste-scan|tag-check|cleanup-rule|review-reminder",
      "name": "Stop dev instances at 6pm",
      "enabled": true,
      "config": {
        "startTime": "08:00",
        "endTime": "18:00",
        "timezone": "America/New_York",
        "daysOfWeek": ["mon","tue","wed","thu","fri"],
        "targetFilter": {"tag:Environment": "dev"},
        "accountIds": ["123456789012"]
      },
      "lastRun": "2026-04-13T18:00:00Z",
      "nextRun": "2026-04-14T08:00:00Z",
      "status": "active",
      "createdAt": "2026-04-13T10:00:00Z"
    }
  ]
}
```

## API Routes

| Method | Path | Description | Tier |
|--------|------|-------------|------|
| GET | /members/schedules | List all schedules | All |
| POST | /members/schedules | Create a schedule | Growth+ |
| PUT | /members/schedules | Update a schedule | Growth+ |
| DELETE | /members/schedules | Delete a schedule | Growth+ |
| POST | /members/schedules/execute | Manually trigger a schedule | Growth+ |

## UI Layout (Act Tab Left Nav)

```
🗑️ Waste Cleanup     ← existing
🏷️ Tag Resources     ← existing  
⏰ Scheduler          ← NEW
```

### Scheduler Section Layout
```
┌─────────────────────────────────────────────────────────┐
│ Scheduler                              [+ New Schedule] │
├─────────────────────────────────────────────────────────┤
│ ┌─ Active Schedules ──────────────────────────────────┐ │
│ │ ⏰ Stop dev instances    Mon-Fri 6pm-8am EST        │ │
│ │    Status: Active  │  Last: Apr 13  │  Savings: $340│ │
│ │    [Pause] [Edit] [Delete]                          │ │
│ │                                                     │ │
│ │ 🔍 Weekly waste scan     Every Monday 9am UTC       │ │
│ │    Status: Active  │  Last: Apr 7   │  Found: 3     │ │
│ │    [Pause] [Edit] [Delete]                          │ │
│ │                                                     │ │
│ │ 🏷️ Tag compliance check  Every Monday 9am UTC       │ │
│ │    Status: Active  │  Coverage: 82% │  ▲ +3%        │ │
│ │    [Pause] [Edit] [Delete]                          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─ Quick Templates ───────────────────────────────────┐ │
│ │ [Office Hours]  [Weekly Scan]  [Tag Check]          │ │
│ │ [EBS Cleanup]   [EIP Cleanup]  [Snapshot Cleanup]   │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1 (MVP) — Recurring Scans + Reminders
- Scheduled waste scan (weekly/monthly) via EventBridge on platform account
- Scheduled tag compliance check
- Email notifications via SES
- UI: schedule list, create/edit/delete, status display
- Storage: schedules in DynamoDB member record

### Phase 2 — Instance Scheduling  
- Deploy EventBridge + Lambda to customer account via CloudFormation
- Start/stop EC2 and RDS on schedule
- Estimated savings calculation
- Requires updated CF template with scheduler permissions

### Phase 3 — Cleanup Automation Rules
- Auto-delete unattached EBS, unused EIPs, old snapshots
- Dry-run mode
- Execution log with audit trail
- JIT safety checks

## IAM Permissions Needed (Customer Account CF Template)

### Phase 2 additions:
```
events:PutRule
events:PutTargets
events:DeleteRule
events:RemoveTargets
events:DescribeRule
lambda:CreateFunction
lambda:DeleteFunction
lambda:InvokeFunction
lambda:AddPermission
iam:PassRole (for Lambda execution role)
```

### Phase 3 additions:
Already covered by existing cleanup permissions (ec2:DeleteVolume, ec2:ReleaseAddress, etc.)

## Token Costs
| Action | Cost |
|--------|------|
| Scheduled waste scan | 🪙 10 |
| Scheduled tag check | 🪙 10 |
| Automated cleanup execution | 🪙 50 |
| Instance schedule (create/update) | 🪙 10 |
| FinOps review email | Free |

## Dependencies
- Amazon EventBridge (platform account for scans, customer account for instance scheduling)
- Amazon SES (email notifications — already configured)
- Updated CF template (Phase 2 only)
- DynamoDB member record (schedules array)
