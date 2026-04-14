#!/usr/bin/env python3
"""Replace _showUpgradeModal with Paddle-integrated version."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find start and end of _showUpgradeModal
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if 'function _showUpgradeModal()' in line and start_idx is None:
        start_idx = i
    if start_idx is not None and i > start_idx:
        # Find the closing } that's at the same indentation level
        if line.strip() == '}' and end_idx is None:
            # Check if next line is empty or starts a new section
            if i + 1 < len(lines) and (lines[i+1].strip() == '' or lines[i+1].startswith('//')):
                end_idx = i
                break

if start_idx is None or end_idx is None:
    print(f"Could not find function boundaries: start={start_idx}, end={end_idx}")
    exit(1)

print(f"Found _showUpgradeModal at lines {start_idx+1}-{end_idx+1}")

new_function = '''function _showUpgradeModal() {
    var currentTier = sessionStorage.getItem('memberTier') || 'free';
    var tokens = JSON.parse(sessionStorage.getItem('memberTokens') || '{}');
    var remaining = tokens.remaining || 0;
    var total = tokens.total || 100;
    var email = getMemberEmail() || '';

    var tierNames = {free:'Free', growth:'Growth', scale:'Scale'};
    var overlay = document.createElement('div');
    overlay.id = 'upgrade-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:900;display:flex;align-items:center;justify-content:center;';
    overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

    var current = tierNames[currentTier] || 'Free';
    var html = '<div style="background:#fff;border-radius:16px;padding:32px;max-width:700px;width:95%;max-height:90vh;overflow-y:auto;">';
    html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">';
    html += '<h2 style="margin:0;font-size:1.3em;">Manage Your Plan</h2>';
    html += '<button onclick="document.getElementById(\\'upgrade-modal\\').remove();" style="background:none;border:none;font-size:1.4em;cursor:pointer;color:#6b7280;">&times;</button></div>';
    html += '<p style="color:#6b7280;font-size:0.85em;margin-bottom:20px;">Current plan: <strong>' + current + '</strong> &middot; Tokens: <strong>' + remaining + '/' + total + '</strong></p>';

    // Plan cards
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;">';

    // Free
    html += '<div style="border:2px solid ' + (currentTier === 'free' ? '#e8714a' : '#e5e7eb') + ';border-radius:12px;padding:16px;text-align:center;">';
    html += '<div style="font-weight:700;font-size:1.1em;">Free</div>';
    html += '<div style="font-size:2em;font-weight:800;margin:8px 0;">$0</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">100 tokens/mo</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">1 account</div>';
    html += currentTier === 'free' ? '<div style="margin-top:12px;color:#10b981;font-weight:600;font-size:0.85em;">&#10003; Current Plan</div>' : '<button class="smb-upgrade-plan-btn" data-plan="free" style="margin-top:12px;background:#f3f4f6;color:#374151;border:1px solid #d1d5db;border-radius:8px;padding:8px 16px;font-size:0.8em;cursor:pointer;width:100%;">Downgrade</button>';
    html += '</div>';

    // Growth
    html += '<div style="border:2px solid ' + (currentTier === 'growth' ? '#e8714a' : '#3b82f6') + ';border-radius:12px;padding:16px;text-align:center;position:relative;">';
    html += '<div style="position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:#3b82f6;color:#fff;font-size:0.65em;font-weight:700;padding:2px 10px;border-radius:100px;">POPULAR</div>';
    html += '<div style="font-weight:700;font-size:1.1em;">Growth</div>';
    html += '<div style="font-size:2em;font-weight:800;margin:8px 0;">$50</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">300 tokens/mo</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">20 accounts &middot; All features</div>';
    html += currentTier === 'growth' ? '<div style="margin-top:12px;color:#10b981;font-weight:600;font-size:0.85em;">&#10003; Current Plan</div>' : '<button class="smb-upgrade-plan-btn" data-plan="growth" style="margin-top:12px;background:linear-gradient(135deg,#e8714a,#d4603a);color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:0.8em;font-weight:600;cursor:pointer;width:100%;">Upgrade to Growth</button>';
    html += '</div>';

    // Scale
    html += '<div style="border:2px solid ' + (currentTier === 'scale' ? '#e8714a' : '#e5e7eb') + ';border-radius:12px;padding:16px;text-align:center;">';
    html += '<div style="font-weight:700;font-size:1.1em;">Scale</div>';
    html += '<div style="font-size:2em;font-weight:800;margin:8px 0;">$200</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">1,500 tokens/mo</div>';
    html += '<div style="color:#6b7280;font-size:0.8em;">20 accounts &middot; Priority</div>';
    html += currentTier === 'scale' ? '<div style="margin-top:12px;color:#10b981;font-weight:600;font-size:0.85em;">&#10003; Current Plan</div>' : '<button class="smb-upgrade-plan-btn" data-plan="scale" style="margin-top:12px;background:#1a1a2e;color:#fff;border:none;border-radius:8px;padding:8px 16px;font-size:0.8em;font-weight:600;cursor:pointer;width:100%;">Upgrade to Scale</button>';
    html += '</div>';
    html += '</div>';

    // Token top-up section
    html += '<div style="border-top:1px solid #e5e7eb;padding-top:20px;">';
    html += '<h3 style="font-size:1em;margin-bottom:12px;">&#x1FA99; Top Up Tokens</h3>';
    html += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">';
    html += '<button class="smb-topup-btn" data-tokens="50" data-price="5" data-paddle="topup5" style="border:1.5px solid #e5e7eb;border-radius:10px;padding:14px;text-align:center;background:#fff;cursor:pointer;"><div style="font-size:1.3em;font-weight:700;">&#x1FA99; 50</div><div style="color:#6b7280;font-size:0.8em;">$5</div></button>';
    html += '<button class="smb-topup-btn" data-tokens="200" data-price="15" data-paddle="topup15" style="border:1.5px solid #3b82f6;border-radius:10px;padding:14px;text-align:center;background:#fff;cursor:pointer;"><div style="font-size:1.3em;font-weight:700;">&#x1FA99; 200</div><div style="color:#3b82f6;font-size:0.8em;font-weight:600;">$15 (25% off)</div></button>';
    html += '<button class="smb-topup-btn" data-tokens="500" data-price="30" data-paddle="topup30" style="border:1.5px solid #10b981;border-radius:10px;padding:14px;text-align:center;background:#fff;cursor:pointer;"><div style="font-size:1.3em;font-weight:700;">&#x1FA99; 500</div><div style="color:#10b981;font-size:0.8em;font-weight:600;">$30 (40% off)</div></button>';
    html += '</div></div>';

    // Legal links
    html += '<div style="margin-top:20px;padding-top:16px;border-top:1px solid #f3f4f6;text-align:center;font-size:0.75em;color:#9ca3af;">';
    html += 'Payments processed by <a href="https://paddle.com" target="_blank" style="color:#9ca3af;text-decoration:underline;">Paddle</a> &middot; ';
    html += '<a href="/terms-and-conditions/" target="_blank" style="color:#9ca3af;text-decoration:underline;">Terms</a> &middot; ';
    html += '<a href="/privacy/" target="_blank" style="color:#9ca3af;text-decoration:underline;">Privacy</a> &middot; ';
    html += '<a href="/refund/" target="_blank" style="color:#9ca3af;text-decoration:underline;">Refund Policy</a></div>';

    html += '</div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);

    // Wire up plan buttons — open Paddle checkout
    overlay.querySelectorAll('.smb-upgrade-plan-btn').forEach(function(btn) {
        btn.onclick = function() {
            var plan = btn.getAttribute('data-plan');
            if (plan === 'free') {
                // Downgrade — just notify, backend handles via webhook on cancel
                if (confirm('Downgrade to Free? Your paid features will remain active until the end of your billing period.')) {
                    notify('To downgrade, cancel your subscription from the Paddle receipt email or contact info@slashmycloudbill.com', 'info', 8000);
                }
                return;
            }
            var priceId = PADDLE_PRICES[plan];
            if (!priceId) return;
            if (typeof Paddle !== 'undefined') {
                Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    customer: {email: email},
                    customData: {memberEmail: email, tier: plan}
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });

    // Wire up top-up buttons — open Paddle checkout
    overlay.querySelectorAll('.smb-topup-btn').forEach(function(btn) {
        btn.onclick = function() {
            var paddleKey = btn.getAttribute('data-paddle');
            var priceId = PADDLE_PRICES[paddleKey];
            if (!priceId) return;
            if (typeof Paddle !== 'undefined') {
                Paddle.Checkout.open({
                    items: [{priceId: priceId, quantity: 1}],
                    customer: {email: email},
                    customData: {memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')}
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });
}
'''

# Replace the lines
new_lines = lines[:start_idx] + [new_function + '\n'] + lines[end_idx+1:]

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Replaced _showUpgradeModal (lines {start_idx+1}-{end_idx+1}) with Paddle-integrated version")
