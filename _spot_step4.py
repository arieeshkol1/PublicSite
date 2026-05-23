#!/usr/bin/env python3
"""Step 4: Append Dashboard + Savings Ledger handlers."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'def handle_spot_dashboard(event):' in content:
    print("Step 4 handlers already present -- skipping")
else:
    with open('_spot_step4_code.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Step 4 complete: Dashboard + Savings Ledger handlers added")
    print(f"File size: {len(content)} chars")
