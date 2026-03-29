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

// Account modal
var accountModal = $('account-modal');
var accountModalTitle = $('account-modal-title');
var accountForm = $('account-form');
var accountIdInput = $('account-id-input');
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

// ============================================================
// Helpers
// ============================================================

function notify(msg, type) {
    notifMsg.textContent = msg;
    notif.className = 'notification notification-' + type;
    notif.hidden = false;
    setTimeout(function() { notif.hidden = true; }, 4000);
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
    resetView.hidden = name !== 'reset';
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
    if (name === 'reset') {
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
    }
}

// ============================================================
// Navigation
// ============================================================

$('show-register').onclick = function(e) { e.preventDefault(); showView('register'); };
$('show-login').onclick = function(e) { e.preventDefault(); showView('login'); };
$('show-forgot').onclick = function(e) { e.preventDefault(); showView('reset'); };
$('show-login-from-reset').onclick = function(e) { e.preventDefault(); showView('login'); };
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

$('reset-email-form').onsubmit = async function(e) {
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

$('reset-otp-form').onsubmit = async function(e) {
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

$('reset-password-form').onsubmit = async function(e) {
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
            '<td>' + esc(a.roleName || '') + '</td>' +
            '<td><span class="status-badge ' + statusClass + '">' + esc(a.connectionStatus || 'pending') + '</span></td>' +
            '<td>' + fmtDate(a.addedAt) + '</td>' +
            '<td>' + fmtDate(a.lastTestedAt) + '</td>' +
            '<td class="actions-cell">' +
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
};

// ============================================================
// Add / Edit Account Modal
// ============================================================

addAccountBtn.onclick = function() { showAccountModal(null); };

function showAccountModal(existingId) {
    accountFormError.textContent = '';
    editingAccountId = existingId;
    if (existingId) {
        accountModalTitle.textContent = 'Edit Account';
        accountSubmitBtn.textContent = 'Update Account';
        accountIdInput.value = '';
        accountIdInput.placeholder = 'New 12-digit Account ID';
    } else {
        accountModalTitle.textContent = 'Add Account';
        accountSubmitBtn.textContent = 'Add Account';
        accountIdInput.value = '';
        accountIdInput.placeholder = '123456789012';
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
    if (!/^\d{12}$/.test(val)) {
        accountFormError.textContent = 'Account ID must be exactly 12 digits.';
        return;
    }

    try {
        showLoading();
        if (editingAccountId) {
            await api('PUT', '/members/accounts', { oldAccountId: editingAccountId, newAccountId: val });
            notify('Account updated.', 'success');
        } else {
            await api('POST', '/members/accounts', { accountId: val });
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
        await api('DELETE', '/members/accounts', { accountId: deletingAccountId });
        notify('Account deleted.', 'success');
        hideDeleteDialog();
        await loadAccounts();
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
var wizardTemplateYaml = null;
var wizardFilename = null;

function showWizard(accountId) {
    wizardAccountId = accountId;
    wizardStep = 1;
    wizardTemplateDownloaded = false;
    wizardCfConsoleUrl = null;
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
        if (wizardCfConsoleUrl) {
            wizLaunchCfBtn.href = wizardCfConsoleUrl;
            wizLaunchCfBtn.style.opacity = '1';
            wizLaunchCfBtn.style.pointerEvents = 'auto';
            wizardTemplateDownloaded = true;
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
    if (!/^\d{12}$/.test(val)) {
        accountFormError.textContent = 'Account ID must be exactly 12 digits.';
        return;
    }
    try {
        showLoading();
        if (editingAccountId) {
            await api('PUT', '/members/accounts', { oldAccountId: editingAccountId, newAccountId: val });
            notify('Account updated.', 'success');
            hideAccountModal();
            await loadAccounts();
        } else {
            await api('POST', '/members/accounts', { accountId: val });
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
        document.querySelectorAll('.member-tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.member-tab-content').forEach(function(c) { c.hidden = true; });
        tab.classList.add('active');
        var target = $(tab.dataset.tab);
        if (target) target.hidden = false;
        if (tab.dataset.tab === 'lab-tab') populateLabAccounts();
    };
});

// ============================================================
// Lab Area
// ============================================================

var labChat = $('lab-chat');
var labCommandInput = $('lab-command-input');
var labRunBtn = $('lab-run-btn');
var labAccountSelect = $('lab-account-select');

function populateLabAccounts() {
    var current = labAccountSelect.value;
    labAccountSelect.innerHTML = '<option value="">Select an account...</option>';
    allAccounts.forEach(function(a) {
        if (a.connectionStatus === 'connected') {
            var opt = document.createElement('option');
            opt.value = a.accountId;
            opt.textContent = a.accountId + ' (' + a.roleName + ')';
            labAccountSelect.appendChild(opt);
        }
    });
    if (current) labAccountSelect.value = current;
}

function addLabMessage(type, content) {
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

labRunBtn.onclick = runLabCommand;
labCommandInput.onkeydown = function(e) {
    if (e.key === 'Enter') { e.preventDefault(); runLabCommand(); }
};

// Click example commands to populate input
labChat.onclick = function(e) {
    if (e.target.tagName === 'CODE' && e.target.closest('.lab-examples')) {
        labCommandInput.value = e.target.textContent;
        labCommandInput.focus();
    }
};
