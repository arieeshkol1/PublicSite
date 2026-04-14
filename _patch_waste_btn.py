#!/usr/bin/env python3
"""Add 'Clean Up' button to waste widget that navigates to Act tab."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Add Clean Up button after waste items
old = """} else {
        html += '<div style="color:#10b981;font-size:0.85em;">No waste detected \\u2713</div>';
    }
    el.innerHTML = html;
}

function _renderMonthly"""

new = """} else {
        html += '<div style="color:#10b981;font-size:0.85em;">No waste detected \\u2713</div>';
    }
    // Add "Clean Up" navigation button if waste exists
    if (waste.items && waste.items.length > 0) {
        html += '<div style="text-align:right;margin-top:8px;"><button onclick="_goToTab(\\'act-tab\\',\\'waste\\');" style="background:none;border:none;color:#6366f1;cursor:pointer;font-size:0.85em;font-weight:600;">Clean Up \\u25b6</button></div>';
    }
    el.innerHTML = html;
}

function _renderMonthly"""

content = content.replace(old, new)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added Clean Up button to waste widget")
