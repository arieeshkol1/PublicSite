content = open('members/members.js', 'r', encoding='utf-8').read()

# Find both Phase 2 blocks
marker = '\n// ============================================================\n// Phase 2 — Chat Tab'
idx1 = content.find(marker)
idx2 = content.find(marker, idx1 + 1)

if idx1 == -1 or idx2 == -1:
    print('ERROR: could not find both blocks', idx1, idx2)
    exit(1)

print(f'Block 1 at: {idx1}, Block 2 at: {idx2}')

# Keep only the second (newer) block — remove the first one
# The first block ends where the second begins
content = content[:idx1] + content[idx2:]

open('members/members.js', 'w', encoding='utf-8').write(content)
print('Deduplication done. New length:', len(content))

# Verify only one block remains
remaining = content.count('Phase 2 — Chat Tab')
print('Phase 2 blocks remaining:', remaining)
