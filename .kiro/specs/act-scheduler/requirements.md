# Act Tab — Scheduler Section: Requirements

## Philosophy
SlashMyBill **recommends** scheduling actions based on analysis of the customer's environment. The customer **manually creates** and owns all schedules. The system never auto-executes — it provides the "what" and "why", the customer provides the "when" and "go".

## Overview
Add a "Scheduler" section to the Act tab that:
1. Analyzes the customer's environment and generates smart scheduling recommendations
2. Provides step-by-step guides and AWS Console deep-links for the customer to implement each recommendation
3. Tracks which recommendations have been implemented (customer marks as done)
4. The AI Chat can also suggest scheduling actions based on questions

## User Stories

### US-1: Scheduling Recommendations Engine
**As a** member  
**I want to** see personalized scheduling recommendations based on my actual AWS usage  
**So that** I know exactly what to schedule and how much I'll save  

**Acceptance Criteria:**
- System analyzes connected accounts and generates recommendations:
  - **Office Hours**: Non-prod EC2/RDS instances running 24/7 → recommend stop schedule
  - **Waste Scan Cadence**: Suggest weekly scan if waste was found in last scan
  - **Tag Compliance**: Suggest weekly check if coverage < 80%
  - **Snapshot Cleanup**: Suggest monthly cleanup if old snapshots exist
  - **EBS gp2→gp3 Migration**: Suggest if gp2 volumes detected
  - **Commitment Review**: Suggest quarterly SP/RI review if commitments exist
- Each recommendation shows: what, why, estimated savings, difficulty, AWS Console link
- Recommendations refresh when user clicks "Analyze" (costs 🪙 10 tokens)

### US-2: Implementation Guides
**As a** member  
**I want to** get step-by-step instructions to implement each scheduling recommendation  
**So that** I can set it up myself in my AWS account  

**Acceptance Criteria:**
- Each recommendation expands to show:
  - Step-by-step instructions (numbered list)
  - AWS Console deep-link to the relevant page
  - CLI command to copy-paste (for advanced users)
  - Estimated time to implement
  - Estimated monthly savings
- For Instance Scheduler: links to AWS Instance Scheduler solution page + CloudFormation template
- For EventBridge rules: provides the cron expression and target config
- For cleanup rules: provides the lifecycle policy JSON

### US-3: Implementation Tracking
**As a** member  
**I want to** mark recommendations as "Done" or "Dismissed"  
**So that** I can track my progress and the system stops showing completed items  

**Acceptance Criteria:**
- Each recommendation has: [Mark as Done] [Dismiss] [Remind Me Later] buttons
- "Done" items move to a "Completed" section with date
- "Dismissed" items are hidden (can be shown via "Show dismissed")
- "Remind Me Later" snoozes for 7/30 days
- Progress bar: "3 of 7 recommendations implemented"
- Stored in DynamoDB on the member record

### US-4: AI Chat Integration
**As a** member  
**I want to** ask the AI about scheduling and get actionable recommendations  
**So that** I can get guidance through natural conversation  

**Acceptance Criteria:**
- AI responds to questions like:
  - "What should I schedule to save money?"
  - "How do I set up office hours for my dev instances?"
  - "What's the best way to automate EBS cleanup?"
- AI references the customer's actual environment data
- AI provides the same deep-links and CLI commands as the Scheduler section

## Data Model

### Scheduler Recommendations (stored in MemberPortal-Members)
```json
{
  "schedulerRecommendations": {
    "lastAnalyzedAt": "2026-04-13T10:00:00Z",
    "recommendations": [
      {
        "id": "rec-office-hours-dev",
        "type": "office-hours",
        "title": "Schedule dev instances to stop at 6pm",
        "reason": "3 EC2 instances tagged Environment=dev running 24/7",
        "estimatedSavings": 340,
        "difficulty": "easy",
        "status": "pending",
        "instances": ["i-abc123", "i-def456", "i-ghi789"],
        "accountId": "991105135552"
      }
    ],
    "completed": [
      {
        "id": "rec-office-hours-dev",
        "completedAt": "2026-04-14T09:00:00Z"
      }
    ],
    "dismissed": []
  }
}
```

## Recommendation Types

| Type | Trigger | Guide | Savings |
|------|---------|-------|---------|
| office-hours | Non-prod EC2/RDS running 24/7 | AWS Instance Scheduler CF template link | 60-70% |
| waste-scan-cadence | Waste found in last scan | EventBridge + Lambda guide | Varies |
| tag-compliance | Coverage < 80% | AWS Config rule guide | Indirect |
| snapshot-cleanup | Snapshots > 180 days | Lifecycle policy guide | $0.05/GB/mo |
| gp2-migration | gp2 volumes detected | EBS modify-volume CLI | 20% |
| commitment-review | Active SP/RI expiring in 60 days | Cost Explorer SP page link | 30-72% |
| idle-cleanup-rule | Recurring idle resources | EventBridge + Lambda guide | Varies |

## API Routes

| Method | Path | Description | Tier |
|--------|------|-------------|------|
| POST | /members/schedules/analyze | Analyze environment, generate recommendations | All (🪙 10) |
| GET | /members/schedules | Get saved recommendations + status | All |
| PUT | /members/schedules/status | Update recommendation status (done/dismissed/snoozed) | All |

## UI Layout (Act Tab Left Nav)

```
🗑️ Waste Cleanup     ← existing
🏷️ Tag Resources     ← existing  
⏰ Scheduler          ← NEW
```

### Scheduler Section
```
┌─────────────────────────────────────────────────────────┐
│ Scheduler                              [🔍 Analyze]     │
│ Personalized recommendations based on your environment  │
├─────────────────────────────────────────────────────────┤
│ Progress: ██████░░░░ 3/7 implemented                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 💰 HIGH SAVINGS                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ⏰ Stop dev instances outside business hours         │ │
│ │ 3 instances (i-abc, i-def, i-ghi) · ~$340/mo saved │ │
│ │ ▼ How to implement                                  │ │
│ │   1. Go to AWS Instance Scheduler                   │ │
│ │   2. Deploy the CloudFormation template              │ │
│ │   3. Tag instances with Schedule=office-hours        │ │
│ │   [Open AWS Console ↗] [Copy CLI Command]           │ │
│ │                                                     │ │
│ │ [✓ Mark as Done]  [Dismiss]  [Remind Me Later]      │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ 🔧 OPTIMIZATION                                        │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 💾 Migrate 5 gp2 volumes to gp3                     │ │
│ │ 120 GB total · ~$2.40/mo saved · Easy               │ │
│ │ ▼ How to implement                                  │ │
│ │   aws ec2 modify-volume --volume-type gp3 ...       │ │
│ │ [✓ Mark as Done]  [Dismiss]                         │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ✅ COMPLETED (3)                                        │
│   ✓ Weekly waste scan configured — Apr 10              │
│   ✓ Tag compliance check enabled — Apr 8               │
│   ✓ Old snapshots cleaned up — Apr 7                   │
└─────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1 — Recommendation Engine + UI
- Backend: analyze environment, generate recommendations based on scan data + dashboard data
- Frontend: scheduler section with recommendation cards, expand for guide, status buttons
- Storage: recommendations in DynamoDB member record
- No automation deployed to customer account — purely advisory

### Phase 2 — Rich Guides + Deep Links
- AWS Console deep-links for each recommendation type
- Copy-paste CLI commands
- CloudFormation template links (e.g., AWS Instance Scheduler)
- Estimated implementation time

### Phase 3 — AI Chat Integration
- AI references scheduler recommendations in responses
- "What should I schedule?" triggers recommendation analysis
- AI provides the same guides inline in chat responses

## Key Principle
> **The system recommends. The customer implements.**  
> SlashMyBill is an advisor, not an operator. All scheduling actions are performed by the customer in their own AWS account. The system provides the intelligence, the guides, and the tracking — never the execution.
