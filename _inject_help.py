import re
content = open('members/index.html', 'r', encoding='utf-8').read()

# Add help.js script tag before closing </body>
old = '</body>'
new = '    <script src="help.js?v=1"></script>\n</body>'
if old in content:
    content = content.replace(old, new, 1)
    print('help.js script tag added')
else:
    print('ERROR: </body> not found')

# Bump cache version
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('Done')
