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
          <p>The platform has four main areas:</p>
          <ul>
            <li><strong>Observe</strong> — FinOps dashboard with 7 interactive charts</li>
            <li><strong>Chat</strong> — Ask natural language questions about your AWS costs</li>
            <li><strong>Act</strong> — Scan for waste and clean up idle resources</li>
            <li><strong>Configure</strong> — Connect and manage your AWS accounts</li>
          </ul>
          <p><strong>Platform URL:</strong> <a href="https://www.eshkolai.com/members/" target="_blank">eshkolai.com/members</a></p>
        `
      },
      {
        id: 'register',
        heading: 'Creating Your Account',
        icon: '👤',
        content: `
          <ol>
            <li>Click <strong>Register</strong> on the login page</li>
            <li>Enter your email and click <strong>Send Code</strong></li>
            <li>Enter the 6-digit code from your email (valid 5 minutes)</li>
            <li>Set a password (minimum 8 characters)</li>
            <li>Log in with your email and password</li>
          </ol>
          <div class="help-tip">💡 If you don't receive the email, check spam. You can request a new code after 60 seconds.</div>
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
          <div class="help-note">⚠ The CloudFormation stack creates an IAM role named <code>SlashMyBill-{AccountID}</code> with ReadOnlyAccess. It does NOT access your application data.</div>
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
    title: 'Observe — FinOps Dashboard',
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
          </table>
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
          <p>Type your question in the Ask box and press Enter or click Ask.</p>
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
          <div class="help-tip">💡 For multi-account questions, select multiple accounts using the account dropdown. The AI will provide per-account breakdowns.</div>
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
          <ol>
            <li>Select accounts using the dropdown</li>
            <li>Click <strong>🔍 Scan for Waste</strong></li>
            <li>Wait 10-20 seconds for the scan to complete</li>
            <li>Review the 7 category cards</li>
          </ol>
          <p>Each category always shows — either a ✓ clean card or a ⚠ findings card with savings amount.</p>
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
      SlashMyBill Help v1.0 · <a href="mailto:support@eshkolai.com" style="color:#6366f1;">support@eshkolai.com</a>
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
