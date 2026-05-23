#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2: Add Server Clusters section to Act tab with Resize wizard."""

with open('members/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove Spot Mgmt from Configure tab nav
content = content.replace(
    '''                        <button class="act-nav-btn" data-section="spot" onclick="_switchConfigSection('spot')">
                            <span style="font-size:1.2em;">\u26a1</span> Spot Mgmt
                        </button>''',
    '<!-- Spot Mgmt moved to Act > Server Clusters -->'
)

# 2. Add Server Clusters nav button to Act tab (after Scheduler)
old_sched_btn = '''                        <button class="act-nav-btn" data-section="scheduler" onclick="_switchActSection('scheduler')">
                            <span style="font-size:1.2em;">\u23f0</span> Scheduler
                        </button>'''
new_sched_btn = old_sched_btn + '''
                        <button class="act-nav-btn" data-section="clusters" onclick="_switchActSection('clusters')">
                            <span style="font-size:1.2em;">\U0001f5a5\ufe0f</span> Server Clusters
                        </button>'''
content = content.replace(old_sched_btn, new_sched_btn)

# 3. Add Server Clusters section HTML (before the Scheduler section closing)
clusters_html = '''
                        <!-- Server Clusters Section -->
                        <div id="act-section-clusters" style="display:none;">
                            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
                                <h2 style="margin:0;color:#1f2937;">Server Clusters</h2>
                            </div>
                            <p style="color:#6b7280;font-size:0.9em;margin-bottom:20px;">Resize servers, migrate to clusters, and optimize compute capacity.</p>

                            <!-- Resize Server Card -->
                            <div style="background:linear-gradient(135deg,#eef2ff,#e0e7ff);border:1px solid #c7d2fe;border-radius:12px;padding:20px;margin-bottom:20px;">
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
                                    <span style="font-size:1.5em;">&#128202;</span>
                                    <div>
                                        <div style="font-weight:700;color:#1f2937;font-size:1.05em;">Resize a Server</div>
                                        <div style="color:#6b7280;font-size:0.85em;">Analyze usage, find cheaper instance types, and resize with one click</div>
                                    </div>
                                </div>

                                <!-- Step 1: Select Instance -->
                                <div id="resize-step-1">
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

                                <!-- Step 2+3: Analysis Results + Recommendations -->
                                <div id="resize-step-2" style="display:none;margin-top:16px;">
                                    <div id="resize-analysis" style="margin-bottom:16px;"></div>
                                    <div id="resize-recommendations" style="margin-bottom:16px;"></div>
                                </div>

                                <!-- Step 4: Execute -->
                                <div id="resize-step-4" style="display:none;margin-top:12px;">
                                    <div id="resize-progress"></div>
                                </div>

                                <div id="resize-status" style="color:#6b7280;font-size:0.85em;margin-top:8px;"></div>
                            </div>

                            <!-- Spot Migration Card (moved from Optimize) -->
                            <div id="spot-migrate-panel-clusters" style="background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px;">
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                                    <span style="font-size:1.3em;">&#9889;</span>
                                    <div style="font-weight:600;color:#1f2937;">Spot Instance Migration</div>
                                </div>
                                <p style="color:#6b7280;font-size:0.85em;">Migrate ASGs to use Spot Instances. Available in Act &#8594; Optimize section.</p>
                            </div>
                        </div>
'''

# Insert before the Schedule Create Wizard Modal
old_wizard = '                        <!-- Schedule Create Wizard Modal -->'
content = content.replace(old_wizard, clusters_html + old_wizard)

# 4. Bump JS version
content = content.replace("members.js?v=72", "members.js?v=73")

with open('members/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Step 2: HTML updated - Server Clusters section added to Act tab")
