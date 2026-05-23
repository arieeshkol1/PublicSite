#!/usr/bin/env python3
"""Step 2b: Append Spot handler code from text file to member-handler."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'def handle_spot_config(event):' in content:
    print("Step 2 handlers already present -- skipping")
else:
    with open('_spot_step2_code.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Step 2 complete: Spot Config + EventBridge + Email + SNS handlers added")
    print(f"File size: {len(content)} chars")
