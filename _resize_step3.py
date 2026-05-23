#!/usr/bin/env python3
"""Step 3: Append resize wizard JS to members.js."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

if '_resizeAnalyze' in content:
    print("Resize JS already present -- skipping")
else:
    with open('_resize_js.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Resize wizard JS added")
