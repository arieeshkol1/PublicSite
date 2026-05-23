#!/usr/bin/env python3
"""Step 3: Append Qualification + Plan + Migrate handlers."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'def handle_spot_qualify(event):' in content:
    print("Step 3 handlers already present -- skipping")
else:
    with open('_spot_step3_code.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Step 3 complete: Qualify + Plan + Migrate handlers added")
    print(f"File size: {len(content)} chars")
