#!/usr/bin/env python3
"""Step 1: Add resize backend handlers + routes to member-handler."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add routes
old_route = "'GET /members/spot/dashboard': handle_spot_dashboard,"
new_route = old_route + """
        'POST /members/servers/analyze': handle_server_analyze,
        'POST /members/servers/resize': handle_server_resize,"""

if 'handle_server_analyze' in content:
    print("Routes already present -- skipping route addition")
else:
    content = content.replace(old_route, new_route)
    print("Routes added")

# Append handlers
if 'def handle_server_analyze' in content:
    print("Handlers already present -- skipping")
else:
    with open('_resize_backend.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    print("Handlers appended")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Step 1 complete")
