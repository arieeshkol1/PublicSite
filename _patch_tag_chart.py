#!/usr/bin/env python3
"""Update Cost by Tag chart to show resource counts instead of dollar amounts."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the label formatter from dollar to count
content = content.replace(
    "label: { show: true, fontSize: 10, formatter: '{b}: ${c}', overflow: 'truncate', width: 110 }",
    "label: { show: true, fontSize: 10, formatter: '{b}: {c}', overflow: 'truncate', width: 110 }"
)

# Update tooltip from dollar to resources
content = content.replace(
    "formatter: function(p) { return p.name + '<br/>$' + p.value.toFixed(2) + ' (' + p.data.pct + '%)'; }",
    "formatter: function(p) { return p.name + '<br/>' + p.value + ' resources (' + p.data.pct + '%)'; }"
)

# Update the "No cost data" message
content = content.replace(
    "chartEl.innerHTML = '<div style=\"color:#9ca3af;text-align:center;padding:60px 0;\">No cost data for this tag key</div>';",
    "chartEl.innerHTML = '<div style=\"color:#9ca3af;text-align:center;padding:60px 0;\">No data for this tag key</div>';"
)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated tag chart to show resource counts")
