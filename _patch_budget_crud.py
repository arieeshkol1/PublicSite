#!/usr/bin/env python3
"""Add edit/delete buttons to budget cards and wire up the JS handlers."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update budget card rendering to include edit/delete buttons
old_card_end = """+ '<div style="font-size:0.8em;color:#6b7280;margin-top:4px;">' + pct + '% used</div></div>';"""

new_card_end = """+ '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;">'
                + '<span style="font-size:0.8em;color:#6b7280;">' + pct + '% used</span>'
                + '<div style="display:flex;gap:6px;">'
                + '<button onclick="_editBudget(\\'' + b.accountId + '\\',\\'' + b.name.replace(/'/g, "\\\\'") + '\\',' + b.limit + ')" style="background:none;border:none;color:#6366f1;cursor:pointer;font-size:0.85em;">✏️ Edit</button>'
                + '<button onclick="_deleteBudget(\\'' + b.accountId + '\\',\\'' + b.name.replace(/'/g, "\\\\'") + '\\')" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:0.85em;">🗑️ Delete</button>'
                + '</div></div></div>';"""

content = content.replace(old_card_end, new_card_end)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added edit/delete buttons to budget cards")
