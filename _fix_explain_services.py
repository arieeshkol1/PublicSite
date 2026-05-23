#!/usr/bin/env python3
"""Add service explanation rule to both system prompts."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '- NEVER recommend reducing "Amazon Registrar" costs \u2014 that is a fixed annual domain registration fee'
new = ('- NEVER recommend reducing "Amazon Registrar" costs \u2014 that is a fixed annual domain registration fee\n'
       '- When a user asks to "explain" or "break down" any service cost, ALWAYS describe: (1) what the service does in plain language, '
       '(2) what the charge includes (features/components), (3) the pricing model and math, '
       '(4) what domain/resource name is associated if possible. Do not just state the dollar amount \u2014 educate the user about what they are paying for.')

count = content.count(old)
content = content.replace(old, new)

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Updated {count} occurrence(s)')
