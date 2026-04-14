#!/usr/bin/env python3
"""Update tag list rendering to show all resources (tagged + untagged) with visual distinction."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the tag list table to show tag status
old_row = """html += '<tr style="border-bottom:1px solid #e5e7eb;">'
            + '<td style="padding:8px 10px;"><input type="checkbox" class="tag-chk" data-arn="' + r.arn + '"' + checked + '></td>'
            + '<td style="padding:8px 10px;color:#1f2937;font-weight:500;" title="' + r.arn + '">' + (r.name || r.resourceId) + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.resourceType || '') + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.account || '').slice(-4) + '</td>'
            + '<td style="padding:8px 10px;">' + missingHtml + '</td></tr>';"""

new_row = """var rowBg = (r.missingTags && r.missingTags.length > 0) ? '' : 'background:#f0fdf4;';
        var statusBadge = (r.missingTags && r.missingTags.length > 0) ? '' : '<span style="color:#10b981;font-weight:600;font-size:0.85em;">✓ Tagged</span>';
        html += '<tr style="border-bottom:1px solid #e5e7eb;' + rowBg + '">'
            + '<td style="padding:8px 10px;"><input type="checkbox" class="tag-chk" data-arn="' + r.arn + '"' + checked + '></td>'
            + '<td style="padding:8px 10px;color:#1f2937;font-weight:500;" title="' + r.arn + '">' + (r.name || r.resourceId) + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.resourceType || '') + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.account || '').slice(-4) + '</td>'
            + '<td style="padding:8px 10px;">' + (missingHtml || statusBadge) + '</td></tr>';"""

content = content.replace(old_row, new_row)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated tag list to show all resources with tagged/untagged distinction")
