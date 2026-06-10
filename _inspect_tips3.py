import gzip, json, os
from collections import defaultdict

path = 'TipsTable'
files = os.listdir(path)
data = []
for f in files:
    if f.endswith('.gz'):
        with gzip.open(os.path.join(path, f), 'rb') as gz:
            content = gz.read().decode('utf-8')
            for line in content.strip().split('\n'):
                if line.strip():
                    item = json.loads(line)
                    if 'Item' in item:
                        data.append(item['Item'])
                    else:
                        data.append(item)

def get_val(item, key):
    v = item.get(key, {})
    if isinstance(v, dict):
        return v.get('S', v.get('N', v.get('BOOL', str(v))))
    return str(v)

# ========================================
# 1. DUPLICATE DETECTION
# ========================================
print("=" * 80)
print("1. DUPLICATE / NEAR-DUPLICATE TIPS")
print("=" * 80)

# Group by title similarity
title_groups = defaultdict(list)
for item in data:
    title = get_val(item, 'title').lower().strip()
    title_groups[title].append(item)

exact_dupes = {k: v for k, v in title_groups.items() if len(v) > 1}
print(f"\nExact title duplicates: {len(exact_dupes)} groups")
for title, items in exact_dupes.items():
    clouds = [get_val(i, 'cloud') for i in items]
    tip_ids = [get_val(i, 'tipId') for i in items]
    print(f"  \"{title}\" -> {len(items)} copies")
    print(f"    Clouds: {clouds}")
    print(f"    TipIDs: {tip_ids}")

# Group by service+category to find conceptual duplicates
svc_cat_groups = defaultdict(list)
for item in data:
    key = f"{get_val(item, 'service')}|{get_val(item, 'category')}"
    svc_cat_groups[key].append(item)

print(f"\nService+Category combos with 3+ tips (potential overlap):")
for key, items in sorted(svc_cat_groups.items(), key=lambda x: -len(x[1])):
    if len(items) >= 3:
        titles = [get_val(i, 'title')[:60] for i in items]
        print(f"  {key} ({len(items)} tips):")
        for t in titles:
            print(f"    - {t}")

# ========================================
# 2. CONTRADICTING TIPS
# ========================================
print("\n" + "=" * 80)
print("2. POTENTIALLY CONTRADICTING TIPS")
print("=" * 80)

# Check for tips that recommend opposite strategies for same service
contradictions = []
for item in data:
    title = get_val(item, 'title').lower()
    desc = get_val(item, 'description').lower()
    svc = get_val(item, 'service')
    cat = get_val(item, 'category')
    
    # Check for reserved vs spot/on-demand contradictions
    if 'reserved' in title or 'commitment' in cat:
        # Find tips for same service that recommend spot/on-demand
        for other in data:
            if other is item:
                continue
            other_svc = get_val(other, 'service')
            other_title = get_val(other, 'title').lower()
            if other_svc == svc and ('spot' in other_title or 'on-demand' in other_title or 'serverless' in other_title):
                contradictions.append((
                    f"[{svc}] {get_val(item, 'title')}",
                    f"[{other_svc}] {get_val(other, 'title')}",
                    "Reserved vs Spot/Serverless"
                ))

# Deduplicate contradictions (A vs B = B vs A)
seen = set()
unique_contradictions = []
for a, b, reason in contradictions:
    key = tuple(sorted([a, b]))
    if key not in seen:
        seen.add(key)
        unique_contradictions.append((a, b, reason))

print(f"\nPotential contradictions found: {len(unique_contradictions)}")
for a, b, reason in unique_contradictions[:10]:
    print(f"  Conflict type: {reason}")
    print(f"    Tip A: {a}")
    print(f"    Tip B: {b}")
    print()

# ========================================
# 3. DRILL-DOWN INSTRUCTIONS CHECK
# ========================================
print("=" * 80)
print("3. TIPS WITH DRILL-DOWN / ANALYSIS INSTRUCTIONS")
print("=" * 80)

drill_keywords = ['go to', 'navigate', 'click', 'use the', 'run', 'check', 'open', 'view', 'scan']
has_drilldown = 0
no_drilldown = 0
drilldown_examples = []
no_drilldown_examples = []

for item in data:
    desc = get_val(item, 'description').lower()
    title = get_val(item, 'title')
    has_action = any(kw in desc for kw in drill_keywords)
    
    if has_action:
        has_drilldown += 1
        if len(drilldown_examples) < 3:
            drilldown_examples.append((title, get_val(item, 'description')[:150]))
    else:
        no_drilldown += 1
        if len(no_drilldown_examples) < 5:
            no_drilldown_examples.append((title, get_val(item, 'description')[:150]))

print(f"\nTips WITH drill-down/action instructions: {has_drilldown}/{len(data)} ({has_drilldown*100//len(data)}%)")
print(f"Tips WITHOUT drill-down instructions: {no_drilldown}/{len(data)} ({no_drilldown*100//len(data)}%)")

print(f"\nExamples WITH drill-down:")
for title, desc in drilldown_examples:
    print(f"  [{title}]: {desc}...")

print(f"\nExamples WITHOUT drill-down (just descriptions, no action path):")
for title, desc in no_drilldown_examples:
    print(f"  [{title}]: {desc}...")

# ========================================
# 4. SLASHMYBILL NAVIGATION REFERENCES
# ========================================
print("\n" + "=" * 80)
print("4. TIPS REFERENCING SLASHMYBILL PLATFORM NAVIGATION")
print("=" * 80)

platform_refs = ['slashmybill', 'act >', 'plan >', 'configure >', 'observe >', 'waste cleanup', 'scheduler', 'tag resources']
has_platform_ref = 0
for item in data:
    desc = get_val(item, 'description').lower()
    if any(ref in desc for ref in platform_refs):
        has_platform_ref += 1

print(f"Tips referencing SlashMyBill platform features: {has_platform_ref}/{len(data)} ({has_platform_ref*100//len(data)}%)")
print(f"Tips with NO platform navigation: {len(data) - has_platform_ref}/{len(data)}")

# ========================================
# 5. implementedInAct vs actionLabel analysis
# ========================================
print("\n" + "=" * 80)
print("5. ACTION IMPLEMENTATION STATUS")
print("=" * 80)

implemented = sum(1 for i in data if get_val(i, 'implementedInAct') == 'True' or get_val(i, 'implementedInAct') == True)
coming_soon = sum(1 for i in data if 'coming soon' in get_val(i, 'actionLabel').lower())
has_action_label = sum(1 for i in data if get_val(i, 'actionLabel') and get_val(i, 'actionLabel') != '{}')

print(f"implementedInAct=True: {implemented}/{len(data)}")
print(f"actionLabel='Coming Soon': {coming_soon}/{len(data)}")
print(f"Has any actionLabel: {has_action_label}/{len(data)}")

# Show actionLabel values
action_labels = defaultdict(int)
for item in data:
    label = get_val(item, 'actionLabel')
    if label and label != '{}':
        action_labels[label] += 1
print(f"\nAction label distribution:")
for label, count in sorted(action_labels.items(), key=lambda x: -x[1]):
    print(f"  {label}: {count}")

# ========================================
# 6. DESCRIPTION LENGTH ANALYSIS
# ========================================
print("\n" + "=" * 80)
print("6. DESCRIPTION QUALITY (LENGTH)")
print("=" * 80)

lengths = [len(get_val(i, 'description')) for i in data]
lengths.sort()
print(f"Shortest: {lengths[0]} chars")
print(f"Longest: {lengths[-1]} chars")
print(f"Median: {lengths[len(lengths)//2]} chars")
print(f"Average: {sum(lengths)//len(lengths)} chars")
short_tips = [(get_val(i, 'title'), len(get_val(i, 'description'))) for i in data if len(get_val(i, 'description')) < 80]
print(f"\nTips with very short descriptions (<80 chars): {len(short_tips)}")
for title, length in short_tips[:5]:
    print(f"  {title} ({length} chars)")
