"""Replace the dash-tab with an exact copy of the ai-tab structure."""
with open('members/index.html', 'rb') as f:
    raw = f.read()

# First, find and remove the existing dash-tab div entirely
start_marker = b'<div id="dash-tab"'
end_search_from = raw.find(start_marker)
if end_search_from == -1:
    print('ERROR: dash-tab not found')
    exit(1)

# Find the closing </div> by counting depth
pos = raw.find(b'>', end_search_from) + 1
depth = 1
while depth > 0 and pos < len(raw):
    next_open = raw.find(b'<div', pos)
    next_close = raw.find(b'</div>', pos)
    if next_close == -1:
        break
    if next_open != -1 and next_open < next_close:
        depth += 1
        pos = next_open + 4
    else:
        depth -= 1
        if depth == 0:
            end_pos = next_close + 6  # len('</div>')
            break
        pos = next_close + 6

old_dash = raw[end_search_from:end_pos]
print(f'Found old dash-tab: {len(old_dash)} bytes')

# Now find the ai-tab div to copy its structure
ai_start = raw.find(b'<div id="ai-tab"')
if ai_start == -1:
    print('ERROR: ai-tab not found')
    exit(1)

# Find ai-tab closing
pos2 = raw.find(b'>', ai_start) + 1
depth2 = 1
while depth2 > 0 and pos2 < len(raw):
    next_open2 = raw.find(b'<div', pos2)
    next_close2 = raw.find(b'</div>', pos2)
    if next_close2 == -1:
        break
    if next_open2 != -1 and next_open2 < next_close2:
        depth2 += 1
        pos2 = next_open2 + 4
    else:
        depth2 -= 1
        if depth2 == 0:
            ai_end = next_close2 + 6
            break
        pos2 = next_close2 + 6

ai_tab_html = raw[ai_start:ai_end]
print(f'Found ai-tab: {len(ai_tab_html)} bytes')

# Create dash-tab as a simple copy with changed IDs and title
dash_tab = ai_tab_html
dash_tab = dash_tab.replace(b'id="ai-tab"', b'id="dash-tab"', 1)
dash_tab = dash_tab.replace(b'<h2>AI Agent</h2>', b'<h2>Dashboard</h2>', 1)
# Change the welcome message
dash_tab = dash_tab.replace(
    b'Hi - We are here to help you slash your Bill',
    b'FinOps Dashboard - Coming Soon'
)

# Replace old dash-tab with new one
raw = raw.replace(old_dash, dash_tab, 1)

# Bump version
raw = raw.replace(b'members.js?v=12', b'members.js?v=13')
raw = raw.replace(b'members.css?v=12', b'members.css?v=13')

with open('members/index.html', 'wb') as f:
    f.write(raw)

print('Done - dash-tab is now a copy of ai-tab')
