/**
 * SlashMyBill Help Content v1.0
 * ─────────────────────────────
 * This file is the single source of truth for in-app help.
 * Update this file whenever a feature changes.
 * Structure: HELP_CONTENT[tabId] = { title, sections[] }
 * Each section: { id, heading, icon, content (HTML string) }
 */

var HELP_CONTENT = {

  // ── Global (shown when no specific tab is active) ──────────────────────────
  global: {
    title: 'SlashMyBill Help',
    sections: [
      {
        id: 'intro',
        heading: 'What is SlashMyBill?',
        icon: '💡',
        content: `
          <p>SlashMyBill is an AI-powered AWS FinOps platform that helps you analyze, optimize,
          and reduce your cloud spending across multiple AWS accounts.</p>
          <p>The platform has five main areas:</p>
          <ul>
            <li><strong>Configure</strong> — Connect and manage your AWS accounts</li>
            <li><strong>Plan</strong> — Budget management and tag resources</li>
            <li><strong>Observe</strong> — FinOps dashboard with sub-sections: Cost Analysis, Commitments, Business Metrics, Health & Score, Invoices</li>
            <li><strong>Chat</strong> — Ask natural language questions about your AWS costs (🪙 2 tokens per question)</li>
            <li><strong>Act</strong> — Scan for waste, clean up idle resources, automate stop/start schedules, resize servers, and optimize ASG clusters (🪙 10 per scan, 🪙 50 per action)</li>
          </ul>
          <p><strong>Platform URL:</strong> <a href="https://slashmycloudbill.com/members/" target="_blank">slashmycloudbill.com/members</a></p>
        `
      },
      {
        id: 'pricing',
        heading: 'Plans & Credits',
        icon: '💰',
        content: `
          <h4>Free Plan</h4>
          <ul>
            <li><strong>1 AWS Account</strong></li>
            <li>BI dashboard with all charts (cost by service, daily trend, waste detection, rightsizing, regional breakdown, Savings Plans &amp; RIs)</li>
            <li>🪙 100 tokens/month — AI questions cost 2 tokens, scans cost 10 tokens, cleanup actions cost 50 tokens</li>
            <li>Tokens reset monthly</li>
            <li>Free forever, no credit card required</li>
          </ul>
          <h4>Growth Plan — $50/month</h4>
          <ul>
            <li><strong>Up to 5 AWS Accounts</strong></li>
            <li>Everything in Free, plus:</li>
            <li>🪙 300 tokens/month</li>
            <li>1-click automated cleanup (Actions tab)</li>
            <li>AI Agent with full execution capabilities</li>
            <li>Automated Scheduler — stop/start EC2, RDS, ASG, EKS, SageMaker, Redshift, WorkSpaces on your schedule</li>
            <li>Virtual Tagging &amp; Unit Economics</li>
          </ul>
          <h4>Scale Plan — $200/month</h4>
          <ul>
            <li><strong>Up to 20 AWS Accounts</strong></li>
            <li>Everything in Growth, plus:</li>
            <li>🪙 1,500 tokens/month</li>
            <li>Priority AI processing</li>
            <li>Bulk token top-ups at discount</li>
            <li>Dedicated support</li>
          </ul>
          <h4>Token Top-Ups</h4>
          <p>Need more tokens? Purchase one-time top-ups anytime:</p>
          <ul>
            <li>🪙 50 tokens — $5</li>
            <li>🪙 200 tokens — $15 (25% off)</li>
            <li>🪙 500 tokens — $30 (40% off)</li>
          </ul>
          <p>Top-up tokens are added to your bonus balance and don't expire at month end.</p>
          <div class="help-tip">💡 Your current plan and remaining tokens are shown in the header bar. Click the 🪙 coin icon or the <strong>Upgrade</strong> button to manage your plan or buy tokens.</div>
          <h4>Payments</h4>
          <p>All payments are processed securely by <strong>Paddle.com</strong> (our Merchant of Record). Paddle handles tax, invoicing, and compliance.</p>
          <p>Legal: <a href="/terms-and-conditions/" target="_blank">Terms</a> · <a href="/privacy/" target="_blank">Privacy</a> · <a href="/refund/" target="_blank">Refund Policy</a></p>
        `
      },
      {
        id: 'credits',
        heading: 'How Tokens Work',
        icon: '🪙',
        content: `
          <p>Tokens are the currency for using platform features. Each plan includes a monthly token allowance that resets at the start of each billing cycle:</p>
          <table class="help-table">
            <tr><th>Action</th><th>Token Cost</th></tr>
            <tr><td>AI Chat question</td><td>🪙 2 tokens</td></tr>
            <tr><td>Scan for Savings (Act tab)</td><td>🪙 10 tokens</td></tr>
            <tr><td>Cleanup Action (delete/stop resource)</td><td>🪙 50 tokens</td></tr>
            <tr><td>Dashboard refresh</td><td>Free</td></tr>
            <tr><td>Account management</td><td>Free</td></tr>
          </table>
          <p><strong>Token display:</strong> The header shows your remaining tokens as 🪙 XX/YY. It turns red when you're below 20%.</p>
          <p><strong>Bonus tokens:</strong> Purchased top-ups are added as bonus tokens that don't reset monthly — they persist until used.</p>
          <p><strong>Top up:</strong> Click the 🪙 coin icon in the header to open the upgrade modal and purchase additional tokens via Paddle checkout.</p>
          <div class="help-note">⚠ Monthly tokens reset at the start of each billing cycle. Bonus tokens from top-ups carry over.</div>
        `
      },
      {
        id: 'register',
        heading: 'Creating Your Account',
        icon: '👤',
        content: `
          <p><strong>From the landing page (after bill analysis):</strong></p>
          <ol>
            <li>Click <strong>Start Free</strong> on the results page</li>
            <li>Your email is pre-verified — just set a password</li>
            <li>Account is created instantly, no additional verification needed</li>
          </ol>
          <p><strong>Direct registration:</strong></p>
          <ol>
            <li>Go to <a href="https://slashmycloudbill.com/members/" target="_blank">slashmycloudbill.com/members</a></li>
            <li>Click <strong>Register</strong></li>
            <li>Enter your email and password</li>
            <li>Enter the 6-digit verification code from your email</li>
            <li>Log in with your credentials</li>
          </ol>
          <div class="help-tip">💡 If you already verified your email during bill analysis, the verification step is skipped automatically.</div>
        `
      }
    ]
  },

  // ── Configure Tab ──────────────────────────────────────────────────────────
  'accounts-tab': {
    title: 'Configure — Account Management',
    sections: [
      {
        id: 'connect-account',
        heading: 'Connecting an AWS Account',
        icon: '🔗',
        content: `
          <p>SlashMyBill uses a secure cross-account IAM role — no credentials are stored.</p>
          <ol>
            <li>Click <strong>+ Add Account</strong></li>
            <li>Enter your 12-digit AWS Account ID and an optional name</li>
            <li>Click <strong>Add</strong> — the Setup Wizard opens automatically</li>
          </ol>
          <h4>Setup Wizard (4 steps)</h4>
          <ol>
            <li><strong>Download Template</strong> — Click "Download CF Template"</li>
            <li><strong>Deploy in AWS</strong> — Upload to CloudFormation and create the stack</li>
            <li><strong>Wait</strong> — Stack takes 1-2 minutes to deploy</li>
            <li><strong>Test &amp; Configure</strong> — Click "Test Connection" to verify access</li>
          </ol>
          <div class="help-note">⚠ The CloudFormation stack creates an IAM role named <code>SlashMyBill-{AccountID}</code> with ReadOnlyAccess + a write policy for cleanup, tagging, and scheduling. It does NOT access your application data.</div>
        `
      },
      {
        id: 'hourly',
        heading: 'Enabling Hourly Cost Tracking',
        icon: '⏱',
        content: `
          <p>For real-time hourly cost charts, enable hourly granularity in AWS Cost Explorer:</p>
          <ol>
            <li>Sign in to the <strong>management (payer) account</strong></li>
            <li>Go to <strong>AWS Cost Management → Cost Explorer → Settings</strong></li>
            <li>Check <strong>"Hourly and Resource Level Data"</strong></li>
            <li>Click Save — wait 24-48 hours for data to appear</li>
          </ol>
          <p><strong>Cost:</strong> ~$0.01 per 1,000 usage records/month (typically &lt;$1/month)</p>
          <div class="help-note">⚠ This cannot be enabled via API — it requires a manual action in the AWS Console from the management account.</div>
          <p>To check status: click the ⏱ button next to any account, or run "Test Connection" — the result shows ⏱✓ or ⏱✗</p>
        `
      },
      {
        id: 'optimize-cluster',
        heading: 'Optimize a Cluster',
        icon: '\u26a1',
        content: '<p>The <strong>Optimize a Cluster</strong> wizard analyzes your Auto Scaling Groups against 7 best practices:</p>'
          + '<ol>'
          + '<li><strong>Multi-AZ</strong> \u2014 Ensures instances span 2+ Availability Zones for high availability</li>'
          + '<li><strong>Load Balancer</strong> \u2014 Verifies ALB/NLB is attached with healthy targets</li>'
          + '<li><strong>Spot Mix</strong> \u2014 Checks for MixedInstancesPolicy with price-capacity-optimized strategy</li>'
          + '<li><strong>Instance Diversification</strong> \u2014 Multiple instance types for better Spot availability</li>'
          + '<li><strong>Scaling Policy</strong> \u2014 Target tracking or step scaling configured</li>'
          + '<li><strong>Launch Template</strong> \u2014 Uses Launch Template (not deprecated LaunchConfiguration)</li>'
          + '<li><strong>Health Check Type</strong> \u2014 ELB health checks when load balancer is attached</li>'
          + '</ol>'
          + '<p>Each check shows a grade (A/B/C/D) and specific fix recommendations.</p>'
      },
      {
        id: 'resize-server',
        heading: 'Resize a Server',
        icon: '\U0001f4ca',
        content: '<p>The <strong>Resize a Server</strong> wizard helps you find cheaper EC2 instance types:</p>'
          + '<ol>'
          + '<li>Select an account and EC2 instance</li>'
          + '<li>Click <strong>Optimize</strong> to analyze 30 days of CPU and memory usage</li>'
          + '<li>Review the full instance spec card (vCPU, memory, network, EBS, architecture)</li>'
          + '<li>Browse the sortable comparison table of cheaper alternatives</li>'
          + '<li>Click <strong>Resize</strong> to execute (instance stops for 1-3 minutes during resize)</li>'
          + '</ol>'
          + '<p>The wizard only shows instance types compatible with your current architecture (x86/ARM).</p>'
      },
      {
        id: 'update-permissions',
        heading: 'Updating Role Permissions',
        icon: '🔒',
        content: `
          <p>When new features are added (e.g., tagging, scheduling), the cross-account role needs updated permissions.</p>
          <h4>One-Click Update (Recommended)</h4>
          <ol>
            <li>Go to <strong>Configure</strong> tab</li>
            <li>Click the <strong>🔒</strong> (lock) button next to the account</li>
            <li>Confirm the update</li>
            <li>Done — the latest policy is pushed directly to the role</li>
          </ol>
          <p>This uses <code>iam:PutRolePolicy</code> to update the inline policy without touching CloudFormation.</p>
          <h4>When It Fails</h4>
          <p>If the role was created with a very old template that lacks <code>iam:PutRolePolicy</code>, the one-click update won’t work. In that case:</p>
          <ol>
            <li>Download the latest CF template from Configure tab</li>
            <li>Go to AWS CloudFormation in the target account</li>
            <li>Update the stack with the new template</li>
          </ol>
          <div class="help-tip">💡 The Update Permissions button is the easiest way to keep your role current. Use it whenever you see permission errors in Act or Plan tabs.</div>
        `
      },
      {
        id: 'delete-account',
        heading: 'Deleting an Account Connection',
        icon: '🗑',
        content: `
          <p>When you delete an account, SlashMyBill:</p>
          <ol>
            <li>Assumes the cross-account role</li>
            <li>Detaches all managed policies from the IAM role</li>
            <li>Deletes all inline policies</li>
            <li>Deletes the IAM role</li>
            <li>Deletes the CloudFormation stack</li>
            <li>Removes the account from SlashMyBill</li>
          </ol>
          <div class="help-tip">💡 Your AWS resources are not affected — only the SlashMyBill access role is removed.</div>
          <p>If deletion fails with an older template, redeploy the latest CF template first, then try again.</p>
        `
      },
      {
        id: 'account-table',
        heading: 'Account Table Actions',
        icon: '⚙️',
        content: `
          <table class="help-table">
            <tr><th>Button</th><th>Action</th></tr>
            <tr><td>▲▼</td><td>Reorder account priority (affects dashboard and AI query order)</td></tr>
            <tr><td>↓</td><td>Download CloudFormation template</td></tr>
            <tr><td>⚡</td><td>Test connection + detect hourly status</td></tr>
            <tr><td>🔒</td><td>Update Permissions — push latest IAM policy to the role (no AWS Console needed)</td></tr>
            <tr><td>⏱</td><td>Enable hourly granularity guide</td></tr>
            <tr><td>✏</td><td>Edit account name or ID</td></tr>
            <tr><td>🗑</td><td>Delete account connection</td></tr>
          </table>
          <p>Status badges: <strong>pending</strong> | <strong>connected</strong> | <strong>failed</strong> | <strong>partial</strong></p>
          <p>Hourly badges: ⏱✓ (enabled) | ⏱✗ (not enabled)</p>
        `
      }
    ]
  },

  // ── Observe Tab ────────────────────────────────────────────────────────────
  'dash-tab': {
    title: 'Observe — FinOps Dashboard (Cost Analysis, Commitments, Business Metrics, Health & Score, Invoices)',
    sections: [
      {
        id: 'kpi-bar',
        heading: 'KPI Bar',
        icon: '📊',
        content: `
          <p>The KPI bar at the top shows four key metrics:</p>
          <ul>
            <li><strong>Month-over-Month</strong> — Cost change vs previous month (green = decrease)</li>
            <li><strong>Efficiency Score</strong> — 0-100% based on identified waste vs total spend</li>
            <li><strong>Potential Savings</strong> — Total monthly savings identified. Click to open Chat with a savings question.</li>
            <li><strong>Accounts</strong> — Number of accounts included in the view</li>
          </ul>
        `
      },
      {
        id: 'widgets',
        heading: 'Dashboard Widgets',
        icon: '��',
        content: `
          <table class="help-table">
            <tr><th>Widget</th><th>What It Shows</th><th>How to Use</th></tr>
            <tr><td>Cost by Service</td><td>Treemap of spending by service</td><td>Click a tile to drill into usage types</td></tr>
            <tr><td>Cost Trend</td><td>Daily or hourly cost over time</td><td>Toggle Daily/Hourly. Red markers = anomalies</td></tr>
            <tr><td>Cost Allocation</td><td>Costs by business unit</td><td>Click "Manage Rules" to define business units</td></tr>
            <tr><td>Waste Detection</td><td>Idle resources with dollar amounts</td><td>Click "Chat ▶" to ask the AI</td></tr>
            <tr><td>Rightsizing</td><td>Over-provisioned instances</td><td>Shows Compute Optimizer recommendations</td></tr>
            <tr><td>Monthly Trend</td><td>Cost by service month-over-month</td><td>Stacked bar — each color is a service</td></tr>
            <tr><td>Unit Cost Trend</td><td>Cost per business unit</td><td>Requires business metrics to be configured</td></tr>
            <tr><td>Live Business Metrics</td><td>Auto-discovered operational KPIs (Cognito users, DynamoDB items, API GW requests, Lambda invocations, S3 objects, Route 53 queries) with cost-per-unit economics</td><td>Dual-axis chart: purple volume bars + amber cost line. Use metric selector to switch between Auto-Discovered and Manual groups</td></tr>
            <tr><td>Tag Distribution</td><td>Resource count by tag value (donut chart)</td><td>Click "Manage Tags ▶" to go to Plan → Tag Resources</td></tr>
            <tr><td>Budget KPI</td><td>Spend vs budget limit progress bar</td><td>Click to go to Plan → Budget</td></tr>
            <tr><td>Cost by Region</td><td>Donut chart of spend by AWS region</td><td>Hover for cost and percentage breakdown</td></tr>
            <tr><td>Savings Plans &amp; RIs</td><td>Active commitments, coverage gauges</td><td>Shows SP/EC2 RI/RDS RI counts, coverage %, and details</td></tr>
          </table>
          <h4>Widget Customization</h4>
          <p>You can customize your dashboard layout:</p>
          <ul>
            <li><strong>▲▼ Move</strong> — Reorder widgets up or down</li>
            <li><strong>✕ Hide</strong> — Remove a widget from view</li>
            <li><strong>+ Add</strong> — Restore hidden widgets</li>
          </ul>
          <p>Your layout is saved in localStorage and persists across sessions.</p>
        `
      },
      {
        id: 'drilldown',
        heading: 'Cost by Service Drill-Down',
        icon: '🔍',
        content: `
          <p>The Cost by Service treemap supports 2-phase drill-down:</p>
          <ul>
            <li><strong>Level 1 (Services)</strong> — All AWS services as colored tiles sized by cost</li>
            <li><strong>Level 2 (Usage Types)</strong> — Click any tile to see usage type breakdown</li>
          </ul>
          <p><strong>Navigation:</strong></p>
          <ul>
            <li>Click a tile → drill into usage types</li>
            <li>Click "← All Services" breadcrumb → return to service view</li>
            <li>Click "Details ↗" → open side panel with bar chart + AI chat button</li>
          </ul>
          <div class="help-tip">💡 Example: EC2-Other breaks into VolumeUsage.gp3, NatGateway-Hours, DataTransfer</div>
        `
      },
      {
        id: 'account-select-dash',
        heading: 'Account Selection',
        icon: '🏦',
        content: `
          <p>Use the account selector dropdown (top right) to choose which accounts to include.
          All accounts are selected by default.</p>
          <p>Your selection is preserved when you switch between Observe, Chat, and Act tabs.</p>
        `
      },
      {
        id: 'tag-filter',
        heading: 'Tag-Based Cost Filtering',
        icon: '🏷️',
        content: `
          <p>Filter all dashboard widgets by a specific cost allocation tag. This lets you view costs for a single team, environment, or project.</p>
          <h4>How to Use</h4>
          <ol>
            <li>In the Observe tab header, find the <strong>"Filter by Tag"</strong> dropdowns</li>
            <li>Select a <strong>Tag Key</strong> (e.g., Environment, Team, CostCenter)</li>
            <li>Select a <strong>Tag Value</strong> (e.g., production, dev, marketing)</li>
            <li>All widgets refresh with filtered data</li>
          </ol>
          <h4>Behavior</h4>
          <ul>
            <li><strong>Default:</strong> "All (no filter)" — shows all costs unfiltered</li>
            <li><strong>Tag Distribution widget:</strong> Always shows unfiltered data regardless of filter</li>
            <li><strong>Chat tab:</strong> When a tag filter is active, AI queries also use the filter</li>
            <li><strong>Persistence:</strong> Filter state is preserved when switching between Observe and Chat tabs</li>
            <li><strong>Cache:</strong> Tag keys and values are cached for 5 minutes to avoid repeated API calls</li>
          </ul>
          <h4>Prerequisites</h4>
          <p>Tag filtering requires <strong>cost allocation tags</strong> to be activated in your AWS management account (Billing → Cost Allocation Tags). Resource tags alone are not enough — they must be activated for cost tracking.</p>
          <div class="help-tip">💡 Use the FinOps Healthcheck (Observe → Health & Score) to check if cost allocation tags are activated and fix it with one click.</div>
        `
      }
    ]
  },

  // ── Chat Tab ───────────────────────────────────────────────────────────────
  'ai-tab': {
    title: 'Chat — AI Agent',
    sections: [
      {
        id: 'findings-widget',
        heading: 'Top Findings Widget',
        icon: '💡',
        content: `
          <p>The welcome screen shows your top savings findings from the last scan:</p>
          <ul>
            <li>🔴 Red = high savings (&gt;$20/month)</li>
            <li>🟡 Yellow = medium savings ($5-20/month)</li>
            <li>🟢 Green = low savings (&lt;$5/month)</li>
          </ul>
          <p>Click any finding row or its <strong>Ask ▶</strong> button to populate the Ask box.
          Then press Enter or click Ask to submit.</p>
          <p>Click <strong>🔍 Scan for Savings Opportunities</strong> to run a fresh scan.</p>
          <p>Click <strong>↻ Refresh Findings</strong> (in the header) to rescan at any time.</p>
        `
      },
      {
        id: 'asking',
        heading: 'Asking Questions',
        icon: '💬',
        content: `
          <p>Type your question in the Ask box and press Enter or click Ask. Each question costs <strong>🪙 2 tokens</strong>.</p>
          <p><strong>Example questions:</strong></p>
          <ul>
            <li>"How efficient is my account?"</li>
            <li>"Where can I save money?"</li>
            <li>"Compare my costs over the last 3 months"</li>
            <li>"Which S3 buckets need lifecycle policies?"</li>
            <li>"List Lambda transactions for Jan, Feb, March"</li>
            <li>"Which EC2 instances are over-provisioned?"</li>
            <li>"How do I set up AWS Budgets with cost alerts?"</li>
            <li>"Which of my instances can use Spot pricing?"</li>
          </ul>
          <p>Your remaining tokens are shown in the header bar (🪙 icon).</p>
          <div class="help-tip">💡 For multi-account questions, select multiple accounts using the account dropdown. The AI will provide per-account breakdowns.</div>
          <div class="help-tip">🏷️ When a tag filter is active in the Observe tab (e.g., Environment=production), AI queries automatically use the same filter. Clear the filter to ask about all costs.</div>
        `
      },
      {
        id: 'answer-features',
        heading: 'Answer Features',
        icon: '📋',
        content: `
          <p>Each AI answer includes:</p>
          <ul>
            <li><strong>Commands log</strong> — Shows exactly which AWS APIs were called</li>
            <li><strong>Drill-down buttons</strong> — Follow-up questions based on the answer</li>
            <li><strong>Show as table</strong> — Convert data to a sortable table (shown when relevant)</li>
            <li><strong>👍/👎 Feedback</strong> — Rate the answer to improve future responses</li>
            <li><strong>📋 Copy</strong> — Copy the answer text to clipboard</li>
          </ul>
          <p>Use <strong>A-</strong> and <strong>A+</strong> buttons to adjust font size.</p>
        `
      },
      {
        id: 'general-questions',
        heading: 'General Questions',
        icon: '❓',
        content: `
          <p>The welcome screen shows clickable example questions under "General questions:".
          Click any example to populate the Ask box, then press Enter to submit.</p>
        `
      },
      {
        id: 'ai-agent',
        heading: 'AI Agent (Bedrock)',
        icon: '🤖',
        content: `
          <p>The AI Agent tab provides a conversational interface powered by Amazon Bedrock that can execute multi-step actions on your behalf.</p>
          <h4>Capabilities</h4>
          <ul>
            <li>Query cost data across all connected accounts</li>
            <li>Analyze EC2 instances, EBS volumes, and other resources</li>
            <li>Provide optimization recommendations with specific savings estimates</li>
            <li>Execute cleanup actions (with your confirmation)</li>
          </ul>
          <h4>Multi-Region</h4>
          <p>The AI automatically discovers resources across regions where you have charges (via Cost Explorer). For broad questions, it focuses on cost data only to stay within response time limits.</p>
          <div class="help-tip">💡 For best results, ask specific questions like "List my EC2 instances with CPU usage" rather than broad ones like "How efficient is my account?"</div>
        `
      }
    ]
  },

  // ── Act Tab ────────────────────────────────────────────────────────────────
  'act-tab': {
    title: 'Act — Resource Cleanup',
    sections: [
      {
        id: 'scan',
        heading: 'Running a Scan',
        icon: '🔍',
        content: `
          <p>Each scan costs <strong>10 tokens</strong> (🪙). Cleanup actions cost <strong>50 tokens</strong> each.</p>
          <ol>
            <li>Select accounts using the dropdown</li>
            <li>Click <strong>🔍 Scan for Waste</strong></li>
            <li>Wait 10-20 seconds for the scan to complete</li>
            <li>Review the 7 category cards</li>
          </ol>
          <p>Each category always shows — either a ✓ clean card or a ⚠ findings card with savings amount.</p>
          <div class="help-tip">💡 Token costs: scans = 🪙10, cleanup actions = 🪙50. Your balance updates in the header after each action.</div>
        `
      },
      {
        id: 'cards',
        heading: 'Scan Categories',
        icon: '🗂',
        content: `
          <table class="help-table">
            <tr><th>Card</th><th>What It Finds</th><th>Action</th></tr>
            <tr><td>🌐 Elastic IPs</td><td>Unassociated IPs ($3.65/mo each)</td><td>Release Address</td></tr>
            <tr><td>💾 EBS Volumes</td><td>Unattached volumes ($0.10/GB/mo)</td><td>Delete Volume</td></tr>
            <tr><td>⚖️ Load Balancers</td><td>LBs with 0 healthy targets ($16/mo)</td><td>Delete Load Balancer</td></tr>
            <tr><td>🪣 S3 Buckets</td><td>No lifecycle policy or inactive 90+ days</td><td>Apply Lifecycle / Browse</td></tr>
            <tr><td>🖥️ EC2 Instances</td><td>Avg CPU &lt;5% over 14 days</td><td>Stop Instance</td></tr>
            <tr><td>🗄️ RDS Instances</td><td>Avg CPU &lt;5%, &lt;2 connections over 14 days</td><td>Delete (with snapshot)</td></tr>
            <tr><td>📸 EBS Snapshots</td><td>Older than 180 days</td><td>Delete Snapshot</td></tr>
          </table>
        `
      },
      {
        id: 's3-browse',
        heading: 'S3 Bucket Browser',
        icon: '🪣',
        content: `
          <p>Click <strong>Browse</strong> on any S3 bucket to see its contents:</p>
          <ul>
            <li>Object list with size, last modified date, and age</li>
            <li>Objects 90+ days old highlighted in red ⚠</li>
            <li>Sort by: Oldest first | Largest first | Newest first</li>
          </ul>
          <p><strong>Actions in the Browse modal:</strong></p>
          <ul>
            <li><strong>Apply Lifecycle Policy</strong> — Adds Intelligent-Tiering after 90 days (safe, reversible)</li>
            <li><strong>Delete All Objects</strong> — Permanently removes all objects (bucket remains)</li>
          </ul>
          <div class="help-note">⚠ Delete All Objects is irreversible. A confirmation dialog shows the object count and size before proceeding.</div>
        `
      },
      {
        id: 'safety',
        heading: 'Safety Guardrails',
        icon: '🛡',
        content: `
          <p>Before every cleanup action, a <strong>Just-In-Time (JIT) check</strong> verifies the resource state:</p>
          <ul>
            <li><strong>EIP</strong> — Skips if now associated with an instance</li>
            <li><strong>EBS Volume</strong> — Skips if reattached (state no longer "available")</li>
            <li><strong>Load Balancer</strong> — Skips if traffic has resumed</li>
            <li><strong>EC2</strong> — Detaches from Auto Scaling Group before stopping</li>
            <li><strong>RDS</strong> — Always creates a final snapshot before deletion</li>
            <li><strong>Snapshots</strong> — Verifies still older than 180 days</li>
          </ul>
        `
      },
      {
        id: 'iam-permissions',
        heading: 'IAM Permissions for Write Actions',
        icon: '🔐',
        content: `
          <p>Write actions require an updated CloudFormation template. If you see a blue
          <strong>"⚠ Requires updated IAM role"</strong> banner:</p>
          <ol>
            <li>Go to <strong>Configure</strong> tab</li>
            <li>Click <strong>↓ Download CF Template</strong> for the affected account</li>
            <li>In AWS CloudFormation, find the stack <code>SlashMyBill-Access-{AccountID}</code></li>
            <li>Click <strong>Update → Replace current template</strong> → upload the new file</li>
            <li>Review the new IAM permissions and confirm</li>
          </ol>
          <p>Click <strong>"How to update →"</strong> in the banner for step-by-step guidance.</p>
        `
      },
      {
        id: 'scheduler',
        heading: 'Scheduler — Automated Stop/Start',
        icon: '\u23f0',
        content: `
          <p><strong>What it does:</strong> Automatically stops, starts, and scales your AWS resources on a schedule you define. No more paying for dev/test environments running 24/7.</p>
          <h4>Creating a Schedule</h4>
          <ol>
            <li>Go to <strong>Act \u2192 Scheduler</strong></li>
            <li>Click <strong>"+ New Schedule"</strong></li>
            <li>Select the AWS account</li>
            <li>Choose a schedule type (EC2, RDS, ASG, EKS, SageMaker, Redshift, WorkSpaces, ELB, or a review type)</li>
            <li>Set the days, times, and timezone</li>
            <li>Click <strong>Create</strong></li>
          </ol>
          <h4>Schedule Types</h4>
          <p><strong>Stop/Start types</strong> create two EventBridge rules \u2014 one for the stop action and one for the start action. <strong>Review types</strong> (waste scan, snapshot cleanup, gp2\u2192gp3 migration, SP/RI review) create a single rule.</p>
          <table class="help-table">
            <tr><th>Type</th><th>Actions</th></tr>
            <tr><td>EC2</td><td>Stop / Start instances</td></tr>
            <tr><td>RDS</td><td>Stop / Start DB instances</td></tr>
            <tr><td>ASG</td><td>Scale to zero / Restore</td></tr>
            <tr><td>EKS</td><td>Scale nodegroups to zero / Restore</td></tr>
            <tr><td>SageMaker</td><td>Stop / Start notebook instances</td></tr>
            <tr><td>Redshift</td><td>Pause / Resume clusters</td></tr>
            <tr><td>WorkSpaces</td><td>Set to AUTO_STOP mode</td></tr>
            <tr><td>ELB</td><td>Tear down load balancers</td></tr>
            <tr><td>Waste Scan</td><td>Automated waste detection</td></tr>
            <tr><td>Snapshot Cleanup</td><td>Remove old snapshots</td></tr>
            <tr><td>gp2\u2192gp3 Migration</td><td>Upgrade EBS volumes</td></tr>
            <tr><td>SP/RI Review</td><td>Savings Plans & RI analysis</td></tr>
          </table>
          <h4>Managing Schedules</h4>
          <ul>
            <li><strong>Pause</strong> \u2014 Disables the schedule without deleting it. You can resume anytime.</li>
            <li><strong>Resume</strong> \u2014 Re-enables a paused schedule.</li>
            <li><strong>Delete</strong> \u2014 Permanently removes the schedule and its EventBridge rules.</li>
          </ul>
          <h4>Execution History</h4>
          <p>Expand any schedule card to see the last 10 runs with per-resource success/failure details.</p>
          <ul>
            <li>\u2705 <strong>Success</strong> \u2014 All resources processed</li>
            <li>\u26a0\ufe0f <strong>Partial</strong> \u2014 Some resources failed (expand for details)</li>
            <li>\u274c <strong>Failure</strong> \u2014 All resources failed</li>
          </ul>
          <div class="help-note">\u26a0 Scheduler write actions require an updated CloudFormation template with write permissions. Go to <strong>Configure</strong> and re-download the CF template if prompted.</div>
        `
      },
      {
        id: 'service-optimization',
        heading: 'Service Optimization (Unified Card)',
        icon: '\u2699\ufe0f',
        content: `
          <p>The <strong>Service Optimization</strong> card provides a unified interface for analyzing and optimizing individual AWS resources.</p>
          <h4>How to Use</h4>
          <ol>
            <li>Select an <strong>account</strong> from the dropdown</li>
            <li>Choose the <strong>optimization type</strong></li>
            <li>For EC2/Cluster: select the specific resource</li>
            <li>Click <strong>Analyze</strong></li>
          </ol>
          <h4>Optimization Types</h4>
          <table class="help-table">
            <tr><th>Type</th><th>What It Does</th></tr>
            <tr><td>\U0001f4ca Resize an Instance</td><td>Analyze EC2 CPU/memory usage over 30 days. Shows cheaper alternatives sorted by savings. One-click resize (1-3 min downtime).</td></tr>
            <tr><td>\u26a1 Optimize a Cluster (ASG)</td><td>Grade your Auto Scaling Group against 7 best practices: Multi-AZ, Load Balancer, Spot Mix, Instance Diversification, Scaling Policy, Launch Template, Health Check.</td></tr>
            <tr><td>\U0001f4b0 Optimize Licensing</td><td>Scan Windows Server and SQL Server instances. Find savings through vCPU optimization, BYOL opportunities, and edition downgrades.</td></tr>
            <tr><td>\U0001f5c3 Optimize RDS Database</td><td>Analyze RDS instances for rightsizing, Multi-AZ optimization, storage type upgrades, and engine version recommendations.</td></tr>
            <tr><td>\u26a1 Optimize Lambda Functions</td><td>Analyze Lambda functions for memory optimization, timeout tuning, and architecture recommendations (ARM64 migration).</td></tr>
            <tr><td>\U0001f4be Optimize EBS Volumes</td><td>Find gp2\u2192gp3 migration candidates, over-provisioned IOPS, and unattached volumes.</td></tr>
          </table>
          <div class="help-tip">\U0001f4a1 Multi-region: The optimizer automatically discovers resources across all regions where you have charges \u2014 no need to specify a region.</div>
        `
      },
      {
        id: 'spot-management',
        heading: 'Spot Instance Management',
        icon: '\U0001f4b8',
        content: `
          <p>Migrate eligible On-Demand EC2 instances to Spot pricing for up to 90% savings.</p>
          <h4>Workflow</h4>
          <ol>
            <li><strong>Configure</strong> \u2014 Set your risk tolerance and savings target</li>
            <li><strong>Qualify</strong> \u2014 Scan instances for Spot eligibility (stateless, fault-tolerant, etc.)</li>
            <li><strong>Plan</strong> \u2014 Review the migration plan with estimated savings</li>
            <li><strong>Migrate</strong> \u2014 Execute the migration (creates Spot Fleet or modifies ASG)</li>
          </ol>
          <h4>Dashboard</h4>
          <p>Track your Spot savings over time with the Spot Dashboard showing interruption history and cumulative savings.</p>
          <div class="help-note">\u26a0 Spot instances can be interrupted with 2 minutes notice. Only use for fault-tolerant workloads (batch processing, CI/CD, stateless web servers behind a load balancer).</div>
        `
      },
      {
        id: 'healthcheck',
        heading: 'FinOps Healthcheck',
        icon: '\U0001f3e5',
        content: `
          <p>Scan your AWS account for FinOps best-practice settings and fix issues with one click.</p>
          <h4>What It Checks</h4>
          <table class="help-table">
            <tr><th>Check</th><th>What It Verifies</th></tr>
            <tr><td>Cost Allocation Tags</td><td>Are cost allocation tags activated for tracking?</td></tr>
            <tr><td>Anomaly Detection</td><td>Is AWS Cost Anomaly Detection configured?</td></tr>
            <tr><td>Compute Optimizer</td><td>Is AWS Compute Optimizer enrolled?</td></tr>
            <tr><td>Tag Backfill</td><td>Is cost allocation tag backfill running?</td></tr>
          </table>
          <h4>Auto-Fix</h4>
          <p>Click <strong>Fix</strong> next to any failed check to automatically enable the setting in your AWS account.</p>
          <div class="help-tip">\U0001f4a1 Run the healthcheck after connecting a new account to ensure all FinOps features are enabled.</div>
        `
      }
    ]
  },

  // ── Plan Tab ───────────────────────────────────────────────────────────────
  'plan-tab': {
    title: 'Plan — Budget & Tag Management',
    sections: [
      {
        id: 'budget-management',
        heading: 'Budget Management',
        icon: '💰',
        content: `
          <p>Create and manage AWS Budgets directly from SlashMyBill. Budgets are created in your actual AWS account via the Budgets API.</p>
          <h4>Creating a Budget</h4>
          <ol>
            <li>Go to <strong>Plan → Budget</strong></li>
            <li>Click <strong>"+ Create Budget"</strong></li>
            <li>Enter a monthly budget amount</li>
            <li>Configure alert thresholds (default: 50%, 75%, 100%, 120%)</li>
            <li>Add email addresses for notifications</li>
            <li>Optionally add tag-based filtering (e.g., <code>Environment=production</code>)</li>
            <li>Click <strong>Create</strong></li>
          </ol>
          <h4>Managing Budgets</h4>
          <ul>
            <li><strong>Edit</strong> — Change budget amount or alert thresholds</li>
            <li><strong>Delete</strong> — Remove the budget from your AWS account</li>
            <li><strong>View</strong> — See spend vs limit progress bars for all budgets</li>
          </ul>
          <div class="help-tip">💡 Budget alerts come directly from AWS, not SlashMyBill — they work even when you're not logged in.</div>
          <div class="help-note">⚠ For tag-based budgets, use TagKeyValue format. The Plan tab handles this formatting automatically.</div>
        `
      },
      {
        id: 'tag-policy',
        heading: 'Tag Policy',
        icon: '📋',
        content: `
          <p>Define your organization’s required tags. The tag policy drives the Tag Resources scan — resources missing required tags are flagged.</p>
          <h4>Setting Up</h4>
          <ol>
            <li>Go to <strong>Plan → Tag Policy</strong></li>
            <li>Add required tag keys (e.g., <code>Environment</code>, <code>Owner</code>, <code>CostCenter</code>)</li>
            <li>Click <strong>Save</strong></li>
          </ol>
          <p>The policy is stored per-member and applies to all connected accounts.</p>
          <div class="help-tip">💡 A good starting set: Environment, Owner, CostCenter, Application. These enable cost allocation and accountability.</div>
        `
      },
      {
        id: 'tag-resources',
        heading: 'Tag Resources',
        icon: '🏷',
        content: `
          <p>Scan all resources across connected accounts for tag coverage and bulk-apply tags for cost allocation.</p>
          <h4>How It Works</h4>
          <ol>
            <li>Go to <strong>Plan → Tag Resources</strong></li>
            <li>Review the resource list — untagged resources show red badges, tagged resources show green ✓</li>
            <li>Select resources using checkboxes</li>
            <li>Enter tag key-value pairs (pre-populated keys: <code>Environment</code>, <code>Owner</code>, <code>CostCenter</code>, <code>Application</code>)</li>
            <li>Click <strong>"Apply Tags"</strong> to tag all selected resources</li>
          </ol>
          <h4>Features</h4>
          <ul>
            <li>Uses the AWS Resource Groups Tagging API</li>
            <li>Sticky table headers for scrolling through large resource lists</li>
            <li>Filter by account, service, or tag status</li>
            <li>Bulk apply tags to multiple resources at once</li>
          </ul>
          <div class="help-tip">💡 Good tagging enables accurate cost allocation in the Observe tab's Cost Allocation widget and tag-based budgets.</div>
        `
      }
    ]
  }
};

// ── Help Panel UI ─────────────────────────────────────────────────────────────

var _helpOpen = false;
var _helpCurrentTab = 'global';

function initHelp() {
  // Add ? button to header
  var headerRight = document.querySelector('.header-right');
  if (!headerRight) return;

  var helpBtn = document.createElement('button');
  helpBtn.id = 'help-btn';
  helpBtn.className = 'btn btn-outline btn-sm';
  helpBtn.innerHTML = '? Help';
  helpBtn.style.cssText = 'margin-right:8px;';
  helpBtn.onclick = function() { toggleHelp(); };
  headerRight.insertBefore(helpBtn, headerRight.firstChild);

  // Build the help panel
  var panel = document.createElement('div');
  panel.id = 'help-panel';
  panel.style.cssText = [
    'position:fixed;top:0;right:-420px;width:400px;max-width:95vw;height:100vh',
    'background:#fff;border-left:2px solid #e5e7eb;z-index:900',
    'overflow-y:auto;box-shadow:-4px 0 20px rgba(0,0,0,0.12)',
    'transition:right 0.3s ease;display:flex;flex-direction:column;'
  ].join(';');

  panel.innerHTML = `
    <div style="background:#1f3864;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;">
      <div>
        <div style="color:#fff;font-weight:700;font-size:1.05em;" id="help-panel-title">SlashMyBill Help</div>
        <div style="color:#93c5fd;font-size:0.78em;margin-top:2px;" id="help-panel-subtitle">Select a tab to see contextual help</div>
      </div>
      <button onclick="toggleHelp();" style="background:none;border:none;color:#93c5fd;font-size:1.4em;cursor:pointer;padding:4px;">✕</button>
    </div>
    <div id="help-search-bar" style="padding:10px 16px;border-bottom:1px solid #e5e7eb;flex-shrink:0;">
      <input id="help-search" type="text" placeholder="Search help..." 
        style="width:100%;padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:0.85em;box-sizing:border-box;"
        oninput="searchHelp(this.value);">
    </div>
    <div id="help-body" style="flex:1;padding:16px 20px;overflow-y:auto;"></div>
    <div style="padding:12px 20px;border-top:1px solid #e5e7eb;background:#f9fafb;flex-shrink:0;font-size:0.78em;color:#6b7280;text-align:center;">
      SlashMyBill Help v5.0 · <a href="mailto:ariel@slashmycloudbill.com" style="color:#6366f1;">ariel@slashmycloudbill.com</a>
    </div>
  `;

  document.body.appendChild(panel);

  // Add help styles
  var style = document.createElement('style');
  style.textContent = `
    #help-panel h3 { color:#1f3864;font-size:0.95em;margin:16px 0 6px;border-bottom:2px solid #e5e7eb;padding-bottom:4px; }
    #help-panel h4 { color:#374151;font-size:0.88em;margin:10px 0 4px; }
    #help-panel p, #help-panel li { font-size:0.85em;color:#374151;line-height:1.6;margin:4px 0; }
    #help-panel ul, #help-panel ol { padding-left:18px;margin:6px 0; }
    #help-panel code { background:#f3f4f6;padding:1px 5px;border-radius:3px;font-size:0.85em;color:#1f3864; }
    #help-panel a { color:#6366f1; }
    .help-tip { background:#f0fdf4;border-left:3px solid #16a34a;padding:6px 10px;margin:8px 0;border-radius:0 4px 4px 0;font-size:0.82em;color:#166534; }
    .help-note { background:#fff7ed;border-left:3px solid #d97706;padding:6px 10px;margin:8px 0;border-radius:0 4px 4px 0;font-size:0.82em;color:#92400e; }
    .help-section { margin-bottom:16px;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden; }
    .help-section-header { background:#f9fafb;padding:10px 14px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none; }
    .help-section-header:hover { background:#f3f4f6; }
    .help-section-title { font-weight:600;color:#1f3864;font-size:0.88em; }
    .help-section-body { padding:12px 14px;display:none; }
    .help-section-body.open { display:block; }
    .help-table { width:100%;border-collapse:collapse;font-size:0.82em;margin:6px 0; }
    .help-table th { background:#1f3864;color:#fff;padding:5px 8px;text-align:left; }
    .help-table td { padding:4px 8px;border-bottom:1px solid #e5e7eb; }
    .help-table tr:nth-child(even) td { background:#f9fafb; }
    .help-highlight { background:#fef9c3;border-radius:2px; }
  `;
  document.head.appendChild(style);

  // Listen for tab changes to update contextual help
  document.querySelectorAll('.member-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      if (_helpOpen) {
        renderHelp(tab.dataset.tab);
      }
    });
  });

  renderHelp('global');
}

function toggleHelp() {
  _helpOpen = !_helpOpen;
  var panel = document.getElementById('help-panel');
  if (!panel) return;
  panel.style.right = _helpOpen ? '0' : '-420px';
  // Shrink main content when help is open (side-by-side layout)
  var dashView = document.getElementById('dashboard-view');
  if (dashView) {
    dashView.style.marginRight = _helpOpen ? '410px' : '0';
    dashView.style.transition = 'margin-right 0.3s ease';
  }
  // Resize all ECharts instances after the transition completes
  setTimeout(function() {
    if (typeof dashboardCharts !== 'undefined') {
      dashboardCharts.forEach(function(ch) { try { ch.resize(); } catch(e) {} });
    }
    // Also resize any echarts instance on the page
    var allChartDoms = document.querySelectorAll('[_echarts_instance_]');
    allChartDoms.forEach(function(dom) {
      var inst = echarts.getInstanceByDom(dom);
      if (inst) try { inst.resize(); } catch(e) {}
    });
  }, 350);
  if (_helpOpen) {
    // Show help for current active tab
    var activeTab = document.querySelector('.member-tab.active');
    renderHelp(activeTab ? activeTab.dataset.tab : 'global');
    // Clear search
    var search = document.getElementById('help-search');
    if (search) search.value = '';
  }
}

function renderHelp(tabId) {
  _helpCurrentTab = tabId;
  var content = HELP_CONTENT[tabId] || HELP_CONTENT['global'];
  var titleEl = document.getElementById('help-panel-title');
  var subtitleEl = document.getElementById('help-panel-subtitle');
  var body = document.getElementById('help-body');
  if (!body) return;

  if (titleEl) titleEl.textContent = content.title;
  if (subtitleEl) subtitleEl.textContent = tabId === 'global' ? 'General help' : 'Contextual help for current tab';

  var html = '';
  content.sections.forEach(function(sec, idx) {
    html += `
      <div class="help-section" id="help-sec-${sec.id}">
        <div class="help-section-header" onclick="toggleHelpSection('${sec.id}')">
          <span class="help-section-title">${sec.icon} ${sec.heading}</span>
          <span id="help-chev-${sec.id}" style="color:#9ca3af;font-size:0.8em;">${idx === 0 ? '▲' : '▼'}</span>
        </div>
        <div class="help-section-body ${idx === 0 ? 'open' : ''}" id="help-body-${sec.id}">
          ${sec.content}
        </div>
      </div>
    `;
  });

  // Add link to global help if on a specific tab
  if (tabId !== 'global') {
    html += `<div style="text-align:center;margin-top:12px;">
      <button onclick="renderHelp('global');" style="background:none;border:none;color:#6366f1;cursor:pointer;font-size:0.82em;text-decoration:underline;">
        ← Back to General Help
      </button>
    </div>`;
  }

  body.innerHTML = html;
}

function toggleHelpSection(id) {
  var body = document.getElementById('help-body-' + id);
  var chev = document.getElementById('help-chev-' + id);
  if (!body) return;
  var isOpen = body.classList.contains('open');
  body.classList.toggle('open', !isOpen);
  if (chev) chev.textContent = isOpen ? '▼' : '▲';
}

function searchHelp(query) {
  var body = document.getElementById('help-body');
  if (!body) return;
  if (!query.trim()) {
    renderHelp(_helpCurrentTab);
    return;
  }
  var q = query.toLowerCase();
  var content = HELP_CONTENT[_helpCurrentTab] || HELP_CONTENT['global'];
  var results = [];

  // Search across all tabs
  Object.values(HELP_CONTENT).forEach(function(tabContent) {
    tabContent.sections.forEach(function(sec) {
      var text = sec.heading.toLowerCase() + ' ' + sec.content.toLowerCase().replace(/<[^>]+>/g, ' ');
      if (text.indexOf(q) !== -1) {
        results.push(sec);
      }
    });
  });

  if (results.length === 0) {
    body.innerHTML = '<div style="color:#6b7280;font-size:0.85em;padding:20px;text-align:center;">No results found for "' + query + '"</div>';
    return;
  }

  var html = '<div style="color:#6b7280;font-size:0.78em;margin-bottom:10px;">' + results.length + ' result(s) for "' + query + '"</div>';
  results.forEach(function(sec) {
    var highlighted = sec.content.replace(/<[^>]+>/g, ' ').substring(0, 200) + '...';
    html += `
      <div class="help-section" style="margin-bottom:8px;">
        <div class="help-section-header" onclick="toggleHelpSection('sr-${sec.id}')">
          <span class="help-section-title">${sec.icon} ${sec.heading}</span>
          <span id="help-chev-sr-${sec.id}" style="color:#9ca3af;font-size:0.8em;">▼</span>
        </div>
        <div class="help-section-body" id="help-body-sr-${sec.id}">
          ${sec.content}
        </div>
      </div>
    `;
  });
  body.innerHTML = html;
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initHelp);
} else {
  initHelp();
}
