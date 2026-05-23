#!/usr/bin/env python3
"""Step 6b: Append Spot JS functions to members.js."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

if '_populateSpotAccountSelector' in content:
    print("Step 6b JS already present -- skipping")
else:
    with open('_spot_step6_js.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Step 6b: Spot JS functions added to members.js")
    print(f"File size: {len(content)} chars")
