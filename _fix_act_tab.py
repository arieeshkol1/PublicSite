import re

content = open('members/index.html', 'r', encoding='utf-8').read()

# ── 1. Reorder tab buttons: Observe → Chat → Act → Configure ──────────────
old_buttons = '<button class="member-tab" data-tab="accounts-tab">Configure</button>\n                <button class="member-tab" data-tab="act-tab">Act</button>'
new_buttons = '<button class="member-tab" data-tab="act-tab">Act</button>\n                <button class="member-tab" data-tab="accounts-tab">Configure</button>'

if old_buttons in content:
    content = content.replace(old_buttons, new_buttons)
    print('Tab order fixed')
else:
    print('WARNING: tab button order not found as expected')

# ── 2. Replace Hello World placeholder with full Act tab content ──────────
old_act = '<div id="act-tab" class="member-tab-content" hidden>\n                <div style="padding:40px;color:#e6edf3;font-size:1.1em;">Hello World</div>\n            </div>'

new_act = '''<div id="act-tab" class="member-tab-content" hidden>
                <div class="tab-toolbar">
                    <h2>Act <span style="font-size:0.65em;color:#6b7280;font-weight:400;">Level 1 — Resource Hygiene</span></h2>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <select id="act-account-select" class="form-input" style="min-width:160px;padding:6px 10px;font-size:0.85em;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;">
                            <option value="">All Connected Accounts</option>
                        </select>
                        <button id="act-scan-btn" class="btn btn-primary btn-sm">&#128269; Scan for Waste</button>
                    </div>
                </div>
                <div id="act-scan-status" style="padding:0 0 12px;color:#6b7280;font-size:0.85em;min-height:20px;"></div>
                <div id="act-total-savings" style="display:none;background:linear-gradient(135deg,#064e3b,#065f46);border-radius:10px;padding:14px 20px;margin-bottom:16px;display:flex;align-items:center;gap:12px;">
                    <span style="font-size:1.8em;">&#128176;</span>
                    <div><div style="color:#6ee7b7;font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;">Total Potential Monthly Savings</div><div id="act-total-savings-amount" style="color:#fff;font-size:1.6em;font-weight:700;"></div></div>
                </div>
                <div id="act-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding-bottom:32px;"></div>
                <div id="act-empty" style="text-align:center;padding:60px 20px;color:#6b7280;">
                    <div style="font-size:2.5em;margin-bottom:12px;">&#129529;</div>
                    <div style="font-size:1em;margin-bottom:6px;color:#c9d1d9;">Click "Scan for Waste" to identify idle resources</div>
                    <div style="font-size:0.85em;">Scans for unassociated Elastic IPs, unattached EBS volumes,<br>idle Load Balancers, and S3 buckets without lifecycle rules.</div>
                </div>
                <!-- Confirm Execute Dialog -->
                <div id="act-confirm-dialog" class="modal-overlay" hidden>
                    <div class="modal-card modal-card-sm" style="max-width:480px;">
                        <h3 id="act-confirm-title" style="margin-top:0;color:#e6edf3;"></h3>
                        <p id="act-confirm-body" style="color:#8b949e;font-size:0.9em;"></p>
                        <div id="act-confirm-resources" style="background:#161b22;border-radius:6px;padding:10px;margin-bottom:16px;max-height:160px;overflow-y:auto;font-size:0.82em;color:#c9d1d9;"></div>
                        <div style="background:#7f1d1d;border:1px solid #ef4444;border-radius:6px;padding:10px;margin-bottom:16px;font-size:0.82em;color:#fca5a5;">
                            &#9888; This action is <strong>irreversible</strong>. A JIT safety check will run before each deletion.
                        </div>
                        <div style="display:flex;gap:8px;justify-content:flex-end;">
                            <button onclick="document.getElementById('act-confirm-dialog').hidden=true;" class="btn btn-outline">Cancel</button>
                            <button id="act-confirm-execute-btn" class="btn btn-primary" style="background:#dc2626;border-color:#dc2626;">&#9889; Execute Cleanup</button>
                        </div>
                    </div>
                </div>
            </div>'''

if old_act in content:
    content = content.replace(old_act, new_act)
    print('Act tab content replaced')
else:
    print('WARNING: act tab placeholder not found as expected')
    idx = content.find('act-tab')
    print(repr(content[idx:idx+200]))

# ── 3. Bump cache version ─────────────────────────────────────────────────
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1))
    new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache bumped v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('Done')
