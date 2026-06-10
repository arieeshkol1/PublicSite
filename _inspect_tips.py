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
                    # DynamoDB export format has {"Item": {...}}
                    if 'Item' in item:
                        data.append(item['Item'])
                    else:
                        data.append(item)

print(f"Total items: {len(data)}")
if data:
    print(f"\nKeys in first item: {list(data[0].keys())}")
    print(f"\nFirst item sample:")
    print(json.dumps(data[0], indent=2, default=str)[:3000])
    
    # Check for tip categories/types
    categories = set()
    services = set()
    clouds = set()
    has_confidence = 0
    has_provider_routing = 0
    for item in data:
        # Handle DynamoDB format (with S, N, etc type indicators)
        if 'category' in item:
            cat = item['category']
            categories.add(cat.get('S', cat) if isinstance(cat, dict) else cat)
        if 'service' in item:
            svc = item['service']
            services.add(svc.get('S', svc) if isinstance(svc, dict) else svc)
        if 'cloud' in item:
            cl = item['cloud']
            clouds.add(cl.get('S', cl) if isinstance(cl, dict) else cl)
        if 'confidence' in item or 'confidenceTag' in item:
            has_confidence += 1
        if 'providerRouting' in item:
            has_provider_routing += 1
    
    print(f"\n--- Statistics ---")
    print(f"Categories: {sorted(categories)}")
    print(f"Services ({len(services)}): {sorted(list(services))[:20]}...")
    print(f"Clouds: {sorted(clouds)}")
    print(f"Items with confidence: {has_confidence}/{len(data)}")
    print(f"Items with providerRouting: {has_provider_routing}/{len(data)}")
    
    # Check for forecast-related tips
    forecast_tips = [i for i in data if any(
        kw in json.dumps(i, default=str).lower() 
        for kw in ['forecast', 'predict', 'projection', 'budget alert', 'anomaly detection']
    )]
    print(f"\nForecast/prediction related tips: {len(forecast_tips)}")
    for t in forecast_tips[:5]:
        title = t.get('title', t.get('tipId', ''))
        if isinstance(title, dict):
            title = title.get('S', str(title))
        print(f"  - {title}")
