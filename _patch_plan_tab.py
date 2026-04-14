#!/usr/bin/env python3
"""Add Plan tab section switcher and rewire budget/tag to Plan tab."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add _switchPlanSection function after _switchActSection
old_switch = "function _switchActSection(section) {"
new_switch = """function _switchPlanSection(section) {
    document.querySelectorAll('#plan-tab .act-nav-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.section === section);
    });
    ['plan-budget', 'plan-tagging'].forEach(function(s) {
        var el = document.getElementById('plan-section-' + s);
        if (el) el.style.display = s === section ? 'block' : 'none';
    });
}

function _switchActSection(section) {"""

content = content.replace(old_switch, new_switch, 1)

# 2. Update showView to handle plan-tab
old_show = "loginView.hidden = name !== 'login';"
new_show = """loginView.hidden = name !== 'login';
    var planTab = document.getElementById('plan-tab');
    if (planTab) planTab.hidden = name !== 'plan';"""
# Only add if not already there
if 'planTab' not in content:
    content = content.replace(old_show, new_show, 1)

# 3. Rewire budget buttons to use plan- prefixed IDs
content = content.replace(
    "var loadBtn = document.getElementById('act-budget-load-btn');",
    "var loadBtn = document.getElementById('plan-budget-load-btn');"
)
content = content.replace(
    "var createBtn = document.getElementById('act-budget-create-btn');",
    "var createBtn = document.getElementById('plan-budget-create-btn');"
)
content = content.replace(
    "var submitBtn = document.getElementById('budget-wizard-submit');",
    "var submitBtn = document.getElementById('plan-budget-wizard-submit');"
)

# 4. Rewire _loadBudgets to use plan- IDs
content = content.replace("document.getElementById('act-budget-status')", "document.getElementById('plan-budget-status')")
content = content.replace("document.getElementById('act-budget-list')", "document.getElementById('plan-budget-list')")
content = content.replace("document.getElementById('act-budget-empty')", "document.getElementById('plan-budget-empty')")

# 5. Rewire _showBudgetWizard
content = content.replace("document.getElementById('act-budget-wizard')", "document.getElementById('plan-budget-wizard')")
content = content.replace("document.getElementById('budget-account-select')", "document.getElementById('plan-budget-account-select')")
content = content.replace("document.getElementById('budget-alert-email')", "document.getElementById('plan-budget-alert-email')")
content = content.replace("document.getElementById('budget-wizard-error')", "document.getElementById('plan-budget-wizard-error')")

# 6. Rewire _createBudget
content = content.replace("document.getElementById('budget-name')", "document.getElementById('plan-budget-name')")
content = content.replace("document.getElementById('budget-amount')", "document.getElementById('plan-budget-amount')")
content = content.replace("document.getElementById('budget-alert-50')", "document.getElementById('plan-alert-50')")
content = content.replace("document.getElementById('budget-alert-75')", "document.getElementById('plan-alert-75')")
content = content.replace("document.getElementById('budget-alert-100')", "document.getElementById('plan-alert-100')")
content = content.replace("document.getElementById('budget-alert-120')", "document.getElementById('plan-alert-120')")

# 7. Rewire tag manager to use plan- IDs for the Plan tab version
# The tag scan button
content = content.replace(
    "var tagBtn = document.getElementById('act-tag-btn');",
    "var tagBtn = document.getElementById('plan-tag-btn') || document.getElementById('act-tag-btn');"
)

# 8. Update activateMemberTab to handle plan-tab
old_activate = "function activateMemberTab(tabId) {"
if old_activate in content:
    # Find and update the function to include plan-tab
    pass  # The tab switching is handled by the member-tab click handler already

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Plan tab wiring complete!")
