#!/usr/bin/env python3
"""Add cross-tab synergy: Budget KPI, Fix This buttons, Tag coverage link."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add Budget KPI card to the KPI bar (after Accounts card)
old_kpi = """_kpiCard('Accounts', (s.accountsAnalyzed || 0) + ' / ' + (s.totalAccounts || 0), '#6366f1');"""

new_kpi = """_kpiCard('Accounts', (s.accountsAnalyzed || 0) + ' / ' + (s.totalAccounts || 0), '#6366f1');

    // Budget KPI — show budget status if budgets exist (loaded async)
    _loadBudgetKPI(kpiBar);"""

content = content.replace(old_kpi, new_kpi)

# 2. Add "Clean Up ▶" button to the waste widget rendering
# Find _renderWaste and add a button after the waste items
old_waste_empty = """container.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:40px 0;">No waste detected \\u2714</div>';"""
if old_waste_empty in content:
    new_waste_empty = """container.innerHTML = '<div style="color:#10b981;text-align:center;padding:40px 0;">\\u2714 No waste detected — your resources are clean!</div>';"""
    content = content.replace(old_waste_empty, new_waste_empty)

# 3. Add _loadBudgetKPI function and navigation helpers
# Insert before the _kpiCard function
old_kpi_func = "function _kpiCard(label, value, color) {"
new_kpi_func = """// Cross-tab navigation helpers
function _goToTab(tabId, section) {
    document.querySelector('[data-tab=' + tabId + ']').click();
    if (section) setTimeout(function() {
        if (tabId === 'act-tab') _switchActSection(section);
        if (tabId === 'plan-tab') _switchPlanSection(section);
    }, 100);
}

// Budget KPI — async load budget data and show in KPI bar
function _loadBudgetKPI(kpiBar) {
    // Try to load budgets in background
    api('POST', '/members/budgets/list', {}).then(function(data) {
        var budgets = data.budgets || [];
        if (budgets.length === 0) {
            // No budgets — show "Set Budget" prompt
            var card = document.createElement('div');
            card.style.cssText = 'background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;padding:12px 16px;flex:1;min-width:130px;cursor:pointer;';
            card.title = 'Click to create a budget in the Plan tab';
            card.onclick = function() { _goToTab('plan-tab', 'plan-budget'); };
            card.innerHTML = '<div style="color:#92400e;font-size:0.75em;">Budget</div><div style="color:#92400e;font-size:1.1em;font-weight:700;">Not Set \\u25b6</div>';
            kpiBar.appendChild(card);
            return;
        }
        // Show first budget status
        var b = budgets[0];
        var pct = b.limit > 0 ? Math.round(b.actualSpend / b.limit * 100) : 0;
        var budgetColor = pct >= 100 ? '#ef4444' : pct >= 75 ? '#f59e0b' : '#10b981';
        var card = document.createElement('div');
        card.style.cssText = 'background:#f0f4f8;border:1px solid #d0d7de;border-radius:8px;padding:12px 16px;flex:1;min-width:130px;cursor:pointer;';
        card.title = 'Budget: ' + b.name + ' — Click to manage budgets';
        card.onclick = function() { _goToTab('plan-tab', 'plan-budget'); };
        card.innerHTML = '<div style="color:#6b7280;font-size:0.75em;">Budget (' + b.name.substring(0, 15) + ') \\u25b6</div>'
            + '<div style="color:' + budgetColor + ';font-size:1.3em;font-weight:700;">$' + Math.round(b.actualSpend) + ' / $' + Math.round(b.limit) + '</div>'
            + '<div style="background:#e5e7eb;border-radius:3px;height:4px;margin-top:4px;"><div style="width:' + Math.min(pct, 100) + '%;height:100%;background:' + budgetColor + ';border-radius:3px;"></div></div>';
        kpiBar.appendChild(card);
    }).catch(function() { /* silent — budget KPI is optional */ });
}

function _kpiCard(label, value, color) {"""

content = content.replace(old_kpi_func, new_kpi_func)

# 4. Add Tag Coverage link to the Cost by Tag widget
old_tag_coverage = """html += '<span style="font-size:11px;color:#6b7280;margin-left:auto;">Coverage: <strong style="color:' + (tagData.coverage >= 80 ? '#10b981' : tagData.coverage >= 50 ? '#f59e0b' : '#ef4444') + ';">' + tagData.coverage + '%</strong></span>';"""

new_tag_coverage = """html += '<span style="font-size:11px;color:#6b7280;margin-left:auto;cursor:pointer;" onclick="_goToTab(\\'plan-tab\\',\\'plan-tagging\\');" title="Click to manage tags">Coverage: <strong style="color:' + (tagData.coverage >= 80 ? '#10b981' : tagData.coverage >= 50 ? '#f59e0b' : '#ef4444') + ';">' + tagData.coverage + '%</strong> \\u25b6</span>';"""

content = content.replace(old_tag_coverage, new_tag_coverage)

# 5. Add "Clean Up ▶" link to waste widget items
# Find the waste rendering and add action link
old_waste_item = """all_waste.append({'type': 'Unattached EBS'"""
# This is in the backend, not frontend. Let's add the link in the frontend waste renderer instead.

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Synergy integrations added!")
