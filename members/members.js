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
    dashboardCharts.forEach(function(ch) { try { ch.destroy(); } catch (e) {} });
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
            var canvas = $(chartId);
            if (canvas && cfg && window.Chart) {
                var chart = new Chart(canvas, {
                    type: cfg.type || 'bar',
                    data: {
                        labels: cfg.labels || [],
                        datasets: [{
                            label: cfg.datasetLabel || 'Values',
                            data: cfg.data || [],
                            borderWidth: 2,
                            backgroundColor: ['#3b82f6', '#22c55e', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4'],
                            borderColor: '#1d4ed8'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: true } }
                    }
                });
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
            opt.textContent = a.accountId + ' (' + a.roleName + ')';
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
    var current = aiAccountSelect.value;
    aiAccountSelect.innerHTML = '<option value="">Select an account...</option>';
    allAccounts.forEach(function(a) {
        if (a.connectionStatus === 'connected') {
            var opt = document.createElement('option');
            opt.value = a.accountId;
            opt.textContent = a.accountId + ' (' + a.roleName + ')';
            aiAccountSelect.appendChild(opt);
        }
    });
    if (current) aiAccountSelect.value = current;
}

function addAIMessage(type, content) {
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
        div.innerHTML =
            '<div class="lab-msg-output" style="color:#e2e8f0;border-color:#4c1d95;">' + formatted + '</div>' +
            '<div style="margin-top:10px;text-align:right;">' +
            '<button class="btn btn-outline btn-sm ai-visualize-btn" data-question="' + ea(questionText) + '" data-answer="' + ea(content) + '">Visualize</button>' +
            '</div>';
    } else if (type === 'commands') {
        var cmdsHtml = '<div class="lab-msg-info" style="color:#7ee787;">Commands executed:</div>';
        content.forEach(function(c) {
            cmdsHtml += '<div class="lab-msg-command" style="font-size:11px;color:#58a6ff;">$ ' + esc(c) + '</div>';
        });
        div.innerHTML = cmdsHtml;
    } else if (type === 'thinking') {
        div.innerHTML = '<div class="lab-msg-info" style="color:#a78bfa;">&#129302; ' + esc(content) + '</div>';
        div.id = 'ai-thinking';
    } else if (type === 'error') {
        div.innerHTML = '<div class="lab-msg-output lab-msg-error">' + esc(content) + '</div>';
    }

    aiChat.appendChild(div);
    aiChat.scrollTop = aiChat.scrollHeight;
}

async function askAI() {
    if (!aiAccountSelect || !aiQuestionInput) return;
    var accountId = aiAccountSelect.value;
    var question = aiQuestionInput.value.trim();

    if (!accountId) { notify('Please select an account first.', 'error'); return; }
    if (!question) return;

    addAIMessage('question', question);
    aiQuestionInput.dataset.lastQuestion = question;
    aiQuestionInput.value = '';
    addAIMessage('thinking', 'Analyzing your question...');

    try {
        var data = await api('POST', '/members/accounts/ai-query', {
            accountId: accountId,
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
        addAIMessage('answer', data.answer || 'No answer available.');

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
