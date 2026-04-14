with open('admin/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace all eshkolai.png with SlashMyBill.png
html = html.replace('../eshkolai.png', '../SlashMyBill.png')

# Replace alt text
html = html.replace('alt="Eshkol Logo"', 'alt="SlashMyCloudBill Logo"')

# Replace title
html = html.replace('Admin Panel - Cloud and AI', 'Admin Panel - SlashMyCloudBill')

# Replace any "Eshkol AI" or "Cloud and AI" branding text
html = html.replace('Cloud and AI', 'SlashMyCloudBill')

count = html.count('SlashMyBill.png')
print(f"SlashMyBill.png references: {count}")
print(f"eshkolai remaining: {html.count('eshkolai')}")

with open('admin/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Admin panel logo updated")
