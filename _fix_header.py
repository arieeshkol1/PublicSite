import sys

with open('members/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find the span with header-email
marker = 'id="header-email"'
idx = html.find(marker)
print(f"Found marker at: {idx}")

if idx < 0:
    print("ERROR: marker not found")
    sys.exit(1)

# Find the start of the <span tag
start = html.rfind('<span', max(0, idx - 50), idx)
print(f"Span starts at: {start}")

# Insert tokens + upgrade BEFORE the header-email span
inject = (
    '<span id="header-tier-badge" style="background:#fef3c7;color:#92400e;'
    'padding:2px 10px;border-radius:100px;font-size:0.75em;font-weight:700;'
    'margin-right:6px;">Free</span>'
    '<span id="header-tokens" style="display:inline-flex;align-items:center;'
    'gap:4px;background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff;'
    'padding:3px 10px;border-radius:100px;font-size:0.75em;font-weight:700;'
    'cursor:pointer;margin-right:6px;" title="Click to top up tokens">'
    '&#x1FA99; <span id="header-token-count">100</span></span>'
    '<button id="header-upgrade-btn" style="background:linear-gradient(135deg,'
    '#e8714a,#d4603a);color:#fff;border:none;border-radius:100px;padding:3px 12px;'
    'font-size:0.72em;font-weight:700;cursor:pointer;margin-right:8px;">'
    'Upgrade</button>'
)

html = html[:start] + inject + html[start:]

with open('members/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Header updated successfully")
