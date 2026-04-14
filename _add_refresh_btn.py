import re
content = open('members/index.html', 'r', encoding='utf-8').read()

old = '<button id="ai-font-dec" class="btn btn-outline btn-sm" type="button">A-</button>\n                            <button id="ai-font-inc" class="btn btn-outline btn-sm" type="button">A+</button>'

new = '<button id="ai-font-dec" class="btn btn-outline btn-sm" type="button">A-</button>\n                            <button id="ai-font-inc" class="btn btn-outline btn-sm" type="button">A+</button>\n                            <button id="ai-refresh-findings-btn" class="btn btn-outline btn-sm" type="button" title="Refresh savings findings" style="margin-left:8px;">&#8635; Refresh Findings</button>'

if old in content:
    content = content.replace(old, new)
    print('Refresh button added')
else:
    print('ERROR: pattern not found')

m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
