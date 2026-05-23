#!/usr/bin/env python3
"""Add cluster optimize JS functions."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    js = f.read()

if '_clusterAnalyze' not in js:
    with open('_cluster_js.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    js += code
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(js)
    print("Cluster JS added")
else:
    print("Already present")
