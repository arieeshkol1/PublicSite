from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), '1F3864')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:val'), 'clear')
        cell._tc.get_or_add_tcPr().append(shd)
    for ri, row in enumerate(rows):
        tr = table.rows[ri+1]
        for ci, val in enumerate(row):
            tr.cells[ci].text = str(val)
        if ri % 2 == 0:
            for ci in range(len(row)):
                shd = OxmlElement('w:shd')
                shd.set(qn('w:fill'), 'E8EDF5')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:val'), 'clear')
                tr.cells[ci]._tc.get_or_add_tcPr().append(shd)
    if col_widths:
        for i, w in enumerate(col_widths):
            for row in table.rows:
                row.cells[i].width = Inches(w)
    return table

def tip_box(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    run = p.add_run('💡 Tip: ' + text)
    run.font.color.rgb = RGBColor(22, 101, 52)
    run.font.italic = True

def note_box(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.3)
    run = p.add_run('⚠ Note: ' + text)
    run.font.color.rgb = RGBColor(146, 64, 14)
    run.font.italic = True

doc = Document()
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
run2 = sub.add_run('User Guide')
run2.font.size = Pt(18)
run2.font.color.rgb = RGBColor(99, 102, 241)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run(f'Version 1.0  |  {datetime.date.today().strftime("%B %Y")}  |  AWS FinOps Platform').font.size = Pt(10)
doc.add_paragraph()

# ── Introduction ──────────────────────────────────────────────────────────────
add_heading(doc, '1. Introduction', 1)
doc.add_paragraph(
    'SlashMyBill is an AI-powered AWS cost optimization platform. It connects to your AWS accounts '
    'using read-only (and optionally write) access, analyzes your spending, and helps you identify '
    'and act on savings opportunities — all through a conversational interface and automated cleanup tools.\n\n'
    'Platform URL: https://www.eshkolai.com/members/'
)

add_heading(doc, '1.1 What You Can Do', 2)
add_table(doc,
    ['Feature', 'Description'],
    [
        ['Observe', 'FinOps dashboard with 7 interactive charts — cost by service, trends, waste, rightsizing'],
        ['Chat', 'Ask natural language questions about your AWS costs and get AI-powered answers'],
        ['Act', 'Scan for idle/wasted resources and clean them up with one click'],
        ['Configure', 'Connect and manage your AWS accounts'],
    ],
    [2.0, 6.0]
)

# ── Getting Started ───────────────────────────────────────────────────────────
add_heading(doc, '2. Getting Started', 1)

add_heading(doc, '2.1 Create Your Account', 2)
doc.add_paragraph(
    '1. Go to https://www.eshkolai.com/members/\n'
    '2. Click "Register"\n'
    '3. Enter your email address and click "Send Code"\n'
    '4. Check your email for a 6-digit verification code (valid for 5 minutes)\n'
    '5. Enter the code and click "Verify"\n'
    '6. Set a password (minimum 8 characters) and click "Create Account"\n'
    '7. Log in with your email and password'
)
tip_box(doc, 'If you do not receive the verification email, check your spam folder. You can request a new code after 60 seconds.')

add_heading(doc, '2.2 Connect Your First AWS Account', 2)
doc.add_paragraph(
    'SlashMyBill uses a secure cross-account IAM role to read your AWS cost data. '
    'No credentials are stored — access is granted via a CloudFormation template you deploy.\n\n'
    'Steps:\n'
    '1. Go to the Configure tab\n'
    '2. Click "+ Add Account"\n'
    '3. Enter your 12-digit AWS Account ID and an optional name\n'
    '4. Click "Add" — the Setup Wizard will open automatically\n\n'
    'Setup Wizard (4 steps):\n'
    '  Step 1 — Download Template: Click "Download CF Template" to get the CloudFormation YAML file\n'
    '  Step 2 — Deploy in AWS: Click "Open in CloudFormation Console" or upload the template manually. '
    'Review the IAM permissions and click "Create Stack"\n'
    '  Step 3 — Wait: The stack takes 1-2 minutes to deploy\n'
    '  Step 4 — Test & Configure: Click "Test Connection" to verify access. '
    'The system will also check if hourly cost granularity is enabled'
)
note_box(doc, 'The CloudFormation stack creates an IAM role named SlashMyBill-{AccountID} in your AWS account. '
    'This role has ReadOnlyAccess plus billing/cost permissions. It does NOT have access to your application data.')

add_heading(doc, '2.3 Enable Hourly Cost Tracking (Optional)', 2)
doc.add_paragraph(
    'For real-time hourly cost charts, enable hourly granularity in AWS Cost Explorer:\n\n'
    '1. Sign in to the management (payer) account\n'
    '2. Go to AWS Cost Management → Cost Explorer → Settings\n'
    '3. Check "Hourly and Resource Level Data"\n'
    '4. Click Save\n'
    '5. Wait 24-48 hours for data to appear\n\n'
    'Cost: ~$0.01 per 1,000 usage records/month (typically < $1/month)\n\n'
    'To check status: click the ⏱ button next to any account in the Configure tab, '
    'or run "Test Connection" — the result will show ⏱✓ or ⏱✗'
)
note_box(doc, 'This setting must be enabled from the management (payer) account. '
    'It cannot be enabled via API — it requires a manual action in the AWS Console.')

# ── Observe Tab ───────────────────────────────────────────────────────────────
add_heading(doc, '3. Observe Tab — FinOps Dashboard', 1)
doc.add_paragraph(
    'The Observe tab is your FinOps command center. It loads automatically when you log in '
    'and shows data from all your connected accounts.'
)

add_heading(doc, '3.1 KPI Bar', 2)
doc.add_paragraph(
    'At the top of the dashboard, four key metrics are shown:\n'
    '  • Month-over-Month: Cost change vs previous month (green = decrease, red = increase)\n'
    '  • Efficiency Score: 0-100% score based on identified waste vs total spend\n'
    '  • Potential Savings: Total monthly savings identified — click to open Chat with a savings question\n'
    '  • Accounts: Number of connected accounts included in the view'
)

add_heading(doc, '3.2 Dashboard Widgets', 2)
add_table(doc,
    ['Widget', 'What It Shows', 'How to Use'],
    [
        ['Cost by Service', 'Treemap of spending by AWS service', 'Click a tile to drill into usage types. Click again to go back.'],
        ['Cost Trend', 'Daily or hourly cost over time', 'Toggle Daily/Hourly. Red markers = anomalies (> 2× average).'],
        ['Cost Allocation', 'Costs by business unit (virtual tags)', 'Click "Manage Rules" to define business units.'],
        ['Waste Detection', 'Idle resources with dollar amounts', 'Click "Chat ▶" to ask the AI about specific waste items.'],
        ['Rightsizing', 'Over-provisioned instances', 'Shows Compute Optimizer recommendations with savings.'],
        ['Monthly Trend', 'Cost by service month-over-month', 'Stacked bar chart — each color is a service.'],
        ['Unit Cost Trend', 'Cost per business unit (e.g., per user)', 'Requires business metrics to be configured.'],
    ],
    [1.8, 2.5, 3.7]
)

add_heading(doc, '3.3 Account Selection', 2)
doc.add_paragraph(
    'Use the account selector dropdown (top right of the dashboard) to choose which accounts '
    'to include. All accounts are selected by default. Your selection is preserved when you '
    'switch between Observe, Chat, and Act tabs.'
)

add_heading(doc, '3.4 Cost by Service Drill-Down', 2)
doc.add_paragraph(
    'The Cost by Service treemap supports 2-phase drill-down:\n\n'
    '  Level 1 (Services): Shows all AWS services as colored tiles sized by cost\n'
    '  Level 2 (Usage Types): Click any service tile to see its usage type breakdown '
    '(e.g., EC2-Other breaks into VolumeUsage.gp3, NatGateway-Hours, DataTransfer)\n\n'
    'Navigation:\n'
    '  • Click a tile → drill into usage types\n'
    '  • Click "← All Services" breadcrumb → return to service view\n'
    '  • Click "Details ↗" → open side panel with bar chart + AI chat button'
)

# ── Chat Tab ──────────────────────────────────────────────────────────────────
add_heading(doc, '4. Chat Tab — AI Agent', 1)
doc.add_paragraph(
    'The Chat tab lets you ask natural language questions about your AWS costs. '
    'The AI analyzes your real account data and provides specific, actionable answers.'
)

add_heading(doc, '4.1 Top Findings Widget', 2)
doc.add_paragraph(
    'When you open the Chat tab, the welcome screen shows your top savings findings:\n\n'
    '  • 🔴 Red = high savings (> $20/month)\n'
    '  • 🟡 Yellow = medium savings ($5-20/month)\n'
    '  • 🟢 Green = low savings (< $5/month)\n\n'
    'Click any finding row or its "Ask ▶" button to populate the Ask box with a suggested question. '
    'Then press Enter or click Ask to submit.\n\n'
    'Click "🔍 Scan for Savings Opportunities" to run a fresh scan.\n'
    'Click "↻ Refresh Findings" (in the header) to rescan at any time, even mid-conversation.'
)

add_heading(doc, '4.2 Asking Questions', 2)
doc.add_paragraph(
    'Type your question in the Ask box and press Enter or click Ask.\n\n'
    'Example questions:\n'
    '  • "How efficient is my account?"\n'
    '  • "Where can I save money?"\n'
    '  • "Compare my costs over the last 3 months"\n'
    '  • "Which S3 buckets need lifecycle policies?"\n'
    '  • "List Lambda transactions for Jan, Feb, March"\n'
    '  • "Which EC2 instances are over-provisioned?"\n'
    '  • "How do I set up AWS Budgets with cost alerts?"\n'
    '  • "Which of my instances can use Spot pricing?"\n\n'
    'The AI will show the AWS API commands it executed, then provide a detailed answer '
    'with specific resource IDs, dollar amounts, and actionable recommendations.'
)
tip_box(doc, 'For multi-account questions, select multiple accounts using the account dropdown. '
    'The AI will analyze all selected accounts and provide per-account breakdowns.')

add_heading(doc, '4.3 Answer Features', 2)
doc.add_paragraph(
    'Each AI answer includes:\n'
    '  • Commands log: Shows exactly which AWS APIs were called\n'
    '  • Drill-down buttons: Follow-up questions based on the answer\n'
    '  • Show as table: Convert data to a sortable table (only shown when relevant)\n'
    '  • 👍/👎 Feedback: Rate the answer to improve future responses\n\n'
    'Click "📋 Copy" to copy the answer text to your clipboard.'
)

add_heading(doc, '4.4 Font Size', 2)
doc.add_paragraph(
    'Use the A- and A+ buttons in the header to adjust the chat font size. '
    'The setting applies to both the chat messages and the findings widget.'
)

# ── Act Tab ───────────────────────────────────────────────────────────────────
add_heading(doc, '5. Act Tab — Resource Cleanup', 1)
doc.add_paragraph(
    'The Act tab scans your AWS accounts for idle and wasted resources, '
    'then lets you clean them up with one click.'
)

add_heading(doc, '5.1 Running a Scan', 2)
doc.add_paragraph(
    '1. Select accounts using the dropdown (same style as Chat/Observe)\n'
    '2. Click "🔍 Scan for Waste"\n'
    '3. Wait 10-20 seconds for the scan to complete\n'
    '4. Review the 7 category cards\n\n'
    'Each category always shows — either a ✓ clean card or a ⚠ findings card with savings amount.'
)

add_heading(doc, '5.2 Understanding the Cards', 2)
add_table(doc,
    ['Card', 'What It Finds', 'Action'],
    [
        ['🌐 Elastic IPs', 'Unassociated IPs ($3.65/mo each)', 'Release Address'],
        ['💾 EBS Volumes', 'Unattached volumes ($0.10/GB/mo)', 'Delete Volume'],
        ['⚖️ Load Balancers', 'LBs with 0 healthy targets ($16/mo)', 'Delete Load Balancer'],
        ['🪣 S3 Buckets', 'No lifecycle policy or inactive 90+ days', 'Apply Lifecycle / Browse'],
        ['🖥️ EC2 Instances', 'Avg CPU < 5% over 14 days', 'Stop Instance'],
        ['🗄️ RDS Instances', 'Avg CPU < 5%, < 2 connections over 14 days', 'Delete (with snapshot)'],
        ['📸 EBS Snapshots', 'Older than 180 days', 'Delete Snapshot'],
    ],
    [1.8, 3.0, 2.2]
)

add_heading(doc, '5.3 S3 Bucket Details', 2)
doc.add_paragraph(
    'The S3 card shows each flagged bucket with:\n'
    '  • Size and estimated monthly cost\n'
    '  • Last activity (days since last object change)\n'
    '  • Reason badges: "No lifecycle", "Inactive 95d", "Empty"\n\n'
    'Click "Browse" on any bucket to see its contents:\n'
    '  • Object list with size, last modified date, and age\n'
    '  • Objects 90+ days old highlighted in red\n'
    '  • Sort by: Oldest first | Largest first | Newest first\n'
    '  • "Apply Lifecycle Policy" — adds Intelligent-Tiering after 90 days\n'
    '  • "Delete All Objects" — permanently removes all objects (bucket remains)'
)
note_box(doc, 'Delete All Objects is irreversible. A confirmation dialog will show the object count and size before proceeding.')

add_heading(doc, '5.4 Safety Guardrails', 2)
doc.add_paragraph(
    'Before every cleanup action, the system performs a Just-In-Time (JIT) check:\n'
    '  • EIP: Verifies still unassociated (skips if now attached)\n'
    '  • EBS Volume: Verifies still in "available" state (skips if reattached)\n'
    '  • Load Balancer: Verifies still has 0 healthy targets (skips if traffic resumed)\n'
    '  • EC2: Checks for Auto Scaling Group membership (detaches from ASG before stopping)\n'
    '  • RDS: Always creates a final snapshot before deletion\n'
    '  • Snapshots: Verifies still older than 180 days'
)

add_heading(doc, '5.5 IAM Permissions for Write Actions', 2)
doc.add_paragraph(
    'Write actions (delete, stop, apply lifecycle) require an updated CloudFormation template. '
    'If you see a blue "⚠ Requires updated IAM role" banner:\n\n'
    '1. Go to Configure tab\n'
    '2. Click "↓ Download CF Template" for the affected account\n'
    '3. In AWS CloudFormation, find the stack SlashMyBill-Access-{AccountID}\n'
    '4. Click Update → Replace current template → upload the new file\n'
    '5. Review the new IAM permissions and confirm\n\n'
    'Click "How to update →" in the banner for step-by-step guidance.'
)

# ── Configure Tab ─────────────────────────────────────────────────────────────
add_heading(doc, '6. Configure Tab — Account Management', 1)

add_heading(doc, '6.1 Account Table', 2)
doc.add_paragraph(
    'The Configure tab shows all your connected AWS accounts with:\n'
    '  • Status badge: pending | connected | failed | partial\n'
    '  • Hourly badge: ⏱✓ (enabled) or ⏱✗ (not enabled)\n'
    '  • Last tested date\n\n'
    'Action buttons per account:\n'
    '  ▲▼ — Reorder priority (affects dashboard and AI query order)\n'
    '  ↓ — Download CloudFormation template\n'
    '  ⚡ — Test connection (also checks hourly status)\n'
    '  ⏱ — Enable hourly granularity guide\n'
    '  ✏ — Edit account name or ID\n'
    '  🗑 — Delete account connection'
)

add_heading(doc, '6.2 Deleting an Account', 2)
doc.add_paragraph(
    'When you delete an account connection:\n'
    '  1. SlashMyBill assumes the cross-account role\n'
    '  2. Detaches all managed policies from the IAM role\n'
    '  3. Deletes all inline policies\n'
    '  4. Deletes the IAM role\n'
    '  5. Deletes the CloudFormation stack\n'
    '  6. Removes the account from SlashMyBill\n\n'
    'If the stack deletion fails (e.g., older template without iam:DetachRolePolicy), '
    'you will see a warning with instructions to clean up manually.'
)

# ── Virtual Tagging ───────────────────────────────────────────────────────────
add_heading(doc, '7. Virtual Tagging & Cost Allocation', 1)
doc.add_paragraph(
    'Virtual tagging lets you group AWS costs into business units without changing your '
    'actual AWS resource tags.\n\n'
    'To set up:\n'
    '1. In the Observe tab, click "Manage Rules" on the Cost Allocation widget\n'
    '2. Click "+ Add Business Unit"\n'
    '3. Name the business unit (e.g., "Data Science Team")\n'
    '4. Add rules:\n'
    '   • Dimension: Account | Service | Tag\n'
    '   • Operator: equals | contains | startsWith\n'
    '   • Value: the matching value\n'
    '5. Set rule logic: AND (all rules must match) or OR (any rule matches)\n'
    '6. For shared costs, choose: Even split | Proportional | Custom %\n'
    '7. Click Save\n\n'
    'The Cost Allocation treemap will update to show costs by business unit.'
)

# ── Unit Economics ────────────────────────────────────────────────────────────
add_heading(doc, '8. Unit Economics', 1)
doc.add_paragraph(
    'Unit Economics tracks your cost per business output (e.g., cost per user, cost per transaction).\n\n'
    'To add business metrics:\n'
    '1. In the Observe tab, find the Unit Cost Trend widget\n'
    '2. Click "Add Metric"\n'
    '3. Enter: Metric Name (e.g., "ActiveUsers"), Month (YYYY-MM), Volume (e.g., 50000)\n'
    '4. Click Save\n\n'
    'Auto-discovered IT metrics (no manual entry needed):\n'
    '  • DynamoDB items count\n'
    '  • API Gateway request count\n'
    '  • Lambda invocation count\n'
    '  • S3 bucket count\n\n'
    'The Unit Cost Trend widget shows a dual-axis chart:\n'
    '  • Bar (left axis): Business volume\n'
    '  • Line (right axis): Cost per unit\n\n'
    'If costs increase but cost-per-unit decreases, the AI will frame this as "efficient scaling".'
)

# ── Troubleshooting ───────────────────────────────────────────────────────────
add_heading(doc, '9. Troubleshooting', 1)
add_table(doc,
    ['Issue', 'Cause', 'Solution'],
    [
        ['Connection test fails', 'CloudFormation stack not deployed or role name mismatch', 'Re-run the Setup Wizard and deploy the template'],
        ['Hourly chart shows no data', 'Hourly granularity not enabled in Cost Explorer', 'Enable in AWS Cost Explorer Settings (management account)'],
        ['Scan fails with "Service Unavailable"', 'Lambda timeout (scan too slow)', 'Try scanning fewer accounts at once'],
        ['Write action fails with Access Denied', 'Old CF template without write permissions', 'Redeploy the latest CF template (see Act tab warning)'],
        ['Stack deletion fails', 'Old template missing iam:DetachRolePolicy', 'Redeploy latest template first, then delete'],
        ['AI gives generic answers', 'Question too broad or data not fetched', 'Be specific: include service name, time period, account'],
        ['No findings in Act tab', 'Accounts are clean or scan not run yet', 'Click "Scan for Waste" to run a fresh scan'],
        ['OTP email not received', 'Email in spam or rate limit hit', 'Check spam; wait 60 seconds before requesting a new code'],
    ],
    [2.0, 2.5, 3.5]
)

# ── FAQ ───────────────────────────────────────────────────────────────────────
add_heading(doc, '10. Frequently Asked Questions', 1)

faqs = [
    ('Is my AWS data safe?',
     'SlashMyBill uses read-only access by default. The IAM role has ReadOnlyAccess plus billing permissions. '
     'No application data (S3 objects, database contents, etc.) is ever read. Write permissions are optional '
     'and only used when you explicitly click a cleanup action.'),
    ('Can SlashMyBill modify my AWS resources without my permission?',
     'No. Every cleanup action requires you to click a button and confirm a dialog. '
     'A JIT safety check runs immediately before each action to verify the resource state has not changed.'),
    ('How much does SlashMyBill cost?',
     'Contact the SlashMyBill team at https://www.eshkolai.com for pricing information.'),
    ('How often is the dashboard data refreshed?',
     'Dashboard data is cached for 5 minutes. Click the refresh button to force a reload. '
     'Cost Explorer data itself is updated by AWS once every 24 hours.'),
    ('Can I connect multiple AWS accounts?',
     'Yes. You can connect up to 5 accounts and analyze them together or individually. '
     'Use the account selector in each tab to choose which accounts to include.'),
    ('What happens when I delete an account connection?',
     'SlashMyBill removes the IAM role and CloudFormation stack from your AWS account, '
     'then removes the account from SlashMyBill. Your AWS resources are not affected.'),
    ('Does SlashMyBill support AWS Organizations?',
     'Yes. Connect your management (payer) account for organization-wide cost visibility. '
     'For linked accounts, hourly granularity must be enabled from the management account.'),
]

for q, a in faqs:
    p = doc.add_paragraph()
    run = p.add_run('Q: ' + q)
    run.bold = True
    run.font.color.rgb = RGBColor(31, 56, 100)
    doc.add_paragraph('A: ' + a)
    doc.add_paragraph()

doc.save('SlashMyBill-UserGuide-v1.docx')
print('User Guide saved: SlashMyBill-UserGuide-v1.docx')
