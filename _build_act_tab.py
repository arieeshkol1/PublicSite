content = open('members/index.html', 'r', encoding='utf-8').read()

old = '<div id="act-tab" class="member-tab-content" hidden>\n                <div style="padding:40px;color:#e6edf3;font-size:1.1em;">Hello World</div>\n            </div>'

new = '''<div id="act-tab" class="member-tab-content" hidden>
                <div class="tab-toolbar">
                    <h2>Act <span style="font-size:0.65em;color:#6b7280;font-weight:400;">Level 1 — Resource Hygiene</span></h2>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <select id="act-account-select" class="form-input" style="min-width:160px;padding:6px 10px;font-size:0.85em;">
                            <option value="">All Connected Accounts</option>
                        </select>
                        <button id="act-scan-btn" class="btn btn-primary btn-sm">🔍 Scan for Waste</button>
                    </div>
                </div>
                <div id="act-scan-status" style="padding:0 0 12px;color:#6b7280;font-size:0.85em;"></div>
                <div id="act-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding-bottom:32px;"></div>
                <div id="act-empty" style="text-align:center;padding:60px 20px;color:#6b7280;">
                    <div style="font-size:2.5em;margin-bottom:12px;">🧹</div>
                    <div style="font-size:1em;margin-bottom:6px;">Click "Scan for Waste" to identify idle resources</div>
                    <div style="font-size:0.85em;">Scans for unassociated Elastic IPs, unattached EBS volumes, idle Load Balancers, and S3 buckets without lifecycle rules.</div>
                </div>
            </div>'''

if old in content:
    content = content.replace(old, new)
    open('members/index.html', 'w', encoding='utf-8').write(content)
    print('SUCCESS')
else:
    print('NOT FOUND')
    idx = content.find('act-tab')
    print(repr(content[idx:idx+300]))
