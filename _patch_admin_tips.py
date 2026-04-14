#!/usr/bin/env python3
"""Add 'Act' status column to admin Tips table."""

with open('admin/admin.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Add Act status badge to each tip row in renderTips
# Find the scoreHtml line and add actHtml after it
old = "if(t.confidenceTag==='high-confidence')scoreHtml+=' <span style=\"background:#10b981;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;\">✓</span>';"
new = old + "var actHtml=t.implementedInAct?'<span style=\"background:#6366f1;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;\">✓ Act</span>':'<span style=\"color:#d1d5db;font-size:10px;\">—</span>';"

content = content.replace(old, new)

# Add the Act column to the row HTML — insert before the Check column
old_row = "+'<td>'+sb+'</td><td class=\"actions-cell\">"
new_row = "+'<td style=\"text-align:center\">'+actHtml+'</td><td>'+sb+'</td><td class=\"actions-cell\">"

content = content.replace(old_row, new_row)

with open('admin/admin.js', 'w', encoding='utf-8') as f:
    f.write(content)

# Also add the column header to admin/index.html
with open('admin/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

old_header = '<th class="sortable" data-col="positiveCount">Score <span class="sort-icon">⇅</span></th>\n                            <th>Check</th>'
new_header = '<th class="sortable" data-col="positiveCount">Score <span class="sort-icon">⇅</span></th>\n                            <th>Act</th>\n                            <th>Check</th>'

html = html.replace(old_header, new_header)

with open('admin/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Added 'Act' column to admin Tips table")
