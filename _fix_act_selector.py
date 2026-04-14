content = open('members/index.html', 'r', encoding='utf-8').read()

# Replace the <select> with a <div> container matching dash/AI pattern
old = '<select id="act-account-select" class="form-input" style="min-width:160px;padding:6px 10px;font-size:0.85em;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;">\n                            <option value="">All Connected Accounts</option>\n                        </select>'
new = '<div id="act-account-select" style="display:inline-block;"></div>'

if old in content:
    content = content.replace(old, new)
    print('Selector replaced')
else:
    print('NOT FOUND - trying alternate search')
    idx = content.find('act-account-select')
    print(repr(content[idx-20:idx+300]))

import re
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('Done')
