#!/usr/bin/env python3
"""Add cluster analyze endpoint + route."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add route
if 'handle_cluster_analyze' not in content:
    content = content.replace(
        "'POST /members/servers/list-instances': handle_server_list_instances,",
        "'POST /members/servers/list-instances': handle_server_list_instances,\n"
        "        'POST /members/cluster/analyze': handle_cluster_analyze,"
    )
    with open('_cluster_optimize_backend.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Cluster analyze endpoint added")
else:
    print("Already present")
