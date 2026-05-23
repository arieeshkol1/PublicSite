#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Replace Spot Migration panel with Optimize a Cluster wizard."""

with open('members/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_panel_start = '                            <!-- Spot Migration Panel -->'
old_panel_end = '                            <!-- Resize Server Card -->'

start_idx = content.find(old_panel_start)
end_idx = content.find(old_panel_end)

if start_idx == -1 or end_idx == -1:
    print("ERROR: Could not find panel boundaries")
    exit(1)

new_panel = '''                            <!-- Optimize a Cluster -->
                            <div style="background:linear-gradient(135deg,#eef2ff,#e0e7ff);border:1px solid #c7d2fe;border-radius:12px;padding:20px;margin-bottom:20px;">
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
                                    <span style="font-size:1.5em;">&#9889;</span>
                                    <div>
                                        <div style="font-weight:700;color:#1f2937;font-size:1.05em;">Optimize a Cluster</div>
                                        <div style="color:#6b7280;font-size:0.85em;">Analyze your Auto Scaling Group for HA, Spot mix, scaling policies, and cost optimization</div>
                                    </div>
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
                                    <div>
                                        <label style="font-size:0.8em;color:#6b7280;">Account</label>
                                        <select id="cluster-account" style="width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.85em;" onchange="_clusterLoadASGs()">
                                            <option value="">Select account...</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style="font-size:0.8em;color:#6b7280;">Auto Scaling Group</label>
                                        <select id="cluster-asg" style="width:100%;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.85em;">
                                            <option value="">Select ASG...</option>
                                        </select>
                                    </div>
                                </div>
                                <button class="btn btn-primary btn-sm" onclick="_clusterAnalyze()">&#128270; Analyze Cluster</button>
                                <div id="cluster-report" style="margin-top:16px;"></div>
                                <div id="cluster-status" style="color:#6b7280;font-size:0.85em;margin-top:8px;"></div>
                            </div>

'''

content = content[:start_idx] + new_panel + content[end_idx:]

# Bump version
content = content.replace("members.js?v=78", "members.js?v=79")

with open('members/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML: Optimize a Cluster panel added")
