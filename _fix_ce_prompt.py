#!/usr/bin/env python3
"""Fix the CE cost explanation in the member handler system prompt."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '- NEVER recommend reducing "AWS Cost Explorer" or "Amazon Registrar" costs \u2014 these are platform/domain fees'
new = ('- When explaining AWS Cost Explorer costs: state the pricing model ($0.01 per API request), '
       'calculate implied request count (total/$0.01), explain what generates requests (dashboards, '
       'budgets, anomaly detection, forecasts). Do NOT call it a "platform fee" or say it "cannot be reduced".\n'
       '- NEVER recommend reducing "Amazon Registrar" costs \u2014 that is a fixed annual domain registration fee')

count = content.count(old)
content = content.replace(old, new)

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Replaced {count} occurrence(s)')
