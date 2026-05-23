#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 6a: Add Spot HTML sections to members/index.html."""

with open('members/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

if 'config-section-spot' in content:
    print("Step 6a HTML already present -- skipping")
else:
    # 1. Add Spot nav button to Configure tab
    old_tag_btn = '''                        <button class="act-nav-btn" data-section="tag-policy" onclick="_switchConfigSection('tag-policy')">
                            <span style="font-size:1.2em;">\U0001f3f7\ufe0f</span> Tag Policy
                        </button>
                    </div>'''
    new_tag_btn = '''                        <button class="act-nav-btn" data-section="tag-policy" onclick="_switchConfigSection('tag-policy')">
                            <span style="font-size:1.2em;">\U0001f3f7\ufe0f</span> Tag Policy
                        </button>
                        <button class="act-nav-btn" data-section="spot" onclick="_switchConfigSection('spot')">
                            <span style="font-size:1.2em;">\u26a1</span> Spot Mgmt
                        </button>
                    </div>'''
    content = content.replace(old_tag_btn, new_tag_btn)

    # 2. Find the end of tag-policy section and add Spot config section after it
    # Look for the closing div of tag-policy section
    tag_policy_marker = 'id="config-section-tag-policy"'
    if tag_policy_marker in content:
        # Find the section and add Spot section after the tag-policy closing
        spot_config_html = '''
                        <!-- Spot Management Sub-Section -->
                        <div id="config-section-spot" style="display:none;">
                            <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
                                <h2 style="margin:0;color:#1f2937;">Spot Instance Management</h2>
                            </div>
                            <p style="color:#6b7280;font-size:0.9em;margin-bottom:16px;">Enable Spot orchestration per account. SlashMyBill will manage ASG capacity mix and send real-time interruption notifications.</p>
                            <div style="margin-bottom:16px;">
                                <label style="font-size:0.85em;color:#6b7280;">Account</label>
                                <select id="spot-account-select" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.9em;" onchange="_loadSpotConfig()"></select>
                            </div>
                            <div id="spot-config-panel" style="display:none;">
                                <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;padding:12px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;">
                                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                                        <input type="checkbox" id="spot-enabled-toggle" onchange="_toggleSpotEnabled()">
                                        <span style="font-weight:600;">Enable Spot Management</span>
                                    </label>
                                </div>
                                <div id="spot-qualify-results" style="margin-bottom:16px;"></div>
                                <button id="spot-qualify-btn" class="btn btn-outline btn-sm" onclick="_runSpotQualify()" style="margin-bottom:16px;">Scan ASGs</button>
                                <div id="spot-config-status" style="color:#6b7280;font-size:0.85em;"></div>
                            </div>
                            <div id="spot-config-empty" style="text-align:center;padding:40px;color:#6b7280;">
                                <div style="font-size:2em;margin-bottom:8px;">&#9889;</div>
                                <div>Select a connected account to configure Spot management</div>
                            </div>
                        </div>
'''
        # Insert after the tag-policy section's last element before the closing content div
        # Find the Scheduler section in Act tab to know we're in the right place
        # Actually, let's insert right before the closing of the config content area
        # The tag-policy section ends, then the content div closes, then the config tab closes
        # Let's find the pattern: end of tag-policy section
        import re
        # Find config-section-tag-policy div and its content, then insert after
        # Simpler: insert before the closing of the right content area
        # The structure is: config-section-accounts, config-section-finops-settings, config-section-tag-policy, then </div> (content), </div> (flex), </div> (tab)
        # Let's insert the spot section right after the tag-policy section
        # Find the last occurrence of a config section and add after it
        
        # Strategy: find the tag-policy section start, then find its matching end
        # Easier: just insert before the accounts-tab closing
        old_close = '''                        <!-- Tag Policy Sub-Section -->
                        <div id="config-section-tag-policy"'''
        new_close = spot_config_html + '''                        <!-- Tag Policy Sub-Section -->
                        <div id="config-section-tag-policy"'''
        content = content.replace(old_close, new_close)

    # 3. Bump JS version
    content = content.replace("members.js?v=69", "members.js?v=70")

    with open('members/index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Step 6a: HTML Spot sections added, JS version bumped to v70")
