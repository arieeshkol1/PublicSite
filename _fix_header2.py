import re

with open('members/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Remove ALL injected header elements (tier badge, tokens, upgrade btn)
# They appear before <span id="header-email"
# Pattern: everything between header-right opening and header-email span
# Find header-right div
hr_start = html.find('class="header-right"')
if hr_start < 0:
    print("header-right not found")
    exit(1)

# Find the content between header-right and header-email
he_start = html.find('id="header-email"', hr_start)
if he_start < 0:
    print("header-email not found")
    exit(1)

# Find the span tag start for header-email
span_start = html.rfind('<span', hr_start, he_start)

# Find the end of the SlashMyBill link (the first element in header-right)
smb_link_end = html.find('</a>', hr_start)
if smb_link_end < 0:
    print("SlashMyBill link end not found")
    exit(1)
smb_link_end += 4  # include </a>

# Replace everything between the SlashMyBill link and the header-email span
# with our clean injection
inject = (
    '<span id="header-tier-badge" style="background:#fef3c7;color:#92400e;'
    'padding:2px 10px;border-radius:100px;font-size:0.75em;font-weight:700;'
    'margin-left:8px;margin-right:4px;">Free</span>'
    '<span id="header-tokens" style="display:inline-flex;align-items:center;'
    'gap:4px;background:linear-gradient(135deg,#f59e0b,#d97706);color:#fff;'
    'padding:3px 10px;border-radius:100px;font-size:0.75em;font-weight:700;'
    'cursor:pointer;margin-right:4px;" title="Click to top up tokens" '
    'onclick="_showUpgradeModal();">'
    '&#x1FA99; <span id="header-token-count">100</span></span>'
    '<button id="header-upgrade-btn" style="background:linear-gradient(135deg,'
    '#e8714a,#d4603a);color:#fff;border:none;border-radius:100px;padding:3px 12px;'
    'font-size:0.72em;font-weight:700;cursor:pointer;margin-right:8px;" '
    'onclick="_showUpgradeModal();">Upgrade</button>'
)

# Build new HTML: before smb_link_end + inject + from span_start onwards
# But we need to handle whitespace between elements
new_html = html[:smb_link_end] + inject + html[span_start:]

with open('members/index.html', 'w', encoding='utf-8') as f:
    f.write(new_html)

# Verify
count = new_html.count('header-tier-badge')
print(f"Done. header-tier-badge count: {count}")
