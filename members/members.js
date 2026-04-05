/* Member Portal v1 - SlashMyBill */
var API = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';

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
        loadAccounts();
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
    if (!regEmailValue) { regEmailError.textContent = 'Enter your email.'; return; }

    try {
        showLoading();
        await api('POST', '/members/register', { action: 'send-otp', email: regEmailValue });
        regEmailDisplay.textContent = regEmailValue;
        regStep1.hidden = true;
        regStep2.hidden = false;
    } catch (err) {
        regEmailError.textContent = err.message || 'Failed to send OTP.';
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
        var data = await api('POST', '/members/register', {
            action: 'verify-otp', email: regEmailValue, otp: code
        });
        otpToken = data.otpToken;
        regStep2.hidden = true;
        regStep3.hidden = false;
    } catch (err) {
        regOtpError.textContent = err.message || 'Invalid code.';
    } finally {
        hideLoading();
    }
};

regPasswordForm.onsubmit = async function(e) {
    e.preventDefault();
    regPasswordError.textContent = '';
    var pw = regPassword.value;
    var cpw = regConfirm.value;
    if (pw.length < 8) { regPasswordError.textContent = 'Password must be at least 8 characters.'; return; }
    if (pw !== cpw) { regPasswordError.textContent = 'Passwords do not match.'; return; }

    try {
        showLoading();
        await api('POST', '/members/register', {
            action: 'create-account', otpToken: otpToken, password: pw, confirmPassword: cpw
        });
        notify('Registration successful! Please log in.', 'success');
        showView('login');
    } catch (err) {
        regPasswordError.textContent = err.message || 'Registration failed.';
    } finally {
        hideLoading();
    }
};

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
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td style="color:#999;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + esc(a.accountId || '') + '</td>' +
            '<td>' + esc(a.accountName || '-') + '</td>' +
            '<td>' + esc(a.roleName || '') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + esc(a.connectionStatus || 'pending') + '</span></td>' +
            '<td>' + fmtDate(a.addedAt) + '</td>' +
            '<td>' + fmtDate(a.lastTestedAt) + '</td>' +
            '<td class="actions-cell">' +
                (idx > 0 ? '<button class="btn btn-outline btn-sm" data-a="up" data-id="' + ea(a.accountId) + '" title="Move Up" style="padding:2px 6px;font-size:12px;min-width:28px;">▲</button> ' : '<span style="display:inline-block;width:32px;"></span> ') +
                (idx < accounts.length - 1 ? '<button class="btn btn-outline btn-sm" data-a="down" data-id="' + ea(a.accountId) + '" title="Move Down" style="padding:2px 6px;font-size:12px;min-width:28px;">▼</button> ' : '<span style="display:inline-block;width:32px;"></span> ') +
                '<button class="btn-icon btn-icon-download" data-a="dl" data-id="' + ea(a.accountId) + '" title="Download CF Template">&#8681;</button> ' +
                '<button class="btn-icon btn-icon-test" data-a="test" data-id="' + ea(a.accountId) + '" title="Test Connection">&#9889;</button> ' +
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
        notify(data.message || 'Connection test complete.', 'success');
        await loadAccounts();
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
var wizInd1 = $('wiz-ind-1');
var wizInd2 = $('wiz-ind-2');
var wizInd3 = $('wiz-ind-3');
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

    wizInd1.className = 'wizard-step-indicator' + (wizardStep === 1 ? ' active' : wizardStep > 1 ? ' done' : '');
    wizInd2.className = 'wizard-step-indicator' + (wizardStep === 2 ? ' active' : wizardStep > 2 ? ' done' : '');
    wizInd3.className = 'wizard-step-indicator' + (wizardStep === 3 ? ' active' : '');

    wizBackBtn.hidden = wizardStep <= 1;
    wizNextBtn.hidden = wizardStep >= 3;
    wizFinishBtn.hidden = wizardStep < 3;
}

wizNextBtn.onclick = function() {
    if (wizardStep === 1 && !wizardTemplateDownloaded) {
        notify('Please download the template first.', 'error');
        return;
    }
    if (wizardStep < 3) {
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
        wizTestResult.innerHTML = '<strong>&#10003; Connection Successful!</strong><br>' + (data.message || 'Cost data is accessible.');
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
        var tr = document.createElement('tr');
        tr.innerHTML =
            '<td style="color:#999;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + esc(a.accountId || '') + '</td>' +
            '<td>' + esc(a.accountName || '-') + '</td>' +
            '<td>' + esc(a.roleName || '') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + esc(a.connectionStatus || 'pending') + '</span></td>' +
            '<td>' + fmtDate(a.addedAt) + '</td>' +
            '<td>' + fmtDate(a.lastTestedAt) + '</td>' +
            '<td class="actions-cell">' +
                setupBtn +
                '<button class="btn-icon btn-icon-download" data-a="dl" data-id="' + ea(a.accountId) + '" title="Download CF Template">&#8681;</button> ' +
                '<button class="btn-icon btn-icon-test" data-a="test" data-id="' + ea(a.accountId) + '" title="Test Connection">&#9889;</button> ' +
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
    if (tabId === 'ai-tab') populateAIAccounts();
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
        accountId: (aiAccountSelect && aiAccountSelect.value) || '',
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

                    var html = '<div style="color:#8b949e;font-size:0.85em;margin-bottom:6px;margin-top:12px;">Show as table:</div>';
                    sortedCharts.forEach(function(cd, idx) {
                        html += '<button class="btn btn-outline btn-sm ai-table-btn" style="margin:3px 4px 3px 0;font-size:0.85em;" data-chart-idx="' + idx + '">'
                            + '📋 ' + esc(cd.title) + '</button>';
                    });
                    html += '<div class="ai-table-render-area"></div>';
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
                accountId: (aiAccountSelect && aiAccountSelect.value) || ''
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
                accountId: (aiAccountSelect && aiAccountSelect.value) || ''
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
            accountId: (aiAccountSelect && aiAccountSelect.value) || '',
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
