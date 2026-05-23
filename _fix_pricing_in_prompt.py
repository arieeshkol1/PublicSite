#!/usr/bin/env python3
"""Add pricing explanation rule to the embedded system prompt in member-handler."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the rule about explaining services and add pricing math requirement after it
old = ('- When a user asks to "explain" or "break down" any service cost, ALWAYS describe: '
       '(1) what the service does in plain language, '
       '(2) what the charge includes (features/components), (3) the pricing model and math, '
       '(4) what domain/resource name is associated if possible. '
       'Do not just state the dollar amount \u2014 educate the user about what they are paying for.')

new = ('- When a user asks to "explain" or "break down" any service cost, ALWAYS describe: '
       '(1) what the service does in plain language, '
       '(2) what the charge includes (features/components), (3) the pricing model and math (unit price x quantity = total), '
       '(4) what domain/resource name is associated if possible. '
       'Do not just state the dollar amount \u2014 educate the user about what they are paying for.\n'
       '- ALWAYS show pricing math when explaining costs. Examples: '
       'S3: "$0.19 at $0.023/GB = ~8.3 GB stored". '
       'Cost Explorer: "$39.21 at $0.01/request = ~3,921 API requests". '
       'Route 53: "$0.50/hosted zone/month + $0.40/million queries". '
       'Lambda: "$X at $0.20/1M requests + $0.0000166667/GB-sec". '
       'EC2: "$X at $Y/hour x Z hours". '
       'If you cannot determine the exact unit breakdown, state the pricing model and estimate.')

count = content.count(old)
content = content.replace(old, new)

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Updated {count} occurrence(s)')
