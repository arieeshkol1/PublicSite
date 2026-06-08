/**
 * Dashboard Main Module
 * Orchestrates layout save/load, authentication, and API integration.
 * Includes offline detection with automatic retry and resilient error handling.
 */

const Dashboard = (() => {
    const API_BASE = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';
    const OFFLINE_RETRY_INTERVAL_MS = 15000; // 15 seconds
    const OFFLINE_MAX_RETRIES = 3;

    let authToken = null;
    let memberEmail = null;
    let currentLayoutId = null;
    let isOffline = false;
    let offlineRetryCount = 0;
    let offlineRetryTimer = null;

    function init() {
        // Try to get auth token from multiple sources:
        // 1. URL parameter (passed by parent iframe)
        // 2. sessionStorage (if same browsing context)
        // 3. Listen for postMessage from parent (iframe scenario)
        const urlParams = new URLSearchParams(window.location.search);
        const urlToken = urlParams.get('token');
        const urlEmail = urlParams.get('email');

        if (urlToken) {
            authToken = urlToken;
            memberEmail = urlEmail || 'user';
        } else {
            authToken = sessionStorage.getItem('memberToken') || localStorage.getItem('dashboard_token') || null;
            memberEmail = sessionStorage.getItem('memberEmail') || localStorage.getItem('dashboard_email') || 'user';
        }

        // Listen for token from parent window (iframe embed)
        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'dashboard-auth') {
                authToken = event.data.token;
                memberEmail = event.data.email || 'user';
                if (!document.getElementById('login-view').hidden) {
                    showDashboard();
                }
                // Don't call loadLayouts — backend may not be deployed
            }
        });

        if (authToken) {
            showDashboard();
        } else {
            // Show login view only if not embedded
            if (window === window.parent) {
                document.getElementById('login-view').hidden = false;
                document.getElementById('dashboard-view').hidden = true;
            } else {
                // Embedded — request token from parent
                window.parent.postMessage({ type: 'dashboard-request-token' }, '*');
                // Meanwhile show dashboard in loading state
                showDashboard();
            }
        }

        // Wire up login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', handleLogin);
        }

        // Wire up logout
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', handleLogout);
        }

        // Wire up layout controls
        const saveBtn = document.getElementById('save-layout-btn');
        if (saveBtn) saveBtn.addEventListener('click', saveLayout);

        const newBtn = document.getElementById('new-layout-btn');
        if (newBtn) newBtn.addEventListener('click', newLayout);

        const layoutSelector = document.getElementById('layout-selector');
        if (layoutSelector) layoutSelector.addEventListener('change', onLayoutSelected);

        // Wire up re-auth form
        const reauthForm = document.getElementById('reauth-form');
        if (reauthForm) reauthForm.addEventListener('submit', handleReauth);

        // Wire up offline/online detection
        window.addEventListener('offline', handleOffline);
        window.addEventListener('online', handleOnline);

        // Wire up manual retry button (in offline indicator)
        const manualRetryBtn = document.getElementById('offline-retry-btn');
        if (manualRetryBtn) manualRetryBtn.addEventListener('click', handleManualRetry);
    }

    async function handleLogin(e) {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');

        try {
            // Cognito authentication (placeholder - same flow as members portal)
            errorEl.textContent = '';
            // TODO: Integrate with Cognito auth
            console.log('Login attempt for:', email);
        } catch (err) {
            errorEl.textContent = err.message || 'Login failed';
        }
    }

    function handleLogout() {
        authToken = null;
        memberEmail = null;
        localStorage.removeItem('dashboard_token');
        localStorage.removeItem('dashboard_email');
        document.getElementById('dashboard-view').hidden = true;
        document.getElementById('login-view').hidden = false;
    }

    function showDashboard() {
        document.getElementById('login-view').hidden = true;
        document.getElementById('dashboard-view').hidden = false;
        document.getElementById('header-email').textContent = memberEmail;

        // Initialize grid
        GridManager.init();

        // Skip API calls — backend may not be deployed yet.
        // Layouts will load when backend is available.
    }

    async function loadLayouts() {
        try {
            const resp = await apiRequest('GET', '/dashboard/layouts');
            if (resp && resp.layouts) {
                const selector = document.getElementById('layout-selector');
                selector.innerHTML = '<option value="">-- Select Layout --</option>';
                resp.layouts.forEach(layout => {
                    const opt = document.createElement('option');
                    opt.value = layout.layout_id;
                    opt.textContent = layout.layout_name;
                    selector.appendChild(opt);
                });
            }
        } catch (err) {
            console.error('Failed to load layouts:', err);
        }
    }

    async function saveLayout() {
        const widgets = GridManager.getWidgets();
        const layoutName = prompt('Layout name:', 'My Dashboard');
        if (!layoutName) return;

        try {
            const payload = {
                layout_id: currentLayoutId || undefined,
                layout_name: layoutName,
                widgets: widgets
            };
            const resp = await apiRequest('PUT', '/dashboard/layouts', payload);
            if (resp && resp.layout_id) {
                currentLayoutId = resp.layout_id;
                await loadLayouts();
            }
        } catch (err) {
            console.error('Failed to save layout:', err);
            alert('Failed to save layout: ' + (err.message || 'Unknown error'));
        }
    }

    function newLayout() {
        currentLayoutId = null;
        GridManager.clearGrid();
        document.getElementById('layout-selector').value = '';
    }

    async function onLayoutSelected(e) {
        const layoutId = e.target.value;
        if (!layoutId) return;

        try {
            const resp = await apiRequest('GET', `/dashboard/layouts?layout_id=${layoutId}`);
            if (resp) {
                currentLayoutId = layoutId;
                GridManager.loadLayout(resp);
            }
        } catch (err) {
            console.error('Failed to load layout:', err);
        }
    }

    async function handleReauth(e) {
        e.preventDefault();
        const password = document.getElementById('reauth-password').value;
        const errorEl = document.getElementById('reauth-error');
        try {
            // TODO: Re-authenticate with Cognito
            errorEl.textContent = '';
            document.getElementById('reauth-modal').hidden = true;
        } catch (err) {
            errorEl.textContent = err.message || 'Re-authentication failed';
        }
    }

    async function apiRequest(method, path, body) {
        // Check if we're offline before making a request
        if (!navigator.onLine) {
            handleOffline();
            throw new Error('No network connection');
        }

        const opts = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            }
        };
        if (body) opts.body = JSON.stringify(body);

        let resp;
        try {
            resp = await fetch(API_BASE + path, opts);
        } catch (fetchErr) {
            // Network error (offline or server unreachable)
            handleOffline();
            throw new Error('Network error: ' + (fetchErr.message || 'Connection failed'));
        }

        // Successful network response - clear offline state
        if (isOffline) {
            handleOnline();
        }

        if (resp.status === 401) {
            // Token expired or backend not deployed — just throw error, don't show modal
            throw new Error('Session expired');
        }

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || `Request failed (${resp.status})`);
        }

        return resp.json();
    }

    function handleOffline() {
        if (isOffline) return; // Already in offline state
        isOffline = true;
        offlineRetryCount = 0;
        showOfflineIndicator('⚠️ Connection lost. Retrying...');
        startOfflineRetry();
    }

    function handleOnline() {
        isOffline = false;
        offlineRetryCount = 0;
        clearOfflineRetryTimer();
        hideOfflineIndicator();
    }

    function startOfflineRetry() {
        clearOfflineRetryTimer();

        if (offlineRetryCount >= OFFLINE_MAX_RETRIES) {
            // Max retries exhausted - show manual retry option
            showOfflineIndicator('⚠️ Connection lost. <button id="offline-retry-btn" class="btn btn-outline btn-sm" style="margin-left:8px;">Retry Now</button>', true);
            const retryBtn = document.getElementById('offline-retry-btn');
            if (retryBtn) retryBtn.addEventListener('click', handleManualRetry);
            return;
        }

        offlineRetryTimer = setTimeout(async () => {
            offlineRetryCount++;
            showOfflineIndicator(`⚠️ Connection lost. Retry ${offlineRetryCount}/${OFFLINE_MAX_RETRIES}...`);

            // Attempt a lightweight connectivity check
            try {
                const checkResp = await fetch(API_BASE + '/dashboard/layouts', {
                    method: 'GET',
                    headers: { 'Authorization': `Bearer ${authToken}` }
                });
                if (checkResp.ok || checkResp.status === 401) {
                    // Server is reachable (even 401 means network is up)
                    handleOnline();
                    return;
                }
            } catch (e) {
                // Still offline
            }

            // Schedule next retry if still offline
            if (isOffline && offlineRetryCount < OFFLINE_MAX_RETRIES) {
                startOfflineRetry();
            } else if (offlineRetryCount >= OFFLINE_MAX_RETRIES) {
                showOfflineIndicator('⚠️ Connection lost. <button id="offline-retry-btn" class="btn btn-outline btn-sm" style="margin-left:8px;">Retry Now</button>', true);
                const retryBtn = document.getElementById('offline-retry-btn');
                if (retryBtn) retryBtn.addEventListener('click', handleManualRetry);
            }
        }, OFFLINE_RETRY_INTERVAL_MS);
    }

    function handleManualRetry() {
        offlineRetryCount = 0;
        showOfflineIndicator('⚠️ Reconnecting...');
        startOfflineRetry();
    }

    function clearOfflineRetryTimer() {
        if (offlineRetryTimer) {
            clearTimeout(offlineRetryTimer);
            offlineRetryTimer = null;
        }
    }

    function showOfflineIndicator(html, isManualRetry) {
        const indicator = document.getElementById('offline-indicator');
        if (indicator) {
            indicator.innerHTML = html;
            indicator.hidden = false;
        }
    }

    function hideOfflineIndicator() {
        const indicator = document.getElementById('offline-indicator');
        if (indicator) {
            indicator.hidden = true;
        }
    }

    function preserveUnsavedWork() {
        // Save current widget configs to localStorage for recovery
        const widgets = GridManager.getWidgets();
        localStorage.setItem('dashboard_unsaved_widgets', JSON.stringify(widgets));
    }

    function getToken() {
        return authToken;
    }

    function getEmail() {
        return memberEmail;
    }

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', init);

    return {
        apiRequest,
        getToken,
        getEmail,
        loadLayouts,
        showDashboard,
        isNetworkOffline: () => isOffline
    };
})();
