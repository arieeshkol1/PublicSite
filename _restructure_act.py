#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove Server Clusters section, move Resize to Optimize, rename Spot panel."""

with open('members/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove Server Clusters nav button
content = content.replace(
    '''                        <button class="act-nav-btn" data-section="clusters" onclick="_switchActSection('clusters')">
                            <span style="font-size:1.2em;">\U0001f5a5\ufe0f</span> Server Clusters
                        </button>''',
    ''
)
print("1. Server Clusters nav button removed")

# 2. Rename Spot Migration panel title in Optimize section
content = content.replace(
    '<div style="font-weight:700;color:#1f2937;font-size:1.05em;">Spot Instance Migration</div>',
    '<div style="font-weight:700;color:#1f2937;font-size:1.05em;">Optimize Auto Scaling Group using Spot Instances</div>'
)
content = content.replace(
    '<div style="color:#6b7280;font-size:0.85em;">Migrate ASGs to use Spot Instances with price-capacity-optimized strategy (up to 90% savings)</div>',
    '<div style="color:#6b7280;font-size:0.85em;">Convert ASGs to use Spot Instances with price-capacity-optimized strategy (up to 90% savings)</div>'
)
print("2. Spot panel renamed")

# 3. Add Resize Server card into Optimize section (before the scan status)
resize_card = '''
                            <!-- Resize Server Card -->
                            <div style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);border:1px solid #bbf7d0;border-radius:12px;padding:20px;margin-bottom:20px;">
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
                                    <span style="font-size:1.5em;">&#128202;</span>
                                    <div>
                                        <div style="font-weight:700;color:#1f2937;font-size:1.05em;">Resize a Server</div>
                                        <div style="color:#6b7280;font-size:0.85em;">Analyze usage, find cheaper instance types, and resize with one click</div>
                                    </div>
                                </div>
                                <div id="resize-step-1-opt">
                                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
                                        <div>
                                            <label style="font-size:0.8em;color:#6b7280;">Account</label>
                                            <select id="resize-account" style="width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.85em;" onchange="_resizeLoadInstances()">
                                                <option value="">Select account...</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label style="font-size:0.8em;color:#6b7280;">Instance</label>
                                            <select id="resize-instance" style="width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.85em;">
                                                <option value="">Select instance...</option>
                                            </select>
                                        </div>
                                    </div>
                                    <button class="btn btn-primary btn-sm" onclick="_resizeAnalyze()">&#128270; Analyze Usage</button>
                                </div>
                                <div id="resize-step-2" style="display:none;margin-top:16px;">
                                    <div id="resize-analysis" style="margin-bottom:16px;"></div>
                                    <div id="resize-recommendations" style="margin-bottom:16px;"></div>
                                </div>
                                <div id="resize-step-4" style="display:none;margin-top:12px;">
                                    <div id="resize-progress"></div>
                                </div>
                                <div id="resize-status" style="color:#6b7280;font-size:0.85em;margin-top:8px;"></div>
                            </div>

'''

# Insert before the scan status div in Optimize section
old_scan_status = '                            <div id="act-optimize-status"'
content = content.replace(old_scan_status, resize_card + old_scan_status)
print("3. Resize card added to Optimize section")

# 4. Remove the entire Server Clusters section
start_marker = '                        <!-- Server Clusters Section -->'
end_marker = '                        <!-- Schedule Create Wizard Modal -->'
start_idx = content.find(start_marker)
end_idx = content.find(end_marker)
if start_idx > 0 and end_idx > start_idx:
    content = content[:start_idx] + content[end_idx:]
    print("4. Server Clusters section removed")
else:
    print("4. WARNING: Could not find Server Clusters section boundaries")

# 5. Bump JS version
content = content.replace("members.js?v=74", "members.js?v=75")

with open('members/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
