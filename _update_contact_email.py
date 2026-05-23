#!/usr/bin/env python3
"""Replace all info@slashmycloudbill.com contact references with ariel@slashmycloudbill.com."""

import os

OLD = 'info@slashmycloudbill.com'
NEW = 'ariel@slashmycloudbill.com'

files_to_update = [
    'members/help.js',
    'members/members.js',
    'slashMyBill/index.html',
    'slashMyBill/slashMyBill.js',
    'privacy/index.html',
    'refund/index.html',
    'terms-and-conditions/index.html',
]

# Also update the contact form handler default recipient
contact_form_files = [
    ('contact-form-handler/lambda_function.py', 'ariel.eshkol@gmail.com', 'ariel@slashmycloudbill.com'),
]

for filepath in files_to_update:
    if not os.path.exists(filepath):
        print(f"  SKIP (not found): {filepath}")
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if OLD in content:
        count = content.count(OLD)
        content = content.replace(OLD, NEW)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Updated {count} occurrence(s): {filepath}")
    else:
        print(f"  No change needed: {filepath}")

# Update contact form handler default
for filepath, old_val, new_val in contact_form_files:
    if not os.path.exists(filepath):
        print(f"  SKIP (not found): {filepath}")
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if old_val in content:
        content = content.replace(old_val, new_val)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Updated contact form recipient: {filepath}")
    else:
        print(f"  No change needed: {filepath}")

print("Done")
