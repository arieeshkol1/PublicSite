import re

with open('admin/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Find all img tags
imgs = re.findall(r'<img[^>]+>', html)
print("Images found:")
for img in imgs:
    print(" ", img[:120])

# Find eshkolai references
for match in re.finditer(r'eshkolai', html, re.IGNORECASE):
    start = max(0, match.start() - 40)
    end = min(len(html), match.end() + 40)
    print(f"\neshkolai ref at {match.start()}: ...{repr(html[start:end])}...")

# Find logo/branding text
for term in ['Admin Panel', 'Eshkol', 'Cloud and AI', 'logo']:
    idx = html.find(term)
    if idx > 0:
        print(f"\n'{term}' at {idx}: ...{repr(html[max(0,idx-30):idx+50])}...")
