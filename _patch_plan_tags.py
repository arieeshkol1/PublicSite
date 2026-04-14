#!/usr/bin/env python3
"""Rewire tag manager JS to use plan- prefixed IDs for the Plan tab."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# The tag manager init looks for act-tag-btn — update to plan-tag-btn
content = content.replace(
    "var tagBtn = document.getElementById('plan-tag-btn') || document.getElementById('act-tag-btn');",
    "var tagBtn = document.getElementById('plan-tag-btn');"
)

# Update _runTagScan to use plan- IDs
content = content.replace("document.getElementById('act-tag-panel')", "document.getElementById('plan-tag-panel')")
content = content.replace("document.getElementById('act-tag-empty')", "document.getElementById('plan-tag-empty')")
content = content.replace("document.getElementById('act-tag-scan-status')", "document.getElementById('plan-tag-scan-status')")
content = content.replace("document.getElementById('act-tag-stats')", "document.getElementById('plan-tag-stats')")
content = content.replace("document.getElementById('act-tag-search')", "document.getElementById('plan-tag-search')")
content = content.replace("document.getElementById('act-tag-list')", "document.getElementById('plan-tag-list')")
content = content.replace("document.getElementById('act-tag-select-all')", "document.getElementById('plan-tag-select-all')")
content = content.replace("document.getElementById('act-tag-apply-btn')", "document.getElementById('plan-tag-apply-btn')")
content = content.replace("document.getElementById('act-tag-modal')", "document.getElementById('plan-tag-modal')")
content = content.replace("document.getElementById('act-tag-count')", "document.getElementById('plan-tag-count')")
content = content.replace("document.getElementById('act-tag-inputs')", "document.getElementById('plan-tag-inputs')")
content = content.replace("document.getElementById('act-tag-apply-status')", "document.getElementById('plan-tag-apply-status')")
content = content.replace("document.getElementById('act-tag-confirm-btn')", "document.getElementById('plan-tag-confirm-btn')")
content = content.replace("document.getElementById('act-tag-add-row')", "document.getElementById('plan-tag-add-row')")

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Rewired tag manager to plan- IDs")
