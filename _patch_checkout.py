#!/usr/bin/env python3
"""Fix Paddle.Checkout.open calls to use correct v2 API format."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix plan upgrade checkout calls
old_plan = '''Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    customer: {email: email},
                    customData: {memberEmail: email, tier: plan}
                });'''

new_plan = '''Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en',
                        successUrl: 'https://slashmycloudbill.com/members/?payment=success'
                    },
                    customData: {memberEmail: email, tier: plan}
                });'''

content = content.replace(old_plan, new_plan)

# Fix top-up checkout calls
old_topup = '''Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    customer: {email: email},
                    customData: {memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')}
                });'''

new_topup = '''Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en',
                        successUrl: 'https://slashmycloudbill.com/members/?payment=success'
                    },
                    customData: {memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')}
                });'''

content = content.replace(old_topup, new_topup)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed Paddle.Checkout.open calls")
