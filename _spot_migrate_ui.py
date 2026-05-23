#!/usr/bin/env python3
"""Add Spot Migration UI JS functions to members.js."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

if '_spotDryRun' in content:
    print("Spot migrate UI already present -- skipping")
else:
    with open('_spot_migrate_ui.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Spot Migration UI JS added")
