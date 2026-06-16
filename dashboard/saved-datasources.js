/**
 * Saved Data Sources Panel Module
 * Displays saved data source configurations with run and delete actions.
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

const SavedDataSources = (() => {
    const CONTAINER_ID = 'saved-datasources-container';

    /**
     * Render the saved data sources list.
     * Fetches GET /dashboard/datasources and displays each item
     * with name, creation date, Run button, and Delete button.
     */
    async function render() {
        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        container.innerHTML = '<p class="saved-ds-loading">Loading saved data sources...</p>';

        try {
            const data = await Dashboard.apiRequest('GET', '/dashboard/datasources');
            const datasources = data.datasources || [];

            if (datasources.length === 0) {
                container.innerHTML = '<p class="saved-ds-empty">No saved data sources yet</p>';
                return;
            }

            let html = '<div class="saved-ds-list">';
            datasources.forEach(ds => {
                const formattedDate = _formatDate(ds.created_at);
                html += `<div class="saved-ds-item" data-id="${ds.datasource_id}">
                    <div class="saved-ds-info">
                        <span class="saved-ds-name">${_escapeHtml(ds.datasource_name)}</span>
                        <span class="saved-ds-date">${formattedDate}</span>
                    </div>
                    <div class="saved-ds-actions">
                        <button class="btn btn-sm btn-primary saved-ds-run-btn" data-id="${ds.datasource_id}">Run</button>
                        <button class="btn btn-sm btn-danger saved-ds-delete-btn" data-id="${ds.datasource_id}" data-name="${_escapeHtml(ds.datasource_name)}">Delete</button>
                    </div>
                </div>`;
            });
            html += '</div>';
            container.innerHTML = html;

            // Wire up Run buttons
            container.querySelectorAll('.saved-ds-run-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-id');
                    runSaved(id);
                });
            });

            // Wire up Delete buttons
            container.querySelectorAll('.saved-ds-delete-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.getAttribute('data-id');
                    const name = btn.getAttribute('data-name');
                    deleteSaved(id, name);
                });
            });
        } catch (err) {
            if (err.message && err.message.includes('401')) {
                // Redirect to login view on auth failure
                document.getElementById('dashboard-view').hidden = true;
                document.getElementById('login-view').hidden = false;
                return;
            }
            container.innerHTML = `<p class="saved-ds-error">Failed to load data sources: ${_escapeHtml(err.message)}</p>`;
        }
    }

    /**
     * Execute a saved data source configuration and display results.
     * Posts to POST /dashboard/datasources/query with the saved config,
     * then renders results via ResultTable.
     * @param {string} datasourceId - The data source ID to run
     */
    async function runSaved(datasourceId) {
        const container = document.getElementById(CONTAINER_ID);

        // Show loading state on the run button
        const runBtn = container ? container.querySelector(`.saved-ds-run-btn[data-id="${datasourceId}"]`) : null;
        if (runBtn) {
            runBtn.disabled = true;
            runBtn.textContent = 'Running...';
        }

        try {
            const result = await Dashboard.apiRequest('POST', '/dashboard/datasources/query', {
                datasource_id: datasourceId
            });

            // Render results using ResultTable
            if (typeof ResultTable !== 'undefined' && ResultTable.render) {
                ResultTable.render(result);
            }
        } catch (err) {
            if (err.message && err.message.includes('401')) {
                document.getElementById('dashboard-view').hidden = true;
                document.getElementById('login-view').hidden = false;
                return;
            }
            alert('Query failed: ' + (err.message || 'Unknown error'));
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
     * @param {string} datasourceId - The data source ID to delete
     * @param {string} name - The display name for the confirmation dialog
     */
    async function deleteSaved(datasourceId, name) {
        const confirmed = confirm(`Delete data source '${name}'?`);
        if (!confirmed) return;

        const container = document.getElementById(CONTAINER_ID);
        const deleteBtn = container ? container.querySelector(`.saved-ds-delete-btn[data-id="${datasourceId}"]`) : null;
        if (deleteBtn) {
            deleteBtn.disabled = true;
            deleteBtn.textContent = 'Deleting...';
        }

        try {
            await Dashboard.apiRequest('DELETE', `/dashboard/datasources/${datasourceId}`);
            // Refresh the list after successful deletion
            await render();
        } catch (err) {
            if (err.message && err.message.includes('401')) {
                document.getElementById('dashboard-view').hidden = true;
                document.getElementById('login-view').hidden = false;
                return;
            }
            alert('Delete failed: ' + (err.message || 'Unknown error'));
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
     * @param {string} isoString - ISO 8601 date string
     * @returns {string} Formatted date or fallback text
     */
    function _formatDate(isoString) {
        if (!isoString) return '';
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
     * @param {string} str - Raw string
     * @returns {string} Escaped HTML-safe string
     */
    function _escapeHtml(str) {
        if (!str) return '';
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    return {
        render,
        runSaved,
        deleteSaved
    };
})();
