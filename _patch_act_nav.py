#!/usr/bin/env python3
"""Update Act tab JS for left-nav sections and improved tag list styling."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add section switcher function before initActTab
old_init = "function initActTab() {"
new_init = """function _switchActSection(section) {
    document.querySelectorAll('.act-nav-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.section === section);
    });
    var waste = document.getElementById('act-section-waste');
    var tagging = document.getElementById('act-section-tagging');
    if (waste) waste.style.display = section === 'waste' ? 'block' : 'none';
    if (tagging) tagging.style.display = section === 'tagging' ? 'block' : 'none';
}

function initActTab() {"""

content = content.replace(old_init, new_init, 1)

# 2. Update _runTagScan to work with new structure (no more hiding waste cards)
old_run = """    // Hide waste cards, show tag panel
    if (cardsGrid) cardsGrid.style.display = 'none';
    if (empty) empty.style.display = 'none';
    if (totalSavings) totalSavings.style.display = 'none';
    if (panel) panel.style.display = 'block';
    if (status) status.textContent = 'Scanning for untagged resources...';"""

new_run = """    if (panel) panel.style.display = 'block';
    var tagEmpty = document.getElementById('act-tag-empty');
    if (tagEmpty) tagEmpty.style.display = 'none';
    var tagStatus = document.getElementById('act-tag-scan-status');
    if (tagStatus) tagStatus.textContent = 'Scanning for untagged resources...';"""

content = content.replace(old_run, new_run)

# 3. Update the success status line
old_status = """if (status) status.textContent = 'Tag scan complete — ' + _tagScanResults.length + ' resources need tagging';"""
new_status = """if (tagStatus) tagStatus.textContent = 'Tag scan complete — ' + _tagScanResults.length + ' resources need tagging';"""
content = content.replace(old_status, new_status)

# 4. Update the error status line
old_err = """if (status) status.textContent = 'Tag scan failed: ' + (e.message || 'Unknown error');"""
new_err = """if (tagStatus) tagStatus.textContent = 'Tag scan failed: ' + (e.message || 'Unknown error');"""
content = content.replace(old_err, new_err)

# 5. Update tag list rendering to use proper fonts and black text
old_table = """var html = '<table style="width:100%;border-collapse:collapse;font-size:0.82em;">';
    html += '<tr style="border-bottom:1px solid #30363d;"><th style="padding:6px 8px;text-align:left;color:#8b949e;width:30px;"></th><th style="padding:6px 8px;text-align:left;color:#8b949e;">Resource</th><th style="padding:6px 8px;text-align:left;color:#8b949e;">Type</th><th style="padding:6px 8px;text-align:left;color:#8b949e;">Account</th><th style="padding:6px 8px;text-align:left;color:#8b949e;">Missing Tags</th></tr>';"""

new_table = """var html = '<table style="width:100%;border-collapse:collapse;font-size:0.9em;">';
    html += '<tr style="border-bottom:2px solid #e5e7eb;"><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;width:30px;"></th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Resource</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Type</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Account</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Missing Tags</th></tr>';"""

content = content.replace(old_table, new_table)

# 6. Update tag list row styling
old_row = """html += '<tr style="border-bottom:1px solid #21262d;">'
            + '<td style="padding:6px 8px;"><input type="checkbox" class="tag-chk" data-arn="' + r.arn + '"' + checked + '></td>'
            + '<td style="padding:6px 8px;color:#c9d1d9;" title="' + r.arn + '">' + (r.name || r.resourceId) + '</td>'
            + '<td style="padding:6px 8px;color:#8b949e;">' + (r.resourceType || '') + '</td>'
            + '<td style="padding:6px 8px;color:#8b949e;font-size:0.9em;">' + (r.account || '').slice(-4) + '</td>'
            + '<td style="padding:6px 8px;">' + missingHtml + '</td></tr>';"""

new_row = """html += '<tr style="border-bottom:1px solid #e5e7eb;">'
            + '<td style="padding:8px 10px;"><input type="checkbox" class="tag-chk" data-arn="' + r.arn + '"' + checked + '></td>'
            + '<td style="padding:8px 10px;color:#1f2937;font-weight:500;" title="' + r.arn + '">' + (r.name || r.resourceId) + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.resourceType || '') + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.account || '').slice(-4) + '</td>'
            + '<td style="padding:8px 10px;">' + missingHtml + '</td></tr>';"""

content = content.replace(old_row, new_row)

# 7. Update tag stats to use light theme
old_stats = """el.innerHTML = '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;flex:1;min-width:100px;">'
        + '<div style="color:#8b949e;font-size:0.75em;">Tag Coverage</div>'
        + '<div style="color:' + covColor + ';font-size:1.3em;font-weight:700;">' + cov + '%</div></div>'
        + '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;flex:1;min-width:100px;">'
        + '<div style="color:#8b949e;font-size:0.75em;">Total Resources</div>'
        + '<div style="color:#c9d1d9;font-size:1.3em;font-weight:700;">' + (s.total || 0) + '</div></div>'
        + '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;flex:1;min-width:100px;">'
        + '<div style="color:#8b949e;font-size:0.75em;">Fully Tagged</div>'
        + '<div style="color:#10b981;font-size:1.3em;font-weight:700;">' + (s.fullyTagged || 0) + '</div></div>'
        + '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;flex:1;min-width:100px;">'
        + '<div style="color:#8b949e;font-size:0.75em;">Need Tagging</div>'
        + '<div style="color:#ef4444;font-size:1.3em;font-weight:700;">' + ((s.partiallyTagged || 0) + (s.untagged || 0)) + '</div></div>';"""

new_stats = """el.innerHTML = '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Tag Coverage</div>'
        + '<div style="color:' + covColor + ';font-size:1.4em;font-weight:700;">' + cov + '%</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Total Resources</div>'
        + '<div style="color:#1f2937;font-size:1.4em;font-weight:700;">' + (s.total || 0) + '</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Fully Tagged</div>'
        + '<div style="color:#10b981;font-size:1.4em;font-weight:700;">' + (s.fullyTagged || 0) + '</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Need Tagging</div>'
        + '<div style="color:#ef4444;font-size:1.4em;font-weight:700;">' + ((s.partiallyTagged || 0) + (s.untagged || 0)) + '</div></div>';"""

content = content.replace(old_stats, new_stats)

# 8. Update tag input row styling for light theme
old_input = """row.innerHTML = '<input type="text" placeholder="Tag Key (e.g. Environment)" style="flex:1;padding:6px 10px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#c9d1d9;font-size:0.85em;" class="tag-key-input">'
        + '<input type="text" placeholder="Tag Value (e.g. production)" style="flex:1;padding:6px 10px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#c9d1d9;font-size:0.85em;" class="tag-val-input">'
        + '<button onclick="this.parentElement.remove();" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:1.2em;">✕</button>';"""

new_input = """row.innerHTML = '<input type="text" placeholder="Tag Key (e.g. Environment)" style="flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#1f2937;font-size:0.9em;" class="tag-key-input">'
        + '<input type="text" placeholder="Tag Value (e.g. production)" style="flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#1f2937;font-size:0.9em;" class="tag-val-input">'
        + '<button onclick="this.parentElement.remove();" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:1.2em;">✕</button>';"""

content = content.replace(old_input, new_input)

# 9. Update the tag button onclick to switch to tagging section first
old_tagbtn = """tagBtn.onclick = async function() {
        _syncActSelection();
        var accountIds = getActSelectedAccountIds();
        await _runTagScan(accountIds);
    };"""

new_tagbtn = """tagBtn.onclick = async function() {
        _switchActSection('tagging');
        _syncActSelection();
        var accountIds = getActSelectedAccountIds();
        await _runTagScan(accountIds);
    };"""

content = content.replace(old_tagbtn, new_tagbtn)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("All Act tab updates applied!")
