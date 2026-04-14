#!/usr/bin/env python3
"""Fix Paddle customData to be JSON string instead of object."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix plan upgrade customData - stringify it
content = content.replace(
    "customData: {memberEmail: email, tier: plan}",
    "customData: JSON.stringify({memberEmail: email, tier: plan})"
)

# Fix top-up customData - stringify it
content = content.replace(
    "customData: {memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')}",
    "customData: JSON.stringify({memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')})"
)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed customData to use JSON.stringify")
