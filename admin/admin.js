/* Admin Panel — Client-side logic for Slash My Bill admin dashboard */

const API_BASE_URL = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';

// ============================================================
// State
// ============================================================
let allLeads = [];
let allTips = [];
let editingTip = null; // null = create mode, object = edit mode
let deletingTip = null; // { service, tipId } for pending delete
let debounceTimer = null;

// ============================================================
// DOM References
// ============================================================
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const loginUsername = document.getElementById('login-username');
const loginPassword = document.getElementById('login-password');
const loginError = document.getElementById('login-error');
const loginSubmit = document.getElementById('login-submit');

const headerUsername = document.getElementById('header-username');
const logoutBtn = document.getElementById('logout-btn');

const leadsTab = document.getElementById('leads-tab');
const tipsTab = document.getElementById('tips-tab');
const leadsSearch = document.getElementById('leads-search');
const tipsSearch = document.getElementById('tips-search');
const leadsTbody = document.getElementById('leads-tbody');
const tipsTbody = document.getElementById('tips-tbody');
const leadsEmpty = document.getElementById('leads-empty');
const tipsEmpty = document.getElementById('tips-empty');
const addTipBtn = document.getElementById('add-tip-btn');

const tipModal = document.getElementById('tip-modal');
const tipModalTitle = document.getElementById('tip-modal-title');
const tipForm = document.getElementById('tip-form');
const tipFormError = document.getElementById('tip-form-error');
const tipCancelBtn = document.getElementById('tip-cancel-btn');
const tipModalClose = document.getElementById('tip-modal-close');
const tipSubmitBtn = document.getElementById('tip-submit-btn');

const deleteDialog = document.getElementById('delete-dialog');
const deleteCancelBtn = document.getElementById('delete-cancel-btn');
const deleteConfirmBtn = document.getElementById('delete-confirm-btn');

const loadingOverlay = document.getElementById('loading-overlay');
const notification = document.getElementById('notification');
const notificationMessage = document.getElementById('notification-message');

// Tip form field IDs
const TIP_FIELDS = ['service', 'tipId', 'category', 'title', 'description', 'estimatedSavings', 'difficulty'];

// ============================================================
// Auth
// ============================================================
async function login(username, password) {
    showLoading();
    loginError.textContent = '';
    try {
        const res = await fetch(`${API_BASE_URL}/admin/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) {
            loginError.textContent = data.message || 'Invalid username or password';
            return;
        }
        sessionStorage.setItem('admin_token', data.token);
        sessionStorage.setItem('admin_username', data.username);
        showDashboard();
        loadLeads();
        loadTips();
    } catch (err) {
        loginError.textContent = 'Unable to connect. Please check your connection.';
    } finally {
        hideLoading();
    }
}

function logout() {
    sessionStorage.removeItem('admin_token');
    sessionStorage.removeItem('admin_username');
    allLeads = [];
    allTips = [];
    leadsTbody.innerHTML = '';
    tipsTbody.innerHTML = '';
    leadsSearch.value = '';
    tipsSearch.value = '';
    showLogin();
}

// ============================================================
// API Helper
// ============================================================
async function apiRequest(method, path, body) {
    const token = sessionStorage.getItem('admin_token');
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        }
    };
    if (body) options.body = JSON.stringify(body);

    const res = await fetch(`${API_BASE_URL}${path}`, options);

    if (res.status === 401) {
        showNotification('Session expired. Please log in again.', 'error');
        logout();
        throw new Error('Unauthorized');
    }

    const data = await res.json();
    if (!res.ok) {
        throw { status: res.status, message: data.message || 'Something went wrong' };
    }
    return data;
}

// ============================================================
// Leads
// ============================================================
async function loadLeads() {
    try {
        showLoading();
        const data = await apiRequest('GET', '/admin/leads');
        allLeads = data.leads || [];
        renderLeads(allLeads);
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            showNotification('Failed to load leads.', 'error');
        }
    } finally {
        hideLoading();
    }
}

function renderLeads(leads) {
    leadsTbody.innerHTML = '';
    if (leads.length === 0) {
        leadsEmpty.hidden = false;
        return;
    }
    leadsEmpty.hidden = true;
    leads.forEach(lead => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(lead.email || '')}</td>
            <td>${escapeHtml(lead.name || '')}</td>
            <td>${escapeHtml(lead.company || '')}</td>
            <td>${escapeHtml(lead.phone || '')}</td>
            <td>${escapeHtml(lead.fileName || '')}</td>
            <td>${formatDate(lead.timestamp)}</td>
        `;
        leadsTbody.appendChild(tr);
    });
}

function filterLeads(query) {
    const q = query.toLowerCase().trim();
    if (!q) { renderLeads(allLeads); return; }
    const filtered = allLeads.filter(l =>
        (l.email || '').toLowerCase().includes(q) ||
        (l.name || '').toLowerCase().includes(q) ||
        (l.company || '').toLowerCase().includes(q)
    );
    renderLeads(filtered);
}

// ============================================================
// Tips
// ============================================================
async function loadTips() {
    try {
        showLoading();
        const data = await apiRequest('GET', '/admin/tips');
        allTips = data.tips || [];
        renderTips(allTips);
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            showNotification('Failed to load tips.', 'error');
        }
    } finally {
        hideLoading();
    }
}

function renderTips(tips) {
    tipsTbody.innerHTML = '';
    if (tips.length === 0) {
        tipsEmpty.hidden = false;
        return;
    }
    tipsEmpty.hidden = true;
    tips.forEach(tip => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(tip.service || '')}</td>
            <td>${escapeHtml(tip.tipId || '')}</td>
            <td>${escapeHtml(tip.category || '')}</td>
            <td>${escapeHtml(tip.title || '')}</td>
            <td title="${escapeHtml(tip.description || '')}">${escapeHtml(tip.description || '')}</td>
            <td>${escapeHtml(tip.estimatedSavings || '')}</td>
            <td><span class="badge badge-${(tip.difficulty || '').toLowerCase()}">${escapeHtml(tip.difficulty || '')}</span></td>
            <td class="actions-cell">
                <button class="btn-icon btn-icon-edit" data-action="edit" data-service="${escapeAttr(tip.service)}" data-tipid="${escapeAttr(tip.tipId)}" title="Edit">&#9998;</button>
                <button class="btn-icon btn-icon-delete" data-action="delete" data-service="${escapeAttr(tip.service)}" data-tipid="${escapeAttr(tip.tipId)}" title="Delete">&#128465;</button>
            </td>
        `;
        tipsTbody.appendChild(tr);
    });
}

function filterTips(query) {
    const q = query.toLowerCase().trim();
    if (!q) { renderTips(allTips); return; }
    const filtered = allTips.filter(t =>
        (t.service || '').toLowerCase().includes(q) ||
        (t.title || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
    );
    renderTips(filtered);
}

// ============================================================
// Tip Form (Create / Edit)
// ============================================================
function showTipForm(tip) {
    tipFormError.textContent = '';
    if (tip) {
        // Edit mode
        editingTip = tip;
        tipModalTitle.textContent = 'Edit Tip';
        tipSubmitBtn.textContent = 'Update Tip';
        TIP_FIELDS.forEach(f => {
            const el = document.getElementById('tip-' + f);
            el.value = tip[f] || '';
        });
        document.getElementById('tip-service').disabled = true;
        document.getElementById('tip-tipId').disabled = true;
    } else {
        // Create mode
        editingTip = null;
        tipModalTitle.textContent = 'Add Tip';
        tipSubmitBtn.textContent = 'Save Tip';
        TIP_FIELDS.forEach(f => {
            document.getElementById('tip-' + f).value = '';
        });
        document.getElementById('tip-service').disabled = false;
        document.getElementById('tip-tipId').disabled = false;
    }
    tipModal.hidden = false;
}

function hideTipForm() {
    tipModal.hidden = true;
    editingTip = null;
}

async function saveTip() {
    tipFormError.textContent = '';
    const tipData = {};
    for (const f of TIP_FIELDS) {
        const val = document.getElementById('tip-' + f).value.trim();
        if (!val) {
            tipFormError.textContent = 'All fields are required.';
            return;
        }
        tipData[f] = val;
    }

    try {
        showLoading();
        if (editingTip) {
            await apiRequest('PUT', '/admin/tips', tipData);
            showNotification('Tip updated successfully.', 'success');
        } else {
            await apiRequest('POST', '/admin/tips', tipData);
            showNotification('Tip created successfully.', 'success');
        }
        hideTipForm();
        await loadTips();
    } catch (err) {
        if (err.status === 409) {
            tipFormError.textContent = 'A tip with this service and ID already exists.';
        } else if (err.message !== 'Unauthorized') {
            tipFormError.textContent = err.message || 'Failed to save tip.';
        }
    } finally {
        hideLoading();
    }
}

// ============================================================
// Delete Tip
// ============================================================
function showDeleteDialog(service, tipId) {
    deletingTip = { service, tipId };
    deleteDialog.hidden = false;
}

function hideDeleteDialog() {
    deleteDialog.hidden = true;
    deletingTip = null;
}

async function deleteTip() {
    if (!deletingTip) return;
    const { service, tipId } = deletingTip;
    hideDeleteDialog();
    try {
        showLoading();
        await apiRequest('DELETE', '/admin/tips', { service, tipId });
        showNotification('Tip deleted successfully.', 'success');
        await loadTips();
    } catch (err) {
        if (err.status === 404) {
            showNotification('Tip not found. It may have been already deleted.', 'error');
            await loadTips();
        } else if (err.message !== 'Unauthorized') {
            showNotification(err.message || 'Failed to delete tip.', 'error');
        }
    } finally {
        hideLoading();
    }
}
