import re

with open('members/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Remove the SlashMyBill link button from header
# Pattern: <a href="...slashMyBill..." ...>SlashMyBill</a>
pattern = r'<a[^>]*href=["\'][^"\']*slashMyBill[^"\']*["\'][^>]*>Slash\s*My\s*Bill</a>\s*'
new_html, count = re.subn(pattern, '', html)
print(f"Removed {count} SlashMyBill button(s)")

if count > 0:
    with open('members/index.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
    print("File saved")
else:
    # Try simpler search
    idx = html.find('SlashMyBill</a>')
    if idx > 0:
        start = html.rfind('<a', max(0, idx-200), idx)
        end = idx + len('SlashMyBill</a>')
        print(f"Found at {start}-{end}: {repr(html[start:end])}")
