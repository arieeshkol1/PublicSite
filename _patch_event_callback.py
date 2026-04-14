#!/usr/bin/env python3
"""Fix Paddle checkout.completed event data extraction."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

old = """if (ev.name === 'checkout.completed') {
                var items = (ev.data && ev.data.items) || [];
                var priceId = items.length > 0 ? items[0].price_id : '';"""

new = """if (ev.name === 'checkout.completed') {
                console.log('Paddle checkout.completed:', JSON.stringify(ev));
                var items = (ev.data && ev.data.items) || [];
                var priceId = '';
                if (items.length > 0) {
                    // Paddle v2: price is nested as items[].price.id
                    priceId = (items[0].price && items[0].price.id) || items[0].price_id || '';
                }"""

if old in content:
    content = content.replace(old, new)
    print("Fixed priceId extraction from checkout.completed event")
else:
    print("WARNING: Could not find old event extraction code")

# Also fix the part that calls the backend API for token top-ups
old_topup = """// Optimistically update token display
                        var storedTokens = JSON.parse(sessionStorage.getItem('memberTokens') || '{}');
                        var newBonus = (storedTokens.bonus || 0) + addedTokens;
                        var newTotal = (storedTokens.total || 100) + addedTokens;
                        var newRemaining = (storedTokens.remaining || 0) + addedTokens;
                        var updated = {used: storedTokens.used || 0, total: newTotal, remaining: newRemaining, bonus: newBonus};
                        _updateTokenDisplay(updated);"""

new_topup = """// Optimistically update token display
                        var storedTokens = JSON.parse(sessionStorage.getItem('memberTokens') || '{}');
                        var newBonus = (storedTokens.bonus || 0) + addedTokens;
                        var newTotal = (storedTokens.total || 100) + addedTokens;
                        var newRemaining = (storedTokens.remaining || 0) + addedTokens;
                        var updated = {used: storedTokens.used || 0, total: newTotal, remaining: newRemaining, bonus: newBonus};
                        _updateTokenDisplay(updated);
                        // Persist to backend
                        var memberEmail = getMemberEmail();
                        if (memberEmail) {
                            api('POST', '/member/add-tokens', {email: memberEmail, tokens: addedTokens, paddleTransactionId: (ev.data && ev.data.id) || ''}).then(function(resp) {
                                if (resp && resp.tokens) _updateTokenDisplay(resp.tokens);
                            }).catch(function(e) { console.warn('Token sync failed:', e); });
                        }"""

if old_topup in content:
    content = content.replace(old_topup, new_topup)
    print("Added backend API call for token sync after checkout")
else:
    print("WARNING: Could not find topup update code")

# Also add backend call for tier upgrades
old_tier = """// Update tier in session immediately
                    sessionStorage.setItem('memberTier', plan.toLowerCase());
                    var badge = document.getElementById('header-tier-badge');
                    if (badge) { badge.textContent = plan; badge.style.background = '#dbeafe'; badge.style.color = '#1e40af'; }"""

new_tier = """// Update tier in session immediately
                    sessionStorage.setItem('memberTier', plan.toLowerCase());
                    var badge = document.getElementById('header-tier-badge');
                    if (badge) { badge.textContent = plan; badge.style.background = '#dbeafe'; badge.style.color = '#1e40af'; }
                    // Persist to backend
                    var memberEmail = getMemberEmail();
                    if (memberEmail) {
                        api('POST', '/member/update-tier', {email: memberEmail, tier: plan.toLowerCase(), paddleSubscriptionId: (ev.data && ev.data.id) || ''}).catch(function(e) { console.warn('Tier sync failed:', e); });
                    }"""

if old_tier in content:
    content = content.replace(old_tier, new_tier)
    print("Added backend API call for tier sync after checkout")
else:
    print("WARNING: Could not find tier update code")

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
