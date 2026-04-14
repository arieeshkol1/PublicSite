#!/usr/bin/env python3
"""Add _populatePlanAccounts function that clones act-account-select into plan-account-select."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Add _populatePlanAccounts before _switchPlanSection
old = "function _switchPlanSection(section) {"
new = """function _populatePlanAccounts() {
    var src = document.getElementById('act-account-select');
    var dst = document.getElementById('plan-account-select');
    if (!src || !dst) return;
    // Clone the act account selector into plan
    dst.innerHTML = src.innerHTML;
    // Re-wire the toggle button click in the cloned version
    var wrapper = dst.querySelector('div');
    if (wrapper) {
        var btn = wrapper.querySelector('button');
        var panel = wrapper.querySelectorAll('div')[0];
        if (btn && panel) {
            btn.onclick = function(e) { e.stopPropagation(); panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; };
            document.addEventListener('click', function(e) { if (!wrapper.contains(e.target)) panel.style.display = 'none'; });
        }
    }
}

function _switchPlanSection(section) {"""

content = content.replace(old, new, 1)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added _populatePlanAccounts")
