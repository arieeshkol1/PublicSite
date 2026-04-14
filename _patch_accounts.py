#!/usr/bin/env python3
"""Update Growth tier from 20 accounts to 5 accounts across frontend files."""

# members.js - upgrade modal
with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace("20 accounts &middot; All features", "5 accounts &middot; All features")
content = content.replace("20 accounts &middot; Priority", "20 accounts &middot; Priority")  # Scale stays 20
with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated members.js")

# slashMyBill/index.html - offer wall
with open('slashMyBill/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
# Growth card
content = content.replace(
    '<li><i class="fas fa-check-circle"></i> Up to 20 AWS Accounts</li>\n                                    <li><i class="fas fa-check-circle"></i> Everything in Free</li>',
    '<li><i class="fas fa-check-circle"></i> Up to 5 AWS Accounts</li>\n                                    <li><i class="fas fa-check-circle"></i> Everything in Free</li>'
)
with open('slashMyBill/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated slashMyBill/index.html")

# help.js
with open('members/help.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    "<li><strong>Up to 20 AWS Accounts</strong></li>\n            <li>Everything in Free, plus:</li>\n            <li>🪙 300 tokens/month</li>",
    "<li><strong>Up to 5 AWS Accounts</strong></li>\n            <li>Everything in Free, plus:</li>\n            <li>🪙 300 tokens/month</li>"
)
with open('members/help.js', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated help.js")

# terms-and-conditions
with open('terms-and-conditions/index.html', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(
    "Growth Plan:</strong> $50/month — 300 tokens, up to 20 AWS accounts",
    "Growth Plan:</strong> $50/month — 300 tokens, up to 5 AWS accounts"
)
with open('terms-and-conditions/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated terms-and-conditions/index.html")

print("Done! Growth tier: 5 accounts, Scale tier: 20 accounts")
