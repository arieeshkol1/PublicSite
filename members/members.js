/* Member Portal v1 - SlashMyBill */
var API = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';

// ============================================================
// Paddle Payment Integration
// ============================================================
var PADDLE_TOKEN = 'live_fe95f6bba28cac28ba97f8d0076';
var PADDLE_PRICES = {
    growth: 'pri_01kp2zns5ph1vpmh71f98wqzcq',
    scale:  'pri_01kp2zs05ft013aezpprne5wvd',
    topup5:  'pri_01kp2zv7h558s5289qvaw59whr',
    topup15: 'pri_01kp2zyxwhppmx3ddqax5qmbcn',
    topup30: 'pri_01kp30738d2d23fqpfyy2nj7aj'
};
// Initialize Paddle
if (typeof Paddle !== 'undefined') {
    Paddle.Initialize({
        token: PADDLE_TOKEN,
        eventCallback: function(ev) {
            if (ev.name === 'checkout.completed') {
                console.log('Paddle checkout.completed:', JSON.stringify(ev));
                var items = (ev.data && ev.data.items) || [];
                var priceId = '';
                if (items.length > 0) {
                    // Paddle v2: price is nested as items[].price.id
                    priceId = (items[0].price && items[0].price.id) || items[0].price_id || '';
                }
                // Determine what was purchased
                if (priceId === PADDLE_PRICES.growth || priceId === PADDLE_PRICES.scale) {
                    var plan = priceId === PADDLE_PRICES.growth ? 'Growth' : 'Scale';
                    notify('Welcome to ' + plan + '! Your plan is being activated...', 'success', 6000);
                    // Update tier in session immediately
                    sessionStorage.setItem('memberTier', plan.toLowerCase());
                    var badge = document.getElementById('header-tier-badge');
                    if (badge) { badge.textContent = plan; badge.style.background = '#dbeafe'; badge.style.color = '#1e40af'; }
                    // Persist to backend
                    var memberEmail = getMemberEmail();
                    if (memberEmail) {
                        api('POST', '/member/update-tier', {email: memberEmail, tier: plan.toLowerCase(), paddleSubscriptionId: (ev.data && ev.data.id) || ''}).catch(function(e) { console.warn('Tier sync failed:', e); });
                    }
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
                        // Persist to backend
                        var memberEmail = getMemberEmail();
                        if (memberEmail) {
                            api('POST', '/member/add-tokens', {email: memberEmail, tokens: addedTokens, paddleTransactionId: (ev.data && ev.data.id) || ''}).then(function(resp) {
                                if (resp && resp.tokens) _updateTokenDisplay(resp.tokens);
                            }).catch(function(e) { console.warn('Token sync failed:', e); });
                        }
                    }
                }
                // Close upgrade modal if open
                var modal = document.getElementById('upgrade-modal');
                if (modal) modal.remove();
                // Reload accounts data to sync with backend after a short delay
                setTimeout(function() { if (typeof loadAccounts === 'function') loadAccounts(); }, 2000);
            }
        }
    });
}

var $ = function(id) { return document.getElementById(id); };

// Views
var loginView = $('login-view');
var registerView = $('register-view');
var resetView = $('reset-view');
var dashboardView = $('dashboard-view');

// Login elements
var loginForm = $('login-form');
var loginEmail = $('login-email');
var loginPassword = $('login-password');
var loginError = $('login-error');

// Registration elements
var regEmailForm = $('reg-email-form');
var regOtpForm = $('reg-otp-form');
var regPasswordForm = $('reg-password-form');
var regStep1 = $('reg-step-1');
var regStep2 = $('reg-step-2');
var regStep3 = $('reg-step-3');
var regEmail = $('reg-email');
var regEmailDisplay = $('reg-email-display');
var regOtp = $('reg-otp');
var regPassword = $('reg-password');
var regConfirm = $('reg-confirm');
var regEmailError = $('reg-email-error');
var regOtpError = $('reg-otp-error');
var regPasswordError = $('reg-password-error');

// Dashboard elements
var headerEmail = $('header-email');
var logoutBtn = $('logout-btn');
var addAccountBtn = $('add-account-btn');
var accountsTbody = $('accounts-tbody');
var accountsEmpty = $('accounts-empty');
var dashboardViewType = $('dashboard-view-type');
var dashboardTitleInput = $('dashboard-title');
var dashboardPromptInput = $('dashboard-prompt');
var dashboardAnswerInput = $('dashboard-answer');
var dashboardChartConfigInput = $('dashboard-chart-config');
var dashboardAddBtn = $('dashboard-add-btn');
var dashboardGrid = $('dashboard-grid');
var dashboardEmpty = $('dashboard-empty');
var visualizeModal = $('visualize-modal');
var visualizeTypeSelect = $('visualize-type-select');
var visualizeTitleInput = $('visualize-title-input');
var visualizeChartType = $('visualize-chart-type');
var visualizeDatasetLabel = $('visualize-dataset-label');
var visualizeLabelsInput = $('visualize-labels-input');
var visualizeValuesInput = $('visualize-values-input');
var visualizeCloseBtn = $('visualize-close-btn');
var visualizeCancelBtn = $('visualize-cancel-btn');
var visualizeSaveBtn = $('visualize-save-btn');

// Account modal
var accountModal = $('account-modal');
var accountModalTitle = $('account-modal-title');
var accountForm = $('account-form');
var accountIdInput = $('account-id-input');
var accountNameInput = $('account-name-input');
var accountFormError = $('account-form-error');
var accountCancelBtn = $('account-cancel-btn');
var accountModalClose = $('account-modal-close');
var accountSubmitBtn = $('account-submit-btn');

// Delete dialog
var deleteDialog = $('delete-dialog');
var deleteMsg = $('delete-dialog-msg');
var deleteCancelBtn = $('delete-cancel-btn');
var deleteConfirmBtn = $('delete-confirm-btn');

// Loading & notification
var loading = $('loading-overlay');
var notif = $('notification');
var notifMsg = $('notification-message');

// State
var otpToken = null;
var regEmailValue = '';
var editingAccountId = null;
var deletingAccountId = null;
var resetEmailValue = '';
var resetToken = null;
var dashboardItems = [];
var pendingVisualize = null;
var dashboardCharts = [];

// ============================================================
// Helpers
// ============================================================

function notify(msg, type, duration) {
    notifMsg.textContent = msg;
    notif.className = 'notification notification-' + (type || 'info');
    notif.hidden = false;
    setTimeout(function() { notif.hidden = true; }, duration || 4000);
}

function showLoading() { loading.hidden = false; }
function hideLoading() { loading.hidden = true; }

function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function ea(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtDate(ts) {
    if (!ts) return '-';
    try {
        var d = new Date(ts);
        return isNaN(d) ? ts : d.toLocaleString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
    } catch (e) { return ts; }
}

function getToken() { return sessionStorage.getItem('memberToken'); }
function getMemberEmail() { return sessionStorage.getItem('memberEmail'); }

// ============================================================
// API wrapper
// ============================================================

async function api(method, path, body) {
    var opts = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    var token = getToken();
    if (token) {
        opts.headers['Authorization'] = 'Bearer ' + token;
    }
    if (body) opts.body = JSON.stringify(body);

    var resp;
    try {
        resp = await fetch(API + path, opts);
    } catch (e) {
        throw { status: 0, message: 'Connection error, please try again' };
    }

    var data;
    try {
        data = await resp.json();
    } catch (e) {
        data = {};
    }

    // Update token display from any response that includes token info
    if (data.aiCredits) _updateTokenDisplay(data.aiCredits);
    if (data.tokens) _updateTokenDisplay(data.tokens);

    if (!resp.ok) {
        if (resp.status === 401) {
            sessionStorage.removeItem('memberToken');
            sessionStorage.removeItem('memberEmail');
            sessionStorage.removeItem('memberDisplayName');
            showView('login');
        }
        throw { status: resp.status, message: data.message || 'Error' };
    }
    return data;
}

function _updateTokenDisplay(tokens) {
    if (!tokens) return;
    var remaining = tokens.remaining != null ? tokens.remaining : 0;
    var total = tokens.total != null ? tokens.total : 100;
    var el = document.getElementById('header-token-count');
    var wrapper = document.getElementById('header-tokens');
    if (el) el.textContent = remaining + '/' + total;
    if (wrapper) {
        var pct = total > 0 ? (remaining / total) : 0;
        if (pct <= 0.2) {
            wrapper.style.background = 'linear-gradient(135deg,#ef4444,#dc2626)';
            wrapper.title = 'Low tokens! Click to top up.';
        } else {
            wrapper.style.background = 'linear-gradient(135deg,#f59e0b,#d97706)';
            wrapper.title = 'Click to top up tokens';
        }
    }
    sessionStorage.setItem('memberTokens', JSON.stringify(tokens));
}

function _showUpgradeModal() {
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
    html += '<button onclick="document.getElementById(\'upgrade-modal\').remove();" style="background:none;border:none;font-size:1.4em;cursor:pointer;color:#6b7280;">&times;</button></div>';
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
    html += '<div style="color:#6b7280;font-size:0.8em;">5 accounts &middot; All features</div>';
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
                    settings: {displayMode: 'overlay', theme: 'light', locale: 'en'},
                    customData: JSON.stringify({memberEmail: email, tier: plan})
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
                    settings: {displayMode: 'overlay', theme: 'light', locale: 'en'},
                    customData: JSON.stringify({memberEmail: email, type: 'topup', tokens: btn.getAttribute('data-tokens')})
                });
            } else {
                notify('Payment system loading... please try again in a moment.', 'error', 4000);
            }
        };
    });
}


// ============================================================
// View management
// ============================================================

function showView(name) {
    loginView.hidden = name !== 'login';
    registerView.hidden = name !== 'register';
    if (resetView) resetView.hidden = name !== 'reset';
    dashboardView.hidden = name !== 'dashboard';

    if (name === 'register') {
        regStep1.hidden = false;
        regStep2.hidden = true;
        regStep3.hidden = true;
        regEmailError.textContent = '';
        regOtpError.textContent = '';
        regPasswordError.textContent = '';
        regEmail.value = '';
        regOtp.value = '';
        regPassword.value = '';
        regConfirm.value = '';
        otpToken = null;
        regEmailValue = '';
    }
    if (name === 'login') {
        loginError.textContent = '';
        loginEmail.value = '';
        loginPassword.value = '';
    }
    if (name === 'reset' && $('reset-step-1')) {
        $('reset-step-1').hidden = false;
        $('reset-step-2').hidden = true;
        $('reset-step-3').hidden = true;
        $('reset-email-error').textContent = '';
        $('reset-otp-error').textContent = '';
        $('reset-password-error').textContent = '';
        $('reset-email').value = '';
        $('reset-otp').value = '';
        $('reset-new-password').value = '';
        $('reset-confirm-password').value = '';
        resetEmailValue = '';
        resetToken = null;
    }
    if (name === 'dashboard') {
        headerEmail.textContent = getMemberEmail() || '';
        loadAccounts().then(function() {
            populateDashAccounts();
            loadDashboardData();
        });
        loadDashboard();
    }
}

// ============================================================
// Navigation
// ============================================================

var _el;
_el = $('show-register'); if (_el) _el.onclick = function(e) { e.preventDefault(); showView('register'); };
_el = $('show-login'); if (_el) _el.onclick = function(e) { e.preventDefault(); showView('login'); };
_el = $('show-forgot'); if (_el) _el.onclick = function(e) { e.preventDefault(); showView('reset'); };
_el = $('show-login-from-reset'); if (_el) _el.onclick = function(e) { e.preventDefault(); showView('login'); };
logoutBtn.onclick = function() {
    sessionStorage.removeItem('memberToken');
    sessionStorage.removeItem('memberEmail');
    sessionStorage.removeItem('memberDisplayName');
    showView('login');
};

// ============================================================
// Login
// ============================================================

loginForm.onsubmit = async function(e) {
    e.preventDefault();
    loginError.textContent = '';
    var email = loginEmail.value.trim();
    var password = loginPassword.value;
    if (!email || !password) { loginError.textContent = 'Enter email and password.'; return; }

    try {
        showLoading();
        var data = await api('POST', '/members/login', { email: email, password: password });
        sessionStorage.setItem('memberToken', data.token);
        sessionStorage.setItem('memberEmail', data.email);
        sessionStorage.setItem('memberDisplayName', data.displayName);
        showView('dashboard');
    } catch (err) {
        loginError.textContent = err.message || 'Login failed.';
    } finally {
        hideLoading();
    }
};

// ============================================================
// Registration
// ============================================================

regEmailForm.onsubmit = async function(e) {
    e.preventDefault();
    regEmailError.textContent = '';
    regEmailValue = regEmail.value.trim().toLowerCase();
    var pw = regPassword.value;
    var cpw = regConfirm.value;
    if (!regEmailValue) { regEmailError.textContent = 'Enter your email.'; return; }
    if (pw.length < 8) { regEmailError.textContent = 'Password must be at least 8 characters.'; return; }
    if (pw !== cpw) { regEmailError.textContent = 'Passwords do not match.'; return; }

    try {
        showLoading();
        // Cognito sign_up: send email + password together, Cognito sends verification email
        await api('POST', '/members/register', { action: 'send-otp', email: regEmailValue, password: pw });
        regEmailDisplay.textContent = regEmailValue;
        regStep1.hidden = true;
        regStep2.hidden = false;
    } catch (err) {
        regEmailError.textContent = err.message || 'Failed to create account.';
    } finally {
        hideLoading();
    }
};

regOtpForm.onsubmit = async function(e) {
    e.preventDefault();
    regOtpError.textContent = '';
    var code = regOtp.value.trim();
    if (!code || code.length !== 6) { regOtpError.textContent = 'Enter the 6-digit code.'; return; }

    try {
        showLoading();
        // Cognito confirm_sign_up: verify the code, then create profile
        var data = await api('POST', '/members/register', {
            action: 'verify-otp', email: regEmailValue, otp: code
        });
        otpToken = data.otpToken;
        // Immediately complete registration (no separate password step needed)
        await api('POST', '/members/register', {
            action: 'create-account', otpToken: otpToken
        });
        notify('Registration successful! Please log in.', 'success');
        showView('login');
    } catch (err) {
        regOtpError.textContent = err.message || 'Invalid code.';
    } finally {
        hideLoading();
    }
};

// Resend OTP link
var regResendOtp = $('reg-resend-otp');
if (regResendOtp) {
    regResendOtp.onclick = async function(e) {
        e.preventDefault();
        try {
            await api('POST', '/members/register', { action: 'resend-otp', email: regEmailValue });
            notify('Verification code resent.', 'success');
        } catch (err) {
            notify(err.message || 'Failed to resend code.', 'error');
        }
    };
}

// Keep regPasswordForm stub for backward compat (no longer shown)
var regPasswordForm = $('reg-password-form');
if (regPasswordForm) {
    regPasswordForm.onsubmit = function(e) { e.preventDefault(); };
}

// ============================================================
// Password Reset
// ============================================================

if ($('reset-email-form')) $('reset-email-form').onsubmit = async function(e) {
    e.preventDefault();
    $('reset-email-error').textContent = '';
    resetEmailValue = $('reset-email').value.trim().toLowerCase();
    if (!resetEmailValue) { $('reset-email-error').textContent = 'Enter your email.'; return; }

    try {
        showLoading();
        await api('POST', '/members/reset-password', { action: 'send-otp', email: resetEmailValue });
        $('reset-email-display').textContent = resetEmailValue;
        $('reset-step-1').hidden = true;
        $('reset-step-2').hidden = false;
    } catch (err) {
        $('reset-email-error').textContent = err.message || 'Failed to send reset code.';
    } finally {
        hideLoading();
    }
};

if ($('reset-otp-form')) $('reset-otp-form').onsubmit = async function(e) {
    e.preventDefault();
    $('reset-otp-error').textContent = '';
    var code = $('reset-otp').value.trim();
    if (!code || code.length !== 6) { $('reset-otp-error').textContent = 'Enter the 6-digit code.'; return; }

    try {
        showLoading();
        var data = await api('POST', '/members/reset-password', {
            action: 'verify-otp', email: resetEmailValue, otp: code
        });
        resetToken = data.resetToken;
        $('reset-step-2').hidden = true;
        $('reset-step-3').hidden = false;
    } catch (err) {
        $('reset-otp-error').textContent = err.message || 'Invalid code.';
    } finally {
        hideLoading();
    }
};

if ($('reset-password-form')) $('reset-password-form').onsubmit = async function(e) {
    e.preventDefault();
    $('reset-password-error').textContent = '';
    var pw = $('reset-new-password').value;
    var cpw = $('reset-confirm-password').value;
    if (pw.length < 8) { $('reset-password-error').textContent = 'Password must be at least 8 characters.'; return; }
    if (pw !== cpw) { $('reset-password-error').textContent = 'Passwords do not match.'; return; }

    try {
        showLoading();
        await api('POST', '/members/reset-password', {
            action: 'set-password', resetToken: resetToken, password: pw, confirmPassword: cpw
        });
        notify('Password reset successful! Please log in.', 'success');
        showView('login');
    } catch (err) {
        $('reset-password-error').textContent = err.message || 'Reset failed.';
    } finally {
        hideLoading();
    }
};

// ============================================================
// Dashboard - Accounts
// ============================================================

var allAccounts = [];
async function loadAccounts() {
    try {
        showLoading();
        var data = await api('GET', '/members/accounts');
        allAccounts = data.accounts || [];
        renderAccounts(allAccounts);
        // Update header with tier and token info
        if (data.tier) {
            var badge = $('header-tier-badge');
            if (badge) {
                var tierNames = {free:'Free',growth:'Growth',scale:'Scale'};
                badge.textContent = tierNames[data.tier] || data.tier;
                if (data.tier === 'growth') badge.style.background = '#dbeafe';
                if (data.tier === 'scale') badge.style.background = '#ede9fe';
            }
            var upgradeBtn = $('header-upgrade-btn');
            if (upgradeBtn && data.tier !== 'free') upgradeBtn.style.display = 'none';
        }
        if (data.tokens) {
            var tokenEl = $('header-token-count');
            if (tokenEl) tokenEl.textContent = data.tokens.remaining + '/' + data.tokens.total;
            sessionStorage.setItem('memberTokens', JSON.stringify(data.tokens));
            sessionStorage.setItem('memberTier', data.tier || 'free');
        }
    } catch (err) {
        notify('Failed to load accounts.', 'error');
    } finally {
        hideLoading();
    }
}

function renderAccounts(accounts) {
    accountsTbody.innerHTML = '';
    if (!accounts.length) {
        accountsEmpty.hidden = false;
        return;
    }
    accountsEmpty.hidden = true;
    accounts.forEach(function(a, idx) {
        var statusClass = 'status-' + (a.connectionStatus || 'pending');
        var hourlyBadge = a.connectionStatus === 'connected'
            ? (a.hourlyEnabled
                ? '<span title="Hourly granularity enabled" style="color:#16a34a;font-size:11px;margin-left:4px;">⏱✓</span>'
                : '<span title="Hourly granularity not enabled — click ⏱ to enable" style="color:#d97706;font-size:11px;margin-left:4px;">⏱✗</span>')
            : '';
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td style="color:#999;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + esc(a.accountId || '') + '</td>' +
            '<td>' + esc(a.accountName || '-') + '</td>' +
            '<td>' + esc(a.roleName || '') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + esc(a.connectionStatus || 'pending') + '</span>' + hourlyBadge + '</td>' +
            '<td>' + fmtDate(a.addedAt) + '</td>' +
            '<td>' + fmtDate(a.lastTestedAt) + '</td>' +
            '<td class="actions-cell">' +
                (idx > 0 ? '<button class="btn btn-outline btn-sm" data-a="up" data-id="' + ea(a.accountId) + '" title="Move Up" style="padding:2px 6px;font-size:12px;min-width:28px;">▲</button> ' : '<span style="display:inline-block;width:32px;"></span> ') +
                (idx < accounts.length - 1 ? '<button class="btn btn-outline btn-sm" data-a="down" data-id="' + ea(a.accountId) + '" title="Move Down" style="padding:2px 6px;font-size:12px;min-width:28px;">▼</button> ' : '<span style="display:inline-block;width:32px;"></span> ') +
                '<button class="btn-icon btn-icon-download" data-a="dl" data-id="' + ea(a.accountId) + '" title="Download CF Template">&#8681;</button> ' +
                '<button class="btn-icon btn-icon-test" data-a="test" data-id="' + ea(a.accountId) + '" title="Test Connection">&#9889;</button> ' +
                '<button class="btn-icon" data-a="hourly" data-id="' + ea(a.accountId) + '" title="Enable Hourly Cost Data" style="font-size:11px;">&#9201;</button> ' +
                '<button class="btn-icon btn-icon-edit" data-a="edit" data-id="' + ea(a.accountId) + '" title="Edit">&#9998;</button> ' +
                '<button class="btn-icon btn-icon-delete" data-a="del" data-id="' + ea(a.accountId) + '" title="Delete">&#128465;</button>' +
            '</td>';
        accountsTbody.appendChild(tr);
    });
}

// ============================================================
// Account table actions
// ============================================================

accountsTbody.onclick = function(e) {
    var btn = e.target.closest('[data-a]');
    if (!btn) return;
    var action = btn.dataset.a;
    var accountId = btn.dataset.id;

    if (action === 'edit') showAccountModal(accountId);
    else if (action === 'del') showDeleteDialog(accountId);
    else if (action === 'dl') downloadTemplate(accountId);
    else if (action === 'test') testConnection(accountId, btn);
    else if (action === 'up' || action === 'down') reorderAccount(accountId, action);
    else if (action === 'hourly') showEnableHourlyModal(accountId);
};

async function reorderAccount(accountId, direction) {
    var ids = allAccounts.filter(function(a) { return true; }).map(function(a) { return a.accountId; });
    var idx = ids.indexOf(accountId);
    if (idx === -1) return;
    var swapIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= ids.length) return;
    var tmp = ids[idx]; ids[idx] = ids[swapIdx]; ids[swapIdx] = tmp;
    try {
        await api('POST', '/members/accounts/reorder', { order: ids });
        // Update local order
        var tmpAcct = allAccounts[idx];
        allAccounts[idx] = allAccounts[swapIdx];
        allAccounts[swapIdx] = tmpAcct;
        renderAccounts(allAccounts);
        populateAIAccounts();
    } catch (err) {
        notify('Failed to reorder accounts.', 'error');
    }
}

// ============================================================
// Add / Edit Account Modal
// ============================================================

addAccountBtn.onclick = function() { showAccountModal(null); };

function showAccountModal(existingId) {
    accountFormError.textContent = '';
    editingAccountId = existingId;
    if (existingId) {
        var existing = allAccounts.find(function(a) { return a.accountId === existingId; }) || {};
        accountModalTitle.textContent = 'Edit Account';
        accountSubmitBtn.textContent = 'Update Account';
        accountIdInput.value = existingId;
        accountIdInput.placeholder = 'New 12-digit Account ID';
        if (accountNameInput) accountNameInput.value = existing.accountName || '';
    } else {
        accountModalTitle.textContent = 'Add Account';
        accountSubmitBtn.textContent = 'Add Account';
        accountIdInput.value = '';
        accountIdInput.placeholder = '123456789012';
        if (accountNameInput) accountNameInput.value = '';
    }
    accountModal.hidden = false;
    accountIdInput.focus();
}

function hideAccountModal() { accountModal.hidden = true; editingAccountId = null; }

accountCancelBtn.onclick = hideAccountModal;
accountModalClose.onclick = hideAccountModal;
accountModal.onclick = function(e) { if (e.target === accountModal) hideAccountModal(); };

accountForm.onsubmit = async function(e) {
    e.preventDefault();
    accountFormError.textContent = '';
    var val = accountIdInput.value.trim();
    var accountName = accountNameInput ? accountNameInput.value.trim() : '';
    if (!/^\d{12}$/.test(val)) {
        accountFormError.textContent = 'Account ID must be exactly 12 digits.';
        return;
    }

    try {
        showLoading();
        if (editingAccountId) {
            await api('PUT', '/members/accounts', { oldAccountId: editingAccountId, newAccountId: val, accountName: accountName });
            notify('Account updated.', 'success');
        } else {
            await api('POST', '/members/accounts', { accountId: val, accountName: accountName });
            notify('Account added.', 'success');
        }
        hideAccountModal();
        await loadAccounts();
    } catch (err) {
        accountFormError.textContent = err.message || 'Failed.';
    } finally {
        hideLoading();
    }
};

// ============================================================
// Delete Account
// ============================================================

function showDeleteDialog(accountId) {
    deletingAccountId = accountId;
    deleteMsg.textContent = 'Delete account ' + accountId + '? This cannot be undone.';
    deleteConfirmBtn.hidden = false;
    deleteCancelBtn.textContent = 'Cancel';
    deleteDialog.hidden = false;
}

function hideDeleteDialog() { deleteDialog.hidden = true; deletingAccountId = null; }

deleteCancelBtn.onclick = hideDeleteDialog;
deleteDialog.onclick = function(e) { if (e.target === deleteDialog) hideDeleteDialog(); };

deleteConfirmBtn.onclick = async function() {
    if (!deletingAccountId) return;
    deleteConfirmBtn.disabled = true;
    deleteConfirmBtn.textContent = 'Deleting...';
    try {
        const result = await api('DELETE', '/members/accounts', { accountId: deletingAccountId });
        hideDeleteDialog();
        await loadAccounts();
        if (result.warning) {
            // Stack couldn't be auto-deleted (old role template) — show actionable message
            notify(result.warning, 'warning', 12000);
        } else {
            notify('Account disconnected and AWS stack deleted.', 'success');
        }
    } catch (err) {
        deleteMsg.textContent = 'Error: ' + (err.message || 'Delete failed.');
        deleteConfirmBtn.hidden = true;
        deleteCancelBtn.textContent = 'Close';
    } finally {
        deleteConfirmBtn.disabled = false;
        deleteConfirmBtn.textContent = 'Delete';
    }
};

// ============================================================
// Download CloudFormation Template
// ============================================================

async function downloadTemplate(accountId) {
    try {
        showLoading();
        var data = await api('POST', '/members/accounts/template', { accountId: accountId });
        var blob = new Blob([data.template], { type: 'application/x-yaml' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = data.filename || ('SlashMyBill-' + accountId + '.yaml');
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        notify('Template downloaded.', 'success');
    } catch (err) {
        notify(err.message || 'Failed to download template.', 'error');
    } finally {
        hideLoading();
    }
}

// ============================================================
// Test Connection
// ============================================================

async function testConnection(accountId, btn) {
    try {
        showLoading();
        var data = await api('POST', '/members/accounts/test', { accountId: accountId });
        var msg = data.message || 'Connection test complete.';
        notify(msg, 'success');
        await loadAccounts();
        // If hourly is not enabled, show the enable modal after a short delay
        if (data.hourlyEnabled === false) {
            setTimeout(function() {
                if (confirm('Hourly granularity is not enabled on this account.\n\nWould you like to see how to enable it for real-time cost tracking?')) {
                    showEnableHourlyModal(accountId);
                }
            }, 800);
        }
    } catch (err) {
        notify(err.message || 'Connection test failed.', 'error');
        await loadAccounts();
    } finally {
        hideLoading();
    }
}

// ============================================================
// Init
// ============================================================

if (getToken()) {
    showView('dashboard');
} else {
    showView('login');
}

// ============================================================
// Setup Wizard
// ============================================================

var wizardModal = $('wizard-modal');
var wizardClose = $('wizard-close');
var wizStep1 = $('wiz-step-1');
var wizStep2 = $('wiz-step-2');
var wizStep3 = $('wiz-step-3');
var wizStep4 = $('wiz-step-4');
var wizInd1 = $('wiz-ind-1');
var wizInd2 = $('wiz-ind-2');
var wizInd3 = $('wiz-ind-3');
var wizInd4 = $('wiz-ind-4');
var wizBackBtn = $('wiz-back-btn');
var wizNextBtn = $('wiz-next-btn');
var wizFinishBtn = $('wiz-finish-btn');
var wizDownloadBtn = $('wiz-download-btn');
var wizTestBtn = $('wiz-test-btn');
var wizTestResult = $('wiz-test-result');
var wizRoleName = $('wiz-role-name');
var wizStackName = $('wiz-stack-name');
var wizLaunchCfBtn = $('wiz-launch-cf-btn');
var wizAccountDisplay = $('wiz-account-display');
var wizStackName2 = $('wiz-stack-name-2');
var wizRoleName2 = $('wiz-role-name-2');
var wizardAccountId = null;
var wizardStep = 1;
var wizardTemplateDownloaded = false;
var wizardCfConsoleUrl = null;
var wizardCfUpdateUrl = null;
var wizardTemplateYaml = null;
var wizardFilename = null;

function showWizard(accountId) {
    wizardAccountId = accountId;
    wizardStep = 1;
    wizardTemplateDownloaded = false;
    wizardCfConsoleUrl = null;
    wizardCfUpdateUrl = null;
    var roleName = 'SlashMyBill-' + accountId;
    var stackName = 'SlashMyBill-Access-' + accountId;
    wizRoleName.textContent = roleName;
    wizStackName.textContent = stackName;
    wizStackName2.textContent = stackName;
    wizRoleName2.textContent = roleName;
    wizAccountDisplay.textContent = accountId;
    wizTestResult.hidden = true;
    wizTestResult.className = 'wizard-test-result';
    wizLaunchCfBtn.href = '#';
    wizLaunchCfBtn.style.opacity = '0.5';
    wizLaunchCfBtn.style.pointerEvents = 'none';
    // Pre-fetch the template to get the CF console URL
    _fetchTemplate(accountId);
    updateWizardStep();
    wizardModal.hidden = false;
}

async function _fetchTemplate(accountId) {
    try {
        var data = await api('POST', '/members/accounts/template', { accountId: accountId });
        wizardTemplateYaml = data.template;
        wizardFilename = data.filename;
        wizardCfConsoleUrl = data.cfConsoleUrl;
        wizardCfUpdateUrl = data.cfUpdateUrl;
        if (wizardCfConsoleUrl) {
            wizLaunchCfBtn.href = wizardCfConsoleUrl;
            wizLaunchCfBtn.style.opacity = '1';
            wizLaunchCfBtn.style.pointerEvents = 'auto';
            wizardTemplateDownloaded = true;
        }
        // Show update button if update URL is available
        var updateBtn = document.getElementById('wiz-update-cf-btn');
        if (updateBtn && wizardCfUpdateUrl) {
            updateBtn.href = wizardCfUpdateUrl;
            updateBtn.hidden = false;
        }
    } catch (err) {
        notify(err.message || 'Failed to generate template.', 'error');
    }
}

function hideWizard() {
    wizardModal.hidden = true;
    wizardAccountId = null;
    loadAccounts();
}

function updateWizardStep() {
    wizStep1.hidden = wizardStep !== 1;
    wizStep2.hidden = wizardStep !== 2;
    wizStep3.hidden = wizardStep !== 3;
    if (wizStep4) wizStep4.hidden = wizardStep !== 4;

    wizInd1.className = 'wizard-step-indicator' + (wizardStep === 1 ? ' active' : wizardStep > 1 ? ' done' : '');
    wizInd2.className = 'wizard-step-indicator' + (wizardStep === 2 ? ' active' : wizardStep > 2 ? ' done' : '');
    wizInd3.className = 'wizard-step-indicator' + (wizardStep === 3 ? ' active' : wizardStep > 3 ? ' done' : '');
    if (wizInd4) wizInd4.className = 'wizard-step-indicator' + (wizardStep === 4 ? ' active' : '');

    wizBackBtn.hidden = wizardStep <= 1;
    wizNextBtn.hidden = wizardStep >= 4;
    wizFinishBtn.hidden = wizardStep < 4;
}

wizNextBtn.onclick = function() {
    if (wizardStep === 1 && !wizardTemplateDownloaded) {
        notify('Please download the template first.', 'error');
        return;
    }
    if (wizardStep < 4) {
        wizardStep++;
        updateWizardStep();
    }
};

wizBackBtn.onclick = function() {
    if (wizardStep > 1) {
        wizardStep--;
        updateWizardStep();
    }
};

wizFinishBtn.onclick = function() { hideWizard(); };
wizardClose.onclick = function() { hideWizard(); };
wizardModal.onclick = function(e) { if (e.target === wizardModal) hideWizard(); };

wizLaunchCfBtn.onclick = function() {
    if (wizardCfConsoleUrl) {
        wizardTemplateDownloaded = true;
    }
};

wizDownloadBtn.onclick = function() {
    if (!wizardTemplateYaml) {
        notify('Template not ready yet, please wait...', 'error');
        return;
    }
    var blob = new Blob([wizardTemplateYaml], { type: 'application/x-yaml' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = wizardFilename || ('SlashMyBill-' + wizardAccountId + '.yaml');
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    wizardTemplateDownloaded = true;
    notify('Template downloaded!', 'success');
};

wizTestBtn.onclick = async function() {
    if (!wizardAccountId) return;
    wizTestResult.hidden = true;
    try {
        showLoading();
        var data = await api('POST', '/members/accounts/test', { accountId: wizardAccountId });
        wizTestResult.hidden = false;
        wizTestResult.className = 'wizard-test-result test-success';
        var hourlyNote = data.hourlyEnabled
            ? ' <span style="color:#16a34a;">⏱✓ Hourly enabled</span>'
            : ' <span style="color:#d97706;">⏱✗ Hourly not enabled</span>';
        wizTestResult.innerHTML = '<strong>&#10003; Connection Successful!</strong>' + hourlyNote + '<br>' + (data.message || 'Cost data is accessible.');
        // Update hourly status section
        _updateWizHourlyStatus(data.hourlyEnabled);
    } catch (err) {
        wizTestResult.hidden = false;
        if (err.message && err.message.includes('Cost Explorer')) {
            wizTestResult.className = 'wizard-test-result test-partial';
        } else {
            wizTestResult.className = 'wizard-test-result test-failed';
        }
        wizTestResult.innerHTML = '<strong>&#10007; Connection Failed</strong><br>' + (err.message || 'Please check the CloudFormation stack.');
    } finally {
        hideLoading();
        await loadAccounts();
    }
};

function _updateWizHourlyStatus(enabled) {
    var statusDiv = $('wiz-hourly-status');
    if (!statusDiv) return;
    if (enabled === true) {
        statusDiv.innerHTML = '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:8px 12px;color:#16a34a;font-size:0.85em;">✓ Hourly granularity is <strong>enabled</strong> on this account.</div>';
    } else if (enabled === false) {
        statusDiv.innerHTML = '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:8px 12px;color:#92400e;font-size:0.85em;">✗ Not enabled yet. Click "Open CE Settings" above, enable "Hourly and Resource Level Data", then check again after 24–48 hours.</div>';
    } else {
        statusDiv.innerHTML = '';
    }
}

var wizCheckHourlyBtn = $('wiz-check-hourly-btn');
if (wizCheckHourlyBtn) {
    wizCheckHourlyBtn.onclick = async function() {
        if (!wizardAccountId) return;
        wizCheckHourlyBtn.disabled = true;
        wizCheckHourlyBtn.textContent = 'Checking...';
        try {
            var data = await api('POST', '/members/accounts/test', { accountId: wizardAccountId });
            _updateWizHourlyStatus(data.hourlyEnabled);
            await loadAccounts();
        } catch (err) {
            _updateWizHourlyStatus(null);
        } finally {
            wizCheckHourlyBtn.disabled = false;
            wizCheckHourlyBtn.textContent = 'Check Hourly Status';
        }
    };
}

// Override the add account flow to show wizard after adding
var _originalAccountFormSubmit = accountForm.onsubmit;
accountForm.onsubmit = async function(e) {
    e.preventDefault();
    accountFormError.textContent = '';
    var val = accountIdInput.value.trim();
    var accountName = accountNameInput ? accountNameInput.value.trim() : '';
    if (!/^\d{12}$/.test(val)) {
        accountFormError.textContent = 'Account ID must be exactly 12 digits.';
        return;
    }
    try {
        showLoading();
        if (editingAccountId) {
            await api('PUT', '/members/accounts', { oldAccountId: editingAccountId, newAccountId: val, accountName: accountName });
            notify('Account updated.', 'success');
            hideAccountModal();
            await loadAccounts();
        } else {
            await api('POST', '/members/accounts', { accountId: val, accountName: accountName });
            notify('Account added!', 'success');
            hideAccountModal();
            await loadAccounts();
            // Show the setup wizard for the new account
            showWizard(val);
        }
    } catch (err) {
        accountFormError.textContent = err.message || 'Failed.';
    } finally {
        hideLoading();
    }
};

// Also add a "Setup" button to the accounts table for pending accounts
var _originalRenderAccounts = renderAccounts;
renderAccounts = function(accounts) {
    accountsTbody.innerHTML = '';
    if (!accounts.length) {
        accountsEmpty.hidden = false;
        return;
    }
    accountsEmpty.hidden = true;
    accounts.forEach(function(a, idx) {
        var statusClass = 'status-' + (a.connectionStatus || 'pending');
        var setupBtn = (a.connectionStatus === 'pending' || a.connectionStatus === 'failed')
            ? '<button class="btn-icon btn-icon-test" data-a="setup" data-id="' + ea(a.accountId) + '" title="Setup Wizard" style="background:rgba(0,102,255,0.1);color:#0066ff;">&#9881;</button> '
            : '';
        var hourlyBadge2 = a.connectionStatus === 'connected'
            ? (a.hourlyEnabled
                ? '<span title="Hourly granularity enabled" style="color:#16a34a;font-size:11px;margin-left:4px;">⏱✓</span>'
                : '<span title="Hourly granularity not enabled — click ⏱ to enable" style="color:#d97706;font-size:11px;margin-left:4px;">⏱✗</span>')
            : '';
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td style="color:#999;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + esc(a.accountId || '') + '</td>' +
            '<td>' + esc(a.accountName || '-') + '</td>' +
            '<td>' + esc(a.roleName || '') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + esc(a.connectionStatus || 'pending') + '</span>' + hourlyBadge2 + '</td>' +
            '<td>' + fmtDate(a.addedAt) + '</td>' +
            '<td>' + fmtDate(a.lastTestedAt) + '</td>' +
            '<td class="actions-cell">' +
                setupBtn +
                '<button class="btn-icon btn-icon-download" data-a="dl" data-id="' + ea(a.accountId) + '" title="Download CF Template">&#8681;</button> ' +
                '<button class="btn-icon btn-icon-test" data-a="test" data-id="' + ea(a.accountId) + '" title="Test Connection">&#9889;</button> ' +
                '<button class="btn-icon" data-a="hourly" data-id="' + ea(a.accountId) + '" title="Enable Hourly Cost Data" style="font-size:11px;">&#9201;</button> ' +
                '<button class="btn-icon btn-icon-edit" data-a="edit" data-id="' + ea(a.accountId) + '" title="Edit">&#9998;</button> ' +
                '<button class="btn-icon btn-icon-delete" data-a="del" data-id="' + ea(a.accountId) + '" title="Delete">&#128465;</button>' +
            '</td>';
        accountsTbody.appendChild(tr);
    });
};

// Add setup action to the table click handler
var _originalTableClick = accountsTbody.onclick;
accountsTbody.onclick = function(e) {
    var btn = e.target.closest('[data-a]');
    if (!btn) return;
    var action = btn.dataset.a;
    var accountId = btn.dataset.id;

    if (action === 'setup') showWizard(accountId);
    else if (action === 'edit') showAccountModal(accountId);
    else if (action === 'del') showDeleteDialog(accountId);
    else if (action === 'dl') downloadTemplate(accountId);
    else if (action === 'test') testConnection(accountId, btn);
    else if (action === 'up' || action === 'down') reorderAccount(accountId, action);
    else if (action === 'hourly') showEnableHourlyModal(accountId);
};

// ============================================================
// Member Tabs
// ============================================================

document.querySelectorAll('.member-tab').forEach(function(tab) {
    tab.onclick = function() {
        activateMemberTab(tab.dataset.tab);
    };
});

function activateMemberTab(tabId) {
    document.querySelectorAll('.member-tab').forEach(function(t) {
        t.classList.toggle('active', t.dataset.tab === tabId);
    });
    document.querySelectorAll('.member-tab-content').forEach(function(c) {
        c.hidden = c.id !== tabId;
    });
    if (tabId === 'ai-tab') {
        _syncAccountSelection('dash'); // save dash selection before switching
        populateAIAccounts();
        _applySharedSelection('ai-acct-cb'); // apply shared selection to AI tab
    }
    if (tabId === 'dash-tab') {
        _syncAccountSelection('ai'); // save AI selection before switching
        console.log('Dashboard tab activated');
        populateDashAccounts();
        _applySharedSelection('dash-acct-cb'); // apply shared selection to dash tab
        loadDashboardData();
    }
    if (tabId === 'act-tab') {
        _syncAccountSelection('dash'); // save current selection
        populateActAccounts();
        _applySharedSelection('act-acct-cb'); // apply shared selection to Act tab
    }
}

// ============================================================
// Dashboard (Saved Queries + Visuals)
// ============================================================

function extractValues(text) {
    var matches = String(text || '').match(/-?\\d+(?:\\.\\d+)?/g) || [];
    return matches.slice(0, 8).map(function(v, idx) {
        return { label: 'V' + (idx + 1), value: Number(v) };
    }).filter(function(x) { return !isNaN(x.value); });
}

function buildChartConfigFromText(text) {
    var values = extractValues(text);
    if (!values.length) return null;
    return {
        type: 'bar',
        labels: values.map(function(v) { return v.label; }),
        data: values.map(function(v) { return v.value; }),
        datasetLabel: 'Values'
    };
}

function parseCsvNumbers(s) {
    return String(s || '').split(',').map(function(v) { return Number(v.trim()); }).filter(function(v) { return !isNaN(v); });
}

function parseCsvLabels(s) {
    return String(s || '').split(',').map(function(v) { return v.trim(); }).filter(Boolean);
}

function renderMiniGraph(values) {
    if (!values.length) return '<p>Provide numeric values in the answer to render a graph.</p>';
    var max = Math.max.apply(null, values.map(function(v) { return Math.abs(v.value); })) || 1;
    var rows = values.map(function(v) {
        var pct = Math.max(4, Math.round(Math.abs(v.value) / max * 100));
        return '<div class=\"mini-bar-row\"><span>' + esc(v.label) + '</span><div class=\"mini-bar\" style=\"width:' + pct + '%\"></div><strong>' + esc(String(v.value)) + '</strong></div>';
    }).join('');
    return '<div class=\"mini-bars\">' + rows + '</div>';
}

function renderMiniTable(values) {
    if (!values.length) return '<p>Provide numeric values in the answer to render a table.</p>';
    var rows = values.map(function(v) {
        return '<tr><td>' + esc(v.label) + '</td><td>' + esc(String(v.value)) + '</td></tr>';
    }).join('');
    return '<table class=\"mini-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function renderDashboard() {
    if (!dashboardGrid || !dashboardEmpty) return;
    dashboardCharts.forEach(function(ch) { try { ch.dispose(); } catch (e) {} });
    dashboardCharts = [];
    dashboardGrid.innerHTML = '';
    dashboardEmpty.hidden = dashboardItems.length > 0;
    if (!dashboardItems.length) return;

    dashboardItems.forEach(function(item) {
        var card = document.createElement('div');
        card.className = 'dashboard-card';
        var values = extractValues(item.answer || '');
        var chartId = 'dash-chart-' + (item.id || Math.random().toString(36).slice(2));
        var visual = item.viewType === 'table'
            ? renderMiniTable(values)
            : '<canvas id="' + chartId + '" height="180"></canvas>';
        card.innerHTML =
            '<h3>' + esc(item.title || 'Saved Query') + '</h3>' +
            '<div class=\"dashboard-card-meta\">' + esc((item.viewType || 'graph').toUpperCase()) + ' • ' + esc(fmtDate(item.createdAt)) + '</div>' +
            '<p><strong>Request:</strong> ' + esc(item.prompt || '') + '</p>' +
            '<p><strong>Response:</strong> ' + esc(item.answer || '-') + '</p>' +
            visual +
            '<div class=\"dashboard-actions\"><button class=\"btn btn-outline btn-sm\" data-dashboard-del=\"' + ea(item.id || '') + '\">Delete</button></div>';
        dashboardGrid.appendChild(card);

        if (item.viewType !== 'table') {
            var cfg = item.chartConfig && item.chartConfig.labels && item.chartConfig.data
                ? item.chartConfig
                : buildChartConfigFromText(item.answer || '');
            var chartDiv = $(chartId);
            if (chartDiv && cfg && window.echarts) {
                var chart = echarts.init(chartDiv, 'dark');
                var dColors = ['#3b82f6','#22c55e','#f59e0b','#a855f7','#ef4444','#06b6d4'];
                var dLabels = cfg.labels || [];
                var dValues = cfg.data || [];
                var dOption = {
                    tooltip: { trigger: 'axis' },
                    xAxis: { type: 'category', data: dLabels, axisLabel: { color: '#8b949e', fontSize: 10 } },
                    yAxis: { type: 'value', axisLabel: { color: '#8b949e' } },
                    series: [{ type: cfg.type || 'bar', data: dValues.map(function(v,i) { return { value: v, itemStyle: { color: dColors[i%dColors.length] } }; }) }],
                    grid: { left: 50, right: 10, bottom: 30, top: 10 },
                };
                chart.setOption(dOption);
                dashboardCharts.push(chart);
            }
        }
    });
}

async function loadDashboard() {
    try {
        var data = await api('GET', '/members/dashboard');
        dashboardItems = Array.isArray(data.items) ? data.items : [];
        renderDashboard();
    } catch (err) {
        notify(err.message || 'Failed to load dashboard', 'error');
    }
}

async function addDashboardItem() {
    if (!dashboardViewType || !dashboardPromptInput) return;
    var payload = {
        viewType: dashboardViewType.value || 'graph',
        title: (dashboardTitleInput && dashboardTitleInput.value || '').trim(),
        prompt: dashboardPromptInput.value.trim(),
        answer: (dashboardAnswerInput && dashboardAnswerInput.value || '').trim(),
        accountId: (getSelectedAccountIds()[0]) || '',
    };
    if (dashboardChartConfigInput && dashboardChartConfigInput.value.trim()) {
        try {
            payload.chartConfig = JSON.parse(dashboardChartConfigInput.value.trim());
        } catch (e) {
            notify('Chart Config must be valid JSON.', 'error');
            return;
        }
    }
    if (!payload.prompt) {
        notify('Please describe what you want to visualize.', 'error');
        return;
    }
    try {
        await api('POST', '/members/dashboard', payload);
        if (dashboardPromptInput) dashboardPromptInput.value = '';
        if (dashboardTitleInput) dashboardTitleInput.value = '';
        if (dashboardAnswerInput) dashboardAnswerInput.value = '';
        if (dashboardChartConfigInput) dashboardChartConfigInput.value = '';
        notify('Saved to dashboard.', 'success');
        loadDashboard();
    } catch (err) {
        notify(err.message || 'Failed to save dashboard item', 'error');
    }
}

if (dashboardAddBtn) dashboardAddBtn.onclick = addDashboardItem;
if (dashboardGrid) dashboardGrid.onclick = async function(e) {
    var btn = e.target.closest('[data-dashboard-del]');
    if (!btn) return;
    var id = btn.getAttribute('data-dashboard-del');
    if (!id) return;
    try {
        await api('DELETE', '/members/dashboard', { id: id });
        notify('Dashboard item removed.', 'success');
        loadDashboard();
    } catch (err) {
        notify(err.message || 'Failed to delete dashboard item', 'error');
    }
};

// ============================================================
// Lab Area
// ============================================================

var labChat = $('lab-chat');
var labCommandInput = $('lab-command-input');
var labRunBtn = $('lab-run-btn');
var labAccountSelect = $('lab-account-select');

function populateLabAccounts() {
    if (!labAccountSelect) return;
    var current = labAccountSelect.value;
    labAccountSelect.innerHTML = '<option value="">Select an account...</option>';
    allAccounts.forEach(function(a) {
        if (a.connectionStatus === 'connected') {
            var opt = document.createElement('option');
            opt.value = a.accountId;
            opt.textContent = a.accountId + ' (' + (a.accountName || 'Account ' + a.accountId.slice(-4)) + ')';
            labAccountSelect.appendChild(opt);
        }
    });
    if (current) labAccountSelect.value = current;
}

function addLabMessage(type, content) {
    if (!labChat) return;
    // Remove welcome message if present
    var welcome = labChat.querySelector('.lab-welcome');
    if (welcome) welcome.remove();

    var div = document.createElement('div');
    div.className = 'lab-message';

    if (type === 'command') {
        div.innerHTML = '<div class="lab-msg-command">' + esc(content) + '</div>';
    } else if (type === 'output') {
        div.innerHTML = '<div class="lab-msg-output">' + esc(content) + '</div>';
    } else if (type === 'error') {
        div.innerHTML = '<div class="lab-msg-output lab-msg-error">' + esc(content) + '</div>';
    } else if (type === 'info') {
        div.innerHTML = '<div class="lab-msg-info">' + esc(content) + '</div>';
    }

    labChat.appendChild(div);
    labChat.scrollTop = labChat.scrollHeight;
}

async function runLabCommand() {
    var accountId = labAccountSelect.value;
    var command = labCommandInput.value.trim();

    if (!accountId) { notify('Please select an account first.', 'error'); return; }
    if (!command) return;

    addLabMessage('command', command);
    labCommandInput.value = '';
    addLabMessage('info', 'Running on account ' + accountId + '...');

    try {
        var data = await api('POST', '/members/accounts/execute', {
            accountId: accountId,
            command: command,
        });
        // Remove the "Running..." message
        var msgs = labChat.querySelectorAll('.lab-msg-info');
        if (msgs.length) msgs[msgs.length - 1].parentElement.remove();

        if (data.output && data.output.startsWith('ERROR:')) {
            addLabMessage('error', data.output);
        } else {
            addLabMessage('output', data.output || 'No output');
        }
    } catch (err) {
        var msgs2 = labChat.querySelectorAll('.lab-msg-info');
        if (msgs2.length) msgs2[msgs2.length - 1].parentElement.remove();
        addLabMessage('error', err.message || 'Command failed');
    }
}

if (labRunBtn) labRunBtn.onclick = runLabCommand;
if (labCommandInput) labCommandInput.onkeydown = function(e) {
    if (e.key === 'Enter') { e.preventDefault(); runLabCommand(); }
};

// Click example commands to populate input
if (labChat) labChat.onclick = function(e) {
    if (e.target.tagName === 'CODE' && e.target.closest('.lab-examples')) {
        labCommandInput.value = e.target.textContent;
        labCommandInput.focus();
    }
};

// ============================================================
// AI Agent
// ============================================================

var aiChat = $('ai-chat');
var aiQuestionInput = $('ai-question-input');
var aiAskBtn = $('ai-ask-btn');
var aiAccountSelect = $('ai-account-select');
var aiFontDecBtn = $('ai-font-dec');
var aiFontIncBtn = $('ai-font-inc');
var aiFontSize = 18;

// Shared account selection state across tabs
var _sharedSelectedAccounts = null; // null = use defaults

function _syncAccountSelection(source) {
    // Save current selection from the source selector
    var ids;
    if (source === 'dash') {
        ids = getDashSelectedAccountIds();
    } else if (source === 'act') {
        ids = getActSelectedAccountIds();
    } else {
        ids = getSelectedAccountIds();
    }
    if (ids.length > 0) _sharedSelectedAccounts = ids;
}

function _applySharedSelection(checkboxClass) {
    if (!_sharedSelectedAccounts) return;
    var cbs = document.querySelectorAll('.' + checkboxClass);
    cbs.forEach(function(cb) {
        cb.checked = _sharedSelectedAccounts.indexOf(cb.value) !== -1;
    });
}

function populateAIAccounts() {
    if (!aiAccountSelect) return;
    aiAccountSelect.innerHTML = '';
    var connected = allAccounts.filter(function(a) { return a.connectionStatus === 'connected'; });
    if (!connected.length) {
        aiAccountSelect.innerHTML = '<div style="color:#8b949e;font-size:0.85em;">No connected accounts</div>';
        return;
    }

    // Dropdown toggle button
    var toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn btn-outline btn-sm';
    toggleBtn.style.cssText = 'font-size:0.85em;padding:4px 12px;min-width:180px;text-align:left;position:relative;';
    function updateToggleLabel() {
        var checked = document.querySelectorAll('.ai-acct-cb:checked');
        if (checked.length === 0) toggleBtn.textContent = 'Select accounts...';
        else if (checked.length === 1) toggleBtn.textContent = checked[0].parentElement.dataset.label || checked[0].value;
        else toggleBtn.textContent = checked.length + ' accounts selected';
        toggleBtn.textContent += ' ▾';
    }

    // Dropdown panel
    var panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;top:100%;left:0;z-index:200;background:#fff;border:1px solid #d0d7de;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);min-width:260px;max-height:200px;overflow-y:auto;padding:6px 0;margin-top:4px;';

    connected.forEach(function(a, idx) {
        var row = document.createElement('label');
        row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;color:#24292f;font-size:0.85em;white-space:nowrap;';
        row.dataset.label = a.accountId + ' (' + (a.accountName || 'Account') + ')';
        row.onmouseenter = function() { row.style.background = '#f6f8fa'; };
        row.onmouseleave = function() { row.style.background = ''; };
        var cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = a.accountId;
        cb.className = 'ai-acct-cb';
        if (idx === 0) cb.checked = true;
        cb.style.cssText = 'accent-color:#6366f1;flex-shrink:0;';
        cb.onchange = updateToggleLabel;
        row.appendChild(cb);
        row.appendChild(document.createTextNode(a.accountId + ' (' + (a.accountName || 'Account ' + a.accountId.slice(-4)) + ')'));
        panel.appendChild(row);
    });

    // Select All / None row
    var ctrlRow = document.createElement('div');
    ctrlRow.style.cssText = 'display:flex;gap:8px;padding:6px 12px;border-top:1px solid #d0d7de;margin-top:4px;';
    var selAll = document.createElement('a');
    selAll.href = '#'; selAll.textContent = 'Select All';
    selAll.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selAll.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.ai-acct-cb').forEach(function(c) { c.checked = true; }); updateToggleLabel(); };
    var selNone = document.createElement('a');
    selNone.href = '#'; selNone.textContent = 'Clear';
    selNone.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selNone.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.ai-acct-cb').forEach(function(c) { c.checked = false; }); updateToggleLabel(); };
    ctrlRow.appendChild(selAll);
    ctrlRow.appendChild(selNone);
    panel.appendChild(ctrlRow);

    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;display:inline-block;';
    wrapper.appendChild(toggleBtn);
    wrapper.appendChild(panel);
    aiAccountSelect.appendChild(wrapper);

    toggleBtn.onclick = function(e) {
        e.stopPropagation();
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    };
    document.addEventListener('click', function(e) {
        if (!wrapper.contains(e.target)) panel.style.display = 'none';
    });

    updateToggleLabel();
}

function getSelectedAccountIds() {
    var cbs = document.querySelectorAll('.ai-acct-cb:checked');
    var ids = [];
    cbs.forEach(function(cb) { ids.push(cb.value); });
    return ids;
}

function addAIMessage(type, content, topServices) {
    if (!aiChat) return;
    var welcome = aiChat.querySelector('.lab-welcome');
    if (welcome) welcome.remove();
    // Also hide the welcome screen if it's still visible
    var welcomeScreen = $('ai-welcome-screen');
    if (welcomeScreen) welcomeScreen.style.display = 'none';

    var div = document.createElement('div');
    div.className = 'lab-message';

    if (type === 'question') {
        div.innerHTML = '<div class="lab-msg-command" style="color:#a78bfa;">' + esc(content) + '</div>';
    } else if (type === 'answer') {
        // Render markdown-like formatting
        var formatted = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n- /g, '\n• ')
            .replace(/\n/g, '<br>');
        var questionText = aiQuestionInput && aiQuestionInput.dataset.lastQuestion ? aiQuestionInput.dataset.lastQuestion : '';

        // Generate drill-down follow-up suggestions based on the QUESTION context, not just answer content
        var followUps = [];
        var answerLower = content.toLowerCase();
        var questionLower = questionText.toLowerCase();

        // Detect if this was a comparison/trend question
        var isComparison = questionLower.indexOf('compare') !== -1 || questionLower.indexOf('month') !== -1 ||
            questionLower.indexOf('trend') !== -1 || questionLower.indexOf('last') !== -1 ||
            questionLower.indexOf('חודש') !== -1 || questionLower.indexOf('תשווה') !== -1;

        // Detect if this was an efficiency/savings question
        var isEfficiency = questionLower.indexOf('efficient') !== -1 || questionLower.indexOf('save') !== -1 ||
            questionLower.indexOf('waste') !== -1 || questionLower.indexOf('don\'t need') !== -1 ||
            questionLower.indexOf('reduce') !== -1 || questionLower.indexOf('optimize') !== -1;

        if (isComparison) {
            // Comparison-context drill-downs
            followUps.push('What caused the biggest cost increase?');
            followUps.push('Which services are trending up?');
            followUps.push('How efficient is my account?');
            followUps.push('Where can I save money?');
        } else if (isEfficiency) {
            // Efficiency-context drill-downs
            if (answerLower.indexOf('ebs') !== -1) followUps.push('List my unattached EBS volumes with sizes');
            if (answerLower.indexOf('vpc') !== -1) followUps.push('List all my VPC endpoints with costs');
            if (answerLower.indexOf('kms') !== -1) followUps.push('List my KMS keys and which are unused');
            if (answerLower.indexOf('lambda') !== -1) followUps.push('List unused Lambda functions I can delete');
            if (followUps.length < 2) followUps.push('Compare my costs over the last 3 months');
        } else {
            // General/specific question drill-downs based on answer content
            if (answerLower.indexOf('ebs') !== -1 || answerLower.indexOf('volume') !== -1)
                followUps.push('List my unattached EBS volumes with sizes');
            if (answerLower.indexOf('nat gateway') !== -1)
                followUps.push('Show my NAT Gateways and their VPCs');
            if (answerLower.indexOf('vpc endpoint') !== -1 || answerLower.indexOf('vpc') !== -1)
                followUps.push('List all my VPC endpoints with costs');
            if (answerLower.indexOf('elastic ip') !== -1)
                followUps.push('Show my unattached Elastic IPs');
            if (answerLower.indexOf('kms') !== -1 || answerLower.indexOf('key management') !== -1)
                followUps.push('List my KMS keys and which are unused');
            if (answerLower.indexOf('rds') !== -1 || answerLower.indexOf('database') !== -1)
                followUps.push('Show my RDS instances with RI pricing comparison');
            if (answerLower.indexOf('ec2') !== -1 && answerLower.indexOf('instance') !== -1)
                followUps.push('List my EC2 instances with rightsizing recommendations');
            if (answerLower.indexOf('s3') !== -1 || answerLower.indexOf('storage') !== -1)
                followUps.push('Analyze my S3 buckets for storage class optimization');
            if (answerLower.indexOf('route 53') !== -1 || answerLower.indexOf('hosted zone') !== -1)
                followUps.push('List my Route 53 hosted zones with record counts');
            if (answerLower.indexOf('lambda') !== -1 || answerLower.indexOf('invocation') !== -1 || answerLower.indexOf('function') !== -1) {
                if (answerLower.indexOf('error') !== -1)
                    followUps.push('Which Lambda functions have errors?');
                if (answerLower.indexOf('duration') !== -1 || answerLower.indexOf('timeout') !== -1)
                    followUps.push('Which Lambda functions are slow or hitting timeouts?');
                if (answerLower.indexOf('0 invocation') !== -1 || answerLower.indexOf('deletion') !== -1)
                    followUps.push('List unused Lambda functions I can delete');
            }
        }

        // Limit to 4 most relevant follow-ups
        followUps = followUps.slice(0, 4);

        // Generate service-based follow-up topics from the actual bill
        var serviceTopics = [];
        var svcTopicMap = {
            'Amazon Relational Database Service': 'Is my RDS right-sized? Show CPU and pricing options',
            'Amazon Elastic Compute Cloud - Compute': 'Are my EC2 instances right-sized? Show Savings Plan options',
            'EC2 - Other': 'Break down my EC2-Other costs (EBS, NAT, data transfer)',
            'Amazon Virtual Private Cloud': 'Break down my VPC costs and find idle resources',
            'Amazon Elastic Load Balancing': 'Are any of my load balancers idle or underused?',
            'AWS Key Management Service': 'List my KMS keys and which are unused',
            'Amazon Simple Storage Service': 'Analyze my S3 buckets for storage class optimization',
            'AWS Lambda': 'Show my Lambda functions with invocation counts and errors',
            'AmazonCloudWatch': 'Can I reduce my CloudWatch costs?',
            'Amazon Route 53': 'List my Route 53 hosted zones with record counts',
            'Amazon CloudFront': 'How can I optimize my CloudFront cache hit ratio?',
            'Amazon ElastiCache': 'Is my ElastiCache right-sized? Show CPU and memory usage',
            'Amazon DynamoDB': 'Should my DynamoDB tables use on-demand or provisioned capacity?',
            'Amazon Elastic Container Service': 'Show my ECS clusters with running tasks and utilization',
            'Amazon Elastic Kubernetes Service': 'Show my EKS clusters with status and version',
            'AWS Secrets Manager': 'How many secrets do I have and can I consolidate?',
            'Amazon Elastic Block Store': 'List my EBS volumes with IOPS usage and rightsizing',
            'Amazon Elastic Container Registry (ECR)': 'Can I clean up old ECR images to save storage?',
            'AWS Config': 'Can I reduce AWS Config costs by limiting recorded resources?',
            'Amazon GuardDuty': 'What is my GuardDuty finding volume and cost breakdown?',
            'AWS Security Hub': 'Can I optimize Security Hub by disabling unused standards?',
            'Amazon Bedrock': 'What is my Bedrock model usage and cost per invocation?',
        };
        if (topServices && topServices.length > 0) {
            topServices.forEach(function(svc) {
                var topic = svcTopicMap[svc.service];
                if (topic && followUps.indexOf(topic) === -1) {
                    serviceTopics.push({question: topic, service: svc.service, cost: svc.cost});
                }
            });
        }

        var followUpHtml = '';
        if (followUps.length > 0) {
            followUpHtml = '<div class="ai-followups" style="margin-top:12px;"><div style="color:#8b949e;font-size:0.85em;margin-bottom:6px;">Drill down:</div>';
            followUps.forEach(function(q) {
                followUpHtml += '<button class="btn btn-outline btn-sm ai-followup-btn" style="margin:3px 4px 3px 0;font-size:0.85em;" data-question="' + ea(q) + '">' + esc(q) + '</button>';
            });
            followUpHtml += '</div>';
        }

        // Service-based follow-up topics from the bill
        if (serviceTopics.length > 0) {
            followUpHtml += '<div class="ai-service-topics" style="margin-top:10px;"><div style="color:#8b949e;font-size:0.85em;margin-bottom:6px;">Explore your services:</div>';
            serviceTopics.slice(0, 6).forEach(function(st) {
                followUpHtml += '<button class="btn btn-outline btn-sm ai-followup-btn" style="margin:3px 4px 3px 0;font-size:0.8em;border-color:#4c1d95;color:#a78bfa;" data-question="' + ea(st.question) + '" title="$' + st.cost + '/month">' + esc(st.question) + '</button>';
            });
            followUpHtml += '</div>';
        }

        div.innerHTML =
            '<div class="lab-msg-output" style="color:#e2e8f0;border-color:#4c1d95;position:relative;">' +
            '<button class="ai-copy-btn" title="Copy to clipboard" style="position:absolute;top:6px;right:6px;background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;cursor:pointer;padding:3px 6px;font-size:0.75em;">📋 Copy</button>' +
            formatted + '</div>' +
            followUpHtml +
            '<div class="ai-feedback-widget" style="margin-top:10px;padding:8px 0;border-top:1px solid #30363d;">' +
                '<span style="color:#8b949e;font-size:0.85em;margin-right:8px;">Did this help you?</span>' +
                '<button class="ai-fb-btn ai-fb-up" title="Helpful" style="background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;cursor:pointer;padding:4px 10px;font-size:1em;margin-right:4px;">👍</button>' +
                '<button class="ai-fb-btn ai-fb-down" title="Not helpful" style="background:#21262d;border:1px solid #30363d;border-radius:4px;color:#8b949e;cursor:pointer;padding:4px 10px;font-size:1em;">👎</button>' +
                '<div class="ai-fb-correction" style="display:none;margin-top:8px;">' +
                    '<input type="text" class="ai-fb-correction-input" placeholder="What was missing or incorrect?" style="background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:8px 10px;color:#c9d1d9;font-size:0.85em;width:70%;margin-right:6px;">' +
                    '<button class="ai-fb-correction-submit btn btn-primary btn-sm" style="font-size:0.8em;">Submit</button>' +
                '</div>' +
                '<div class="ai-fb-status" style="display:none;color:#7ee787;font-size:0.85em;margin-top:6px;"></div>' +
            '</div>' +
            '<div class="ai-table-area"></div>';
    } else if (type === 'commands') {
        var cmdsHtml = '<div class="lab-msg-info" style="color:#7ee787;">Commands executed:</div>';
        content.forEach(function(c) {
            cmdsHtml += '<div class="lab-msg-command" style="color:#58a6ff;">$ ' + esc(c) + '</div>';
        });
        div.innerHTML = cmdsHtml;
    } else if (type === 'thinking') {
        div.innerHTML = '<div class="lab-msg-info" style="color:#a78bfa;"><img src="../smallninja2.png" alt="" style="height:32px;vertical-align:middle;margin-right:4px;"> ' + esc(content) + '</div>';
        div.id = 'ai-thinking';
    } else if (type === 'error') {
        div.innerHTML = '<div class="lab-msg-output lab-msg-error">' + esc(content) + '</div>';
    } else if (type === 'chartOptions') {
        // Deprecated — chart options are now part of the answer message
        div.innerHTML = '';
    }

    aiChat.appendChild(div);
    aiChat.scrollTop = aiChat.scrollHeight;
}

async function askAI() {
    if (!aiAccountSelect || !aiQuestionInput) return;
    var accountIds = getSelectedAccountIds();
    var question = aiQuestionInput.value.trim();

    if (!accountIds.length) { notify('Please select at least one account.', 'error'); return; }
    if (!question) return;

    var acctLabel = accountIds.length === 1 ? accountIds[0] : accountIds.length + ' accounts';
    addAIMessage('question', question + (accountIds.length > 1 ? ' [' + acctLabel + ']' : ''));
    aiQuestionInput.dataset.lastQuestion = question;
    aiQuestionInput.value = '';
    addAIMessage('thinking', 'Analyzing ' + acctLabel + '...');

    try {
        var data = await api('POST', '/members/accounts/ai-query', {
            accountIds: accountIds,
            question: question,
        });

        // Remove thinking message
        var thinking = $('ai-thinking');
        if (thinking) thinking.remove();

        // Show commands that were executed
        if (data.commands && data.commands.length > 0) {
            addAIMessage('commands', data.commands);
        }

        // Show the AI answer
        addAIMessage('answer', data.answer || 'No answer available.', data.topServices || []);

        // Store interactionId on the last answer message for feedback
        if (data.interactionId) {
            var lastAnswerMsg = aiChat.querySelector('.lab-message:last-child');
            if (lastAnswerMsg) {
                lastAnswerMsg.setAttribute('data-interaction-id', data.interactionId);
            }
        }

        // Attach chartData to the last answer message for table+chart flow
        if (data.chartData && data.chartData.length > 0) {
            var lastMsg = aiChat.querySelector('.lab-message:last-child');
            if (lastMsg) {
                // Reorder charts based on question context
                var sortedCharts = data.chartData.slice();
                var qLower = (aiQuestionInput && aiQuestionInput.dataset.lastQuestion || '').toLowerCase();
                var isCompQ = qLower.indexOf('compare') !== -1 || qLower.indexOf('month') !== -1 ||
                    qLower.indexOf('trend') !== -1 || qLower.indexOf('last') !== -1;

                // Filter out irrelevant charts for specific service questions
                // KMS, S3 lifecycle, Lambda, snapshots etc. don't need cost/daily/efficiency tables
                var isSpecificServiceQ = (
                    qLower.indexOf('kms') !== -1 || qLower.indexOf('encryption key') !== -1 ||
                    qLower.indexOf('lifecycle') !== -1 || qLower.indexOf('bucket') !== -1 ||
                    qLower.indexOf('snapshot') !== -1 || qLower.indexOf('elastic ip') !== -1 ||
                    qLower.indexOf('nat gateway') !== -1 || qLower.indexOf('vpc endpoint') !== -1 ||
                    qLower.indexOf('budget') !== -1 || qLower.indexOf('cost alert') !== -1 ||
                    qLower.indexOf('billing alarm') !== -1
                );
                if (isSpecificServiceQ) {
                    // Only keep charts directly relevant to the question
                    sortedCharts = sortedCharts.filter(function(c) {
                        var id = (c.id || '').toLowerCase();
                        var title = (c.title || '').toLowerCase();
                        // Always exclude generic cost/daily/efficiency for specific service questions
                        if (id === 'cost-by-service' || id === 'daily-cost-trend' || id === 'cost-efficiency-score') return false;
                        if (title.indexOf('cost by service') !== -1 || title.indexOf('daily cost') !== -1 || title.indexOf('efficiency score') !== -1) return false;
                        return true;
                    });
                }

                if (isCompQ) {
                    // Put monthly trend/comparison charts first
                    sortedCharts.sort(function(a, b) {
                        var aScore = (a.id || '').indexOf('monthly') !== -1 || (a.id || '').indexOf('comparison') !== -1 ? 0 : 1;
                        var bScore = (b.id || '').indexOf('monthly') !== -1 || (b.id || '').indexOf('comparison') !== -1 ? 0 : 1;
                        return aScore - bScore;
                    });
                }
                lastMsg.dataset.chartData = JSON.stringify(sortedCharts);
                // Add "Show as Table" buttons in the table area
                var tableArea = lastMsg.querySelector('.ai-table-area');
                if (tableArea) {
                    // Also parse comparison tables from the AI answer text
                    var answerText = data.answer || '';
                    if (answerText.indexOf('|') !== -1 && (isCompQ || answerText.indexOf('Comparison') !== -1 || answerText.indexOf('vs') !== -1 || answerText.indexOf('Jan') !== -1 || answerText.indexOf('Feb') !== -1 || answerText.indexOf('Mar') !== -1)) {
                        // Check if a month-comparison or monthly-trend chart already exists
                        var hasCompChart = sortedCharts.some(function(c) { return c.id === 'month-comparison' || c.id === 'monthly-service-trend'; });
                        if (!hasCompChart) {
                            // Parse markdown table from answer
                            var lines = answerText.split('\n').filter(function(l) { return l.trim().indexOf('|') === 0; });
                            if (lines.length >= 3) {
                                var headerCells = lines[0].split('|').map(function(c) { return c.trim(); }).filter(Boolean);
                                var dataRows = [];
                                for (var ri = 2; ri < lines.length; ri++) {
                                    var cells = lines[ri].split('|').map(function(c) { return c.trim(); }).filter(Boolean);
                                    if (cells.length >= 2) dataRows.push(cells);
                                }
                                if (dataRows.length > 0 && headerCells.length >= 3) {
                                    // Detect how many month columns (columns with USD/numbers, excluding Difference/% Change)
                                    var monthCols = [];
                                    for (var hi = 1; hi < headerCells.length; hi++) {
                                        var hdr = headerCells[hi].toLowerCase();
                                        if (hdr.indexOf('difference') === -1 && hdr.indexOf('%') === -1 && hdr.indexOf('change') === -1) {
                                            monthCols.push({ idx: hi, label: headerCells[hi].replace(' (USD)', '') });
                                        }
                                    }
                                    if (monthCols.length >= 2) {
                                        var compLabels = dataRows.map(function(r) { return r[0].replace('Amazon ', '').replace('AWS ', '').substring(0, 25); });
                                        if (monthCols.length === 2) {
                                            // 2-month comparison
                                            var compChart = {
                                                id: 'answer-comparison',
                                                title: monthCols[0].label + ' vs ' + monthCols[1].label,
                                                type: 'bar',
                                                labels: compLabels,
                                                data: dataRows.map(function(r) { var v = parseFloat((r[monthCols[0].idx] || '').replace(/[^0-9.\-]/g, '')); return isNaN(v) ? 0 : v; }),
                                                data2: dataRows.map(function(r) { var v = parseFloat((r[monthCols[1].idx] || '').replace(/[^0-9.\-]/g, '')); return isNaN(v) ? 0 : v; }),
                                                dataLabel: monthCols[0].label,
                                                data2Label: monthCols[1].label,
                                                color: '#6366f1',
                                                color2: '#10b981',
                                            };
                                            sortedCharts.unshift(compChart);
                                        } else {
                                            // 3+ month comparison — use monthColumns format
                                            var mcols = {};
                                            var mnames = [];
                                            monthCols.forEach(function(mc) {
                                                mnames.push(mc.label);
                                                mcols[mc.label] = dataRows.map(function(r) { var v = parseFloat((r[mc.idx] || '').replace(/[^0-9.\-]/g, '')); return isNaN(v) ? 0 : v; });
                                            });
                                            var compChart = {
                                                id: 'answer-comparison',
                                                title: mnames.join(' vs '),
                                                type: 'bar',
                                                labels: compLabels,
                                                monthColumns: mcols,
                                                months: mnames,
                                                data: dataRows.map(function(r) { var v = parseFloat((r[1] || '').replace(/[^0-9.\-]/g, '')); return isNaN(v) ? 0 : v; }),
                                            };
                                            sortedCharts.unshift(compChart);
                                        }
                                        lastMsg.dataset.chartData = JSON.stringify(sortedCharts);
                                    }
                                }
                            }
                        }
                    }

                    var html = sortedCharts.length > 0
                        ? '<div style="color:#8b949e;font-size:0.85em;margin-bottom:6px;margin-top:12px;">Show as table:</div>'
                        : '';
                    sortedCharts.forEach(function(cd, idx) {
                        html += '<button class="btn btn-outline btn-sm ai-table-btn" style="margin:3px 4px 3px 0;font-size:0.85em;" data-chart-idx="' + idx + '">'
                            + '📋 ' + esc(cd.title) + '</button>';
                    });                    html += '<div class="ai-table-render-area"></div>';
                    tableArea.innerHTML = html;
                }
            }
        }

        if (data.tipFound) {
            addAIMessage('thinking', 'Tip found in knowledge base ✓');
            var tipNote = $('ai-thinking');
            if (tipNote) tipNote.id = '';
        }
    } catch (err) {
        var thinking2 = $('ai-thinking');
        if (thinking2) thinking2.remove();
        addAIMessage('error', err.message || 'AI query failed. Please try again.');
    }
}

if (aiAskBtn) aiAskBtn.onclick = askAI;
if (aiQuestionInput) aiQuestionInput.onkeydown = function(e) {
    if (e.key === 'Enter') { e.preventDefault(); askAI(); }
};

function applyAIFontSize() {
    if (aiChat) aiChat.style.fontSize = aiFontSize + 'px';
    if (aiQuestionInput) aiQuestionInput.style.fontSize = Math.max(14, aiFontSize - 1) + 'px';
}

var aiInlineCharts = [];

function renderSingleChart(container, cd, overrideType) {
    container.innerHTML = '';
    aiInlineCharts.forEach(function(c) { try { c.dispose(); } catch(e) {} });
    aiInlineCharts = [];

    var chartType = overrideType || cd.type || 'bar';

    var card = document.createElement('div');
    card.style.cssText = 'background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-top:8px;max-width:100%;';

    var title = document.createElement('div');
    title.style.cssText = 'color:#e2e8f0;font-size:0.9em;font-weight:600;margin-bottom:10px;';
    title.textContent = cd.title || 'Chart';
    card.appendChild(title);

    var chartDiv = document.createElement('div');
    var h = (chartType === 'doughnut' || chartType === 'pie') ? 280 : 220;
    chartDiv.style.cssText = 'width:100%;height:' + h + 'px;';
    card.appendChild(chartDiv);

    // Type toggle buttons
    var toggleRow = document.createElement('div');
    toggleRow.style.cssText = 'display:flex;gap:4px;margin-top:10px;flex-wrap:wrap;';
    var _isTS = cd.id === 'daily-trend' || cd.id === 'monthly-total-trend';
    var _isBD = cd.id === 'vpc-breakdown' || cd.id === 'ec2other-breakdown';
    var _isMM = cd.monthColumns && cd.months && cd.months.length > 1;
    var types;
    if (_isTS) types = [{key:'line',label:'📈 Line'},{key:'bar',label:'📊 Bar'}];
    else if (_isBD) types = [{key:'pie',label:'🥧 Pie'},{key:'bar',label:'📊 Bar'},{key:'treemap',label:'🗺️ Treemap'}];
    else if (_isMM) types = [{key:'bar',label:'📊 Grouped Bar'},{key:'line',label:'📈 Line'}];
    else types = [{key:'bar',label:'📊 Bar'},{key:'pie',label:'🥧 Pie'},{key:'line',label:'📈 Line'},{key:'treemap',label:'🗺️ Treemap'}];
    types.forEach(function(t) {
        var btn = document.createElement('button');
        btn.className = 'btn btn-outline btn-sm';
        btn.style.cssText = 'font-size:0.75em;padding:3px 8px;' + (t.key === chartType ? 'background:#4c1d95;color:#e2e8f0;border-color:#6d28d9;' : '');
        btn.textContent = t.label;
        btn.onclick = function() { renderSingleChart(container, cd, t.key); };
        toggleRow.appendChild(btn);
    });
    card.appendChild(toggleRow);
    container.appendChild(card);

    if (!window.echarts) { card.innerHTML += '<div style="color:#f85149;">ECharts not loaded.</div>'; return; }

    var chart = echarts.init(chartDiv, 'dark');
    aiInlineCharts.push(chart);

    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16'];
    var labels = cd.labels || [];
    var values = cd.data || [];
    var isCurrency = cd.isCurrency !== false;
    var fmt = function(v) { return isCurrency ? '$' + Number(v).toFixed(2) : Number(v).toLocaleString(); };

    var option = {};

    if (chartType === 'treemap') {
        var treeData = labels.map(function(l, i) { return { name: l, value: values[i] || 0 }; });
        option = {
            tooltip: { formatter: function(p) { return p.name + ': ' + fmt(p.value); } },
            series: [{ type: 'treemap', data: treeData, label: { show: true, formatter: '{b}', fontSize: 10 },
                breadcrumb: { show: false }, itemStyle: { borderColor: '#161b22', borderWidth: 2 } }]
        };
    } else if (chartType === 'pie' || chartType === 'doughnut') {
        var pieData = labels.map(function(l, i) { return { name: l, value: values[i] || 0 }; });
        option = {
            tooltip: { trigger: 'item', formatter: function(p) { return p.name + ': ' + fmt(p.value) + ' (' + p.percent + '%)'; } },
            legend: { type: 'scroll', orient: 'vertical', right: 10, top: 20, textStyle: { color: '#c9d1d9', fontSize: 10 } },
            series: [{ type: 'pie', radius: chartType === 'doughnut' ? ['40%','70%'] : ['0%','70%'],
                center: ['40%','50%'], data: pieData, label: { show: false },
                emphasis: { label: { show: true, fontSize: 12 } } }],
            color: colors,
        };
    } else if (chartType === 'line') {
        if (cd.monthColumns && cd.months) {
            var series = cd.months.map(function(m, mi) {
                return { name: m, type: 'line', data: cd.monthColumns[m] || [], smooth: true,
                    lineStyle: { width: 2 }, areaStyle: { opacity: 0.1 } };
            });
            option = {
                tooltip: { trigger: 'axis', formatter: function(ps) { var s = ps[0].axisValue + '<br>'; ps.forEach(function(p) { s += p.marker + p.seriesName + ': ' + fmt(p.value) + '<br>'; }); return s; } },
                legend: { textStyle: { color: '#c9d1d9' } },
                xAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10 } },
                yAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return isCurrency ? '$'+v : v; } } },
                series: series, color: colors, grid: { left: 60, right: 20, bottom: 30, top: 40 },
            };
        } else {
            option = {
                tooltip: { trigger: 'axis', formatter: function(ps) { return ps[0].axisValue + ': ' + fmt(ps[0].value); } },
                xAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10, rotate: labels.length > 6 ? 30 : 0 } },
                yAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return isCurrency ? '$'+v : v; } } },
                series: [{ type: 'line', data: values, smooth: true, areaStyle: { opacity: 0.15 },
                    lineStyle: { color: '#6366f1', width: 2 }, itemStyle: { color: '#6366f1' } }],
                grid: { left: 60, right: 20, bottom: 30, top: 20 },
            };
        }
    } else {
        // bar (default)
        var isHorizontal = cd.indexAxis === 'y';
        if (cd.monthColumns && cd.months) {
            var series = cd.months.map(function(m, mi) {
                return { name: m, type: 'bar', data: cd.monthColumns[m] || [] };
            });
            option = {
                tooltip: { trigger: 'axis', formatter: function(ps) { var s = ps[0].axisValue + '<br>'; ps.forEach(function(p) { s += p.marker + p.seriesName + ': ' + fmt(p.value) + '<br>'; }); return s; } },
                legend: { textStyle: { color: '#c9d1d9' } },
                xAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10 } },
                yAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return isCurrency ? '$'+v : v; } } },
                series: series, color: colors, grid: { left: 60, right: 20, bottom: 30, top: 40 },
            };
        } else if (cd.data2) {
            option = {
                tooltip: { trigger: 'axis' },
                legend: { data: [cd.dataLabel || 'Month 1', cd.data2Label || 'Month 2'], textStyle: { color: '#c9d1d9' } },
                xAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10 } },
                yAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return '$'+v; } } },
                series: [
                    { name: cd.dataLabel || 'Month 1', type: 'bar', data: values, itemStyle: { color: '#6366f1' } },
                    { name: cd.data2Label || 'Month 2', type: 'bar', data: cd.data2, itemStyle: { color: '#10b981' } }
                ],
                grid: { left: 60, right: 20, bottom: 30, top: 40 },
            };
        } else if (isHorizontal) {
            option = {
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function(ps) { return ps[0].name + ': ' + fmt(ps[0].value); } },
                xAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return isCurrency ? '$'+v : v; } } },
                yAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10, width: 120, overflow: 'truncate' } },
                series: [{ type: 'bar', data: values.map(function(v, i) { return { value: v, itemStyle: { color: colors[i % colors.length] } }; }) }],
                grid: { left: 140, right: 20, bottom: 20, top: 10 },
            };
        } else {
            option = {
                tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function(ps) { return ps[0].name + ': ' + fmt(ps[0].value); } },
                xAxis: { type: 'category', data: labels, axisLabel: { color: '#8b949e', fontSize: 10, rotate: labels.length > 5 ? 30 : 0 } },
                yAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: function(v) { return isCurrency ? '$'+v : v; } } },
                series: [{ type: 'bar', data: values.map(function(v, i) { return { value: v, itemStyle: { color: colors[i % colors.length] } }; }) }],
                grid: { left: 60, right: 20, bottom: 40, top: 10 },
            };
        }
    }

    try { chart.setOption(option); } catch(e) { console.warn('ECharts render failed:', e); }
    window.addEventListener('resize', function() { try { chart.resize(); } catch(e) {} });
    if (aiChat) aiChat.scrollTop = aiChat.scrollHeight;
}

function renderTableWithChart(container, cd) {
    container.innerHTML = '';

    // Build table
    var tableWrap = document.createElement('div');
    tableWrap.style.cssText = 'background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px;margin-top:8px;max-width:100%;overflow-x:auto;';

    var titleEl = document.createElement('div');
    titleEl.style.cssText = 'color:#e2e8f0;font-size:0.9em;font-weight:600;margin-bottom:8px;';
    titleEl.textContent = cd.title || 'Data';
    tableWrap.appendChild(titleEl);

    var table = document.createElement('table');
    table.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.85em;color:#c9d1d9;';

    // Header — adapt for comparison or multi-month data
    var hasComparison = cd.data2 && cd.data2.length > 0;
    var hasMonthColumns = cd.monthColumns && cd.months && cd.months.length > 0;
    var thead = document.createElement('thead');
    var hrow = document.createElement('tr');
    var headers;
    if (hasMonthColumns) {
        headers = ['#', 'Service'].concat(cd.months);
    } else if (hasComparison) {
        headers = ['#', 'Service', cd.dataLabel || 'Month 1', cd.data2Label || 'Month 2', 'Change'];
    } else {
        headers = ['#', 'Item', 'Cost (USD)'];
    }
    headers.forEach(function(h) {
        var th = document.createElement('th');
        th.style.cssText = 'text-align:left;padding:6px 8px;border-bottom:1px solid #30363d;color:#8b949e;font-weight:600;white-space:nowrap;';
        if (h !== '#' && h !== 'Item' && h !== 'Service') th.style.textAlign = 'right';
        th.textContent = h;
        hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    // Body
    var tbody = document.createElement('tbody');
    var labels = cd.labels || [];
    var data = cd.data || [];
    var data2 = cd.data2 || [];

    if (hasMonthColumns) {
        // Multi-month table
        var monthTotals = {};
        cd.months.forEach(function(m) { monthTotals[m] = 0; });
        labels.forEach(function(label, i) {
            var tr = document.createElement('tr');
            tr.style.cssText = 'border-bottom:1px solid #21262d;';
            var tdNum = document.createElement('td');
            tdNum.style.cssText = 'padding:5px 8px;color:#8b949e;';
            tdNum.textContent = (i + 1);
            tr.appendChild(tdNum);
            var tdLabel = document.createElement('td');
            tdLabel.style.cssText = 'padding:5px 8px;white-space:nowrap;';
            tdLabel.textContent = label;
            tr.appendChild(tdLabel);
            cd.months.forEach(function(m) {
                var val = (cd.monthColumns[m] && cd.monthColumns[m][i]) || 0;
                monthTotals[m] += val;
                var td = document.createElement('td');
                td.style.cssText = 'padding:5px 8px;text-align:right;font-family:monospace;';
                td.textContent = '$' + val.toFixed(2);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        // Total row
        var tfoot = document.createElement('tfoot');
        var tfrow = document.createElement('tr');
        tfrow.style.cssText = 'border-top:2px solid #30363d;font-weight:600;';
        var tfe = document.createElement('td'); tfe.colSpan = 2; tfe.style.cssText = 'padding:6px 8px;'; tfe.textContent = 'Total';
        tfrow.appendChild(tfe);
        cd.months.forEach(function(m) {
            var td = document.createElement('td');
            td.style.cssText = 'padding:6px 8px;text-align:right;font-family:monospace;color:#10b981;';
            td.textContent = '$' + monthTotals[m].toFixed(2);
            tfrow.appendChild(td);
        });
        tfoot.appendChild(tfrow);
        table.appendChild(tfoot);
    } else {
    var total = 0;
    var total2 = 0;
    labels.forEach(function(label, i) {
        var val = data[i] || 0;
        total += val;
        var tr = document.createElement('tr');
        tr.style.cssText = 'border-bottom:1px solid #21262d;';

        var tdNum = document.createElement('td');
        tdNum.style.cssText = 'padding:5px 8px;color:#8b949e;';
        tdNum.textContent = (i + 1);
        tr.appendChild(tdNum);

        var tdLabel = document.createElement('td');
        tdLabel.style.cssText = 'padding:5px 8px;';
        tdLabel.textContent = label;
        tr.appendChild(tdLabel);

        var tdVal = document.createElement('td');
        tdVal.style.cssText = 'padding:5px 8px;text-align:right;font-family:monospace;';
        tdVal.textContent = '$' + val.toFixed(2);
        tr.appendChild(tdVal);

        if (hasComparison) {
            var val2 = data2[i] || 0;
            total2 += val2;
            var tdVal2 = document.createElement('td');
            tdVal2.style.cssText = 'padding:5px 8px;text-align:right;font-family:monospace;';
            tdVal2.textContent = '$' + val2.toFixed(2);
            tr.appendChild(tdVal2);

            var diff = val2 - val;
            var tdDiff = document.createElement('td');
            tdDiff.style.cssText = 'padding:5px 8px;text-align:right;font-family:monospace;color:' + (diff > 0 ? '#ef4444' : diff < 0 ? '#10b981' : '#8b949e') + ';';
            tdDiff.textContent = (diff >= 0 ? '+' : '') + '$' + diff.toFixed(2);
            tr.appendChild(tdDiff);
        }

        tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    // Total row
    var tfoot = document.createElement('tfoot');
    var tfrow = document.createElement('tr');
    tfrow.style.cssText = 'border-top:2px solid #30363d;font-weight:600;';
    var tfe = document.createElement('td'); tfe.colSpan = 2; tfe.style.cssText = 'padding:6px 8px;'; tfe.textContent = 'Total';
    var tfv = document.createElement('td'); tfv.style.cssText = 'padding:6px 8px;text-align:right;font-family:monospace;color:#10b981;'; tfv.textContent = '$' + total.toFixed(2);
    tfrow.appendChild(tfe); tfrow.appendChild(tfv);
    if (hasComparison) {
        var tfv2 = document.createElement('td'); tfv2.style.cssText = 'padding:6px 8px;text-align:right;font-family:monospace;color:#10b981;'; tfv2.textContent = '$' + total2.toFixed(2);
        var totalDiff = total2 - total;
        var tfDiff = document.createElement('td'); tfDiff.style.cssText = 'padding:6px 8px;text-align:right;font-family:monospace;color:' + (totalDiff > 0 ? '#ef4444' : totalDiff < 0 ? '#10b981' : '#8b949e') + ';'; tfDiff.textContent = (totalDiff >= 0 ? '+' : '') + '$' + totalDiff.toFixed(2);
        tfrow.appendChild(tfv2); tfrow.appendChild(tfDiff);
    }
    tfoot.appendChild(tfrow);
    table.appendChild(tfoot);
    } // end else (single/comparison table)

    tableWrap.appendChild(table);

    // Chart format buttons below table
    var chartRow = document.createElement('div');
    chartRow.style.cssText = 'display:flex;gap:4px;margin-top:12px;flex-wrap:wrap;align-items:center;';
    var chartLabel = document.createElement('span');
    chartLabel.style.cssText = 'color:#8b949e;font-size:0.8em;margin-right:4px;';
    chartLabel.textContent = 'Visualize:';
    chartRow.appendChild(chartLabel);

    var chartTypes = [];
    // Smart chart type suggestions based on data shape
    var hasMultiMonth = cd.monthColumns && cd.months && cd.months.length > 1;
    var isTimeSeries = cd.id === 'daily-trend' || cd.id === 'monthly-total-trend';
    var isBreakdown = cd.id === 'vpc-breakdown' || cd.id === 'ec2other-breakdown';

    if (isTimeSeries) {
        chartTypes = [
            { key: 'line', label: '📈 Line' },
            { key: 'bar', label: '📊 Bar' },
        ];
    } else if (isBreakdown) {
        chartTypes = [
            { key: 'doughnut', label: '🍩 Doughnut' },
            { key: 'pie', label: '🥧 Pie' },
            { key: 'bar', label: '📊 Bar' },
        ];
    } else if (hasMultiMonth) {
        chartTypes = [
            { key: 'bar', label: '📊 Grouped Bar' },
            { key: 'line', label: '📈 Line' },
        ];
    } else {
        chartTypes = [
            { key: 'bar', label: '📊 Bar' },
            { key: 'doughnut', label: '🍩 Doughnut' },
            { key: 'line', label: '📈 Line' },
        ];
    }
    var chartArea = document.createElement('div');
    chartArea.className = 'ai-chart-render-area';

    chartTypes.forEach(function(t) {
        var btn = document.createElement('button');
        btn.className = 'btn btn-outline btn-sm';
        btn.style.cssText = 'font-size:0.75em;padding:3px 8px;';
        btn.textContent = t.label;
        btn.onclick = function() {
            // Highlight active
            chartRow.querySelectorAll('button').forEach(function(b) { b.style.background = ''; b.style.borderColor = ''; });
            btn.style.background = '#4c1d95';
            btn.style.borderColor = '#6d28d9';
            renderSingleChart(chartArea, cd, t.key);
        };
        chartRow.appendChild(btn);
    });

    tableWrap.appendChild(chartRow);
    tableWrap.appendChild(chartArea);
    container.appendChild(tableWrap);

    if (aiChat) aiChat.scrollTop = aiChat.scrollHeight;
}

if (aiFontDecBtn) aiFontDecBtn.onclick = function() {
    aiFontSize = Math.max(14, aiFontSize - 1);
    applyAIFontSize();
};
if (aiFontIncBtn) aiFontIncBtn.onclick = function() {
    aiFontSize = Math.min(28, aiFontSize + 1);
    applyAIFontSize();
};
applyAIFontSize();

// Refresh Findings button — always visible in chat header
var aiRefreshFindingsBtn = $('ai-refresh-findings-btn');
if (aiRefreshFindingsBtn) {
    aiRefreshFindingsBtn.onclick = async function() {
        aiRefreshFindingsBtn.disabled = true;
        aiRefreshFindingsBtn.textContent = '⏳ Scanning…';
        try {
            await _runScanFromChat();
        } finally {
            aiRefreshFindingsBtn.disabled = false;
            aiRefreshFindingsBtn.innerHTML = '&#8635; Refresh Findings';
        }
    };
}

// Click example questions to populate input
if (aiChat) aiChat.onclick = function(e) {
    // Handle feedback thumbs-up
    var fbUp = e.target.closest('.ai-fb-up');
    if (fbUp) {
        var msgDiv = fbUp.closest('.lab-message');
        var widget = fbUp.closest('.ai-feedback-widget');
        if (msgDiv && widget) {
            fbUp.style.background = '#238636'; fbUp.style.borderColor = '#2ea043'; fbUp.style.color = '#fff';
            widget.querySelectorAll('.ai-fb-btn').forEach(function(b) { b.disabled = true; });
            var interactionId = msgDiv.getAttribute('data-interaction-id') || '';
            var answerEl = msgDiv.querySelector('.lab-msg-output');
            var agentResponse = answerEl ? answerEl.textContent.replace('📋 Copy', '').trim() : '';
            var statusEl = widget.querySelector('.ai-fb-status');
            api('POST', '/members/accounts/ai-feedback', {
                interactionId: interactionId,
                feedbackScore: 'yes',
                userQuestion: (aiQuestionInput && aiQuestionInput.dataset.lastQuestion) || '',
                agentResponse: agentResponse,
            }).then(function() {
                if (statusEl) { statusEl.style.display = 'block'; statusEl.textContent = 'Thanks for your feedback!'; }
            }).catch(function(err) {
                if (statusEl) { statusEl.style.display = 'block'; statusEl.style.color = '#f85149'; statusEl.textContent = 'Failed to send feedback.'; }
                widget.querySelectorAll('.ai-fb-btn').forEach(function(b) { b.disabled = false; });
            });
        }
        return;
    }
    // Handle feedback thumbs-down
    var fbDown = e.target.closest('.ai-fb-down');
    if (fbDown) {
        var msgDiv2 = fbDown.closest('.lab-message');
        var widget2 = fbDown.closest('.ai-feedback-widget');
        if (msgDiv2 && widget2) {
            fbDown.style.background = '#da3633'; fbDown.style.borderColor = '#f85149'; fbDown.style.color = '#fff';
            widget2.querySelectorAll('.ai-fb-btn').forEach(function(b) { b.disabled = true; });
            var correctionArea = widget2.querySelector('.ai-fb-correction');
            if (correctionArea) correctionArea.style.display = 'block';
            // Also send negative feedback immediately (without correction)
            var interactionId2 = msgDiv2.getAttribute('data-interaction-id') || '';
            var answerEl2 = msgDiv2.querySelector('.lab-msg-output');
            var agentResponse2 = answerEl2 ? answerEl2.textContent.replace('📋 Copy', '').trim() : '';
            widget2._fbPayload = {
                interactionId: interactionId2,
                feedbackScore: 'no',
                userQuestion: (aiQuestionInput && aiQuestionInput.dataset.lastQuestion) || '',
                agentResponse: agentResponse2,
            };
        }
        return;
    }
    // Handle correction submit
    var corrSubmit = e.target.closest('.ai-fb-correction-submit');
    if (corrSubmit) {
        var widget3 = corrSubmit.closest('.ai-feedback-widget');
        if (widget3 && widget3._fbPayload) {
            var corrInput = widget3.querySelector('.ai-fb-correction-input');
            var correction = corrInput ? corrInput.value.trim() : '';
            var payload = Object.assign({}, widget3._fbPayload);
            if (correction) payload.userCorrection = correction;
            var statusEl3 = widget3.querySelector('.ai-fb-status');
            var corrArea = widget3.querySelector('.ai-fb-correction');
            api('POST', '/members/accounts/ai-feedback', payload).then(function() {
                if (corrArea) corrArea.style.display = 'none';
                if (statusEl3) { statusEl3.style.display = 'block'; statusEl3.textContent = 'Thanks for your feedback!'; }
            }).catch(function() {
                if (statusEl3) { statusEl3.style.display = 'block'; statusEl3.style.color = '#f85149'; statusEl3.textContent = 'Failed to send feedback.'; }
            });
        }
        return;
    }
    // Handle copy button
    var copyBtn = e.target.closest('.ai-copy-btn');
    if (copyBtn) {
        var output = copyBtn.closest('.lab-msg-output');
        if (output) {
            var text = output.textContent.replace('📋 Copy', '').trim();
            navigator.clipboard.writeText(text).then(function() {
                copyBtn.textContent = '✓ Copied';
                setTimeout(function() { copyBtn.textContent = '📋 Copy'; }, 2000);
            });
        }
        return;
    }
    // Handle follow-up drill-down buttons
    var followUpBtn = e.target.closest('.ai-followup-btn');
    if (followUpBtn) {
        var followUpQ = followUpBtn.getAttribute('data-question');
        if (followUpQ && aiQuestionInput) {
            aiQuestionInput.value = followUpQ;
            askAI();
        }
        return;
    }
    // Handle chart option buttons (legacy — now handled via table flow)
    var chartBtn = e.target.closest('.ai-chart-btn');
    if (chartBtn) {
        var idx = parseInt(chartBtn.getAttribute('data-chart-idx'), 10);
        var msgDiv = chartBtn.closest('.lab-message');
        if (msgDiv && msgDiv.dataset.chartData) {
            var allCharts = JSON.parse(msgDiv.dataset.chartData);
            var cd = allCharts[idx];
            if (cd) {
                var renderArea = msgDiv.querySelector('.ai-chart-render-area');
                if (renderArea) {
                    renderSingleChart(renderArea, cd);
                }
            }
        }
        return;
    }
    // Handle "Show as Table" buttons
    var tableBtn = e.target.closest('.ai-table-btn');
    if (tableBtn) {
        var tidx = parseInt(tableBtn.getAttribute('data-chart-idx'), 10);
        var tmsgDiv = tableBtn.closest('.lab-message');
        if (tmsgDiv && tmsgDiv.dataset.chartData) {
            var tAllCharts = JSON.parse(tmsgDiv.dataset.chartData);
            var tcd = tAllCharts[tidx];
            if (tcd) {
                var tRenderArea = tmsgDiv.querySelector('.ai-table-render-area');
                if (tRenderArea) {
                    renderTableWithChart(tRenderArea, tcd);
                }
            }
        }
        return;
    }
    var visualizeBtn = e.target.closest('.ai-visualize-btn');
    if (visualizeBtn) {
        pendingVisualize = {
            prompt: visualizeBtn.getAttribute('data-question') || '',
            answer: visualizeBtn.getAttribute('data-answer') || '',
            accountId: (getSelectedAccountIds()[0]) || '',
        };
        if (visualizeTitleInput) visualizeTitleInput.value = '';
        if (visualizeTypeSelect) visualizeTypeSelect.value = 'graph';
        if (visualizeChartType) visualizeChartType.value = 'bar';
        if (visualizeDatasetLabel) visualizeDatasetLabel.value = '';
        if (visualizeLabelsInput) visualizeLabelsInput.value = '';
        if (visualizeValuesInput) visualizeValuesInput.value = '';
        if (visualizeModal) visualizeModal.hidden = false;
        return;
    }
    if (e.target.tagName === 'CODE' && e.target.closest('.lab-examples')) {
        aiQuestionInput.value = e.target.textContent;
        aiQuestionInput.focus();
    }
};

function closeVisualizeModal() {
    if (visualizeModal) visualizeModal.hidden = true;
    pendingVisualize = null;
}

async function saveVisualizedAnswer() {
    if (!pendingVisualize) return;
    var payload = {
        viewType: (visualizeTypeSelect && visualizeTypeSelect.value) || 'graph',
        title: (visualizeTitleInput && visualizeTitleInput.value || '').trim(),
        prompt: pendingVisualize.prompt || 'AI Query',
        answer: pendingVisualize.answer || '',
        accountId: pendingVisualize.accountId || '',
    };
    if (payload.viewType === 'graph') {
        var labels = parseCsvLabels(visualizeLabelsInput && visualizeLabelsInput.value);
        var data = parseCsvNumbers(visualizeValuesInput && visualizeValuesInput.value);
        if (labels.length && data.length && labels.length === data.length) {
            payload.chartConfig = {
                type: (visualizeChartType && visualizeChartType.value) || 'bar',
                labels: labels,
                data: data,
                datasetLabel: (visualizeDatasetLabel && visualizeDatasetLabel.value || '').trim() || 'Values'
            };
        }
    }
    try {
        await api('POST', '/members/dashboard', payload);
        closeVisualizeModal();
        notify('Visualization added to Dashboard.', 'success');
        activateMemberTab('dashboard-tab');
    } catch (err) {
        notify(err.message || 'Failed to add visualization', 'error');
    }
}

if (visualizeCloseBtn) visualizeCloseBtn.onclick = closeVisualizeModal;
if (visualizeCancelBtn) visualizeCancelBtn.onclick = closeVisualizeModal;
if (visualizeSaveBtn) visualizeSaveBtn.onclick = saveVisualizedAnswer;


// ============================================================
// FinOps Dashboard
// ============================================================
var dashDataCache = null;
var dashDataCacheTime = 0;
var DASH_CACHE_TTL = 300000; // 5 minutes

function populateDashAccounts() {
    var el = $('dash-account-select');
    if (!el) return;
    el.innerHTML = '';
    var connected = allAccounts.filter(function(a) { return a.connectionStatus === 'connected'; });
    if (!connected.length) { el.innerHTML = '<span style="color:#8b949e;font-size:0.85em;">No connected accounts</span>'; return; }

    var toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn btn-outline btn-sm';
    toggleBtn.style.cssText = 'font-size:0.85em;padding:4px 12px;min-width:180px;text-align:left;';
    function updateLabel() {
        var checked = el.querySelectorAll('.dash-acct-cb:checked');
        if (checked.length === 0) toggleBtn.textContent = 'Select accounts...';
        else if (checked.length === 1) toggleBtn.textContent = checked[0].parentElement.dataset.label || checked[0].value;
        else toggleBtn.textContent = checked.length + ' accounts selected';
        toggleBtn.textContent += ' \u25be';
    }

    var panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;top:100%;left:0;z-index:200;background:#fff;border:1px solid #d0d7de;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);min-width:260px;max-height:200px;overflow-y:auto;padding:6px 0;margin-top:4px;';

    connected.forEach(function(a, idx) {
        var row = document.createElement('label');
        row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;color:#24292f;font-size:0.85em;white-space:nowrap;';
        row.dataset.label = a.accountId + ' (' + (a.accountName || 'Account') + ')';
        row.onmouseenter = function() { row.style.background = '#f6f8fa'; };
        row.onmouseleave = function() { row.style.background = ''; };
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = a.accountId; cb.className = 'dash-acct-cb';
        cb.checked = true; // All accounts selected by default for dashboard
        cb.style.cssText = 'accent-color:#6366f1;flex-shrink:0;';
        cb.onchange = function() { updateLabel(); dashDataCache = null; loadDashboardData(); };
        row.appendChild(cb);
        row.appendChild(document.createTextNode(a.accountId + ' (' + (a.accountName || 'Account ' + a.accountId.slice(-4)) + ')'));
        panel.appendChild(row);
    });

    var ctrlRow = document.createElement('div');
    ctrlRow.style.cssText = 'display:flex;gap:8px;padding:6px 12px;border-top:1px solid #d0d7de;margin-top:4px;';
    var selAll = document.createElement('a');
    selAll.href = '#'; selAll.textContent = 'Select All'; selAll.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selAll.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.dash-acct-cb').forEach(function(c) { c.checked = true; }); updateLabel(); dashDataCache = null; loadDashboardData(); };
    var selNone = document.createElement('a');
    selNone.href = '#'; selNone.textContent = 'Clear'; selNone.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selNone.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.dash-acct-cb').forEach(function(c) { c.checked = false; }); updateLabel(); };
    ctrlRow.appendChild(selAll); ctrlRow.appendChild(selNone);
    panel.appendChild(ctrlRow);

    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;display:inline-block;';
    wrapper.appendChild(toggleBtn); wrapper.appendChild(panel);
    el.appendChild(wrapper);

    toggleBtn.onclick = function(e) { e.stopPropagation(); panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; };
    document.addEventListener('click', function(e) { if (!wrapper.contains(e.target)) panel.style.display = 'none'; });
    updateLabel();
}

function getDashSelectedAccountIds() {
    var cbs = document.querySelectorAll('.dash-acct-cb:checked');
    var ids = []; cbs.forEach(function(cb) { ids.push(cb.value); }); return ids;
}

async function loadDashboardData() {
    var kpiBar = $('dash-kpi-bar');
    var grid = $('dash-grid');
    if (!kpiBar || !grid) { console.error('Dashboard containers not found'); return; }

    var now = Date.now();
    if (dashDataCache && (now - dashDataCacheTime) < DASH_CACHE_TTL) {
        renderDashboardWidgets(dashDataCache);
        return;
    }

    kpiBar.innerHTML = '<div style="color:#6b7280;padding:20px;width:100%;">Loading dashboard data from your accounts...</div>';
    grid.innerHTML = '';

    try {
        var selectedIds = getDashSelectedAccountIds();
        var url = '/members/dashboard-data';
        if (selectedIds.length > 0) url += '?accountIds=' + selectedIds.join(',');
        var data = await api('GET', url);
        dashDataCache = data;
        dashDataCacheTime = Date.now();
        renderDashboardWidgets(data);
    } catch (e) {
        console.error('Dashboard load error:', e);
        kpiBar.innerHTML = '<div style="color:#ef4444;padding:20px;">Dashboard failed: ' + esc(e.message || 'Error') + '<br><button class="btn btn-outline btn-sm" style="margin-top:8px;" onclick="dashDataCache=null;loadDashboardData();">Retry</button></div>';
    }
}

function renderDashboardWidgets(data) {
    // Wire refresh button
    var refreshBtn = $('dash-refresh-btn');
    if (refreshBtn) refreshBtn.onclick = function() { dashDataCache = null; loadDashboardData(); };
    var kpiBar = $('dash-kpi-bar');
    var grid = $('dash-grid');
    if (!kpiBar || !grid) return;
    var s = data.summary || {};

    // KPI Bar
    var momColor = s.monthOverMonthChange <= 0 ? '#10b981' : '#ef4444';
    var momArrow = s.monthOverMonthChange <= 0 ? '▼' : '▲';
    var effColor = s.efficiencyScore >= 90 ? '#10b981' : s.efficiencyScore >= 75 ? '#f59e0b' : '#ef4444';
    // Build savings breakdown tooltip
    var savingsTooltip = '';
    if (s.savingsBreakdown) {
        var entries = Object.entries(s.savingsBreakdown).sort(function(a,b){return b[1]-a[1];});
        savingsTooltip = entries.map(function(e){return e[0]+': $'+e[1].toFixed(2);}).join('\n');
    }

    kpiBar.innerHTML =
        _kpiCard('Month-over-Month', momArrow + ' ' + Math.abs(s.monthOverMonthChange || 0) + '%', momColor) +
        _kpiCard('Efficiency Score', (s.efficiencyScore || 0) + '% (' + (s.efficiencyRating || '') + ')', effColor) +
        '<div style="background:#f0f4f8;border:1px solid #d0d7de;border-radius:8px;padding:12px 16px;flex:1;min-width:130px;cursor:pointer;" title="' + ea(savingsTooltip) + '" onclick="_syncAccountSelection(\'dash\');document.querySelector(\'[data-tab=ai-tab]\').click();setTimeout(function(){var inp=document.getElementById(\'ai-question-input\');if(inp){inp.value=\'Where can I save money?\';document.getElementById(\'ai-ask-btn\').click();}},300);">' +
            '<div style="color:#6b7280;font-size:0.75em;">Potential Savings \u25b6</div>' +
            '<div style="color:#f59e0b;font-size:1.3em;font-weight:700;">$' + (s.potentialSavings || 0).toLocaleString(undefined, {minimumFractionDigits:2}) + '</div></div>' +
        _kpiCard('Accounts', (s.accountsAnalyzed || 0) + ' / ' + (s.totalAccounts || 0), '#6366f1');

    // Grid widgets — use customizable layout
    grid.innerHTML = '';
    _buildDashWidgets(grid);

    // Render ECharts
    setTimeout(function() {
        _renderTreemap(data.costByService || [], data.drillDown || {});
        _renderDailyTrend(data.dailyTrend || [], data.hourlyTrend || []);
        _renderAllocationTreemap(data.costAllocation || null);
        _renderWaste(data.waste || {});
        _renderMonthly(data.monthlyTrend || {});
        _renderUnitEconomics(data.unitEconomics || null);
        _renderRegionalPie(data.costByRegion || []);
        _renderCommitments(data.commitments || {});
        _renderCostByTag(data.costByTag || {});
    }, 100);
}

function _kpiCard(label, value, color) {
    return '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:130px;">' +
        '<div style="color:#8b949e;font-size:0.75em;">' + label + '</div>' +
        '<div style="color:' + color + ';font-size:1.3em;font-weight:700;">' + value + '</div></div>';
}

// Widget layout management
var DASH_WIDGET_DEFS = [
    {id:'dash-treemap', title:'Cost by Service', height:300, q:'Show me my cost breakdown by service'},
    {id:'dash-daily', title:'Cost Trend', height:250, q:'Are there any cost anomalies?', extraTitle:' <span id="dash-trend-toggle" style="font-size:0.7em;margin-left:8px;"><button class="btn btn-outline btn-sm" style="padding:1px 6px;font-size:0.8em;" onclick="_toggleTrendView(\'daily\')">Daily</button> <button class="btn btn-outline btn-sm" style="padding:1px 6px;font-size:0.8em;background:#6366f1;color:#fff;border-color:#6366f1;" onclick="_toggleTrendView(\'hourly\')">Hourly</button></span>'},
    {id:'dash-allocation', title:'Cost Allocation by Business Unit', height:280, q:'Break down my costs by business unit', extraTitle:' <button class="btn btn-outline btn-sm" style="font-size:0.7em;margin-left:8px;padding:2px 6px;" onclick="showAllocationRulesModal();">Manage Rules</button>'},
    {id:'dash-waste', title:'Waste Detection', height:250, q:'What services do I not need? Show me all waste.'},
    {id:'dash-monthly', title:'Monthly Cost by Service', height:320, q:'Compare my costs over the last 3 months'},
    {id:'dash-unit-economics', title:'Unit Cost Trend', height:280, q:'How is my cost per unit trending?', extraTitle:' <button class="btn btn-outline btn-sm" style="font-size:0.7em;margin-left:8px;padding:2px 6px;" onclick="showBusinessMetricsModal();">Add Metrics</button>'},
    {id:'dash-regional', title:'Cost by Region', height:300, q:'Show me my cost breakdown by region'},
    {id:'dash-commitments', title:'Savings Plans & Reserved Instances', height:350, q:'What Savings Plans and Reserved Instances do I have?'},
    {id:'dash-cost-by-tag', title:'Cost by Tag', height:320, q:'Show me cost breakdown by tags'},
];

function _getDashLayout() {
    try {
        var saved = localStorage.getItem('dashWidgetLayout');
        if (saved) return JSON.parse(saved);
    } catch(e) {}
    return DASH_WIDGET_DEFS.map(function(w){return {id:w.id, visible:true};});
}

function _saveDashLayout(layout) {
    try { localStorage.setItem('dashWidgetLayout', JSON.stringify(layout)); } catch(e) {}
}

function _buildDashWidgets(grid) {
    var layout = _getDashLayout();
    // Ensure all widgets exist in layout (new ones added at end)
    var layoutIds = layout.map(function(l){return l.id;});
    DASH_WIDGET_DEFS.forEach(function(def) {
        if (layoutIds.indexOf(def.id) === -1) layout.push({id:def.id, visible:true});
    });

    grid.innerHTML = '';
    var visibleCount = 0;
    layout.forEach(function(item, idx) {
        if (!item.visible) return;
        var def = DASH_WIDGET_DEFS.find(function(d){return d.id===item.id;});
        if (!def) return;
        visibleCount++;
        _addWidget(grid, def.id, def.title + (def.extraTitle||''), def.height, def.q, idx, layout.length);
    });

    // Add "+" button to add hidden widgets back
    var hiddenWidgets = layout.filter(function(l){return !l.visible;});
    if (hiddenWidgets.length > 0) {
        var addBtn = document.createElement('div');
        addBtn.style.cssText = 'background:#f0f4f8;border:2px dashed #d0d7de;border-radius:8px;padding:24px;text-align:center;cursor:pointer;color:#6b7280;';
        addBtn.innerHTML = '<div style="font-size:1.5em;margin-bottom:4px;">+</div><div style="font-size:0.8em;">Add Widget (' + hiddenWidgets.length + ' hidden)</div>';
        addBtn.onclick = function() { _showAddWidgetPicker(grid); };
        grid.appendChild(addBtn);
    }
}

function _showAddWidgetPicker(grid) {
    var layout = _getDashLayout();
    var hidden = layout.filter(function(l){return !l.visible;});
    if (!hidden.length) return;
    var html = '<div style="position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:800;display:flex;align-items:center;justify-content:center;" id="widget-picker-overlay" onclick="if(event.target===this)this.remove();">';
    html += '<div style="background:#fff;border-radius:12px;padding:24px;max-width:400px;width:90%;">';
    html += '<h3 style="margin:0 0 16px;font-size:1em;">Add Widget</h3>';
    hidden.forEach(function(item) {
        var def = DASH_WIDGET_DEFS.find(function(d){return d.id===item.id;});
        if (!def) return;
        html += '<button class="btn btn-outline btn-sm" style="display:block;width:100%;margin-bottom:8px;text-align:left;padding:10px 14px;" onclick="_restoreWidget(\'' + item.id + '\')">' + def.title + '</button>';
    });
    html += '<button class="btn btn-sm" style="margin-top:8px;" onclick="document.getElementById(\'widget-picker-overlay\').remove();">Cancel</button>';
    html += '</div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
}

function _restoreWidget(widgetId) {
    var layout = _getDashLayout();
    layout.forEach(function(l){if(l.id===widgetId)l.visible=true;});
    _saveDashLayout(layout);
    var overlay = document.getElementById('widget-picker-overlay');
    if (overlay) overlay.remove();
    if (dashDataCache) renderDashboardWidgets(dashDataCache);
}

function _removeWidget(widgetId) {
    var layout = _getDashLayout();
    layout.forEach(function(l){if(l.id===widgetId)l.visible=false;});
    _saveDashLayout(layout);
    if (dashDataCache) renderDashboardWidgets(dashDataCache);
}

function _moveWidget(widgetId, direction) {
    var layout = _getDashLayout();
    var visibleLayout = layout.filter(function(l){return l.visible;});
    var idx = -1;
    visibleLayout.forEach(function(l,i){if(l.id===widgetId)idx=i;});
    if (idx < 0) return;
    var newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= visibleLayout.length) return;
    // Swap in the visible list
    var temp = visibleLayout[idx];
    visibleLayout[idx] = visibleLayout[newIdx];
    visibleLayout[newIdx] = temp;
    // Rebuild full layout: visible items in new order, then hidden items
    var hiddenLayout = layout.filter(function(l){return !l.visible;});
    _saveDashLayout(visibleLayout.concat(hiddenLayout));
    if (dashDataCache) renderDashboardWidgets(dashDataCache);
}

function _addWidget(grid, id, title, height, aiQuestion, idx, total) {
    var w = document.createElement('div');
    w.style.cssText = 'background:#f0f4f8;border:1px solid #d0d7de;border-radius:8px;padding:14px;';
    w.setAttribute('data-widget-id', id);
    var aiLink = aiQuestion ? ' <a href="#" style="font-size:0.7em;color:#6366f1;text-decoration:none;" onclick="event.preventDefault();_askAIFromDashboard(\'' + aiQuestion.replace(/'/g, "\\'") + '\');">Chat &#9654;</a>' : '';
    var controls = '<span style="float:right;display:flex;gap:4px;align-items:center;">';
    if (typeof idx === 'number') {
        controls += '<button style="background:none;border:none;cursor:pointer;font-size:0.7em;color:#6b7280;padding:2px;" onclick="_moveWidget(\'' + id + '\',-1)" title="Move up">&#9650;</button>';
        controls += '<button style="background:none;border:none;cursor:pointer;font-size:0.7em;color:#6b7280;padding:2px;" onclick="_moveWidget(\'' + id + '\',1)" title="Move down">&#9660;</button>';
        controls += '<button style="background:none;border:none;cursor:pointer;font-size:0.8em;color:#ef4444;padding:2px;margin-left:4px;" onclick="_removeWidget(\'' + id + '\')" title="Hide widget">&times;</button>';
    }
    controls += aiLink + '</span>';
    w.innerHTML = '<div style="color:#1f2937;font-size:0.9em;font-weight:600;margin-bottom:8px;">' + title + controls + '</div>' +
        '<div id="' + id + '" style="width:100%;height:' + height + 'px;"></div>';
    grid.appendChild(w);
}

function _askAIFromDashboard(question) {
    _syncAccountSelection('dash'); // preserve dashboard account selection
    document.querySelector('[data-tab="ai-tab"]').click();
    setTimeout(function() {
        var inp = document.getElementById('ai-question-input');
        if (inp) {
            inp.value = question;
            document.getElementById('ai-ask-btn').click();
        }
    }, 300);
}

var _dashDailyData = null;
var _dashHourlyData = null;
var _dashDrillDown = {};

function _toggleTrendView(mode) {
    var btns = document.querySelectorAll('#dash-trend-toggle button');
    btns.forEach(function(b) { b.style.background = ''; b.style.color = ''; b.style.borderColor = ''; });
    if (mode === 'hourly') {
        btns[1].style.background = '#6366f1'; btns[1].style.color = '#fff'; btns[1].style.borderColor = '#6366f1';
        _renderHourlyTrend(_dashHourlyData || []);
    } else {
        btns[0].style.background = '#6366f1'; btns[0].style.color = '#fff'; btns[0].style.borderColor = '#6366f1';
        _renderDailyChart(_dashDailyData || []);
    }
}

// ============================================================
// Cost by Service Treemap — 2-phase drill-down
// ============================================================
var _treemapChart = null;
var _treemapLevel = 'services'; // 'services' | 'usageTypes'
var _treemapCurrentService = null;
var _treemapServiceData = [];
var _treemapColors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16'];

function _renderTreemap(costByService, drillDown) {
    _dashDrillDown = drillDown || {};
    _treemapServiceData = costByService || [];
    var el = $('dash-treemap'); if (!el || !window.echarts) return;

    if (_treemapChart) { try { _treemapChart.dispose(); } catch(e){} }
    _treemapChart = echarts.init(el, null);
    _treemapLevel = 'services';
    _treemapCurrentService = null;

    _renderTreemapServices();
    window.addEventListener('resize', function() { if (_treemapChart) _treemapChart.resize(); });
}

function _renderTreemapServices() {
    var el = $('dash-treemap'); if (!el) return;

    // Remove any existing breadcrumb
    var old = document.getElementById('treemap-breadcrumb');
    if (old) old.remove();

    var treeData = _treemapServiceData.map(function(s, i) {
        // Normalize service name — strip Amazon/AWS prefix for display
        var displayName = s.service.replace(/^Amazon\s+/,'').replace(/^AWS\s+/,'');
        return {
            name: displayName,
            fullName: s.service,
            value: s.cost,
            pct: s.pct,
            itemStyle: { color: _treemapColors[i % _treemapColors.length] }
        };
    });

    _treemapChart.setOption({
        tooltip: { formatter: function(p) {
            return '<b>' + (p.data.fullName || p.name) + '</b><br>$' + p.value.toFixed(2) +
                (p.data.pct ? ' (' + p.data.pct + '%)' : '') +
                '<br><span style="color:#aaa;font-size:11px;">Click to drill down ▼</span>';
        }},
        series: [{ type: 'treemap', data: treeData,
            label: { show: true, formatter: function(p) { return p.name + '\n$' + p.value.toFixed(2); }, fontSize: 11, color: '#fff' },
            breadcrumb: { show: false },
            itemStyle: { borderColor: '#fff', borderWidth: 2 },
            levels: [{ itemStyle: { borderWidth: 3, gapWidth: 3 } }],
            roam: false,
        }],
    }, true);

    _treemapChart.off('click');
    _treemapChart.on('click', function(params) {
        var svc = params.data;
        _drillIntoService(svc.fullName || svc.name, svc.value, svc.pct, svc.itemStyle && svc.itemStyle.color);
    });
    _treemapLevel = 'services';
}

function _drillIntoService(serviceName, totalCost, pct, color) {
    // Look up usage types
    var svcKey = serviceName.replace(/ /g, '_').replace(/-/g, '_');
    var svcKeyShort = serviceName.replace(/^Amazon\s+/,'').replace(/^AWS\s+/,'').replace(/ /g, '_').replace(/-/g, '_');
    var dd = _dashDrillDown[svcKey] || _dashDrillDown[svcKeyShort];

    if (!dd || !dd.usageTypes || dd.usageTypes.length === 0) {
        // No usage type data — show the side panel instead
        _showServiceDrillPanel(serviceName, totalCost, pct, color);
        return;
    }

    _treemapLevel = 'usageTypes';
    _treemapCurrentService = { name: serviceName, cost: totalCost, pct: pct, color: color };

    // Add breadcrumb above the chart
    var el = $('dash-treemap');
    var breadcrumb = document.createElement('div');
    breadcrumb.id = 'treemap-breadcrumb';
    breadcrumb.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 0 4px;font-size:0.82em;';
    breadcrumb.innerHTML =
        '<button onclick="_renderTreemapServices();" style="background:none;border:none;color:#6366f1;cursor:pointer;font-size:0.9em;padding:2px 6px;border-radius:4px;border:1px solid #6366f1;">← All Services</button>' +
        '<span style="color:#6b7280;">›</span>' +
        '<span style="color:#e6edf3;font-weight:600;">' + esc(serviceName.replace(/^Amazon\s+/,'').replace(/^AWS\s+/,'')) + '</span>' +
        '<span style="color:#10b981;margin-left:4px;">$' + totalCost.toFixed(2) + '</span>' +
        '<button onclick="_showServiceDrillPanel(' + JSON.stringify(serviceName) + ',' + totalCost + ',' + JSON.stringify(pct||'') + ',' + JSON.stringify(color||'#6366f1') + ');" style="background:none;border:none;color:#8b949e;cursor:pointer;font-size:0.85em;margin-left:auto;padding:2px 6px;border-radius:4px;border:1px solid #30363d;">Details ↗</button>';
    el.parentNode.insertBefore(breadcrumb, el);

    // Build usage type treemap data
    var items = dd.usageTypes.slice().sort(function(a,b){ return b.cost - a.cost; });
    var baseColor = color || '#6366f1';
    var utData = items.map(function(ut, i) {
        var label = ut.usageType || ut.name || 'Unknown';
        var shortLabel = label.split(':').pop().split('/').pop();
        // Shade the base color slightly per item
        return {
            name: shortLabel,
            fullName: label,
            value: ut.cost,
            itemStyle: { color: _shadeColor(baseColor, i * -8) }
        };
    });

    _treemapChart.setOption({
        tooltip: { formatter: function(p) {
            return '<b>' + (p.data.fullName || p.name) + '</b><br>$' + p.value.toFixed(2) +
                '<br><span style="color:#aaa;font-size:11px;">Click for details panel</span>';
        }},
        series: [{ type: 'treemap', data: utData,
            label: { show: true, formatter: function(p) { return p.name + '\n$' + p.value.toFixed(2); }, fontSize: 10, color: '#fff' },
            breadcrumb: { show: false },
            itemStyle: { borderColor: '#fff', borderWidth: 1 },
            levels: [{ itemStyle: { borderWidth: 2, gapWidth: 2 } }],
            roam: false,
        }],
    }, true);

    _treemapChart.off('click');
    _treemapChart.on('click', function(params) {
        // Clicking a usage type tile opens the side panel for the parent service
        _showServiceDrillPanel(serviceName, totalCost, pct, color);
    });
}

function _shadeColor(hex, percent) {
    // Lighten/darken a hex color by percent (-100 to 100)
    try {
        var num = parseInt(hex.replace('#',''), 16);
        var r = Math.min(255, Math.max(0, (num >> 16) + percent));
        var g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + percent));
        var b = Math.min(255, Math.max(0, (num & 0xff) + percent));
        return '#' + ((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1);
    } catch(e) { return hex; }
}

function _showServiceDrillPanel(serviceName, totalCost, pct, color) {
    // Find drill-down data
    var svcKey = serviceName.replace(/ /g, '_').replace(/-/g, '_');
    // Also try without Amazon/AWS prefix
    var svcKeyShort = serviceName.replace('Amazon ','').replace('AWS ','').replace(/ /g, '_').replace(/-/g, '_');
    var dd = _dashDrillDown[svcKey] || _dashDrillDown[svcKeyShort];

    // Remove existing panel
    var existing = document.getElementById('svc-drill-panel');
    if (existing) existing.remove();

    var panel = document.createElement('div');
    panel.id = 'svc-drill-panel';
    panel.style.cssText = 'position:fixed;top:0;right:0;width:420px;max-width:95vw;height:100vh;background:#1c2128;border-left:2px solid #30363d;z-index:500;overflow-y:auto;box-shadow:-4px 0 20px rgba(0,0,0,0.4);display:flex;flex-direction:column;';

    var header = '<div style="padding:16px 20px;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between;">' +
        '<div>' +
            '<div style="font-size:1.1em;font-weight:700;color:#e6edf3;">' + esc(serviceName.replace('Amazon ','').replace('AWS ','')) + '</div>' +
            '<div style="color:#10b981;font-size:1.3em;font-weight:700;">$' + (totalCost||0).toFixed(2) + (pct ? ' <span style="color:#6b7280;font-size:0.75em;">(' + pct + '%)</span>' : '') + '</div>' +
        '</div>' +
        '<button onclick="document.getElementById(\'svc-drill-panel\').remove();" style="background:none;border:none;color:#8b949e;font-size:1.4em;cursor:pointer;padding:4px;">✕</button>' +
    '</div>';

    var body = '<div style="padding:16px 20px;flex:1;">';

    if (dd && dd.usageTypes && dd.usageTypes.length > 0) {
        // Sort by cost desc
        var items = dd.usageTypes.slice().sort(function(a,b){ return b.cost - a.cost; });
        var maxCost = items[0].cost;

        body += '<div style="color:#8b949e;font-size:0.8em;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.05em;">Usage Type Breakdown</div>';

        // Mini bar chart using divs
        items.forEach(function(ut, i) {
            var barPct = maxCost > 0 ? (ut.cost / maxCost * 100) : 0;
            var label = ut.usageType || ut.name || 'Unknown';
            // Shorten label: take last meaningful segment
            var shortLabel = label.split(':').pop().split('/').pop();
            body += '<div style="margin-bottom:10px;">' +
                '<div style="display:flex;justify-content:space-between;margin-bottom:3px;">' +
                    '<span style="color:#c9d1d9;font-size:0.82em;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + esc(label) + '">' + esc(shortLabel) + '</span>' +
                    '<span style="color:#10b981;font-size:0.82em;font-weight:600;white-space:nowrap;margin-left:8px;">$' + ut.cost.toFixed(2) + '</span>' +
                '</div>' +
                '<div style="background:#21262d;border-radius:3px;height:6px;">' +
                    '<div style="background:' + (color || '#6366f1') + ';width:' + barPct.toFixed(1) + '%;height:6px;border-radius:3px;transition:width 0.4s;"></div>' +
                '</div>' +
            '</div>';
        });

        // Total row
        body += '<div style="border-top:1px solid #30363d;padding-top:10px;margin-top:4px;display:flex;justify-content:space-between;">' +
            '<span style="color:#8b949e;font-size:0.85em;">Total</span>' +
            '<span style="color:#e6edf3;font-weight:700;">$' + (totalCost||0).toFixed(2) + '</span>' +
        '</div>';
    } else {
        body += '<div style="color:#8b949e;font-size:0.9em;padding:20px 0;">No usage type breakdown available for this service.<br><br>Usage type data is fetched when Cost Explorer has resource-level data enabled.</div>';
    }

    // Chat link
    body += '<div style="margin-top:20px;padding-top:16px;border-top:1px solid #30363d;">' +
        '<button onclick="_drillToChat(this);" data-svc="' + ea(serviceName) + '" class="btn btn-primary" style="width:100%;font-size:0.9em;">💬 Ask AI about ' + esc(serviceName.replace('Amazon ','').replace('AWS ','')) + '</button>' +
    '</div>';

    body += '</div>';

    panel.innerHTML = header + body;

    // Close on outside click
    panel.addEventListener('click', function(e) { e.stopPropagation(); });
    document.addEventListener('click', function _closeDrill(e) {
        var p = document.getElementById('svc-drill-panel');
        if (p && !p.contains(e.target)) { p.remove(); document.removeEventListener('click', _closeDrill); }
    });

    document.body.appendChild(panel);
}

function _drillToChat(btn) {
    var serviceName = btn.dataset.svc || btn;
    var panel = document.getElementById('svc-drill-panel');
    if (panel) panel.remove();
    _syncAccountSelection('dash');
    document.querySelector('[data-tab="ai-tab"]').click();
    setTimeout(function() {
        var q = 'Break down my ' + serviceName + ' costs in detail — what are the main usage types and how can I reduce them?';
        if (aiQuestionInput) { aiQuestionInput.value = q; aiQuestionInput.focus(); }
    }, 300);
}

function _renderDailyTrend(daily, hourly) {
    _dashDailyData = daily;
    _dashHourlyData = hourly;
    _renderDailyChart(daily);
}

function _renderDailyChart(daily) {
    var el = $('dash-daily'); if (!el || !window.echarts || !daily.length) return;
    var chart = echarts.init(el, null);
    var anomalyPoints = daily.filter(function(d) { return d.isAnomaly; }).map(function(d) {
        return { xAxis: d.date.substring(5), yAxis: d.cost, value: '+' + d.spikePct + '%' };
    });
    chart.setOption({
        tooltip: { trigger: 'axis', formatter: function(ps) { var d = ps[0]; var tip = d.axisValue + ': $' + d.value.toFixed(2); var orig = daily.find(function(x){return x.date.substring(5)===d.axisValue;}); if(orig&&orig.isAnomaly) tip+=' \u26a0\ufe0f +'+orig.spikePct+'% spike'; return tip; } },
        xAxis: { type: 'category', data: daily.map(function(d) { return d.date.substring(5); }), axisLabel: { color: '#6b7280', fontSize: 9, rotate: daily.length > 15 ? 45 : 0 } },
        yAxis: { type: 'value', axisLabel: { color: '#6b7280', formatter: '${value}' }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
        series: [{ type: 'line', data: daily.map(function(d) { return d.cost; }), smooth: true,
            areaStyle: { opacity: 0.15, color: '#10b981' }, lineStyle: { color: '#10b981' }, itemStyle: { color: '#10b981' },
            markPoint: { data: anomalyPoints.map(function(a) { return { coord: [a.xAxis, a.yAxis], value: '\u26a0\ufe0f', itemStyle: { color: '#ef4444' } }; }),
                label: { show: true, fontSize: 12 }, symbolSize: 25 } }],
        grid: { left: 50, right: 10, bottom: 30, top: 15 },
    });
    window.addEventListener('resize', function() { chart.resize(); });
}

function _renderHourlyTrend(hourly) {
    var el = $('dash-daily'); if (!el || !window.echarts) return;
    if (!hourly.length) { el.innerHTML = '<div style="color:#6b7280;font-size:0.85em;padding:20px;">No hourly usage data detected in the last 24 hours.</div>'; return; }
    var chart = echarts.init(el, null);
    // Detect anomalies: > 3x the average hourly cost
    var costs = hourly.map(function(h) { return h.cost; });
    var avg = costs.reduce(function(a,b){return a+b;},0) / costs.length;
    chart.setOption({
        tooltip: { trigger: 'axis', formatter: function(ps) {
            var h = ps[0]; var cost = h.value;
            var tip = h.axisValue + ': $' + cost.toFixed(4);
            if (cost > avg * 3) tip += ' \u26a0\ufe0f SPIKE (' + Math.round((cost/avg-1)*100) + '% above avg)';
            return tip;
        }},
        xAxis: { type: 'category', data: hourly.map(function(h) { return h.hour.substring(11, 16) || h.hour.substring(5); }), axisLabel: { color: '#6b7280', fontSize: 8, rotate: 45 } },
        yAxis: { type: 'value', axisLabel: { color: '#6b7280', formatter: '${value}' }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
        series: [{ type: 'bar', data: hourly.map(function(h) {
            return { value: h.cost, itemStyle: { color: h.cost > avg * 3 ? '#ef4444' : '#6366f1' } };
        }) }],
        grid: { left: 50, right: 10, bottom: 40, top: 10 },
    });
    window.addEventListener('resize', function() { chart.resize(); });
}

function _renderRightsizing(rs, waste) {
    var el = $('dash-rightsizing'); if (!el) return;
    var html = '<div style="display:flex;gap:12px;margin-bottom:10px;">';
    html += '<div style="text-align:center;flex:1;"><div style="color:#ef4444;font-size:1.8em;font-weight:700;">' + (rs.overProvisioned || 0) + '</div><div style="color:#8b949e;font-size:0.75em;">Over-Provisioned</div></div>';
    html += '</div>';
    if (rs.topOpportunities && rs.topOpportunities.length > 0) {
        html += '<div style="font-size:0.8em;color:#8b949e;margin-bottom:4px;">Top Opportunities:</div>';
        rs.topOpportunities.slice(0, 4).forEach(function(o) {
            html += '<div style="font-size:0.8em;color:#c9d1d9;padding:3px 0;border-bottom:1px solid #21262d;">' +
                '<span style="color:#f59e0b;">' + (o.currentType || '') + '</span> → <span style="color:#10b981;">' + (o.recommendedType || '') + '</span>' +
                ' <span style="color:#10b981;float:right;">-$' + (o.monthlySavings || 0).toFixed(2) + '/mo</span></div>';
        });
    } else {
        html += '<div style="color:#10b981;font-size:0.85em;margin-top:8px;">No over-provisioned resources detected ✓</div>';
    }
    el.innerHTML = html;
}

function _renderWaste(waste) {
    var el = $('dash-waste'); if (!el) return;
    var html = '<div style="color:#ef4444;font-size:1.5em;font-weight:700;margin-bottom:8px;">$' + (waste.totalWaste || 0).toFixed(2) + '<span style="color:#8b949e;font-size:0.5em;"> /month waste</span></div>';
    if (waste.items && waste.items.length > 0) {
        waste.items.slice(0, 6).forEach(function(w) {
            html += '<div style="font-size:0.8em;color:#c9d1d9;padding:3px 0;border-bottom:1px solid #21262d;">' +
                esc(w.type) + ': ' + esc(w.resource) + ' <span style="color:#ef4444;float:right;">$' + (w.monthlyCost || 0).toFixed(2) + '</span></div>';
        });
    } else {
        html += '<div style="color:#10b981;font-size:0.85em;">No waste detected ✓</div>';
    }
    el.innerHTML = html;
}

function _renderMonthly(monthlyTrend) {
    var el = $('dash-monthly'); if (!el || !window.echarts) return;
    var months = Object.keys(monthlyTrend).sort();
    if (months.length < 1) { el.innerHTML = '<div style="color:#6b7280;font-size:0.85em;">No monthly data yet</div>'; return; }

    // Get all services across all months and find top ones
    var allSvcs = {};
    months.forEach(function(m) {
        Object.entries(monthlyTrend[m]).forEach(function(e) {
            allSvcs[e[0]] = (allSvcs[e[0]] || 0) + e[1];
        });
    });
    // Remove Tax
    delete allSvcs['Tax'];
    // Sort by total cost, take top 8
    var topSvcs = Object.entries(allSvcs).sort(function(a,b){return b[1]-a[1];}).slice(0, 8).map(function(e){return e[0];});

    var labels = months.map(function(m) { var p=m.split('-'); var mn=['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; return (mn[parseInt(p[1])]||p[1])+' '+p[0]; });
    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316'];

    var series = topSvcs.map(function(svc, i) {
        return {
            name: svc.replace('Amazon ','').replace('AWS ','').substring(0, 25),
            type: 'bar',
            stack: 'total',
            data: months.map(function(m) { return Math.round((monthlyTrend[m][svc] || 0) * 100) / 100; }),
            itemStyle: { color: colors[i % colors.length] },
            emphasis: { focus: 'series' },
        };
    });

    var chart = echarts.init(el, null);
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
            formatter: function(ps) {
                var s = ps[0].axisValue + '<br>';
                var total = 0;
                ps.forEach(function(p) { if (p.value > 0) { s += p.marker + p.seriesName + ': $' + p.value.toFixed(2) + '<br>'; total += p.value; } });
                s += '<strong>Total: $' + total.toFixed(2) + '</strong>';
                return s;
            }
        },
        legend: { type: 'scroll', bottom: 0, textStyle: { color: '#6b7280', fontSize: 10 }, itemWidth: 12, itemHeight: 8 },
        xAxis: { type: 'category', data: labels, axisLabel: { color: '#6b7280', fontSize: 10 } },
        yAxis: { type: 'value', axisLabel: { color: '#6b7280', formatter: '${value}' }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
        series: series,
        grid: { left: 55, right: 10, bottom: 50, top: 10 },
    });
    window.addEventListener('resize', function() { chart.resize(); });
}

function _renderAccountComparison(perAccount) {
    var el = $('dash-accounts'); if (!el || !window.echarts) return;
    var valid = perAccount.filter(function(a) { return !a.error && a.totalSpend > 0; });
    if (!valid.length) { el.innerHTML = '<div style="color:#8b949e;font-size:0.85em;">No account data</div>'; return; }
    var chart = echarts.init(el, 'dark');
    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6'];
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: function(ps) { return ps[0].name + ': $' + ps[0].value.toFixed(2); } },
        xAxis: { type: 'value', axisLabel: { color: '#8b949e', formatter: '${value}' } },
        yAxis: { type: 'category', data: valid.map(function(a) { return (a.accountName || a.accountId).substring(0,20); }), axisLabel: { color: '#8b949e' } },
        series: [{ type: 'bar', data: valid.map(function(a,i) { return { value: a.totalSpend, itemStyle: { color: colors[i%colors.length] } }; }) }],
        grid: { left: 100, right: 10, bottom: 20, top: 10 },
    });
    window.addEventListener('resize', function() { chart.resize(); });
}


// ============================================================
// Cost Allocation Rules (Virtual Tagging)
// ============================================================
var allocRulesCache = null;

async function loadAllocationRules() {
    try {
        var data = await api('GET', '/members/allocation-rules');
        allocRulesCache = data.rules || [];
        return allocRulesCache;
    } catch (e) { allocRulesCache = []; return []; }
}

function showAllocationRulesModal() {
    loadAllocationRules().then(function() {
        var config = allocRulesCache || {};
        var bus = (config.businessUnits || config || []);
        if (Array.isArray(bus) && bus.length > 0 && bus[0].matchType) {
            // Legacy format — convert
            var converted = {};
            bus.forEach(function(r) {
                var bu = r.businessUnit || r.name || 'Default';
                if (!converted[bu]) converted[bu] = {name: bu, rules: []};
                converted[bu].rules.push({dimension: r.matchType || 'account', operator: 'equals', value: r.matchValue || ''});
            });
            bus = Object.values(converted);
        }
        if (!Array.isArray(bus)) bus = config.businessUnits || [];
        var sharedMode = config.sharedCostMode || 'proportional';

        var modal = document.createElement('div');
        modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:center;justify-content:center;';
        var card = document.createElement('div');
        card.style.cssText = 'background:#fff;border-radius:12px;padding:24px;max-width:700px;width:95%;max-height:85vh;overflow-y:auto;';

        card.innerHTML =
            '<h2 style="margin-top:0;color:#1f2937;">Define Business Units</h2>' +
            '<p style="color:#6b7280;font-size:0.85em;">Allocate costs to teams using "If-This-Then-That" rules. Assign costs IF Account equals X, OR Service equals Y, OR Tag contains Z.</p>' +
            '<div id="bu-list"></div>' +
            '<button id="bu-add" class="btn btn-outline btn-sm" style="margin-top:10px;">+ Add Business Unit</button>' +
            '<hr style="margin:16px 0;border-color:#e5e7eb;">' +
            '<div style="margin-bottom:12px;"><strong style="color:#1f2937;">Shared Cost Splitting</strong><p style="color:#6b7280;font-size:0.8em;margin:4px 0;">How should untaggable costs (support, networking) be split?</p>' +
            '<label style="display:block;padding:3px 0;cursor:pointer;font-size:0.9em;"><input type="radio" name="shared-mode" value="even"' + (sharedMode === 'even' ? ' checked' : '') + '> Split Evenly across all units</label>' +
            '<label style="display:block;padding:3px 0;cursor:pointer;font-size:0.9em;"><input type="radio" name="shared-mode" value="proportional"' + (sharedMode === 'proportional' ? ' checked' : '') + '> Proportional (based on each unit\'s spend)</label>' +
            '<label style="display:block;padding:3px 0;cursor:pointer;font-size:0.9em;"><input type="radio" name="shared-mode" value="custom"' + (sharedMode === 'custom' ? ' checked' : '') + '> Custom Percentage</label></div>' +
            '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
            '<button id="bu-cancel" class="btn btn-outline">Cancel</button>' +
            '<button id="bu-save" class="btn btn-primary">Save Business Units</button></div>';

        modal.appendChild(card);
        document.body.appendChild(modal);

        function renderBUs() {
            var list = card.querySelector('#bu-list');
            list.innerHTML = '';
            bus.forEach(function(bu, bi) {
                var box = document.createElement('div');
                box.style.cssText = 'background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:10px;';
                var header = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
                    '<input type="text" value="' + ea(bu.name || '') + '" placeholder="Business Unit Name (e.g. Data Science Team)" style="font-size:1em;font-weight:600;border:1px solid #d0d7de;border-radius:4px;padding:4px 8px;flex:1;margin-right:8px;" data-bu-name="' + bi + '">' +
                    '<button style="background:none;border:none;cursor:pointer;font-size:16px;color:#ef4444;" data-del-bu="' + bi + '">\u2716</button></div>';
                var rulesHtml = '<div style="padding-left:12px;" data-rules-for="' + bi + '">' +
                    '<div style="margin-bottom:6px;font-size:0.85em;display:flex;align-items:center;gap:6px;">' +
                    '<span style="color:#6b7280;">Match rules using:</span>' +
                    '<label style="cursor:pointer;"><input type="radio" name="logic-' + bi + '" value="or"' + ((bu.ruleLogic || 'or') === 'or' ? ' checked' : '') + ' data-logic="' + bi + '"> <strong>OR</strong> (any rule matches)</label>' +
                    '<label style="cursor:pointer;"><input type="radio" name="logic-' + bi + '" value="and"' + (bu.ruleLogic === 'and' ? ' checked' : '') + ' data-logic="' + bi + '"> <strong>AND</strong> (all rules must match)</label></div>';
                (bu.rules || []).forEach(function(r, ri) {
                    rulesHtml += '<div style="display:flex;gap:4px;align-items:center;margin-bottom:4px;font-size:0.85em;">' +
                        '<span style="color:#6b7280;">IF</span>' +
                        '<select data-rule-dim="' + bi + '-' + ri + '" style="padding:3px;border:1px solid #d0d7de;border-radius:4px;">' +
                        '<option value="account"' + (r.dimension === 'account' ? ' selected' : '') + '>Account ID</option>' +
                        '<option value="service"' + (r.dimension === 'service' ? ' selected' : '') + '>Service</option>' +
                        '<option value="tag"' + (r.dimension === 'tag' ? ' selected' : '') + '>Tag</option></select>' +
                        '<select data-rule-op="' + bi + '-' + ri + '" style="padding:3px;border:1px solid #d0d7de;border-radius:4px;">' +
                        '<option value="equals"' + (r.operator === 'equals' ? ' selected' : '') + '>equals</option>' +
                        '<option value="contains"' + (r.operator === 'contains' ? ' selected' : '') + '>contains</option>' +
                        '<option value="startsWith"' + (r.operator === 'startsWith' ? ' selected' : '') + '>starts with</option></select>' +
                        '<input type="text" value="' + ea(r.value || '') + '" placeholder="Value" style="flex:1;padding:3px 6px;border:1px solid #d0d7de;border-radius:4px;" data-rule-val="' + bi + '-' + ri + '">' +
                        '<button style="background:none;border:none;cursor:pointer;color:#ef4444;" data-del-rule="' + bi + '-' + ri + '">\u2716</button></div>';
                });
                rulesHtml += '<button class="btn btn-outline btn-sm" style="font-size:0.75em;margin-top:4px;" data-add-rule="' + bi + '">+ Add Rule</button></div>';
                box.innerHTML = header + rulesHtml;
                list.appendChild(box);
            });
        }
        renderBUs();

        card.querySelector('#bu-add').onclick = function() {
            bus.push({name: '', rules: [{dimension: 'account', operator: 'equals', value: ''}]});
            renderBUs();
        };
        card.querySelector('#bu-list').onclick = function(e) {
            var delBu = e.target.closest('[data-del-bu]');
            if (delBu) { bus.splice(parseInt(delBu.dataset.delBu), 1); renderBUs(); return; }
            var addRule = e.target.closest('[data-add-rule]');
            if (addRule) { bus[parseInt(addRule.dataset.addRule)].rules.push({dimension: 'account', operator: 'equals', value: ''}); renderBUs(); return; }
            var delRule = e.target.closest('[data-del-rule]');
            if (delRule) { var p = delRule.dataset.delRule.split('-'); bus[parseInt(p[0])].rules.splice(parseInt(p[1]), 1); renderBUs(); }
        };
        card.querySelector('#bu-cancel').onclick = function() { modal.remove(); };
        card.querySelector('#bu-save').onclick = async function() {
            // Collect data from form
            var finalBUs = [];
            bus.forEach(function(bu, bi) {
                var nameInput = card.querySelector('[data-bu-name="' + bi + '"]');
                var name = nameInput ? nameInput.value.trim() : bu.name;
                var rules = [];
                (bu.rules || []).forEach(function(r, ri) {
                    var dim = card.querySelector('[data-rule-dim="' + bi + '-' + ri + '"]');
                    var op = card.querySelector('[data-rule-op="' + bi + '-' + ri + '"]');
                    var val = card.querySelector('[data-rule-val="' + bi + '-' + ri + '"]');
                    if (dim && val && val.value.trim()) {
                        rules.push({dimension: dim.value, operator: op ? op.value : 'equals', value: val.value.trim()});
                    }
                });
                if (name && rules.length) {
                    var logicRadio = card.querySelector('input[name="logic-' + bi + '"]:checked');
                    finalBUs.push({name: name, rules: rules, ruleLogic: logicRadio ? logicRadio.value : 'or'});
                }
            });
            var mode = card.querySelector('input[name="shared-mode"]:checked');
            try {
                var resp = await api('POST', '/members/allocation-rules', {
                    businessUnits: finalBUs,
                    sharedCostMode: mode ? mode.value : 'proportional',
                });
                allocRulesCache = {businessUnits: finalBUs, sharedCostMode: mode ? mode.value : 'proportional', status: 'processing'};
                modal.remove();
                dashDataCache = null;
                loadDashboardData();
                notify(resp.message || 'Business units saved!', 'success');
            } catch (e) { notify('Failed: ' + (e.message || ''), 'error'); }
        };
        modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    });
}

function _renderAllocationTreemap(allocation) {
    var el = $('dash-allocation');
    if (!el) return;
    if (!allocation || !allocation.businessUnits || !allocation.businessUnits.length) {
        el.innerHTML = '<div style="color:#6b7280;font-size:0.85em;padding:20px;text-align:center;">' +
            'No business units defined yet.<br><button class="btn btn-outline btn-sm" style="margin-top:8px;" onclick="showAllocationRulesModal();">+ Define Business Units</button></div>';
        return;
    }
    // Show processing status if applicable
    var statusHtml = '';
    if (allocation.status === 'processing') {
        statusHtml = '<div style="background:#fef3c7;color:#92400e;padding:6px 10px;border-radius:4px;font-size:0.8em;margin-bottom:8px;">\u23f3 Processing... Dashboard will fully reflect these allocations within 24 hours.</div>';
    }
    var allocPct = allocation.allocatedPct || 0;
    var pctColor = allocPct >= 90 ? '#10b981' : allocPct >= 70 ? '#f59e0b' : '#ef4444';
    var headerHtml = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">' +
        '<span style="font-size:0.8em;color:' + pctColor + ';font-weight:700;">' + allocPct + '% allocated</span>' +
        '<span style="font-size:0.75em;color:#6b7280;">Shared: ' + (allocation.sharedCostMode || 'proportional') + '</span></div>';

    el.innerHTML = statusHtml + headerHtml + '<div id="dash-alloc-chart" style="width:100%;height:200px;"></div>';

    if (!window.echarts) return;
    var chartEl = document.getElementById('dash-alloc-chart');
    if (!chartEl) return;
    var chart = echarts.init(chartEl, null);
    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316'];
    chart.setOption({
        tooltip: { formatter: function(p) { return p.name + ': $' + p.value.toFixed(2) + ' (' + (p.data.pct || 0) + '%)'; } },
        series: [{ type: 'treemap', data: allocation.businessUnits.map(function(bu) {
            return { name: bu.businessUnit, value: bu.cost, pct: bu.pct };
        }), label: { show: true, formatter: '{b}\n${c}', fontSize: 11 }, breadcrumb: { show: false },
            itemStyle: { borderColor: '#fff', borderWidth: 2 } }],
        color: colors,
    });
    window.addEventListener('resize', function() { chart.resize(); });
}


// ============================================================
// Unit Economics
// ============================================================
function _renderUnitEconomics(ue) {
    var el = $('dash-unit-economics');
    if (!el) return;
    if (!ue || !ue.trend || !ue.trend.length) {
        el.innerHTML = '<div style="color:#6b7280;font-size:0.85em;padding:20px;text-align:center;">' +
            'No business metrics defined yet.<br>Add monthly volumes (users, transactions, etc.) to see unit cost trends.' +
            '<br><button class="btn btn-outline btn-sm" style="margin-top:8px;" onclick="showBusinessMetricsModal();">+ Add Business Metrics</button></div>';
        return;
    }
    if (!window.echarts) return;
    var chart = echarts.init(el, null);
    var months = ue.trend.map(function(t) { var p=t.month.split('-'); var mn=['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; return (mn[parseInt(p[1])]||p[1])+' '+p[0]; });
    var volumes = ue.trend.map(function(t) { return t.volume; });
    var unitCosts = ue.trend.map(function(t) { return t.costPerUnit; });
    chart.setOption({
        tooltip: { trigger: 'axis', formatter: function(ps) { var s = ps[0].axisValue + '<br>'; ps.forEach(function(p) { s += p.marker + p.seriesName + ': ' + (p.seriesName.indexOf('Cost') > -1 ? '$' + p.value.toFixed(4) : p.value.toLocaleString()) + '<br>'; }); return s; } },
        legend: { textStyle: { color: '#374151' }, top: 0 },
        xAxis: { type: 'category', data: months, axisLabel: { color: '#6b7280', fontSize: 10 } },
        yAxis: [
            { type: 'value', name: ue.metricName, nameTextStyle: { color: '#6b7280', fontSize: 10 }, axisLabel: { color: '#6b7280' }, splitLine: { lineStyle: { color: '#e5e7eb' } } },
            { type: 'value', name: 'Cost/Unit', nameTextStyle: { color: '#6b7280', fontSize: 10 }, axisLabel: { color: '#6b7280', formatter: '${value}' }, splitLine: { show: false } }
        ],
        series: [
            { name: ue.metricName + ' Volume', type: 'bar', yAxisIndex: 0, data: volumes, itemStyle: { color: '#6366f1', opacity: 0.7 } },
            { name: 'Cost per ' + ue.metricName, type: 'line', yAxisIndex: 1, data: unitCosts, smooth: true, lineStyle: { color: '#10b981', width: 3 }, itemStyle: { color: '#10b981' }, symbol: 'circle', symbolSize: 8 }
        ],
        grid: { left: 60, right: 60, bottom: 25, top: 40 },
    });
    window.addEventListener('resize', function() { chart.resize(); });
}

function _renderRegionalPie(costByRegion) {
    var container = $('dash-regional');
    if (!container) return;
    if (!costByRegion || costByRegion.length === 0) {
        container.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:40px 0;">No regional cost data available</div>';
        return;
    }
    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16','#a855f7'];
    var total = costByRegion.reduce(function(s,r){return s+r.cost;},0);
    var pieData = costByRegion.map(function(r,i){
        var label = r.region || 'Global';
        if (label === 'global') label = 'Global (no region)';
        return {value:r.cost, name:label + ' ($' + r.cost.toFixed(2) + ', ' + r.pct + '%)', itemStyle:{color:colors[i%colors.length]}};
    });
    var chart = echarts.init(container);
    chart.setOption({
        tooltip:{trigger:'item',formatter:'{b}'},
        series:[{
            type:'pie',
            radius:['35%','70%'],
            center:['50%','55%'],
            data:pieData,
            label:{show:true,fontSize:10,formatter:'{b}',overflow:'truncate',width:120},
            emphasis:{itemStyle:{shadowBlur:10,shadowOffsetX:0,shadowColor:'rgba(0,0,0,0.3)'}},
            animationType:'scale',
        }]
    });
    dashboardCharts.push(chart);
    window.addEventListener('resize',function(){chart.resize();});
}

function _renderCommitments(commitments) {
    var container = $('dash-commitments');
    if (!container) return;
    if (!commitments || (!commitments.savingsPlans && !commitments.ec2ReservedInstances && !commitments.rdsReservedInstances)) {
        container.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:40px 0;">No Data to share</div>';
        return;
    }
    var sp = commitments.savingsPlans || [];
    var ec2ri = commitments.ec2ReservedInstances || [];
    var rdsri = commitments.rdsReservedInstances || [];
    var spCov = commitments.spCoverage || {};
    var riCov = commitments.riCoverage || {};
    var html = '';

    // Summary bar
    html += '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">';
    html += '<div style="flex:1;min-width:120px;background:#f0f2f5;border-radius:10px;padding:12px;text-align:center;">'
        + '<div style="font-size:22px;font-weight:800;color:#6366f1;">' + sp.length + '</div>'
        + '<div style="font-size:11px;color:#9ca3af;">Savings Plans</div></div>';
    html += '<div style="flex:1;min-width:120px;background:#f0f2f5;border-radius:10px;padding:12px;text-align:center;">'
        + '<div style="font-size:22px;font-weight:800;color:#3b82f6;">' + (commitments.totalEC2RI || 0) + '</div>'
        + '<div style="font-size:11px;color:#9ca3af;">EC2 RIs</div></div>';
    html += '<div style="flex:1;min-width:120px;background:#f0f2f5;border-radius:10px;padding:12px;text-align:center;">'
        + '<div style="font-size:22px;font-weight:800;color:#10b981;">' + (commitments.totalRDSRI || 0) + '</div>'
        + '<div style="font-size:11px;color:#9ca3af;">RDS RIs</div></div>';
    html += '</div>';

    // SP Coverage gauge
    var spCovKeys = Object.keys(spCov);
    if (spCovKeys.length > 0) {
        var avgSpCov = spCovKeys.reduce(function(s,k){return s + spCov[k].coveragePct;}, 0) / spCovKeys.length;
        var covColor = avgSpCov >= 70 ? '#10b981' : avgSpCov >= 40 ? '#f59e0b' : '#ef4444';
        html += '<div style="margin-bottom:12px;"><div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">SP Coverage</div>'
            + '<div style="background:#e5e7eb;border-radius:6px;height:10px;overflow:hidden;">'
            + '<div style="width:' + Math.min(avgSpCov, 100) + '%;height:100%;background:' + covColor + ';border-radius:6px;transition:width .5s;"></div></div>'
            + '<div style="font-size:11px;color:#9ca3af;margin-top:2px;">' + avgSpCov.toFixed(1) + '% covered</div></div>';
    }

    // RI Coverage gauge
    var riCovKeys = Object.keys(riCov);
    if (riCovKeys.length > 0) {
        var avgRiCov = riCovKeys.reduce(function(s,k){return s + riCov[k].coveragePct;}, 0) / riCovKeys.length;
        var riColor = avgRiCov >= 70 ? '#10b981' : avgRiCov >= 40 ? '#f59e0b' : '#ef4444';
        html += '<div style="margin-bottom:12px;"><div style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">RI Coverage</div>'
            + '<div style="background:#e5e7eb;border-radius:6px;height:10px;overflow:hidden;">'
            + '<div style="width:' + Math.min(avgRiCov, 100) + '%;height:100%;background:' + riColor + ';border-radius:6px;transition:width .5s;"></div></div>'
            + '<div style="font-size:11px;color:#9ca3af;margin-top:2px;">' + avgRiCov.toFixed(1) + '% covered</div></div>';
    }

    // Savings Plans list
    if (sp.length > 0) {
        html += '<div style="font-size:12px;font-weight:600;color:#374151;margin:12px 0 6px;">Active Savings Plans</div>';
        html += '<div style="max-height:180px;overflow-y:auto;">';
        sp.forEach(function(s) {
            var endDate = s.end ? new Date(s.end).toLocaleDateString() : 'N/A';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;">'
                + '<div><span style="font-weight:600;color:#1f2937;">' + esc(s.type) + '</span>'
                + ' <span style="color:#9ca3af;">' + esc(s.paymentOption) + ' \u00b7 ' + s.term + 'yr</span></div>'
                + '<div style="text-align:right;"><span style="font-weight:700;color:#6366f1;">$' + s.commitment.toFixed(2) + '/hr</span>'
                + '<div style="font-size:10px;color:#9ca3af;">Ends ' + endDate + '</div></div></div>';
        });
        html += '</div>';
    }

    // EC2 RIs
    if (ec2ri.length > 0) {
        html += '<div style="font-size:12px;font-weight:600;color:#374151;margin:12px 0 6px;">EC2 Reserved Instances</div>';
        html += '<div style="max-height:140px;overflow-y:auto;">';
        ec2ri.forEach(function(r) {
            html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;">'
                + '<div><span style="font-weight:600;color:#1f2937;">' + esc(r.instanceType) + '</span>'
                + ' <span style="color:#9ca3af;">\u00d7' + r.count + ' \u00b7 ' + esc(r.offeringClass) + '</span></div>'
                + '<div style="font-size:10px;color:#9ca3af;">' + esc(r.offeringType) + '</div></div>';
        });
        html += '</div>';
    }

    // RDS RIs
    if (rdsri.length > 0) {
        html += '<div style="font-size:12px;font-weight:600;color:#374151;margin:12px 0 6px;">RDS Reserved Instances</div>';
        html += '<div style="max-height:140px;overflow-y:auto;">';
        rdsri.forEach(function(r) {
            html += '<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-bottom:1px solid #f3f4f6;font-size:12px;">'
                + '<div><span style="font-weight:600;color:#1f2937;">' + esc(r.dbInstanceClass) + '</span>'
                + ' <span style="color:#9ca3af;">\u00d7' + r.count + ' \u00b7 ' + esc(r.engine) + '</span></div>'
                + '<div style="font-size:10px;color:#9ca3af;">' + esc(r.offeringType) + '</div></div>';
        });
        html += '</div>';
    }

    // No EC2/RDS fallback
    if (ec2ri.length === 0 && rdsri.length === 0 && sp.length === 0) {
        html = '<div style="color:#9ca3af;text-align:center;padding:40px 0;">No Data to share</div>';
    }

    container.innerHTML = html;
}

var _costByTagCurrentKey = null;

function _renderCostByTag(costByTag) {
    var container = $('dash-cost-by-tag');
    if (!container) return;
    if (!costByTag || !costByTag.tagKeys || costByTag.tagKeys.length === 0) {
        container.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:40px 0;">No cost allocation tags found.<br><span style="font-size:0.85em;">Activate cost allocation tags in AWS Billing &gt; Cost Allocation Tags</span></div>';
        return;
    }

    var tagKeys = costByTag.tagKeys;
    var data = costByTag.data || {};

    // Pick default tag key: prefer Environment, CostCenter, Owner, or first available
    if (!_costByTagCurrentKey || tagKeys.indexOf(_costByTagCurrentKey) === -1) {
        var preferred = ['Environment', 'environment', 'CostCenter', 'costCenter', 'Owner', 'owner', 'Application', 'application'];
        _costByTagCurrentKey = null;
        for (var i = 0; i < preferred.length; i++) {
            if (tagKeys.indexOf(preferred[i]) !== -1 && data[preferred[i]]) {
                _costByTagCurrentKey = preferred[i];
                break;
            }
        }
        if (!_costByTagCurrentKey) _costByTagCurrentKey = tagKeys[0];
    }

    // Build tag key selector
    var html = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">';
    html += '<label style="font-size:12px;font-weight:600;color:#374151;">Tag Key:</label>';
    html += '<select id="dash-tag-key-select" style="padding:4px 8px;border:1px solid #d1d5db;border-radius:6px;font-size:12px;background:#fff;" onchange="_costByTagCurrentKey=this.value;_renderCostByTagChart();">';
    tagKeys.forEach(function(k) {
        var hasData = data[k] && data[k].values && data[k].values.length > 0;
        html += '<option value="' + k + '"' + (k === _costByTagCurrentKey ? ' selected' : '') + (hasData ? '' : ' disabled') + '>' + k + (hasData ? '' : ' (no data)') + '</option>';
    });
    html += '</select>';

    var tagData = data[_costByTagCurrentKey];
    if (tagData) {
        html += '<span style="font-size:11px;color:#6b7280;margin-left:auto;">Coverage: <strong style="color:' + (tagData.coverage >= 80 ? '#10b981' : tagData.coverage >= 50 ? '#f59e0b' : '#ef4444') + ';">' + tagData.coverage + '%</strong></span>';
    }
    html += '</div>';

    html += '<div id="dash-tag-chart" style="width:100%;height:240px;"></div>';
    container.innerHTML = html;

    // Store data for chart rendering
    container._tagData = data;
    _renderCostByTagChart();
}

function _renderCostByTagChart() {
    var container = $('dash-cost-by-tag');
    if (!container || !container._tagData) return;
    var chartEl = document.getElementById('dash-tag-chart');
    if (!chartEl) return;

    var tagData = container._tagData[_costByTagCurrentKey];
    if (!tagData || !tagData.values || tagData.values.length === 0) {
        chartEl.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:60px 0;">No cost data for this tag key</div>';
        return;
    }

    var colors = ['#6366f1','#10b981','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16','#a855f7','#64748b','#d946ef','#0ea5e9'];
    var values = tagData.values;

    var chart = echarts.init(chartEl);
    chart.setOption({
        tooltip: {
            trigger: 'item',
            formatter: function(p) { return p.name + '<br/>$' + p.value.toFixed(2) + ' (' + p.data.pct + '%)'; }
        },
        series: [{
            type: 'pie',
            radius: ['30%', '65%'],
            center: ['50%', '55%'],
            data: values.map(function(v, i) {
                return {
                    value: v.cost,
                    name: v.tag,
                    pct: v.pct,
                    itemStyle: { color: v.tag === '(untagged)' ? '#d1d5db' : colors[i % colors.length] }
                };
            }),
            label: { show: true, fontSize: 10, formatter: '{b}: ${c}', overflow: 'truncate', width: 110 },
            emphasis: { itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.3)' } },
            animationType: 'scale',
        }]
    });
    dashboardCharts.push(chart);
    window.addEventListener('resize', function() { chart.resize(); });
}

function showBusinessMetricsModal() {
    var discovered = (dashDataCache && dashDataCache.discoveredMetrics) || [];
    var modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:center;justify-content:center;';
    var card = document.createElement('div');
    card.style.cssText = 'background:#fff;border-radius:12px;padding:24px;max-width:550px;width:95%;max-height:85vh;overflow-y:auto;';

    var discoveredHtml = '';
    if (discovered.length > 0) {
        discoveredHtml = '<div style="margin-bottom:16px;"><div style="font-weight:600;color:#1f2937;margin-bottom:6px;">Auto-Discovered Metrics (from your AWS accounts):</div>';
        discovered.forEach(function(d, i) {
            discoveredHtml += '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;margin-bottom:4px;font-size:0.85em;">' +
                '<span style="color:#16a34a;font-weight:600;">\u2713</span>' +
                '<span style="flex:1;color:#1f2937;">' + esc(d.metricName) + ': <strong>' + (d.volume || 0).toLocaleString() + '</strong></span>' +
                '<span style="color:#6b7280;font-size:0.8em;">' + esc(d.description || '') + '</span>' +
                '<button class="btn btn-outline btn-sm" style="font-size:0.75em;padding:2px 8px;" data-use-metric="' + i + '">Use</button></div>';
        });
        discoveredHtml += '</div><hr style="border-color:#e5e7eb;margin:12px 0;"><div style="font-weight:600;color:#1f2937;margin-bottom:6px;">Or enter manually:</div>';
    }

    card.innerHTML =
        '<h2 style="margin-top:0;color:#1f2937;">Business Metrics</h2>' +
        '<p style="color:#6b7280;font-size:0.85em;">Enter business volumes to calculate unit costs. You can use auto-discovered AWS metrics or enter custom ones.</p>' +
        discoveredHtml +
        '<div class="form-group" style="margin-bottom:12px;">' +
            '<label style="font-weight:600;font-size:0.9em;color:#374151;">Metric Name</label>' +
            '<input type="text" id="bm-name" placeholder="e.g. ActiveUsers, Transactions, API_Calls" style="width:100%;padding:6px 10px;border:1px solid #d0d7de;border-radius:4px;margin-top:4px;box-sizing:border-box;">' +
        '</div>' +
        '<div style="display:flex;gap:8px;">' +
            '<div class="form-group" style="margin-bottom:12px;flex:1;">' +
                '<label style="font-weight:600;font-size:0.9em;color:#374151;">From Month</label>' +
                '<input type="month" id="bm-month-from" style="width:100%;padding:6px 10px;border:1px solid #d0d7de;border-radius:4px;margin-top:4px;box-sizing:border-box;">' +
            '</div>' +
            '<div class="form-group" style="margin-bottom:12px;flex:1;">' +
                '<label style="font-weight:600;font-size:0.9em;color:#374151;">To Month (optional)</label>' +
                '<input type="month" id="bm-month-to" style="width:100%;padding:6px 10px;border:1px solid #d0d7de;border-radius:4px;margin-top:4px;box-sizing:border-box;">' +
            '</div>' +
        '</div>' +
        '<div class="form-group" style="margin-bottom:12px;">' +
            '<label style="font-weight:600;font-size:0.9em;color:#374151;">Volume (per month)</label>' +
            '<input type="number" id="bm-volume" placeholder="e.g. 50000" style="width:100%;padding:6px 10px;border:1px solid #d0d7de;border-radius:4px;margin-top:4px;box-sizing:border-box;">' +
        '</div>' +
        '<div id="bm-error" style="color:#ef4444;font-size:0.85em;margin-bottom:8px;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
            '<button id="bm-cancel" class="btn btn-outline">Cancel</button>' +
            '<button id="bm-save" class="btn btn-primary">Save Metric(s)</button></div>';
    modal.appendChild(card);
    document.body.appendChild(modal);

    // Handle "Use" button for discovered metrics
    card.onclick = function(e) {
        var useBtn = e.target.closest('[data-use-metric]');
        if (useBtn) {
            var idx = parseInt(useBtn.dataset.useMetric);
            var d = discovered[idx];
            if (d) {
                card.querySelector('#bm-name').value = d.metricName;
                card.querySelector('#bm-volume').value = d.volume;
            }
        }
    };

    card.querySelector('#bm-cancel').onclick = function() { modal.remove(); };
    card.querySelector('#bm-save').onclick = async function() {
        var name = card.querySelector('#bm-name').value.trim();
        var monthFrom = card.querySelector('#bm-month-from').value;
        var monthTo = card.querySelector('#bm-month-to').value || monthFrom;
        var volume = parseFloat(card.querySelector('#bm-volume').value);
        var errEl = card.querySelector('#bm-error');
        if (!name || !monthFrom || isNaN(volume) || volume <= 0) {
            errEl.textContent = 'Metric name, month, and volume (>0) are required.';
            return;
        }
        // Generate list of months from monthFrom to monthTo
        var months = [];
        var cur = monthFrom;
        while (cur <= monthTo) {
            months.push(cur);
            var parts = cur.split('-');
            var y = parseInt(parts[0]), m = parseInt(parts[1]) + 1;
            if (m > 12) { m = 1; y++; }
            cur = y + '-' + (m < 10 ? '0' + m : m);
        }
        try {
            for (var i = 0; i < months.length; i++) {
                await api('POST', '/members/business-metrics', { metricName: name, metricMonth: months[i], metricVolume: volume });
            }
            modal.remove();
            dashDataCache = null;
            loadDashboardData();
            notify('Saved ' + months.length + ' month(s) of business metrics!', 'success');
        } catch (e) { errEl.textContent = e.message || 'Failed to save.'; }
    };
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
}


// ============================================================
// Enable Hourly Cost Data
// ============================================================
function showEnableHourlyModal(accountId) {
    var modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:1000;display:flex;align-items:center;justify-content:center;';
    var card = document.createElement('div');
    card.style.cssText = 'background:#fff;border-radius:12px;padding:24px;max-width:550px;width:95%;max-height:80vh;overflow-y:auto;';
    card.innerHTML =
        '<h2 style="margin-top:0;color:#1f2937;">Enable Hourly Cost Data</h2>' +
        '<p style="color:#6b7280;font-size:0.9em;">To get real-time hourly cost tracking in SlashMyBill, you need to enable hourly granularity in your AWS account\'s Cost Explorer settings.</p>' +
        '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:16px 0;">' +
            '<div style="font-weight:600;color:#16a34a;margin-bottom:8px;">Steps to enable:</div>' +
            '<ol style="color:#1f2937;font-size:0.9em;margin:0;padding-left:20px;">' +
                '<li>Sign in to the <strong>management (payer) account</strong> for ' + accountId + '</li>' +
                '<li>Go to <strong>AWS Cost Management \u2192 Cost Explorer \u2192 Settings</strong></li>' +
                '<li>Under "Cost Explorer", check <strong>"Hourly and Resource Level Data"</strong></li>' +
                '<li>Click <strong>Save</strong></li>' +
                '<li>Wait 24\u201348 hours for hourly data to become available</li>' +
            '</ol>' +
        '</div>' +
        '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px;margin-bottom:12px;">' +
            '<div style="font-size:0.85em;color:#92400e;"><strong>Why console-only?</strong> AWS does not currently provide an API to enable this setting programmatically. It must be done manually in the console once per account.</div>' +
        '</div>' +
        '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px;margin-bottom:16px;">' +
            '<div style="font-size:0.85em;color:#1e40af;"><strong>Cost:</strong> ~$0.01 per 1,000 usage records/month (typically &lt;$1/month). For linked accounts, enable from the management (payer) account.</div>' +
        '</div>' +
        '<div id="hourly-check-result-' + accountId + '" style="margin-bottom:12px;"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;">' +
            '<button id="hourly-check-btn-' + accountId + '" class="btn btn-outline">Check Status</button>' +
            '<a href="https://us-east-1.console.aws.amazon.com/cost-management/home?region=us-east-1#/settings" target="_blank" rel="noopener" class="btn btn-primary" style="text-decoration:none;">Open Cost Explorer Settings \u2192</a>' +
        '</div>';
    modal.appendChild(card);
    modal.className = 'modal-overlay';
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);

    // Wire up the Check Status button
    var checkBtn = document.getElementById('hourly-check-btn-' + accountId);
    var resultDiv = document.getElementById('hourly-check-result-' + accountId);
    if (checkBtn) {
        checkBtn.onclick = async function() {
            checkBtn.disabled = true;
            checkBtn.textContent = 'Checking...';
            resultDiv.innerHTML = '';
            try {
                var data = await api('POST', '/members/accounts/test', { accountId: accountId });
                if (data.hourlyEnabled) {
                    resultDiv.innerHTML = '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:10px;color:#16a34a;font-size:0.9em;">✓ Hourly granularity is <strong>enabled</strong> on this account.</div>';
                } else {
                    resultDiv.innerHTML = '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:10px;color:#92400e;font-size:0.9em;">✗ Hourly granularity is <strong>not yet enabled</strong>. After enabling in the console, wait 24\u201348 hours and check again.</div>';
                }
                await loadAccounts();
            } catch (err) {
                resultDiv.innerHTML = '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:10px;color:#dc2626;font-size:0.9em;">Error: ' + esc(err.message || 'Check failed') + '</div>';
            } finally {
                checkBtn.disabled = false;
                checkBtn.textContent = 'Check Status';
            }
        };
    }
}

// ============================================================
// Act Tab — Level 1 Resource Hygiene
// ============================================================
var _actScanData = null;
var _actPendingCard = null;

function populateActAccounts() {
    var el = $('act-account-select');
    if (!el) return;
    el.innerHTML = '';
    var connected = allAccounts.filter(function(a) { return a.connectionStatus === 'connected'; });
    if (!connected.length) {
        el.innerHTML = '<span style="color:#8b949e;font-size:0.85em;">No connected accounts</span>';
        return;
    }

    var toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn btn-outline btn-sm';
    toggleBtn.style.cssText = 'font-size:0.85em;padding:4px 12px;min-width:180px;text-align:left;';

    function updateActLabel() {
        var checked = el.querySelectorAll('.act-acct-cb:checked');
        if (checked.length === 0) toggleBtn.textContent = 'Select accounts...';
        else if (checked.length === 1) toggleBtn.textContent = checked[0].parentElement.dataset.label || checked[0].value;
        else toggleBtn.textContent = checked.length + ' accounts selected';
        toggleBtn.textContent += ' \u25be';
    }

    var panel = document.createElement('div');
    panel.style.cssText = 'display:none;position:absolute;top:100%;left:0;z-index:200;background:#fff;border:1px solid #d0d7de;border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.15);min-width:260px;max-height:200px;overflow-y:auto;padding:6px 0;margin-top:4px;';

    connected.forEach(function(a) {
        var row = document.createElement('label');
        row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;color:#24292f;font-size:0.85em;white-space:nowrap;';
        row.dataset.label = a.accountId + ' (' + (a.accountName || 'Account') + ')';
        row.onmouseenter = function() { row.style.background = '#f6f8fa'; };
        row.onmouseleave = function() { row.style.background = ''; };
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = a.accountId; cb.className = 'act-acct-cb';
        cb.checked = true;
        cb.style.cssText = 'accent-color:#6366f1;flex-shrink:0;';
        cb.onchange = updateActLabel;
        row.appendChild(cb);
        row.appendChild(document.createTextNode(a.accountId + ' (' + (a.accountName || 'Account ' + a.accountId.slice(-4)) + ')'));
        panel.appendChild(row);
    });

    var ctrlRow = document.createElement('div');
    ctrlRow.style.cssText = 'display:flex;gap:8px;padding:6px 12px;border-top:1px solid #d0d7de;margin-top:4px;';
    var selAll = document.createElement('a');
    selAll.href = '#'; selAll.textContent = 'Select All'; selAll.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selAll.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.act-acct-cb').forEach(function(c) { c.checked = true; }); updateActLabel(); };
    var selNone = document.createElement('a');
    selNone.href = '#'; selNone.textContent = 'Clear'; selNone.style.cssText = 'font-size:0.8em;color:#6366f1;text-decoration:none;';
    selNone.onclick = function(e) { e.preventDefault(); panel.querySelectorAll('.act-acct-cb').forEach(function(c) { c.checked = false; }); updateActLabel(); };
    ctrlRow.appendChild(selAll); ctrlRow.appendChild(selNone);
    panel.appendChild(ctrlRow);

    var wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;display:inline-block;';
    wrapper.appendChild(toggleBtn); wrapper.appendChild(panel);
    el.appendChild(wrapper);

    toggleBtn.onclick = function(e) { e.stopPropagation(); panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; };
    document.addEventListener('click', function(e) { if (!wrapper.contains(e.target)) panel.style.display = 'none'; });
    updateActLabel();
}

function getActSelectedAccountIds() {
    var cbs = document.querySelectorAll('.act-acct-cb:checked');
    var ids = []; cbs.forEach(function(cb) { ids.push(cb.value); }); return ids;
}

function _syncActSelection() {
    // Save Act selection into shared state
    var ids = getActSelectedAccountIds();
    if (ids.length > 0) _sharedSelectedAccounts = ids;
}

function _switchActSection(section) {
    document.querySelectorAll('.act-nav-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.section === section);
    });
    var waste = document.getElementById('act-section-waste');
    var tagging = document.getElementById('act-section-tagging');
    if (waste) waste.style.display = section === 'waste' ? 'block' : 'none';
    if (tagging) tagging.style.display = section === 'tagging' ? 'block' : 'none';
}

function initActTab() {
    var scanBtn = $('act-scan-btn');
    if (!scanBtn) return;

    scanBtn.onclick = async function() {
        _syncActSelection();
        var accountIds = getActSelectedAccountIds();
        await _actRunScan(accountIds);
    };
}
initActTab();

async function _actRunScan(accountIds) {
    var status = $('act-scan-status');
    var grid = $('act-cards-grid');
    var empty = $('act-empty');
    var totalBanner = $('act-total-savings');
    var scanBtn = $('act-scan-btn');

    if (status) status.textContent = '🔍 Scanning accounts for idle resources…';
    if (grid) grid.innerHTML = '';
    if (empty) empty.style.display = 'none';
    if (totalBanner) totalBanner.style.display = 'none';
    if (scanBtn) { scanBtn.disabled = true; scanBtn.textContent = 'Scanning…'; }

    // All 7 scan categories — always shown regardless of findings
    var ALL_CATEGORIES = [
        { type: 'elastic-ip',   icon: '🌐', title: 'Unassociated Elastic IPs',   cleanMsg: 'No unassociated Elastic IPs found' },
        { type: 'ebs-volume',   icon: '💾', title: 'Unattached EBS Volumes',      cleanMsg: 'No unattached EBS volumes found' },
        { type: 'load-balancer',icon: '⚖️', title: 'Idle Load Balancers',         cleanMsg: 'No idle load balancers found' },
        { type: 's3-lifecycle', icon: '🪣', title: 'S3 Buckets Needing Attention',cleanMsg: 'All S3 buckets have lifecycle policies' },
        { type: 'ec2-idle',     icon: '🖥️', title: 'Idle EC2 Instances',          cleanMsg: 'No idle EC2 instances found (CPU ≥ 5%)' },
        { type: 'rds-idle',     icon: '🗄️', title: 'Idle RDS Instances',          cleanMsg: 'No idle RDS instances found' },
        { type: 'ebs-snapshot', icon: '📸', title: 'Stale EBS Snapshots (180d+)', cleanMsg: 'No snapshots older than 180 days' },
    ];

    try {
        var data = await api('POST', '/members/actions/scan', { accountIds: accountIds });
        _actScanData = data;

        if (status) {
            var ts = new Date(data.scannedAt || Date.now()).toLocaleTimeString();
            status.textContent = 'Scanned ' + (data.scannedAccounts || 0) + ' account(s) at ' + ts +
                (data.totalSavings > 0 ? ' · ' + (data.cards || []).filter(function(c){return c.count > 0;}).length + ' issue(s) found' : ' · All clean ✅');
        }

        // Show total savings banner
        if (data.totalSavings > 0 && totalBanner) {
            totalBanner.style.display = 'flex';
            var amtEl = $('act-total-savings-amount');
            if (amtEl) amtEl.textContent = '$' + data.totalSavings.toFixed(2) + '/month';
        }

        // Build a map of returned cards by type (may have multiple accounts per type)
        var cardsByType = {};
        (data.cards || []).forEach(function(card) {
            if (!cardsByType[card.type]) cardsByType[card.type] = [];
            cardsByType[card.type].push(card);
        });

        // Always render all 7 categories
        ALL_CATEGORIES.forEach(function(cat) {
            var found = cardsByType[cat.type] || [];
            if (found.length > 0) {
                if (found.length === 1) {
                    // Single account — render as-is
                    if (grid) grid.appendChild(_actBuildCard(found[0]));
                } else {
                    // Multiple accounts — merge into one combined card
                    if (grid) grid.appendChild(_actBuildMergedCard(cat, found));
                }
            } else {
                // Render a "clean" placeholder card
                if (grid) grid.appendChild(_actBuildCleanCard(cat));
            }
        });

    } catch (err) {
        if (status) status.textContent = '❌ Scan failed: ' + (err.message || 'Unknown error');
        if (empty) empty.style.display = 'block';
    } finally {
        if (scanBtn) { scanBtn.disabled = false; scanBtn.textContent = '🔍 Scan for Waste'; }
    }
}

function _actShowRedeployGuide(accountId) {
    var existing = document.getElementById('act-redeploy-modal');
    if (existing) existing.remove();

    var modal = document.createElement('div');
    modal.id = 'act-redeploy-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:700;display:flex;align-items:center;justify-content:center;';

    var card = document.createElement('div');
    card.style.cssText = 'background:#1c2128;border:1px solid #30363d;border-radius:12px;padding:24px;max-width:520px;width:95%;box-shadow:0 8px 32px rgba(0,0,0,0.5);';
    card.innerHTML =
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">' +
            '<h3 style="margin:0;color:#e6edf3;">🔐 Update IAM Role Permissions</h3>' +
            '<button onclick="document.getElementById(\'act-redeploy-modal\').remove();" style="background:none;border:none;color:#8b949e;font-size:1.3em;cursor:pointer;">✕</button>' +
        '</div>' +
        '<div style="background:#1e3a5f;border:1px solid #2563eb;border-radius:8px;padding:12px;margin-bottom:16px;font-size:0.85em;color:#93c5fd;">' +
            '<strong>Why is this needed?</strong> The SlashMyBill IAM role in your AWS account was deployed with read-only permissions. ' +
            'Write actions (apply lifecycle policies, delete objects, stop instances, delete snapshots) require additional permissions that were added in a newer version of the CloudFormation template.' +
        '</div>' +
        '<div style="background:#161b22;border-radius:8px;padding:14px;margin-bottom:16px;">' +
            '<div style="font-weight:600;color:#e6edf3;margin-bottom:10px;">Steps to update:</div>' +
            '<ol style="color:#c9d1d9;font-size:0.85em;margin:0;padding-left:20px;line-height:1.8;">' +
                '<li>Go to the <strong>Configure</strong> tab in SlashMyBill</li>' +
                '<li>Click the <strong>↓ Download CF Template</strong> button for account <code style="background:#21262d;padding:1px 4px;border-radius:3px;">' + esc(accountId) + '</code></li>' +
                '<li>In your AWS Console, go to <strong>CloudFormation → Stacks</strong></li>' +
                '<li>Find the stack <code style="background:#21262d;padding:1px 4px;border-radius:3px;">SlashMyBill-Access-' + esc(accountId) + '</code></li>' +
                '<li>Click <strong>Update</strong> → <strong>Replace current template</strong> → upload the new template</li>' +
                '<li>Review the IAM permission changes and confirm the update</li>' +
            '</ol>' +
        '</div>' +
        '<div style="background:#3b1f1f;border:1px solid #7f1d1d;border-radius:8px;padding:10px;margin-bottom:16px;font-size:0.82em;color:#fca5a5;">' +
            '⚠ <strong>Important:</strong> The updated template adds write permissions for S3 (lifecycle + delete), EC2 (stop), RDS (delete), and EBS snapshots (delete). ' +
            'Only grant these if you trust SlashMyBill to perform cleanup actions on your behalf. All actions require explicit confirmation before execution.' +
        '</div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end;">' +
            '<button onclick="document.getElementById(\'act-redeploy-modal\').remove();" class="btn btn-outline">Close</button>' +
            '<button onclick="document.getElementById(\'act-redeploy-modal\').remove();document.querySelector(\'[data-tab=accounts-tab]\').click();" class="btn btn-primary">Go to Configure Tab →</button>' +
        '</div>';

    modal.appendChild(card);
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);
}

function _actBuildCleanCard(cat) {
    var div = document.createElement('div');
    div.style.cssText = 'background:#161b22;border:1px solid #21262d;border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:8px;opacity:0.7;';
    div.innerHTML =
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
            '<div style="display:flex;gap:10px;align-items:center;">' +
                '<span style="font-size:1.6em;">' + cat.icon + '</span>' +
                '<div style="font-weight:600;color:#8b949e;font-size:0.9em;">' + esc(cat.title) + '</div>' +
            '</div>' +
            '<span style="color:#16a34a;font-size:1.1em;">✓</span>' +
        '</div>' +
        '<div style="color:#6b7280;font-size:0.82em;">' + esc(cat.cleanMsg) + '</div>';
    return div;
}

function _actBuildMergedCard(cat, cards) {
    // Merge multiple per-account cards of the same type into one combined card
    var totalCount = cards.reduce(function(s, c) { return s + (c.count || 0); }, 0);
    var totalSavings = cards.reduce(function(s, c) { return s + (c.monthlySavings || 0); }, 0);
    var highestRisk = cards.some(function(c) { return c.risk === 'high'; }) ? 'high'
        : cards.some(function(c) { return c.risk === 'medium'; }) ? 'medium' : 'low';

    // Build a merged card using the first card as template, with all resources combined
    var merged = Object.assign({}, cards[0], {
        cardId: cards[0].cardId + '-merged',
        count: totalCount,
        monthlySavings: totalSavings > 0 ? round2(totalSavings) : null,
        risk: highestRisk,
        description: totalCount + ' ' + cat.title.toLowerCase() + ' across ' + cards.length + ' accounts',
        // Combine resources with account labels
        resources: cards.reduce(function(all, card) {
            return all.concat((card.resources || []).map(function(r) {
                return Object.assign({}, r, {
                    _accountLabel: card.accountLabel || card.accountId,
                    _accountId: card.accountId,
                });
            }));
        }, []),
        _mergedAccounts: cards.map(function(c) { return c.accountLabel || c.accountId; }),
    });

    return _actBuildCard(merged);
}

function round2(n) { return Math.round(n * 100) / 100; }

function _actBuildCard(card) {
    var riskColor = card.risk === 'low' ? '#16a34a' : card.risk === 'medium' ? '#d97706' : '#dc2626';
    var riskBg = card.risk === 'low' ? 'rgba(22,163,74,0.15)' : card.risk === 'medium' ? 'rgba(217,119,6,0.15)' : 'rgba(220,38,38,0.15)';

    var div = document.createElement('div');
    div.style.cssText = 'background:#1c2128;border:1px solid #30363d;border-radius:12px;padding:20px;display:flex;flex-direction:column;gap:12px;';

    var savingsHtml = card.monthlySavings != null
        ? '<div style="text-align:right;"><div style="color:#10b981;font-size:1.2em;font-weight:700;">$' + card.monthlySavings.toFixed(2) + '</div><div style="color:#6b7280;font-size:0.72em;">/month savings</div></div>'
        : '<div style="color:#6b7280;font-size:0.82em;">Savings vary</div>';

    // Header
    var headerHtml =
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;">' +
            '<div style="display:flex;gap:10px;align-items:center;">' +
                '<span style="font-size:1.8em;">' + (card.icon || '🔧') + '</span>' +
                '<div>' +
                    '<div style="font-weight:700;color:#e6edf3;font-size:0.95em;">' + esc(card.title) + '</div>' +
                    '<div style="color:#6b7280;font-size:0.78em;">' + esc(card.accountLabel || '') + '</div>' +
                '</div>' +
            '</div>' +
            savingsHtml +
        '</div>' +
        '<div style="color:#8b949e;font-size:0.85em;">' + esc(card.description) + '</div>';

    // S3 card gets special per-bucket rows with Browse button
    var resourcesHtml;
    if (card.type === 's3-lifecycle') {
        resourcesHtml = '<div style="display:flex;flex-direction:column;gap:4px;">';
        (card.resources || []).slice(0, 10).forEach(function(r) {
            var sizeLabel = r.sizeGb > 0 ? (r.sizeGb >= 1 ? r.sizeGb.toFixed(2) + ' GB' : (r.sizeGb * 1024).toFixed(1) + ' MB') : '—';
            var costLabel = r.estimatedMonthlyCost > 0 ? '$' + r.estimatedMonthlyCost.toFixed(3) + '/mo' : '';
            var activityLabel = r.lastModifiedDays != null
                ? (r.lastModifiedDays >= 90 ? '<span style="color:#ef4444;">⚠ ' + r.lastModifiedDays + 'd ago</span>' : '<span style="color:#6b7280;">' + r.lastModifiedDays + 'd ago</span>')
                : '<span style="color:#6b7280;">empty</span>';
            var reasonBadges = (r.reasons || []).map(function(reason) {
                if (reason === 'no_lifecycle') return '<span style="background:#1e3a5f;color:#60a5fa;font-size:0.7em;padding:1px 5px;border-radius:3px;margin-right:3px;">No lifecycle</span>';
                if (reason === 'empty') return '<span style="background:#1f2937;color:#9ca3af;font-size:0.7em;padding:1px 5px;border-radius:3px;margin-right:3px;">Empty</span>';
                if (reason.startsWith('inactive_')) return '<span style="background:#3b1f1f;color:#f87171;font-size:0.7em;padding:1px 5px;border-radius:3px;margin-right:3px;">Inactive ' + reason.split('_')[1] + '</span>';
                return '';
            }).join('');

            resourcesHtml +=
                '<div style="background:#161b22;border-radius:6px;padding:8px 10px;">' +
                    '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">' +
                        '<div style="flex:1;min-width:0;">' +
                            '<div style="font-size:0.82em;color:#c9d1d9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + ea(r.name) + '">' + esc(r.name) + (r._accountLabel ? ' <span style="color:#6b7280;font-size:0.85em;">(' + esc(r._accountLabel) + ')</span>' : '') + '</div>' +
                            '<div style="font-size:0.75em;margin-top:2px;">' + reasonBadges + '</div>' +
                        '</div>' +
                        '<div style="text-align:right;white-space:nowrap;flex-shrink:0;">' +
                            '<div style="font-size:0.78em;color:#e6edf3;">' + sizeLabel + (costLabel ? ' · <span style="color:#10b981;">' + costLabel + '</span>' : '') + '</div>' +
                            '<div style="font-size:0.75em;margin-top:1px;">' + activityLabel + '</div>' +
                        '</div>' +
                        '<button class="btn btn-outline btn-sm act-browse-btn" data-bucket="' + ea(r.name) + '" data-account="' + ea(r._accountId || card.accountId) + '" style="font-size:0.75em;padding:2px 8px;flex-shrink:0;">Browse</button>' +
                    '</div>' +
                '</div>';
        });
        if (card.resources && card.resources.length > 10) {
            resourcesHtml += '<div style="color:#6b7280;font-size:0.75em;padding:4px 0;">+' + (card.resources.length - 10) + ' more buckets</div>';
        }
        resourcesHtml += '</div>';
    } else {
        // Default resource list for EIP, EBS, LB, EC2, RDS, Snapshots
        resourcesHtml =
            '<div style="background:#161b22;border-radius:6px;padding:8px 10px;max-height:130px;overflow-y:auto;">' +
            (card.resources || []).slice(0, 8).map(function(r) {
                var label = r.id || r.name || r.arn || '';
                var sub = '';
                if (card.type === 'ec2-idle') {
                    sub = ' · ' + (r.type || '') + ' · CPU ' + (r.avgCpu != null ? r.avgCpu + '%' : '?');
                    if (r.inAsg) sub += ' · ⚠ In ASG';
                } else if (card.type === 'rds-idle') {
                    sub = ' · ' + (r.class || '') + ' · ' + (r.engine || '') + ' · CPU ' + (r.avgCpu != null ? r.avgCpu + '%' : '?');
                } else if (card.type === 'ebs-snapshot') {
                    sub = ' · ' + (r.size || 0) + ' GB · ' + (r.ageDays || 0) + 'd old';
                } else {
                    sub = r.ip ? ' · ' + r.ip : r.size ? ' · ' + r.size + ' GB ' + (r.type || '') : r.dns ? ' · ' + r.dns.substring(0, 28) : '';
                }
                return '<div style="font-size:0.78em;color:#c9d1d9;padding:2px 0;border-bottom:1px solid #21262d;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="' + ea(label) + '">' +
                    '<span style="color:#6366f1;">▸</span> ' + esc(label.length > 42 ? label.substring(0, 42) + '…' : label) + '<span style="color:#6b7280;">' + esc(sub) + '</span></div>';
            }).join('') +
            (card.resources && card.resources.length > 8 ? '<div style="color:#6b7280;font-size:0.75em;padding-top:4px;">+' + (card.resources.length - 8) + ' more</div>' : '') +
            '</div>';
    }

    var cleanupLabel = card.type === 's3-lifecycle' ? '🧹 Apply Lifecycle Rules'
        : card.type === 'ec2-idle' ? '⏹ Stop Instances'
        : card.type === 'rds-idle' ? '🗑 Delete (with snapshot)'
        : card.type === 'ebs-snapshot' ? '🗑 Delete Snapshots'
        : '🧹 Clean Up Now';

    // Write-action types need the updated CF template
    var needsWritePerms = ['s3-lifecycle', 'ec2-idle', 'rds-idle', 'ebs-snapshot', 'ebs-volume', 'elastic-ip', 'load-balancer'].indexOf(card.type) !== -1;
    var permWarningHtml = needsWritePerms
        ? '<div style="background:#1e3a5f;border:1px solid #2563eb;border-radius:6px;padding:8px 10px;font-size:0.78em;color:#93c5fd;">' +
            '⚠ <strong>Requires updated IAM role.</strong> Write actions (delete/lifecycle) need the latest CloudFormation template deployed in your AWS account. ' +
            '<button onclick="_actShowRedeployGuide(\'' + ea(card.accountId) + '\')" style="background:none;border:none;color:#60a5fa;cursor:pointer;text-decoration:underline;font-size:1em;padding:0;">How to update →</button>' +
          '</div>'
        : '';

    var footerHtml =
        permWarningHtml +
        '<div style="display:flex;justify-content:space-between;align-items:center;">' +
            '<span style="background:' + riskBg + ';color:' + riskColor + ';font-size:0.75em;padding:2px 8px;border-radius:10px;font-weight:600;">' + (card.risk || 'low').toUpperCase() + ' RISK</span>' +
            (card.note ? '<span style="font-size:0.72em;color:#f59e0b;max-width:180px;text-align:right;">' + esc(card.note) + '</span>' : '') +
            '<button class="btn btn-primary btn-sm act-cleanup-btn" data-card-id="' + ea(card.cardId) + '" style="font-size:0.82em;' + (card.risk === 'high' ? 'background:#dc2626;border-color:#dc2626;' : '') + '">' + cleanupLabel + '</button>' +
        '</div>';

    div.innerHTML = headerHtml + resourcesHtml + footerHtml;

    // Wire cleanup button
    div.querySelector('.act-cleanup-btn').onclick = function() { _actShowConfirm(card); };

    // Wire Browse buttons (S3 only)
    div.querySelectorAll('.act-browse-btn').forEach(function(btn) {
        btn.onclick = function(e) {
            e.stopPropagation();
            var accountId = btn.dataset.account || card.accountId;
            _actBrowseBucket(accountId, btn.dataset.bucket);
        };
    });

    return div;
}

async function _actBrowseBucket(accountId, bucketName) {
    // Build and show the browse modal
    var existing = document.getElementById('act-browse-modal');
    if (existing) existing.remove();

    var modal = document.createElement('div');
    modal.id = 'act-browse-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:600;display:flex;align-items:center;justify-content:center;';

    var card = document.createElement('div');
    card.style.cssText = 'background:#1c2128;border:1px solid #30363d;border-radius:12px;width:700px;max-width:95vw;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,0.5);';

    card.innerHTML =
        // ── Header ──────────────────────────────────────────────────
        '<div style="padding:16px 20px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;">' +
            '<div>' +
                '<div style="font-weight:700;color:#e6edf3;font-size:1em;">🪣 ' + esc(bucketName) + '</div>' +
                '<div id="browse-summary" style="color:#6b7280;font-size:0.8em;margin-top:2px;">Loading…</div>' +
            '</div>' +
            '<div style="display:flex;gap:8px;align-items:center;">' +
                '<select id="browse-sort" style="background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:4px 8px;font-size:0.82em;">' +
                    '<option value="oldest">Oldest first</option>' +
                    '<option value="largest">Largest first</option>' +
                    '<option value="newest">Newest first</option>' +
                '</select>' +
                '<button onclick="document.getElementById(\'act-browse-modal\').remove();" style="background:none;border:none;color:#8b949e;font-size:1.3em;cursor:pointer;padding:4px;">✕</button>' +
            '</div>' +
        '</div>' +
        // ── Aged banner ──────────────────────────────────────────────
        '<div id="browse-aged-banner" style="display:none;background:#3b1f1f;border-bottom:1px solid #7f1d1d;padding:8px 20px;font-size:0.82em;color:#fca5a5;flex-shrink:0;"></div>' +
        // ── Object list ──────────────────────────────────────────────
        '<div id="browse-body" style="flex:1;overflow-y:auto;padding:0;min-height:0;">' +
            '<div style="padding:40px;text-align:center;color:#6b7280;">Loading bucket contents…</div>' +
        '</div>' +
        // ── Action footer ────────────────────────────────────────────
        '<div style="padding:14px 20px;border-top:1px solid #30363d;display:flex;flex-direction:column;gap:8px;flex-shrink:0;background:#161b22;border-radius:0 0 12px 12px;">' +
            '<div style="background:#1e3a5f;border:1px solid #2563eb;border-radius:6px;padding:8px 10px;font-size:0.78em;color:#93c5fd;">' +
                '⚠ <strong>Write actions require the updated IAM role.</strong> If you get an "Access Denied" error, redeploy the CloudFormation template from the Configure tab. ' +
                '<button onclick="_actShowRedeployGuide(\'' + ea(accountId) + '\')" style="background:none;border:none;color:#60a5fa;cursor:pointer;text-decoration:underline;font-size:1em;padding:0;">How to update →</button>' +
            '</div>' +
            '<div style="display:flex;gap:10px;align-items:center;">' +
                '<div style="flex:1;font-size:0.8em;color:#6b7280;">Actions apply to the entire bucket</div>' +
                '<button id="browse-lifecycle-btn" class="btn btn-outline btn-sm" style="font-size:0.82em;border-color:#6366f1;color:#6366f1;">📋 Apply Lifecycle Policy</button>' +
                '<button id="browse-delete-btn" class="btn btn-sm" style="font-size:0.82em;background:#7f1d1d;color:#fca5a5;border:1px solid #ef4444;">🗑 Delete All Objects</button>' +
            '</div>' +
        '</div>';

    modal.appendChild(card);
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);

    // Track browse data for action buttons
    var _browseData = null;

    async function loadBrowse(sortBy) {
        var bodyEl = document.getElementById('browse-body');
        var summaryEl = document.getElementById('browse-summary');
        var agedBanner = document.getElementById('browse-aged-banner');
        if (bodyEl) bodyEl.innerHTML = '<div style="padding:40px;text-align:center;color:#6b7280;">Loading…</div>';

        try {
            var data = await api('POST', '/members/actions/browse-bucket', {
                accountId: accountId,
                bucketName: bucketName,
                sortBy: sortBy || 'oldest',
            });
            _browseData = data;

            if (summaryEl) {
                summaryEl.innerHTML =
                    '<span style="color:#e6edf3;">' + (data.totalObjects || 0).toLocaleString() + ' objects</span>' +
                    ' · <span style="color:#e6edf3;">' + (data.totalSizeGb || 0).toFixed(3) + ' GB</span>' +
                    ' · <span style="color:#10b981;">$' + (data.estimatedMonthlyCost || 0).toFixed(3) + '/mo</span>' +
                    (data.truncated ? ' <span style="color:#f59e0b;">(showing first 500)</span>' : '');
            }

            if (agedBanner) {
                if (data.agedObjects > 0) {
                    agedBanner.style.display = 'block';
                    agedBanner.innerHTML = '⚠ <strong>' + data.agedObjects + ' objects</strong> are 90+ days old (' +
                        data.agedSizeGb.toFixed(3) + ' GB · $' + data.agedMonthlyCost.toFixed(3) + '/mo) — candidates for Glacier Instant Retrieval';
                } else {
                    agedBanner.style.display = 'none';
                }
            }

            if (!bodyEl) return;
            if (!data.objects || data.objects.length === 0) {
                bodyEl.innerHTML = '<div style="padding:40px;text-align:center;color:#6b7280;">Bucket is empty</div>';
                return;
            }

            var rows = '<table style="width:100%;border-collapse:collapse;font-size:0.82em;">' +
                '<thead><tr style="background:#161b22;position:sticky;top:0;z-index:1;">' +
                    '<th style="padding:8px 12px;text-align:left;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;">Object Key</th>' +
                    '<th style="padding:8px 12px;text-align:right;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;">Size</th>' +
                    '<th style="padding:8px 12px;text-align:right;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;">Last Modified</th>' +
                    '<th style="padding:8px 12px;text-align:right;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;">Age</th>' +
                    '<th style="padding:8px 12px;text-align:left;color:#8b949e;font-weight:600;border-bottom:1px solid #30363d;">Class</th>' +
                '</tr></thead><tbody>';

            data.objects.forEach(function(obj) {
                var sizeStr = obj.sizeBytes >= 1073741824
                    ? (obj.sizeBytes / 1073741824).toFixed(2) + ' GB'
                    : obj.sizeBytes >= 1048576
                        ? (obj.sizeBytes / 1048576).toFixed(1) + ' MB'
                        : (obj.sizeBytes / 1024).toFixed(0) + ' KB';
                var ageColor = obj.aged ? '#ef4444' : obj.ageDays > 30 ? '#f59e0b' : '#6b7280';
                var keyShort = obj.key.length > 55 ? '…' + obj.key.slice(-52) : obj.key;
                rows +=
                    '<tr style="border-bottom:1px solid #21262d;" onmouseenter="this.style.background=\'#21262d\'" onmouseleave="this.style.background=\'\'">' +
                        '<td style="padding:6px 12px;color:#c9d1d9;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' + ea(obj.key) + '">' + esc(keyShort) + '</td>' +
                        '<td style="padding:6px 12px;text-align:right;color:#e6edf3;white-space:nowrap;">' + sizeStr + '</td>' +
                        '<td style="padding:6px 12px;text-align:right;color:#6b7280;white-space:nowrap;">' + esc(obj.lastModified) + '</td>' +
                        '<td style="padding:6px 12px;text-align:right;white-space:nowrap;color:' + ageColor + ';font-weight:' + (obj.aged ? '600' : '400') + ';">' + obj.ageDays + 'd' + (obj.aged ? ' ⚠' : '') + '</td>' +
                        '<td style="padding:6px 12px;color:#6b7280;font-size:0.9em;">' + esc(obj.storageClass || 'STANDARD') + '</td>' +
                    '</tr>';
            });
            rows += '</tbody></table>';
            bodyEl.innerHTML = rows;
        } catch (err) {
            if (bodyEl) bodyEl.innerHTML = '<div style="padding:40px;text-align:center;color:#ef4444;">Error: ' + esc(err.message || 'Failed to load') + '</div>';
        }
    }

    // ── Apply Lifecycle Policy button ────────────────────────────────
    var lifecycleBtn = document.getElementById('browse-lifecycle-btn');
    if (lifecycleBtn) {
        lifecycleBtn.onclick = async function() {
            if (!confirm('Apply S3 Intelligent-Tiering lifecycle policy to "' + bucketName + '"?\n\nThis will transition objects older than 90 days to Intelligent-Tiering automatically. This is safe and reversible.')) return;
            lifecycleBtn.disabled = true; lifecycleBtn.textContent = '⏳ Applying…';
            try {
                var result = await api('POST', '/members/actions/execute', {
                    accountId: accountId,
                    actionType: 's3-lifecycle',
                    resourceIds: [bucketName],
                });
                var ok = (result.succeeded || []).length > 0;
                lifecycleBtn.textContent = ok ? '✓ Policy Applied' : '⚠ Failed';
                lifecycleBtn.style.color = ok ? '#10b981' : '#ef4444';
                lifecycleBtn.style.borderColor = ok ? '#10b981' : '#ef4444';
                if (!ok && result.failed && result.failed[0]) notify('Lifecycle error: ' + result.failed[0].error, 'error');
            } catch (err) {
                lifecycleBtn.disabled = false; lifecycleBtn.textContent = '📋 Apply Lifecycle Policy';
                notify('Failed: ' + (err.message || 'Unknown error'), 'error');
            }
        };
    }

    // ── Delete All Objects button ────────────────────────────────────
    var deleteBtn = document.getElementById('browse-delete-btn');
    if (deleteBtn) {
        deleteBtn.onclick = async function() {
            var objCount = _browseData ? _browseData.totalObjects : '?';
            var sizeGb = _browseData ? _browseData.totalSizeGb.toFixed(3) : '?';
            if (!confirm('⚠ DELETE ALL OBJECTS in "' + bucketName + '"?\n\n' + objCount + ' objects · ' + sizeGb + ' GB\n\nThis is IRREVERSIBLE. The bucket itself will remain but all contents will be permanently deleted.\n\nType OK to confirm.')) return;
            deleteBtn.disabled = true; deleteBtn.textContent = '⏳ Deleting…';
            try {
                var result = await api('POST', '/members/actions/execute', {
                    accountId: accountId,
                    actionType: 's3-delete-objects',
                    resourceIds: [bucketName],
                });
                var deleted = (result.succeeded || []).length > 0 ? result.succeeded[0].deleted || 0 : 0;
                deleteBtn.textContent = '✓ ' + deleted + ' objects deleted';
                deleteBtn.style.background = '#14532d';
                deleteBtn.style.color = '#6ee7b7';
                deleteBtn.style.borderColor = '#16a34a';
                // Reload the browse view
                setTimeout(function() { loadBrowse(document.getElementById('browse-sort') ? document.getElementById('browse-sort').value : 'oldest'); }, 1000);
            } catch (err) {
                deleteBtn.disabled = false; deleteBtn.textContent = '🗑 Delete All Objects';
                notify('Delete failed: ' + (err.message || 'Unknown error'), 'error');
            }
        };
    }

    // Initial load
    loadBrowse('oldest');

    // Sort change
    var sortSel = document.getElementById('browse-sort');
    if (sortSel) sortSel.onchange = function() { loadBrowse(this.value); };
}

function _actShowConfirm(card) {
    _actPendingCard = card;
    var dialog = $('act-confirm-dialog');
    var title = $('act-confirm-title');
    var body = $('act-confirm-body');
    var resDiv = $('act-confirm-resources');
    var execBtn = $('act-confirm-execute-btn');
    if (!dialog) return;

    if (title) title.textContent = 'Confirm: ' + card.title;
    if (body) body.textContent = card.description + ' — ' + (card.resources || []).length + ' resource(s) will be affected in ' + (card.accountLabel || card.accountId) + '.';
    if (resDiv) resDiv.innerHTML = (card.resources || []).map(function(r) {
        return '<div style="padding:2px 0;">▸ ' + esc(r.id || r.name || r.arn || '') + (r.ip ? ' (' + r.ip + ')' : '') + (r.size ? ' — ' + r.size + ' GB' : '') + '</div>';
    }).join('');

    if (execBtn) {
        execBtn.onclick = function() {
            dialog.hidden = true;
            _actExecute(card);
        };
    }
    dialog.hidden = false;
}

async function _actExecute(card) {
    var status = $('act-scan-status');
    var cleanupBtn = document.querySelector('[data-card-id="' + card.cardId + '"]');

    if (cleanupBtn) { cleanupBtn.disabled = true; cleanupBtn.textContent = '⏳ Executing…'; }
    if (status) status.textContent = '⚡ Executing cleanup for ' + card.title + '…';

    // Build resource IDs list based on type
    var resourceIds = (card.resources || []).map(function(r) {
        if (card.type === 'elastic-ip') return r.id;
        if (card.type === 'ebs-volume') return r.id;
        if (card.type === 'load-balancer') return r.arn;
        if (card.type === 's3-lifecycle') return r.name;
        if (card.type === 'ec2-idle') return r.id;
        if (card.type === 'rds-idle') return r.id;
        if (card.type === 'ebs-snapshot') return r.id;
        return r.id || r.name;
    }).filter(Boolean);

    try {
        var result = await api('POST', '/members/actions/execute', {
            accountId: card.accountId,
            actionType: card.type,
            resourceIds: resourceIds,
        });

        var succeeded = (result.succeeded || []).length;
        var failed = (result.failed || []).length;
        var msg = '✅ ' + succeeded + ' resource(s) cleaned up';
        if (failed > 0) msg += ', ⚠️ ' + failed + ' skipped (safety check or error)';
        if (status) status.textContent = msg;
        notify(msg, succeeded > 0 ? 'success' : 'error');

        // Show per-resource results inline
        if (cleanupBtn) {
            cleanupBtn.textContent = succeeded + ' done' + (failed > 0 ? ', ' + failed + ' skipped' : '');
            cleanupBtn.style.background = succeeded > 0 ? '#16a34a' : '#d97706';
            cleanupBtn.disabled = true;
        }

        // Show failed details if any
        if (failed > 0 && result.failed) {
            result.failed.forEach(function(f) {
                notify('Skipped ' + f.id + ': ' + f.error, 'error', 6000);
            });
        }

    } catch (err) {
        if (status) status.textContent = '❌ Execution failed: ' + (err.message || 'Unknown error');
        notify('Execution failed: ' + (err.message || 'Unknown error'), 'error');
        if (cleanupBtn) { cleanupBtn.disabled = false; cleanupBtn.textContent = '🧹 Clean Up Now'; }
    }
}

// Populate account select when Act tab is clicked — handled by activateMemberTab

// ============================================================
// Phase 2 — Chat Tab "Top Findings" Widget
// ============================================================
var _findingsWidgetOpen = true;
var _lastScanData = null;

// Load last scan when Chat tab is activated
var _origActivateMemberTab = activateMemberTab;
activateMemberTab = function(tabId) {
    _origActivateMemberTab(tabId);
    if (tabId === 'ai-tab') {
        _loadFindingsWidget();
    }
};

async function _loadFindingsWidget() {
    try {
        var data = await api('GET', '/members/actions/last-scan');
        var scan = data.lastScan;
        if (!scan || !scan.findings || scan.findings.length === 0) {
            _showFindingsEmpty();
            return;
        }
        _lastScanData = scan;
        _renderFindingsWidget(scan);
    } catch (err) {
        _showFindingsEmpty();
    }
}

function _showFindingsEmpty() {
    var widget = $('ai-findings-widget');
    var list = $('ai-findings-list');
    if (!widget) return;
    widget.style.display = 'block';
    if (list) list.innerHTML =
        '<div style="padding:10px 14px;color:#6b7280;font-size:0.82em;">' +
        'No scan results yet. <button onclick="_runScanFromChat();" style="background:none;border:none;color:#6366f1;cursor:pointer;text-decoration:underline;font-size:1em;padding:0;">Run a scan</button> to see top findings here.' +
        '</div>';
    var title = $('ai-findings-title');
    if (title) title.textContent = 'Top Findings';
}

function _renderFindingsWidget(scan) {
    var widget = $('ai-findings-widget');
    var list = $('ai-findings-list');
    var title = $('ai-findings-title');
    var badge = $('ai-findings-badge');
    var ts = $('ai-findings-ts');
    if (!widget || !list) return;

    widget.style.display = 'block';

    var findings = (scan.findings || []).filter(function(f) { return f.status === 'found'; }).slice(0, 5);
    var totalSavings = parseFloat(scan.totalSavings || 0);

    if (title) title.textContent = 'Top Findings  ·  $' + totalSavings.toFixed(2) + '/mo potential savings';
    if (badge && findings.length > 0) { badge.style.display = 'inline'; badge.textContent = findings.length; }
    if (ts && scan.scannedAt) {
        var d = new Date(scan.scannedAt);
        var mins = Math.round((Date.now() - d.getTime()) / 60000);
        ts.textContent = mins < 60 ? mins + 'm ago' : Math.round(mins/60) + 'h ago';
    }

    if (!_findingsWidgetOpen) {
        list.style.display = 'none';
        var chev = $('ai-findings-chevron');
        if (chev) chev.textContent = '▶';
    }

    if (findings.length === 0) {
        list.innerHTML = '<div style="padding:10px 14px;color:#10b981;font-size:0.82em;">✅ No issues found — your accounts look clean!</div>';
        return;
    }

    var severityColor = function(savings) {
        if (savings >= 20) return '#ef4444';
        if (savings >= 5) return '#f59e0b';
        return '#10b981';
    };
    var severityDot = function(savings) {
        if (savings >= 20) return '🔴';
        if (savings >= 5) return '🟡';
        return '🟢';
    };

    var html = '';
    findings.forEach(function(f) {
        var savings = f.savingsUsd || 0;
        var question = _findingToQuestion(f);
        html +=
            '<div class="ai-finding-row" data-question="' + ea(question) + '" ' +
            'style="display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid #21262d;" ' +
            'onmouseenter="this.style.background=\'rgba(99,102,241,0.07)\'" onmouseleave="this.style.background=\'\'">' +
                // Severity dot
                '<span style="font-size:1em;flex-shrink:0;">' + severityDot(savings) + '</span>' +
                // Tip text — clickable, fills input
                '<div class="ai-finding-text" style="flex:1;min-width:0;cursor:pointer;">' +
                    '<div style="color:#c9d1d9;font-size:0.9em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
                        (savings > 0 ? '<span style="color:' + severityColor(savings) + ';font-weight:700;margin-right:6px;">$' + savings.toFixed(2) + '/mo</span>' : '') +
                        esc(f.tipTitle || f.service || '') +
                    '</div>' +
                    '<div style="color:#6b7280;font-size:0.8em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px;">' +
                        esc(question) +
                    '</div>' +
                '</div>' +
                // Ask button — larger, prominent
                '<button class="ai-finding-ask-btn" style="flex-shrink:0;background:#6366f1;color:#fff;border:none;border-radius:6px;' +
                'padding:5px 12px;font-size:0.95em;font-weight:600;cursor:pointer;white-space:nowrap;" ' +
                'onmouseenter="this.style.background=\'#4f46e5\'" onmouseleave="this.style.background=\'#6366f1\'">Ask ▶</button>' +
            '</div>';
    });

    // Footer: total + "See all in Act"
    var moreCount = (scan.findings || []).filter(function(f) { return f.status === 'found'; }).length - findings.length;
    html += '<div style="padding:7px 14px;display:flex;justify-content:space-between;align-items:center;">' +
        '<span style="color:#6b7280;font-size:0.75em;">' +
            (moreCount > 0 ? moreCount + ' more finding(s)' : 'All findings shown') +
        '</span>' +
        '<button onclick="document.querySelector(\'[data-tab=act-tab]\').click();" ' +
        'style="background:none;border:none;color:#6366f1;font-size:0.78em;cursor:pointer;text-decoration:underline;padding:0;">See all in Act ▶</button>' +
    '</div>';

    list.innerHTML = html;

    // Event delegation — both tip text and Ask button fill the input
    list.onclick = function(e) {
        var row = e.target.closest('.ai-finding-row');
        if (!row) return;
        var q = row.dataset.question;
        if (q && aiQuestionInput) {
            aiQuestionInput.value = q;
            aiQuestionInput.focus();
        }
    };
}

function _findingToQuestion(f) {
    var tipId = f.tipId || '';
    var title = f.tipTitle || '';
    var svc = f.service || '';
    // Map tip to a natural language question
    var qmap = {
        'ebs-004': 'How do I safely delete my unattached EBS volumes?',
        'ebs-002': 'Which EBS snapshots are older than 180 days and safe to delete?',
        'vpc-001': 'How do I release my unassociated Elastic IPs?',
        's3-002':  'Which S3 buckets need lifecycle policies and how do I set them up?',
        'elb-001': 'Which load balancers are idle and how do I safely remove them?',
        'ec2-001': 'Which EC2 instances are over-provisioned and what should I resize them to?',
        'ec2-003': 'Which of my EC2 instances are good candidates for Spot pricing?',
        'ec2-006': 'Which EC2 instances can I migrate to Graviton for better price-performance?',
        'rds-001': 'Which RDS instances are idle and what should I do with them?',
        'kms-001': 'Which KMS customer-managed keys might be unused?',
        'general-002': 'How do I set up AWS Budgets with cost alerts?',
        'general-014': 'Do I have underutilized Reserved Instances I should sell on the RI Marketplace?',
    };
    return qmap[tipId] || ('Tell me more about: ' + title + (svc ? ' (' + svc + ')' : ''));
}

function _askFromFinding(question) {
    if (aiQuestionInput) {
        aiQuestionInput.value = question;
        aiQuestionInput.focus();
        // Auto-scroll chat to bottom
        if (aiChat) aiChat.scrollTop = aiChat.scrollHeight;
    }
}

function _toggleFindingsWidget() {
    _findingsWidgetOpen = !_findingsWidgetOpen;
    var list = $('ai-findings-list');
    var chev = $('ai-findings-chevron');
    if (list) list.style.display = _findingsWidgetOpen ? 'block' : 'none';
    if (chev) chev.textContent = _findingsWidgetOpen ? '▼' : '▶';
}

async function _runScanFromChat() {
    var status = $('ai-findings-title');
    if (status) status.textContent = '🔍 Scanning…';
    try {
        var accountIds = getSelectedAccountIds();
        var data = await api('POST', '/members/actions/scan', { accountIds: accountIds });
        _lastScanData = data;
        _renderFindingsWidget(data);
    } catch (err) {
        if (status) status.textContent = 'Scan failed: ' + (err.message || 'error');
    }
}

// ============================================================
// Pipeline Entry — Pre-fill from Bill Check redirect
// ============================================================
(function handlePipelineEntry() {
    var params = new URLSearchParams(window.location.search);
    var email = params.get('email');
    var source = params.get('source');
    var savings = params.get('savings');

    if (!email || source !== 'bill-check') return;

    // If already logged in, skip to dashboard
    if (getToken()) return;

    // Show register view with email pre-filled and a welcome message
    showView('register');

    // Pre-fill email
    if (regEmail) regEmail.value = email;

    // Show a welcome banner above the form
    var loginCard = document.querySelector('#register-view .login-card');
    if (loginCard) {
        var banner = document.createElement('div');
        banner.style.cssText = 'background:linear-gradient(135deg,#064e3b,#065f46);border-radius:10px;padding:14px 18px;margin-bottom:16px;color:#fff;font-size:0.9em;';
        var savingsText = savings ? ' We found <strong>$' + parseInt(savings).toLocaleString() + '/month</strong> in potential savings.' : '';
        banner.innerHTML = '🎉 <strong>Your bill analysis is complete!</strong>' + savingsText +
            '<br>Create a free account to connect your AWS account and start saving.';
        loginCard.insertBefore(banner, loginCard.firstChild);
    }
})();


// ============================================================
// Tag Manager (Act Tab)
// ============================================================
var _tagScanResults = [];
var _tagSelectedArns = new Set();

(function initTagManager() {
    var tagBtn = document.getElementById('act-tag-btn');
    if (!tagBtn) return;

    tagBtn.onclick = async function() {
        _switchActSection('tagging');
        _syncActSelection();
        var accountIds = getActSelectedAccountIds();
        await _runTagScan(accountIds);
    };

    var searchInput = document.getElementById('act-tag-search');
    if (searchInput) searchInput.oninput = function() { _renderTagList(); };

    var selectAllBtn = document.getElementById('act-tag-select-all');
    if (selectAllBtn) selectAllBtn.onclick = function() {
        var visible = _getVisibleTagResources();
        var allSelected = visible.every(function(r) { return _tagSelectedArns.has(r.arn); });
        visible.forEach(function(r) {
            if (allSelected) _tagSelectedArns.delete(r.arn);
            else _tagSelectedArns.add(r.arn);
        });
        _renderTagList();
        _updateTagApplyBtn();
    };

    var applyBtn = document.getElementById('act-tag-apply-btn');
    if (applyBtn) applyBtn.onclick = function() { _showTagApplyModal(); };

    var addRowBtn = document.getElementById('act-tag-add-row');
    if (addRowBtn) addRowBtn.onclick = function() { _addTagInputRow(); };

    var confirmBtn = document.getElementById('act-tag-confirm-btn');
    if (confirmBtn) confirmBtn.onclick = async function() { await _applyTags(); };
})();

async function _runTagScan(accountIds) {
    var panel = document.getElementById('act-tag-panel');
    var cardsGrid = document.getElementById('act-cards-grid');
    var empty = document.getElementById('act-empty');
    var status = document.getElementById('act-scan-status');
    var totalSavings = document.getElementById('act-total-savings');

    if (panel) panel.style.display = 'block';
    var tagEmpty = document.getElementById('act-tag-empty');
    if (tagEmpty) tagEmpty.style.display = 'none';
    var tagStatus = document.getElementById('act-tag-scan-status');
    if (tagStatus) tagStatus.textContent = 'Scanning for untagged resources...';

    try {
        var data = await api('POST', '/members/tags/scan', {
            accountIds: accountIds,
            requiredTags: ['Environment', 'Owner', 'CostCenter', 'Application']
        });
        _tagScanResults = data.resources || [];
        _tagSelectedArns = new Set();
        if (tagStatus) tagStatus.textContent = 'Tag scan complete — ' + _tagScanResults.length + ' resources need tagging';
        _renderTagStats(data);
        _renderTagList();
    } catch (e) {
        if (tagStatus) tagStatus.textContent = 'Tag scan failed: ' + (e.message || 'Unknown error');
        notify('Tag scan failed: ' + (e.message || ''), 'error');
    }
}

function _renderTagStats(data) {
    var el = document.getElementById('act-tag-stats');
    if (!el) return;
    var s = data.summary || {};
    var cov = data.coverage || 0;
    var covColor = cov >= 80 ? '#10b981' : cov >= 50 ? '#f59e0b' : '#ef4444';
    el.innerHTML = '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Tag Coverage</div>'
        + '<div style="color:' + covColor + ';font-size:1.4em;font-weight:700;">' + cov + '%</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Total Resources</div>'
        + '<div style="color:#1f2937;font-size:1.4em;font-weight:700;">' + (s.total || 0) + '</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Fully Tagged</div>'
        + '<div style="color:#10b981;font-size:1.4em;font-weight:700;">' + (s.fullyTagged || 0) + '</div></div>'
        + '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;">'
        + '<div style="color:#6b7280;font-size:0.8em;">Need Tagging</div>'
        + '<div style="color:#ef4444;font-size:1.4em;font-weight:700;">' + ((s.partiallyTagged || 0) + (s.untagged || 0)) + '</div></div>';
}

function _getVisibleTagResources() {
    var q = (document.getElementById('act-tag-search') || {}).value || '';
    q = q.toLowerCase().trim();
    if (!q) return _tagScanResults;
    return _tagScanResults.filter(function(r) {
        return (r.name || '').toLowerCase().indexOf(q) !== -1
            || (r.resourceType || '').toLowerCase().indexOf(q) !== -1
            || (r.arn || '').toLowerCase().indexOf(q) !== -1;
    });
}

function _renderTagList() {
    var list = document.getElementById('act-tag-list');
    if (!list) return;
    var visible = _getVisibleTagResources();
    if (visible.length === 0) {
        list.innerHTML = '<div style="text-align:center;padding:40px;color:#6b7280;">No untagged resources found</div>';
        return;
    }
    var html = '<table style="width:100%;border-collapse:collapse;font-size:0.9em;">';
    html += '<tr style="border-bottom:2px solid #e5e7eb;"><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;width:30px;"></th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Resource</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Type</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Account</th><th style="padding:8px 10px;text-align:left;color:#374151;font-weight:600;">Missing Tags</th></tr>';
    visible.forEach(function(r) {
        var checked = _tagSelectedArns.has(r.arn) ? ' checked' : '';
        var missingHtml = (r.missingTags || []).map(function(t) {
            return '<span style="background:#7f1d1d;color:#fca5a5;padding:1px 6px;border-radius:3px;font-size:0.85em;margin-right:3px;">' + t + '</span>';
        }).join('');
        html += '<tr style="border-bottom:1px solid #e5e7eb;">'
            + '<td style="padding:8px 10px;"><input type="checkbox" class="tag-chk" data-arn="' + r.arn + '"' + checked + '></td>'
            + '<td style="padding:8px 10px;color:#1f2937;font-weight:500;" title="' + r.arn + '">' + (r.name || r.resourceId) + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.resourceType || '') + '</td>'
            + '<td style="padding:8px 10px;color:#6b7280;">' + (r.account || '').slice(-4) + '</td>'
            + '<td style="padding:8px 10px;">' + missingHtml + '</td></tr>';
    });
    html += '</table>';
    list.innerHTML = html;

    // Wire checkboxes
    list.querySelectorAll('.tag-chk').forEach(function(chk) {
        chk.onchange = function() {
            if (chk.checked) _tagSelectedArns.add(chk.dataset.arn);
            else _tagSelectedArns.delete(chk.dataset.arn);
            _updateTagApplyBtn();
        };
    });
    _updateTagApplyBtn();
}

function _updateTagApplyBtn() {
    var btn = document.getElementById('act-tag-apply-btn');
    if (!btn) return;
    var count = _tagSelectedArns.size;
    btn.textContent = 'Apply Tags (' + count + ')';
    btn.disabled = count === 0;
}

function _showTagApplyModal() {
    var modal = document.getElementById('act-tag-modal');
    var countEl = document.getElementById('act-tag-count');
    var inputs = document.getElementById('act-tag-inputs');
    var statusEl = document.getElementById('act-tag-apply-status');
    if (!modal) return;
    if (countEl) countEl.textContent = _tagSelectedArns.size;
    if (statusEl) statusEl.textContent = '';
    if (inputs) inputs.innerHTML = '';
    _addTagInputRow();
    modal.hidden = false;
}

function _addTagInputRow() {
    var inputs = document.getElementById('act-tag-inputs');
    if (!inputs) return;
    var row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;margin-bottom:8px;';
    row.innerHTML = '<input type="text" placeholder="Tag Key (e.g. Environment)" style="flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#1f2937;font-size:0.9em;" class="tag-key-input">'
        + '<input type="text" placeholder="Tag Value (e.g. production)" style="flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;background:#fff;color:#1f2937;font-size:0.9em;" class="tag-val-input">'
        + '<button onclick="this.parentElement.remove();" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:1.2em;">✕</button>';
    inputs.appendChild(row);
}

async function _applyTags() {
    var inputs = document.getElementById('act-tag-inputs');
    var statusEl = document.getElementById('act-tag-apply-status');
    var confirmBtn = document.getElementById('act-tag-confirm-btn');
    if (!inputs) return;

    // Collect tags
    var tags = {};
    var keys = inputs.querySelectorAll('.tag-key-input');
    var vals = inputs.querySelectorAll('.tag-val-input');
    for (var i = 0; i < keys.length; i++) {
        var k = (keys[i].value || '').trim();
        var v = (vals[i].value || '').trim();
        if (k && v) tags[k] = v;
    }
    if (Object.keys(tags).length === 0) {
        if (statusEl) { statusEl.style.color = '#ef4444'; statusEl.textContent = 'Enter at least one tag key and value'; }
        return;
    }

    var arns = Array.from(_tagSelectedArns);
    if (confirmBtn) { confirmBtn.disabled = true; confirmBtn.textContent = 'Applying...'; }
    if (statusEl) { statusEl.style.color = '#8b949e'; statusEl.textContent = 'Applying tags to ' + arns.length + ' resources...'; }

    try {
        var data = await api('POST', '/members/tags/apply', { arns: arns, tags: tags });
        if (statusEl) { statusEl.style.color = '#10b981'; statusEl.textContent = data.message || 'Tags applied!'; }
        notify(data.message || 'Tags applied!', 'success');
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = '✓ Done — Close'; confirmBtn.style.background = '#10b981'; confirmBtn.style.borderColor = '#10b981'; confirmBtn.style.opacity = '1';
            confirmBtn.onclick = function() {
                document.getElementById('act-tag-modal').hidden = true;
                confirmBtn.style.background = '#6366f1'; confirmBtn.style.borderColor = '#6366f1';
                confirmBtn.textContent = '🏷️ Apply Tags';
                confirmBtn.onclick = async function() { await _applyTags(); };
                _syncActSelection();
                _runTagScan(getActSelectedAccountIds());
            };
        }
    } catch (e) {
        var errMsg = e.message || 'Unknown error';
        if (errMsg.indexOf('AccessDenied') !== -1 || errMsg.indexOf('not authorized') !== -1) {
            errMsg = 'Permission denied. Please update the CloudFormation template in your AWS account (Configure tab → Download Template → Update Stack).';
        }
        if (statusEl) { statusEl.style.color = '#ef4444'; statusEl.textContent = errMsg; }
        if (confirmBtn) { confirmBtn.disabled = false; confirmBtn.textContent = '🏷️ Apply Tags'; }
    }
}
