content = open('members/index.html', 'r', encoding='utf-8').read()
idx = content.find('id="ai-tab"')
print(repr(content[idx:idx+800]))
