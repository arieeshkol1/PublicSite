content = open('members/members.js', 'r', encoding='utf-8').read()

# Find the Phase 2 block start and end
start_marker = '\n// ============================================================\n// Phase 2 — Chat Tab "Top Findings" Widget\n// ============================================================'
end_marker = '\n// Populate account select when Act tab is clicked — handled by activateMemberTab'

start = content.find(start_marker)
end = content.find(end_marker)

if start == -1 or end == -1:
    print('ERROR: markers not found', start, end)
    exit(1)

new_block = '''
// ============================================================
// Phase 2 — Chat Tab "Top Findings" Widget (v2)
// ============================================================
var _lastScanData = null;

// Load last scan when Chat tab is activated
var _origActivateMemberTab = activateMemberTab;
activateMemberTab = function(tabId) {
    _origActivateMemberTab(tabId);
    if (tabId === 'ai-tab') {
        _loadFindingsWidget();
    }
};

async function _loadFindingsWidget() {
    try {
        var data = await api('GET', '/members/actions/last-scan');
        var scan = data.lastScan;
        if (!scan || !scan.findings || scan.findings.length === 0) {
            // No scan yet — just show the scan button, hide findings section
            var widget = $('ai-findings-widget');
            if (widget) widget.style.display = 'none';
            _updateScanTimestamp(null);
            return;
        }
        _lastScanData = scan;
        _renderFindingsWidget(scan);
    } catch (err) {
        // Silently fail — scan button still visible
    }
}

function _updateScanTimestamp(scannedAt) {
    var ts = $('ai-findings-ts');
    if (!ts) return;
    if (!scannedAt) { ts.textContent = ''; return; }
    var d = new Date(scannedAt);
    var mins = Math.round((Date.now() - d.getTime()) / 60000);
    ts.textContent = 'Last scan: ' + (mins < 60 ? mins + 'm ago' : Math.round(mins/60) + 'h ago');
}

function _renderFindingsWidget(scan) {
    var widget = $('ai-findings-widget');
    var list = $('ai-findings-list');
    var title = $('ai-findings-title');
    var badge = $('ai-findings-badge');
    if (!widget || !list) return;

    _updateScanTimestamp(scan.scannedAt);

    var findings = (scan.findings || []).filter(function(f) { return f.status === 'found'; }).slice(0, 5);
    var totalSavings = parseFloat(scan.totalSavings || 0);

    if (findings.length === 0) {
        widget.style.display = 'none';
        return;
    }

    widget.style.display = 'block';

    if (title) title.textContent = '$' + totalSavings.toFixed(2) + '/mo potential savings';
    if (badge) { badge.style.display = 'inline'; badge.textContent = findings.length; }

    var severityColor = function(s) { return s >= 20 ? '#ef4444' : s >= 5 ? '#f59e0b' : '#10b981'; };
    var severityDot   = function(s) { return s >= 20 ? '🔴' : s >= 5 ? '🟡' : '🟢'; };

    var html = '';
    findings.forEach(function(f) {
        var savings = f.savingsUsd || 0;
        var question = _findingToQuestion(f);
        // Each finding is a button that triggers the full AI answer flow
        html +=
            '<button class="ai-finding-btn" ' +
            'data-question="' + ea(question) + '" ' +
            'style="display:flex;align-items:center;gap:10px;width:100%;text-align:left;' +
            'background:none;border:none;border-bottom:1px solid #21262d;padding:8px 0;cursor:pointer;' +
            'font-size:inherit;color:inherit;" ' +
            'onmouseenter="this.style.background=\'rgba(99,102,241,0.08)\'" ' +
            'onmouseleave="this.style.background=\'none\'">' +
                '<span style="flex-shrink:0;">' + severityDot(savings) + '</span>' +
                '<div style="flex:1;min-width:0;">' +
                    '<div style="color:#c9d1d9;font-size:0.9em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
                        (savings > 0 ? '<span style="color:' + severityColor(savings) + ';font-weight:700;margin-right:6px;">$' + savings.toFixed(2) + '/mo</span>' : '') +
                        esc(f.tipTitle || f.service || '') +
                    '</div>' +
                    '<div style="color:#6b7280;font-size:0.82em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
                        esc(question) +
                    '</div>' +
                '</div>' +
                '<span style="color:#6366f1;font-size:0.8em;flex-shrink:0;font-weight:600;">Ask ▶</span>' +
            '</button>';
    });

    var moreCount = (scan.findings || []).filter(function(f) { return f.status === 'found'; }).length - findings.length;
    if (moreCount > 0) {
        html += '<div style="padding:6px 0;color:#6b7280;font-size:0.78em;">' + moreCount + ' more finding(s) — <button onclick="document.querySelector(\'[data-tab=act-tab]\').click();" style="background:none;border:none;color:#6366f1;cursor:pointer;text-decoration:underline;font-size:1em;padding:0;">see all in Act ▶</button></div>';
    }

    list.innerHTML = html;

    // Apply current font size to findings
    _applyFindingsFontSize();

    // Wire up finding buttons — set input AND submit
    list.querySelectorAll('.ai-finding-btn').forEach(function(btn) {
        btn.onclick = function() {
            var q = btn.dataset.question;
            if (aiQuestionInput) aiQuestionInput.value = q;
            // Hide welcome screen and submit
            var welcome = $('ai-welcome-screen');
            if (welcome) welcome.style.display = 'none';
            askAI();
        };
    });
}

function _applyFindingsFontSize() {
    var list = $('ai-findings-list');
    if (list) list.style.fontSize = aiFontSize + 'px';
}

function _findingToQuestion(f) {
    var tipId = f.tipId || '';
    var title = f.tipTitle || '';
    var svc = f.service || '';
    var qmap = {
        'ebs-004':     'How do I safely delete my unattached EBS volumes?',
        'ebs-002':     'Which EBS snapshots are older than 180 days and safe to delete?',
        'vpc-001':     'How do I release my unassociated Elastic IPs?',
        's3-002':      'Which S3 buckets need lifecycle policies and how do I set them up?',
        'elb-001':     'Which load balancers are idle and how do I safely remove them?',
        'ec2-001':     'Which EC2 instances are over-provisioned and what should I resize them to?',
        'ec2-003':     'Which of my EC2 instances are good candidates for Spot pricing?',
        'ec2-006':     'Which EC2 instances can I migrate to Graviton for better price-performance?',
        'rds-001':     'Which RDS instances are idle and what should I do with them?',
        'kms-001':     'Which KMS customer-managed keys might be unused?',
        'general-002': 'How do I set up AWS Budgets with cost alerts?',
        'general-014': 'Do I have underutilized Reserved Instances I should sell on the RI Marketplace?',
        'ec2-idle':    'Which EC2 instances have been idle for 14+ days?',
        'rds-idle':    'Which RDS instances have been idle for 14+ days?',
        'ebs-snapshot':'Which EBS snapshots are older than 180 days?',
        'spot':        'Which of my instances can use Spot pricing to save money?',
    };
    return qmap[tipId] || ('Tell me about: ' + title + (svc ? ' (' + svc + ')' : ''));
}

async function _runScanFromChat() {
    var scanBtn = $('ai-scan-btn');
    var ts = $('ai-findings-ts');
    if (scanBtn) { scanBtn.disabled = true; scanBtn.textContent = '🔍 Scanning…'; }
    if (ts) ts.textContent = 'Scanning…';
    try {
        var accountIds = getSelectedAccountIds();
        var data = await api('POST', '/members/actions/scan', { accountIds: accountIds });
        _lastScanData = data;
        _renderFindingsWidget(data);
    } catch (err) {
        if (ts) ts.textContent = 'Scan failed: ' + (err.message || 'error');
    } finally {
        if (scanBtn) { scanBtn.disabled = false; scanBtn.textContent = '🔍 Scan for Savings Opportunities'; }
    }
}

// Hook font size changes to also update findings
var _origApplyAIFontSize = applyAIFontSize;
applyAIFontSize = function() {
    _origApplyAIFontSize();
    _applyFindingsFontSize();
};
'''

content = content[:start] + new_block + content[end:]
open('members/members.js', 'w', encoding='utf-8').write(content)
print('Phase 2 widget replaced OK')
print('New JS length:', len(content))
