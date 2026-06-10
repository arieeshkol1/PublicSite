import gzip, json, os

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

# Check for ai-generated tips (these are user-specific saved tips)
ai_tips = [i for i in data if i.get('category', {}).get('S', '') == 'ai-generated']
print(f"=== AI-Generated Tips (user-specific): {len(ai_tips)} ===")
for t in ai_tips[:5]:
    title = t.get('title', {}).get('S', '')
    desc = t.get('description', {}).get('S', '')[:200]
    svc = t.get('service', {}).get('S', '')
    print(f"  Service: {svc}")
    print(f"  Title: {title}")
    print(f"  Desc: {desc}...")
    print()

# Check for fixed-cost category tips
fixed_tips = [i for i in data if i.get('category', {}).get('S', '') == 'fixed-cost']
print(f"\n=== Fixed-Cost Tips: {len(fixed_tips)} ===")
for t in fixed_tips[:3]:
    title = t.get('title', {}).get('S', '')
    svc = t.get('service', {}).get('S', '')
    print(f"  {svc}: {title}")

# Check for budgets/anomaly category
budget_tips = [i for i in data if i.get('category', {}).get('S', '') in ('budgets', 'anomaly', 'finops-settings')]
print(f"\n=== Budget/Anomaly/FinOps Tips: {len(budget_tips)} ===")
for t in budget_tips:
    title = t.get('title', {}).get('S', '')
    cat = t.get('category', {}).get('S', '')
    cloud = t.get('cloud', {}).get('S', '')
    print(f"  [{cloud}] [{cat}] {title}")

# Check what AWS-specific services have tips
aws_tips = [i for i in data if i.get('cloud', {}).get('S', '') == 'AWS']
aws_services = set(t.get('service', {}).get('S', '') for t in aws_tips)
print(f"\n=== AWS Services with Tips ({len(aws_services)}): ===")
print(sorted(aws_services))

# Check for Support-related tips (relevant to the first-of-month spike)
support_tips = [i for i in data if 'support' in json.dumps(i, default=str).lower() and 'plan' in json.dumps(i, default=str).lower()]
print(f"\n=== Support Plan Tips: {len(support_tips)} ===")
for t in support_tips[:3]:
    title = t.get('title', {}).get('S', '')
    svc = t.get('service', {}).get('S', '')
    cat = t.get('category', {}).get('S', '')
    print(f"  [{cat}] {svc}: {title}")

# Check for providerRouting field
has_pr = [i for i in data if 'providerRouting' in i]
print(f"\n=== Items with providerRouting: {len(has_pr)} ===")

# Check confidence tags
conf_items = [i for i in data if 'confidenceTag' in i or 'confidence' in i]
print(f"\n=== Items with confidence/confidenceTag: {len(conf_items)} ===")
for c in conf_items[:3]:
    title = c.get('title', {}).get('S', '')
    conf = c.get('confidenceTag', c.get('confidence', {}))
    if isinstance(conf, dict):
        conf = conf.get('S', str(conf))
    print(f"  {title} -> confidence: {conf}")
