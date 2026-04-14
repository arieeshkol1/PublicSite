#!/usr/bin/env python3
"""Make tag list table headers sticky so they don't scroll with the list."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the table header row to use sticky positioning
old_header = """var html = '<table style="width:100%;border-collapse:collapse;font-size:0.9em;">';
    html += '<tr style="border-bottom:2px solid #e5e7eb;"><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;width:30px;"></th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Resource</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Type</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Account</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Missing Tags</th></tr>';"""

new_header = """var html = '<table style="width:100%;border-collapse:collapse;font-size:0.9em;">';
    html += '<thead><tr style="border-bottom:2px solid #e5e7eb;"><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;width:30px;position:sticky;top:0;background:#fff;z-index:1;"></th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;position:sticky;top:0;background:#fff;z-index:1;">Resource</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;position:sticky;top:0;background:#fff;z-index:1;">Type</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;position:sticky;top:0;background:#fff;z-index:1;">Account</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;position:sticky;top:0;background:#fff;z-index:1;">Missing Tags</th></tr></thead><tbody>';"""

content = content.replace(old_header, new_header)

# Close the tbody tag at the end of the table
old_end = "html += '</table>';"
new_end = "html += '</tbody></table>';"
content = content.replace(old_end, new_end, 1)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Made tag list headers sticky")
