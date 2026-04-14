#!/usr/bin/env python3
"""Restore full Paddle checkout params and fix token update on completion."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix the eventCallback to properly update tokens on checkout.completed
old_callback = """if (ev.name === 'checkout.completed') {
                var items = (ev.data && ev.data.items) || [];
                var priceId = items.length > 0 ? items[0].price_id : '';
                // Determine what was purchased
                if (priceId === PADDLE_PRICES.growth || priceId === PADDLE_PRICES.scale) {
                    var plan = priceId === PADDLE_PRICES.growth ? 'Growth' : 'Scale';
                    notify('Welcome to ' + plan + '! Your plan is being activated...', 'success', 6000);
                    // Sync with backend
                    var email = getMemberEmail();
                    if (email) {
                        api('POST', '/member/update-tier', {
                            email: email,
                            tier: plan.toLowerCase(),
                            paddleSubscriptionId: ev.data.subscription_id || '',
                            paddleCustomerId: ev.data.customer_id || ''
                        }).catch(function(){});
                    }
                } else {
                    // Token top-up
                    var tokenMap = {};
                    tokenMap[PADDLE_PRICES.topup5] = 50;
                    tokenMap[PADDLE_PRICES.topup15] = 200;
                    tokenMap[PADDLE_PRICES.topup30] = 500;
                    var addedTokens = tokenMap[priceId] || 0;
                    if (addedTokens > 0) {
                        notify(addedTokens + ' tokens added to your account!', 'success', 5000);
                        var email = getMemberEmail();
                        if (email) {
                            api('POST', '/member/add-tokens', {
                                email: email,
                                tokens: addedTokens,
                                paddleTransactionId: ev.data.transaction_id || ''
                            }).catch(function(){});
                        }
                    }
                }
                // Close upgrade modal if open
                var modal = document.getElementById('upgrade-modal');
                if (modal) modal.remove();
            }"""

new_callback = """if (ev.name === 'checkout.completed') {
                var items = (ev.data && ev.data.items) || [];
                var priceId = items.length > 0 ? items[0].price_id : '';
                // Determine what was purchased
                if (priceId === PADDLE_PRICES.growth || priceId === PADDLE_PRICES.scale) {
                    var plan = priceId === PADDLE_PRICES.growth ? 'Growth' : 'Scale';
                    notify('Welcome to ' + plan + '! Your plan is being activated...', 'success', 6000);
                    // Update tier in session immediately
                    sessionStorage.setItem('memberTier', plan.toLowerCase());
                    var badge = document.getElementById('header-tier-badge');
                    if (badge) { badge.textContent = plan; badge.style.background = '#dbeafe'; badge.style.color = '#1e40af'; }
                } else {
                    // Token top-up — update tokens immediately in UI
                    var tokenMap = {};
                    tokenMap[PADDLE_PRICES.topup5] = 50;
                    tokenMap[PADDLE_PRICES.topup15] = 200;
                    tokenMap[PADDLE_PRICES.topup30] = 500;
                    var addedTokens = tokenMap[priceId] || 0;
                    if (addedTokens > 0) {
                        notify(addedTokens + ' tokens added to your account!', 'success', 5000);
                        // Optimistically update token display
                        var storedTokens = JSON.parse(sessionStorage.getItem('memberTokens') || '{}');
                        var newBonus = (storedTokens.bonus || 0) + addedTokens;
                        var newTotal = (storedTokens.total || 100) + addedTokens;
                        var newRemaining = (storedTokens.remaining || 0) + addedTokens;
                        var updated = {used: storedTokens.used || 0, total: newTotal, remaining: newRemaining, bonus: newBonus};
                        _updateTokenDisplay(updated);
                    }
                }
                // Close upgrade modal if open
                var modal = document.getElementById('upgrade-modal');
                if (modal) modal.remove();
                // Reload accounts data to sync with backend after a short delay
                setTimeout(function() { if (typeof loadAccounts === 'function') loadAccounts(); }, 2000);
            }"""

if old_callback in content:
    content = content.replace(old_callback, new_callback)
    print("Updated eventCallback with proper token/tier update")
else:
    print("WARNING: Could not find old eventCallback to replace")

# 2. Restore full checkout params for plan buttons
old_plan_checkout = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}]
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });

    // Wire up top-up buttons"""

new_plan_checkout = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {displayMode: 'overlay', theme: 'light', locale: 'en'},
                    customData: JSON.stringify({memberEmail: email, tier: plan})
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });

    // Wire up top-up buttons"""

if old_plan_checkout in content:
    content = content.replace(old_plan_checkout, new_plan_checkout)
    print("Restored plan checkout params")
else:
    print("WARNING: Could not find plan checkout to restore")

# 3. Restore full checkout params for top-up buttons
old_topup_checkout = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}]
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });
}"""

new_topup_checkout = """Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    settings: {displayMode: 'overlay', theme: 'light', locale: 'en'},
                    customData: JSON.stringify({memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')})
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });
}"""

if old_topup_checkout in content:
    content = content.replace(old_topup_checkout, new_topup_checkout)
    print("Restored topup checkout params")
else:
    print("WARNING: Could not find topup checkout to restore")

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
