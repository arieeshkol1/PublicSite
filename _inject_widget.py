content = open('members/index.html', 'r', encoding='utf-8').read()

# Insert the Top Findings widget between lab-header and ai-chat
old = '<div id="ai-chat" class="lab-chat">'

new = '''<div id="ai-findings-widget" style="margin:0 0 0 0;display:none;">
                        <div id="ai-findings-inner" style="background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:10px;overflow:hidden;">
                            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:1px solid #21262d;cursor:pointer;" onclick="_toggleFindingsWidget()">
                                <div style="display:flex;align-items:center;gap:8px;">
                                    <span style="font-size:1em;">💡</span>
                                    <span id="ai-findings-title" style="color:#c9d1d9;font-size:0.85em;font-weight:600;">Top Findings</span>
                                    <span id="ai-findings-badge" style="background:#dc2626;color:#fff;font-size:0.7em;padding:1px 6px;border-radius:10px;display:none;"></span>
                                </div>
                                <div style="display:flex;gap:8px;align-items:center;">
                                    <span id="ai-findings-ts" style="color:#6b7280;font-size:0.75em;"></span>
                                    <button onclick="event.stopPropagation();_runScanFromChat();" style="background:none;border:1px solid #30363d;color:#6366f1;border-radius:4px;padding:2px 8px;font-size:0.75em;cursor:pointer;">↻ Rescan</button>
                                    <button onclick="event.stopPropagation();document.querySelector('[data-tab=act-tab]').click();" style="background:none;border:1px solid #30363d;color:#8b949e;border-radius:4px;padding:2px 8px;font-size:0.75em;cursor:pointer;">Act ▶</button>
                                    <span id="ai-findings-chevron" style="color:#6b7280;font-size:0.8em;">▼</span>
                                </div>
                            </div>
                            <div id="ai-findings-list" style="padding:0;"></div>
                        </div>
                    </div>
                    <div id="ai-chat" class="lab-chat">'''

if old in content:
    content = content.replace(old, new, 1)
    print('Widget injected OK')
else:
    print('ERROR: marker not found')

import re
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
