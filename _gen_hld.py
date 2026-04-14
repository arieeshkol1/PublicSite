from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

def add_heading(doc, text, level=1, color=None):
    h = doc.add_heading(text, level=level)
    if color:
        for run in h.runs:
            run.font.color.rgb = RGBColor(*color)
    return h

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1+len(rows), cols=len(headers))
    table.style = 'Table Grid'
    hdr = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = h
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.color.rgb = RGBColor(255,255,255)
        cell._tc.get_or_add_tcPr().append(OxmlElement('w:shd'))
        shd = cell._tc.get_or_add_tcPr().find(qn('w:shd'))
        shd.set(qn('w:fill'), '1F3864')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:val'), 'clear')
    for ri, row in enumerate(rows):
        tr = table.rows[ri+1]
        for ci, val in enumerate(row):
            tr.cells[ci].text = str(val)
        if ri % 2 == 0:
            for ci in range(len(row)):
                shd = tr.cells[ci]._tc.get_or_add_tcPr().find(qn('w:shd'))
                if shd is None:
                    shd = OxmlElement('w:shd')
                    tr.cells[ci]._tc.get_or_add_tcPr().append(shd)
                shd.set(qn('w:fill'), 'E8EDF5')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:val'), 'clear')
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(w)
    return table

doc = Document()

# Page margins
for section in doc.sections:
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

# Title
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('SlashMyBill')
run.bold = True
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(31, 56, 100)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run2 = sub.add_run('High-Level Design Document')
run2.font.size = Pt(16)
run2.font.color.rgb = RGBColor(99, 102, 241)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run(f'Version 10  |  {datetime.date.today().strftime("%B %Y")}  |  AWS FinOps Platform').font.size = Pt(10)

doc.add_paragraph()

# ── 1. Executive Summary ──────────────────────────────────────────────────────
add_heading(doc, '1. Executive Summary', 1)
doc.add_paragraph(
    'SlashMyBill is an AI-powered AWS FinOps platform that enables organizations to analyze, '
    'optimize, and reduce cloud spending across multiple AWS accounts. Members connect their '
    'AWS accounts via a secure cross-account IAM role, then use a conversational AI agent to '
    'ask natural language questions about costs, detect anomalies, receive actionable savings '
    'recommendations, and execute automated cleanup actions — all backed by live AWS API data.\n\n'
    'Platform URL: https://www.eshkolai.com/members/\n'
    'AWS Platform Account: 991105135552 (us-east-1)\n'
    'AI Engine: Amazon Bedrock Nova Lite v1'
)

# ── 2. Architecture Overview ──────────────────────────────────────────────────
add_heading(doc, '2. Architecture Overview', 1)
add_heading(doc, '2.1 Core Components', 2)
add_table(doc,
    ['Component', 'Technology', 'Purpose'],
    [
        ['Frontend', 'HTML/CSS/JS + ECharts v5', 'Member Portal — Observe, Chat, Act, Configure tabs'],
        ['API Gateway', 'HTTP API v2 (25+ routes)', 'Request routing to Lambda handlers'],
        ['Member Handler', 'Python 3.12 Lambda (256MB, 120s)', 'Auth, accounts, AI queries, scan engine, data gathering'],
        ['Agent Action', 'Python 3.12 Lambda', 'Bedrock Agent action group (cross-account)'],
        ['Bill Analyzer', 'Python 3.12 Lambda (1024MB, 900s)', 'PDF bill parsing + Bedrock analysis'],
        ['AI Engine', 'Amazon Bedrock Nova Lite v1', 'Natural language analysis + recommendations'],
        ['Storage', 'DynamoDB (8 tables) + S3', 'Members, accounts, tips, OTP, feedback, metrics, scan results'],
        ['Email', 'Amazon SES', 'OTP verification emails'],
        ['CDN', 'CloudFront + Route 53', 'HTTPS delivery, DNS'],
        ['CI/CD', 'GitHub Actions + OIDC', 'Automated deployment on push to main'],
    ],
    [2.0, 2.5, 3.5]
)

add_heading(doc, '2.2 Cross-Account Access Model', 2)
doc.add_paragraph(
    'Members deploy a CloudFormation template in their AWS account that creates:\n'
    '  • IAM Role: SlashMyBill-{AccountID} with ReadOnlyAccess managed policy\n'
    '  • Inline policy: Cost Explorer, Budgets, Pricing, Trusted Advisor, S3 write (lifecycle/delete), '
    'EC2 write (stop/snapshot delete), RDS write (delete with snapshot), stack self-management\n'
    '  • Trust policy: Platform account (991105135552) with ExternalId = SHA-256(member_email)\n\n'
    'The ExternalId prevents confused deputy attacks. The role is versioned — users must redeploy '
    'the latest template to enable write actions (Level 1 cleanup).'
)

# ── 3. DynamoDB Data Model ────────────────────────────────────────────────────
add_heading(doc, '3. DynamoDB Data Model (8 Tables)', 1)
add_table(doc,
    ['Table', 'PK', 'SK', 'Purpose'],
    [
        ['ViewMyBill-Leads', 'email', 'timestamp', 'Contact form leads'],
        ['ViewMyBill-CostOptimizationTips', 'service', 'tipId', 'RAG knowledge base (72 tips)'],
        ['ViewMyBill-OTP', 'email', '—', 'OTP codes (TTL 5 min)'],
        ['MemberPortal-Members', 'email', '—', 'Member accounts, allocation rules, last scan cache'],
        ['MemberPortal-Accounts', 'memberEmail', 'accountId', 'Connected AWS accounts + hourly status'],
        ['MemberPortal-AgentFeedback', 'memberEmail', 'interactionId', 'AI feedback (👍/👎) + corrections'],
        ['MemberPortal-BusinessMetrics', 'memberEmail', 'metricMonth', 'Unit economics business metrics'],
        ['MemberPortal-Dashboard', 'memberEmail', 'itemId', 'Saved dashboard queries/charts'],
    ],
    [2.5, 1.5, 1.5, 3.0]
)

doc.add_paragraph()
add_heading(doc, '3.1 Tips Table Schema (72 tips)', 2)
doc.add_paragraph(
    'Each tip in ViewMyBill-CostOptimizationTips contains:\n'
    '  • service: AWS service name (EC2, S3, RDS, Lambda, etc.)\n'
    '  • tipId: Unique identifier (e.g., ec2-001, s3-002)\n'
    '  • category: right-sizing | pricing-model | scheduling | cleanup | lifecycle | etc.\n'
    '  • title / description / estimatedSavings / difficulty\n'
    '  • automatedCheck: Machine-readable check specification (API calls + data fields)\n'
    '  • checkImplemented: bool — whether the scan engine has a check function for this tip\n'
    '  • actionType: delete | modify | advisory | deep-link | pending\n'
    '  • actionLabel: Button label in the Act tab\n'
    '  • level: 1 (hygiene) | 2 (optimization) | 3 (architecture)\n'
    '  • serviceKey: CE service name for presence-gating\n'
    '  • positiveCount: Feedback score from user interactions'
)

# ── 4. API Routes ─────────────────────────────────────────────────────────────
add_heading(doc, '4. API Routes (25+)', 1)
add_table(doc,
    ['Method', 'Route', 'Purpose'],
    [
        ['POST', '/members/register', 'Registration (3-step OTP flow)'],
        ['POST', '/members/login', 'Authentication → JWT token'],
        ['POST', '/members/reset-password', 'Password reset (OTP flow)'],
        ['GET', '/members/accounts', 'List connected AWS accounts'],
        ['POST', '/members/accounts', 'Add AWS account'],
        ['PUT', '/members/accounts', 'Edit account'],
        ['POST', '/members/accounts/reorder', 'Reorder account priority'],
        ['DELETE', '/members/accounts', 'Delete account (IAM cleanup + CF stack delete)'],
        ['POST', '/members/accounts/template', 'Generate CloudFormation template'],
        ['POST', '/members/accounts/test', 'Test connection + detect hourly granularity'],
        ['POST', '/members/accounts/execute', 'Execute AWS CLI command (read-only)'],
        ['POST', '/members/accounts/ai-query', 'AI question → Bedrock analysis'],
        ['POST', '/members/accounts/ai-feedback', 'Submit 👍/👎 feedback'],
        ['GET', '/members/dashboard-data', 'FinOps dashboard data (7 widgets)'],
        ['GET/POST/DELETE', '/members/dashboard', 'Saved dashboard items'],
        ['GET/POST', '/members/allocation-rules', 'Virtual tagging business unit rules'],
        ['GET/POST', '/members/business-metrics', 'Unit economics metrics'],
        ['POST', '/members/actions/scan', 'Tips-driven waste scan (7 categories)'],
        ['GET', '/members/actions/last-scan', 'Retrieve cached last scan for Chat widget'],
        ['POST', '/members/actions/execute', 'Execute cleanup action (EIP/EBS/LB/S3/EC2/RDS/Snapshot)'],
        ['POST', '/members/actions/browse-bucket', 'Browse S3 bucket contents with size/age data'],
    ],
    [0.8, 2.8, 4.4]
)

# ── 5. Member Portal Tabs ─────────────────────────────────────────────────────
add_heading(doc, '5. Member Portal — Tab Structure', 1)

add_heading(doc, '5.1 Observe Tab (FinOps Dashboard)', 2)
doc.add_paragraph(
    'The Observe tab provides a BI-grade dashboard with 7 ECharts widgets:\n\n'
    '  1. Cost by Service (Treemap) — 2-phase drill-down: services → usage types. '
    'Click any tile to open a side panel with usage type breakdown and AI chat link.\n'
    '  2. Cost Trend (Line/Bar) — Daily (30 days) or Hourly toggle. Anomaly detection '
    'marks spikes > 2× the 7-day average.\n'
    '  3. Cost Allocation by Business Unit (Treemap) — Virtual tagging rules applied '
    'to allocate costs to business units with shared cost splitting.\n'
    '  4. Waste Detection — Unattached EBS, idle EIPs, Lambda 0-invocation functions.\n'
    '  5. Rightsizing Summary — Over-provisioned instances from Compute Optimizer.\n'
    '  6. Monthly Cost by Service (Stacked Bar) — Month-over-month service breakdown.\n'
    '  7. Unit Cost Trend (Dual-axis) — Business volume (bar) vs cost/unit (line).\n\n'
    'KPI Bar: Month-over-Month change | Efficiency Score | Potential Savings (clickable → Chat) | Accounts'
)

add_heading(doc, '5.2 Chat Tab (AI Agent)', 2)
doc.add_paragraph(
    'The Chat tab provides a conversational AI interface powered by Amazon Bedrock Nova Lite.\n\n'
    'Welcome Screen Layout (top to bottom):\n'
    '  1. Greeting: "Hi - We are here to help you slash your Bill"\n'
    '  2. Scan button: "🔍 Scan for Savings Opportunities" + last scan timestamp\n'
    '  3. Top Findings: Up to 5 findings from last scan, each with savings amount, '
    'tip title, suggested question, and "Ask ▶" button\n'
    '  4. General Questions: Clickable code examples\n\n'
    'Header Controls: Account selector (multi-select dropdown) | A- / A+ font size | ↻ Refresh Findings\n\n'
    'Answer Features:\n'
    '  • Commands log showing all AWS API calls made\n'
    '  • Drill-down follow-up buttons\n'
    '  • "Show as table" buttons (filtered to relevant charts only)\n'
    '  • 👍/👎 feedback on each answer\n'
    '  • Context-aware chart suggestions'
)

add_heading(doc, '5.3 Act Tab (Resource Hygiene)', 2)
doc.add_paragraph(
    'The Act tab implements Level 1 automated cleanup with a tips-driven scan engine.\n\n'
    'Scan Categories (always shown — clean ✓ or findings ⚠):\n'
    '  1. 🌐 Unassociated Elastic IPs — $3.65/month each\n'
    '  2. 💾 Unattached EBS Volumes — $0.10/GB/month\n'
    '  3. ⚖️ Idle Load Balancers — $16.43/month each (0 healthy targets)\n'
    '  4. 🪣 S3 Buckets Needing Attention — no lifecycle, inactive 90+ days\n'
    '  5. 🖥️ Idle EC2 Instances — avg CPU < 5% over 14 days\n'
    '  6. 🗄️ Idle RDS Instances — avg CPU < 5%, < 2 connections over 14 days\n'
    '  7. 📸 Stale EBS Snapshots — older than 180 days\n\n'
    'Multi-account cards are merged into one combined card with account labels per resource.\n\n'
    'S3 Card Features:\n'
    '  • Per-bucket: size (GB), estimated cost, last activity, reason badges\n'
    '  • Browse button → modal with object list (sortable: oldest/largest/newest)\n'
    '  • Aged data banner (objects 90+ days old)\n'
    '  • Apply Lifecycle Policy button (Intelligent-Tiering after 90 days)\n'
    '  • Delete All Objects button (with confirmation + irreversibility warning)\n\n'
    'Safety Guardrails:\n'
    '  • JIT check before every delete (re-verify resource state)\n'
    '  • ASG detection for EC2 (detach before stop)\n'
    '  • RDS always creates final snapshot before deletion\n'
    '  • IAM permission warning with redeploy guide for write actions'
)

add_heading(doc, '5.4 Configure Tab', 2)
doc.add_paragraph(
    'Account management with 4-step setup wizard:\n'
    '  Step 1: Download CloudFormation template\n'
    '  Step 2: Deploy in AWS Console (or CloudFormation quick-create link)\n'
    '  Step 3: Wait for deployment\n'
    '  Step 4: Test connection + Check hourly granularity status\n\n'
    'Account table features: priority ordering (▲▼), connection status, hourly status badge (⏱✓/⏱✗), '
    'test connection, edit, delete.\n\n'
    'Hourly Granularity: Detected automatically during test connection via CloudWatch HOURLY query. '
    'Cannot be enabled via API — requires manual AWS Console action in Cost Explorer Settings.'
)

# ── 6. AI Engine ──────────────────────────────────────────────────────────────
add_heading(doc, '6. AI Engine Design', 1)

add_heading(doc, '6.1 Data Gathering Pipeline', 2)
doc.add_paragraph(
    'The _gather_account_data() function collects data via cross-account role assumption. '
    'Data collection is gated by:\n'
    '  • Service presence: only fetch data for services with actual CE spend > $0.01\n'
    '  • Question keywords: specific questions (KMS, S3 lifecycle, budgets) skip irrelevant '
    'EC2/VPC/NAT data collection\n'
    '  • Top cost services: NAT/VPC/EBS fetched only when EC2-Other or VPC are in top 6 costs\n\n'
    'Always fetched: CE cost by service (30d), CE daily trend (7d), CE usage type breakdown\n\n'
    'Conditionally fetched: EC2 instances, NAT Gateways, EIPs, VPC endpoints, EBS volumes, '
    'RDS instances, KMS keys, Lambda functions, S3 buckets + lifecycle, Route 53 zones, '
    'EKS/ECS clusters, Compute Optimizer recommendations, Budgets, CloudWatch metrics (batch)'
)

add_heading(doc, '6.2 Multi-Account Query Flow', 2)
doc.add_paragraph(
    'When multiple accounts are selected:\n'
    '  1. Data gathered per account in parallel (up to 5 accounts)\n'
    '  2. All service-specific data passed through to the prompt (lambda_metrics, ec2_instances, '
    'rds_instances, s3_buckets, kms_customer_keys, budgets, etc.)\n'
    '  3. Prompt rule: answer the specific question FIRST using per-account data, '
    'then add cross-account summary\n'
    '  4. Findings cached in MemberPortal-Members.lastScan for the Chat widget'
)

add_heading(doc, '6.3 Prompt Engineering Rules (20+)', 2)
doc.add_paragraph(
    'Key rules governing AI response quality:\n'
    '  • Specific questions answered directly — no generic cost summary\n'
    '  • Tax, Amazon Registrar, AWS Cost Explorer excluded from savings analysis\n'
    '  • Services < $0.50 grouped as "Minor costs"\n'
    '  • Exact resource IDs required in recommendations\n'
    '  • Budget limits based on actual CE spend (no invented amounts)\n'
    '  • S3 lifecycle: list ALL buckets with exact count, reference Act tab for one-click apply\n'
    '  • Deleted-mid-month resources explained (not flagged as waste)\n'
    '  • Rightsize before committing to Savings Plans\n'
    '  • Graviton migration candidates identified from instance type family\n'
    '  • Cost Efficiency Score shown prominently for general questions\n'
    '  • Hebrew language support for comparisons'
)

# ── 7. Tips-Driven Scan Engine ────────────────────────────────────────────────
add_heading(doc, '7. Tips-Driven Scan Engine (Phase 1)', 1)
doc.add_paragraph(
    'The scan engine reads tips from DynamoDB at runtime (ground truth), gates checks by '
    'active services, and evaluates each tip via a registry of check functions.\n\n'
    'Flow:\n'
    '  1. Load tips from DynamoDB (all 72 tips)\n'
    '  2. Collect service data (_collect_service_data) — CE, EC2, S3, RDS, Lambda, LB, KMS, Budgets, '
    'CloudWatch batch metrics\n'
    '  3. Determine active services from CE cost data (> $0.01 spend)\n'
    '  4. For each tip: gate by serviceKey, look up check function in _SCAN_REGISTRY\n'
    '  5. If check implemented: run check → finding with cardData\n'
    '  6. If not implemented: return PENDING placeholder\n'
    '  7. Deduplicate cards by cardId (merge resources from duplicate tip checks)\n'
    '  8. Cache top 10 findings in MemberPortal-Members.lastScan\n\n'
    'Implemented checks (13): EBS unattached, EBS snapshots, EIPs, S3 lifecycle, idle LBs, '
    'idle EC2, idle RDS, KMS keys, Budgets, Spot candidates, RI Marketplace, Graviton candidates, '
    'commercial DB engines'
)

# ── 8. Virtual Tagging ────────────────────────────────────────────────────────
add_heading(doc, '8. Virtual Tagging & Cost Allocation', 1)
doc.add_paragraph(
    'Business unit rules stored in MemberPortal-Members.allocationRules:\n\n'
    'Rule Schema:\n'
    '  • businessUnits[]: name, ruleLogic (AND/OR), rules[]\n'
    '  • rules[]: dimension (account/service/tag), operator (equals/contains/startsWith), value\n'
    '  • sharedCostMode: even | proportional | custom\n'
    '  • customSplits: {buName: percentage}\n\n'
    'Processing: CE cost_by_service matched against rules → allocated to business units → '
    'unallocated costs split by sharedCostMode → displayed as treemap in Observe tab'
)

# ── 9. Unit Economics ─────────────────────────────────────────────────────────
add_heading(doc, '9. Unit Economics', 1)
doc.add_paragraph(
    'MemberPortal-BusinessMetrics table stores monthly business volumes:\n'
    '  • metricName: ActiveUsers, Transactions, API_Calls, etc.\n'
    '  • metricVolume: numerical volume for the month\n'
    '  • businessUnitLink: optional mapping to virtual tag BU\n\n'
    'Auto-discovered IT metrics: DynamoDB items, API GW requests, Lambda invocations, S3 buckets\n\n'
    'Unit Cost = Total Cloud Spend / metricVolume\n\n'
    'AI integration: if costs increased 20% but volume increased 40%, AI frames this as '
    '"efficient scaling" (cost per unit decreased) rather than "cost overrun"'
)

# ── 10. Security ──────────────────────────────────────────────────────────────
add_heading(doc, '10. Security Model', 1)
add_table(doc,
    ['Layer', 'Mechanism'],
    [
        ['Authentication', 'JWT tokens (HS256, 24h expiry)'],
        ['Registration', '3-step OTP flow via SES (5-min TTL, rate-limited 60s)'],
        ['Password', 'bcrypt hashing with salt'],
        ['Cross-Account', 'STS AssumeRole with ExternalId = SHA-256(member_email)'],
        ['Lateral Access', '_verify_account_ownership() on all account operations'],
        ['API Security', 'CORS restricted to eshkolai.com'],
        ['Data Encryption', 'DynamoDB SSE, S3 default encryption'],
        ['IAM', 'ReadOnlyAccess + minimal billing inline policy'],
        ['Deployment', 'GitHub OIDC → IAM Role (no stored credentials)'],
        ['Write Actions', 'Require updated CF template + JIT safety checks before execution'],
    ],
    [2.5, 5.5]
)

# ── 11. Infrastructure ────────────────────────────────────────────────────────
add_heading(doc, '11. Infrastructure (CloudFormation Stack)', 1)
add_heading(doc, '11.1 Lambda Functions', 2)
add_table(doc,
    ['Function', 'Memory', 'Timeout', 'Purpose'],
    [
        ['aws-bill-analyzer-viewmybill', '1024 MB', '900s', 'PDF bill analysis'],
        ['aws-bill-analyzer-upload-handler', '256 MB', '30s', 'PDF upload + validation'],
        ['aws-bill-analyzer-otp-handler', '128 MB', '30s', 'OTP send/verify'],
        ['aws-bill-analyzer-admin-api', '128 MB', '30s', 'Admin CRUD'],
        ['aws-bill-analyzer-member-api', '256 MB', '120s', 'Member portal + AI agent + scan engine'],
        ['SlashMyBill-AgentAction', '256 MB', '120s', 'Bedrock Agent actions'],
    ],
    [3.0, 1.0, 1.0, 3.0]
)

add_heading(doc, '11.2 CI/CD Pipeline', 2)
doc.add_paragraph(
    'Trigger: Push to main branch (or manual dispatch)\n'
    'Platform: GitHub Actions with AWS OIDC authentication\n\n'
    'Steps:\n'
    '  1. Package 6 Lambda functions with dependencies → S3\n'
    '  2. Deploy CloudFormation stack (CAPABILITY_NAMED_IAM)\n'
    '  3. Update Lambda function code from S3\n'
    '  4. Seed DynamoDB knowledge base (72 tips with new schema fields)\n'
    '  5. Deploy website files to S3 (www.eshkolai.com)\n'
    '  6. Inject API Gateway URL into frontend JS\n'
    '  7. Sync to eshkolai.com bucket\n'
    '  8. Invalidate CloudFront cache'
)

# ── 12. Roadmap ───────────────────────────────────────────────────────────────
add_heading(doc, '12. Roadmap', 1)
add_table(doc,
    ['Phase', 'Feature', 'Status'],
    [
        ['Phase 1', 'Tips-driven scan engine with service presence gating', 'Complete'],
        ['Phase 2', 'Chat tab Top Findings widget with last-scan cache', 'Complete'],
        ['Phase 3', 'Act tab hierarchy (Level 1/2/3 collapsible sections)', 'Planned'],
        ['Level 2', 'Rightsizing cards, Spot candidates, gp2→gp3, tagging gaps', 'Planned'],
        ['Level 3', 'NAT→VPC Endpoints, Graviton migration, RI purchase recommendations', 'Planned'],
        ['ScanResults', 'MemberPortal-ScanResults DynamoDB table (7-day TTL)', 'Planned'],
        ['Scheduled Scans', 'EventBridge-triggered daily scan with email digest', 'Planned'],
    ],
    [1.5, 4.0, 1.5]
)

doc.save('SlashMyBill-HLD-v10.docx')
print('HLD saved: SlashMyBill-HLD-v10.docx')
