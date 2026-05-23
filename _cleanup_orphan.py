#!/usr/bin/env python3
"""Clean up orphaned old recommendation code from members.js."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the orphaned block: starts after first "if (step2) step2.style.display"
# and ends before the second occurrence
marker = "if (step2) step2.style.display = 'block';"
first_idx = content.find(marker)
if first_idx == -1:
    print("ERROR: marker not found")
    exit(1)

# Find the second occurrence
second_idx = content.find(marker, first_idx + len(marker))
if second_idx == -1:
    print("No duplicate found - already clean")
    exit(0)

# Remove everything from end of first marker to start of second marker
end_first = first_idx + len(marker)
# Keep the first occurrence, remove the orphaned code + second occurrence
# Replace: first_marker + orphaned_code + second_marker with just first_marker
content = content[:end_first] + content[second_idx + len(marker):]

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Orphaned code cleaned up")
