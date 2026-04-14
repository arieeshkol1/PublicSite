import re
content = open('members/index.html', 'r', encoding='utf-8').read()
tabs = re.findall(r'data-tab="[^"]+"', content)
print('All tabs found:', tabs)
print('Total length:', len(content))
lines = content.split('\n')
print('Lines:', len(lines))

# Find all tab content divs
tab_divs = re.findall(r'id="[^"]*-tab[^"]*"', content)
print('Tab divs:', tab_divs)

# Show the tabs section
idx = content.find('member-tabs')
print('\nTabs section:')
print(content[idx:idx+600])
