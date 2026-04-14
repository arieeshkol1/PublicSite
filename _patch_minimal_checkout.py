#!/usr/bin/env python3
"""Strip Paddle.Checkout.open to absolute minimum params to debug 400."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace plan checkout with minimal call
old_plan = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en',
                        successUrl: 'https://slashmycloudbill.com/members/?payment=success'
                    },
                    customData: JSON.stringify({memberEmail: email, tier: plan})
                });"""

new_plan = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}]
                });"""

content = content.replace(old_plan, new_plan)

# Replace topup checkout with minimal call
old_topup = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {
                        displayMode: 'overlay',
                        theme: 'light',
                        locale: 'en',
                        successUrl: 'https://slashmycloudbill.com/members/?payment=success'
                    },
                    customData: JSON.stringify({memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')})
                });"""

new_topup = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}]
                });"""

content = content.replace(old_topup, new_topup)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Stripped checkout to minimal params")
