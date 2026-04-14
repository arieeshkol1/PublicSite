#!/usr/bin/env python3
"""Remove tag-compliance and budget-setup from scheduler recommendations (now separate sections)."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the budget setup recommendation block
budget_start = "            # 4. Budget setup recommendation"
budget_end = "            # 5. Tag compliance recommendation"
if budget_start in content and budget_end in content:
    idx_start = content.index(budget_start)
    idx_end = content.index(budget_end)
    content = content[:idx_start] + content[idx_end:]
    print("Removed budget-setup recommendation from scheduler")

# Remove the tag compliance recommendation block
tag_start = "            # 5. Tag compliance recommendation"
# Find the next except block that closes this try
tag_end_marker = "        except Exception as e:\n            logger.warning(f\"Scheduler analysis failed"
if tag_start in content and tag_end_marker in content:
    idx_start = content.index(tag_start)
    idx_end = content.index(tag_end_marker, idx_start)
    content = content[:idx_start] + content[idx_end:]
    print("Removed tag-compliance recommendation from scheduler")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
