/**
 * Saved Data Sources Panel Module
 * Displays saved data source configurations with run and delete actions.
 * Integrates with ResultTable.js for query result display.
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

const SavedDataSources = (() => {
    const CONTAINER_ID = 'saved-datasources-container';
    const RESULT_TABLE_CONTAINER_ID = 'saved-datasources-result-table';
    
    // Instance of ResultTable for displaying query results
    let resultTable = null;

    /**
     * Initialize the SavedDataSources module.
     * Sets up the ResultTable instance for displaying query results.
     */
    function init() {
        // Initialize ResultTable for displaying results
        resultTable = new ResultTable({
            containerId: RESULT_TABLE_CONTAINER_ID,
            columns: [],  // Will be populated dynamically from query response
            pageSize: 25,
            onRefresh: function() {
                // Refresh handler can be customized
            }
        });
    }

    /**
     * Render the saved data sources list.
     * Fetches GET /dashboard/datasources and displays each item
     * with name, creation date, Run button, and Delete button.
     * Validates: Requirement 8.1
     */
    async function render() {
        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        container.innerHTML = '<p class="saved-ds-loading">Loading saved data sources...</p>';

        try {
            // Fetch saved datasources from backend API
            const response = await fetch('/dashboard/datasources', {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${_getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.status === 401) {
                // Authentication failed - redirect to login
                _redirectToLogin();
                return;
            }

            if (!response.ok) {
                throw new Error(`Failed to fetch datasources: ${response.statusText}`);
            }

            const data = await response.json();
            const datasources = data.datasources || [];

            if (datasources.length === 0) {
                container.innerHTML = '<p class="saved-ds-empty">No saved data sources yet. Create one in the custom dashboard wizard.</p>';
                return;
            }

            // Build list HTML
            let html = '<div class="saved-ds-list">';
            datasources.forEach(ds => {
                const formattedDate = _formatDate(ds.created_at);
                const escapedName = _escapeHtml(ds.datasource_name);
                const datasourceId = _escapeHtml(ds.datasource_id);
                
                html += `<div class="saved-ds-item" data-id="${datasourceId}">
                    <div class="saved-ds-info">
                        <span class="saved-ds-name">${escapedName}</span>
                        <span class="saved-ds-date">Created: ${formattedDate}</span>
                    </div>
                    <div class="saved-ds-actions">
                        <button class="btn btn-sm btn-primary saved-ds-run-btn" data-id="${datasourceId}" title="Execute this saved data source">Run</button>
                        <button class="btn btn-sm btn-danger saved-ds-delete-btn" data-id="${datasourceId}" data-name="${escapedName}" title="Delete this saved data source">Delete</button>
                    </div>
                </div>`;
            });
            html += '</div>';
            container.innerHTML = html;

            // Wire up Run buttons
            container.querySelectorAll('.saved-ds-run-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const id = btn.getAttribute('data-id');
                    await runSaved(id);
                });
            });

            // Wire up Delete buttons
            container.querySelectorAll('.saved-ds-delete-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.preventDefault();
                    const id = btn.getAttribute('data-id');
                    const name = btn.getAttribute('data-name');
                    await deleteSaved(id, name);
                });
            });
        } catch (err) {
            const errorMsg = err.message || 'Unknown error';
            container.innerHTML = `<p class="saved-ds-error">Failed to load data sources: ${_escapeHtml(errorMsg)}</p>`;
            console.error('SavedDataSources.render() error:', err);
        }
    }

    /**
     * Execute a saved data source configuration and display results.
     * Posts to POST /dashboard/datasources/query with the saved config,
     * then renders results via ResultTable.
     * Validates: Requirement 8.2
     * 
     * @param {string} datasourceId - The data source ID to run
     */
    async function runSaved(datasourceId) {
        const container = document.getElementById(CONTAINER_ID);
        const runBtn = container ? container.querySelector(`.saved-ds-run-btn[data-id="${_escapeHtml(datasourceId)}"]`) : null;
        
        if (runBtn) {
            runBtn.disabled = true;
            runBtn.textContent = 'Running...';
        }

        try {
            // Execute the saved datasource query
            const response = await fetch('/dashboard/datasources/query', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${_getAuthToken()}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    datasource_id: datasourceId
                })
            });

            if (response.status === 401) {
                _redirectToLogin();
                return;
            }

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `Query failed with status ${response.status}`);
            }

            const result = await response.json();

            // Render results using ResultTable
            if (resultTable && result.rows) {
                // Dynamically set columns based on result keys
                const columns = result.columns || (result.rows.length > 0 ? Object.keys(result.rows[0]) : []);
                resultTable.columns = columns.map(col => ({
                    key: col,
                    label: col.replace(/_/g, ' ').toUpperCase(),
                    sortable: true
                }));

                // Render the table with result data
                resultTable.render(result.rows, result.total_count || result.rows.length);
            } else {
                console.warn('ResultTable not initialized or no rows in result');
            }
        } catch (err) {
            const errorMsg = err.message || 'Unknown error';
            console.error('SavedDataSources.runSaved() error:', err);
            alert(`Query failed: ${errorMsg}`);
        } finally {
            // Restore button state
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = 'Run';
            }
        }
    }

    /**
     * Delete a saved data source after user confirmation.
     * Shows confirm() dialog, calls DELETE /dashboard/datasources/{id},
     * then refreshes the list.
     * Validates: Requirement 8.3, 8.4, 8.5
     * 
     * @param {string} datasourceId - The data source ID to delete
     * @param {string} name - The display name for the confirmation dialog
     */
    async function deleteSaved(datasourceId, name) {
        // Show confirmation dialog
        const confirmed = confirm(`Are you sure you want to delete the saved data source "${name}"? This action cannot be undone.`);
        if (!confirmed) return;

        const container = document.getElementById(CONTAINER_ID);
        const deleteBtn = container ? container.querySelector(`.saved-ds-delete-btn[data-id="${_escapeHtml(datasourceId)}"]`) : null;
        
        if (deleteBtn) {
            deleteBtn.disabled = true;
            deleteBtn.textContent = 'Deleting...';
        }

        try {
            // Delete the datasource
            const response = await fetch(`/dashboard/datasources/${datasourceId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${_getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.status === 401) {
                _redirectToLogin();
                return;
            }

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `Delete failed with status ${response.status}`);
            }

            // Refresh the list after successful deletion
            await render();
        } catch (err) {
            const errorMsg = err.message || 'Unknown error';
            console.error('SavedDataSources.deleteSaved() error:', err);
            alert(`Delete failed: ${errorMsg}`);
            
            // Restore button state on failure
            if (deleteBtn) {
                deleteBtn.disabled = false;
                deleteBtn.textContent = 'Delete';
            }
        }
    }

    /**
     * Format an ISO 8601 date string as a human-readable date.
     * e.g., "2024-06-15T10:30:00Z" → "Jun 15, 2024"
     * 
     * @param {string} isoString - ISO 8601 date string
     * @returns {string} Formatted date or fallback text
     */
    function _formatDate(isoString) {
        if (!isoString) return 'Unknown date';
        try {
            const date = new Date(isoString);
            if (isNaN(date.getTime())) return isoString;
            return date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
            });
        } catch (e) {
            return isoString;
        }
    }

    /**
     * Escape HTML entities to prevent XSS when inserting user-provided text.
     * 
     * @param {string} str - Raw string
     * @returns {string} Escaped HTML-safe string
     */
    function _escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * Get the authentication token from localStorage or session.
     * This assumes tokens are stored in the same way as the member portal.
     * 
     * @returns {string} JWT token
     */
    function _getAuthToken() {
        // Try to get token from sessionStorage or localStorage
        let token = sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token');
        if (!token && window.getAuthToken) {
            // Fallback to window function if available
            token = window.getAuthToken();
        }
        return token || '';
    }

    /**
     * Redirect to login view on authentication failure.
     * Assumes there's a login view in the DOM.
     */
    function _redirectToLogin() {
        // Try to hide dashboard view and show login view
        const dashboardView = document.getElementById('dashboard-view');
        const loginView = document.getElementById('login-view');
        
        if (dashboardView) dashboardView.hidden = true;
        if (loginView) loginView.hidden = false;
        
        // Fallback: redirect to login page
        if (!loginView) {
            window.location.href = '../index.html?login=required';
        }
    }

    // Public API
    return {
        init,
        render,
        runSaved,
        deleteSaved
    };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        SavedDataSources.init();
    });
} else {
    SavedDataSources.init();
}
