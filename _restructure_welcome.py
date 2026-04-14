content = open('members/index.html', 'r', encoding='utf-8').read()

# Remove the floating widget we added above ai-chat in Phase 2
old_floating = '''<div id="ai-findings-widget" style="margin:0 0 0 0;display:none;">
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

new_no_floating = '<div id="ai-chat" class="lab-chat">'

if old_floating in content:
    content = content.replace(old_floating, new_no_floating)
    print('Floating widget removed')
else:
    print('WARNING: floating widget not found (may already be removed)')

# Replace the welcome screen with the new integrated layout
old_welcome = '''<div class="lab-welcome">
                        <div class="lab-welcome" style="text-align:left;padding:20px;">
                            <h3 style="color:#c9d1d9;font-size:22px;">Hi - We are here to help you slash your Bill</h3>
                            <div class="lab-examples" style="text-align:left;max-width:100%;margin:0;">

                                <p>Try asking:</p>
                                <code>How efficient is my account?</code>
                                <code>Where can I save money?</code>
                                <code>Compare my costs over the last 3 months</code>
                                <code>What services am I paying for that I don\'t need?</code>
                                <code>Show me my cost breakdown by service</code>
                                <code>Are there any cost anomalies?</code>
                            </div>
                        </div>
                    </div>'''

new_welcome = '''<div class="lab-welcome" id="ai-welcome-screen">
                        <div style="text-align:left;padding:20px 20px 12px;">
                            <h3 style="color:#c9d1d9;font-size:22px;margin-bottom:16px;">Hi - We are here to help you slash your Bill</h3>

                            <!-- Scan button -->
                            <div style="margin-bottom:16px;">
                                <button onclick="_runScanFromChat();" id="ai-scan-btn" class="btn btn-primary btn-sm" style="font-size:0.9em;">
                                    🔍 Scan for Savings Opportunities
                                </button>
                                <span id="ai-findings-ts" style="color:#6b7280;font-size:0.78em;margin-left:10px;"></span>
                            </div>

                            <!-- Findings section (populated after scan) -->
                            <div id="ai-findings-widget" style="display:none;margin-bottom:16px;">
                                <div style="color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">
                                    💡 Top Findings
                                    <span id="ai-findings-badge" style="background:#dc2626;color:#fff;font-size:0.7em;padding:1px 6px;border-radius:10px;margin-left:6px;display:none;"></span>
                                    <span id="ai-findings-title" style="color:#6b7280;font-weight:400;text-transform:none;letter-spacing:0;margin-left:6px;"></span>
                                </div>
                                <div id="ai-findings-list"></div>
                            </div>

                            <!-- General questions -->
                            <div class="lab-examples" style="text-align:left;max-width:100%;margin:0;">
                                <p style="color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Try asking:</p>
                                <code>How efficient is my account?</code>
                                <code>Where can I save money?</code>
                                <code>Compare my costs over the last 3 months</code>
                                <code>What services am I paying for that I don\'t need?</code>
                                <code>Show me my cost breakdown by service</code>
                                <code>Are there any cost anomalies?</code>
                            </div>
                        </div>
                    </div>'''

if old_welcome in content:
    content = content.replace(old_welcome, new_welcome)
    print('Welcome screen restructured')
else:
    print('WARNING: welcome screen not found exactly')
    idx = content.find('lab-welcome')
    print(repr(content[idx:idx+300]))

import re
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('Done')
