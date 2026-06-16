/**
 * Result Table Module
 * Renders tabular data from data source queries with sorting, pagination,
 * and loading/empty/error states.
 */

const ResultTable = (() => {
    const CONTAINER_ID = 'datasource-result-container';

    let currentData = null;       // { rows, total_count, page, page_size, total_pages, has_more }
    let currentConfig = null;     // query config used to fetch data
    let sortColumn = null;        // currently sorted column name
    let sortDirection = 'asc';    // 'asc' or 'desc'

    /**
     * Render the result table from a query response.
     * @param {object} response - { rows: [{...}], total_count, page, page_size, total_pages, has_more }
     * @param {object} config - The query config used to produce this response (for refresh)
     */
    function render(response, config) {
        currentData = response;
        if (config) currentConfig = config;

        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        const rows = response.rows || [];
        if (rows.length === 0) {
            showEmpty();
            return;
        }

        // Determine columns dynamically from the first row or config attributes
        const columns = _getColumns(rows, config);

        // Build row count display
        const page = response.page || 1;
        const pageSize = response.page_size || rows.length;
        const totalCount = response.total_count || rows.length;
        const startRow = (page - 1) * pageSize + 1;
        const endRow = Math.min(page * pageSize, totalCount);
        const rowCountText = `Showing ${startRow.toLocaleString()}-${endRow.toLocaleString()} of ${totalCount.toLocaleString()} records`;

        // Apply client-side sort if active
        let displayRows = rows.slice();
        if (sortColumn) {
            displayRows = _sortRows(displayRows, sortColumn, sortDirection);
        }

        // Build HTML
        let html = '<div class="result-table-wrapper">';
        html += `<div class="result-table-info">${rowCountText}</div>`;
        html += '<div class="result-table-scroll"><table class="result-table"><thead><tr>';

        // Column headers with sort indicators
        columns.forEach(col => {
            const sortIndicator = _getSortIndicator(col);
            html += `<th class="result-table-th" data-column="${_escapeHtml(col)}">${_escapeHtml(col)}${sortIndicator}</th>`;
        });
        html += '</tr></thead><tbody>';

        // Data rows
        displayRows.forEach(row => {
            html += '<tr>';
            columns.forEach(col => {
                const value = row[col];
                html += `<td>${_formatCellValue(col, value)}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';

        // Pagination controls
        html += renderPagination(response);
        html += '</div>';

        container.innerHTML = html;

        // Bind sort handlers to column headers
        container.querySelectorAll('.result-table-th').forEach(th => {
            th.addEventListener('click', () => {
                const col = th.getAttribute('data-column');
                sort(col);
            });
        });

        // Bind pagination handlers
        _bindPaginationHandlers(container);
    }

    /**
     * Toggle sort on a column header click (asc → desc → asc).
     * Client-side sort on current page data.
     * @param {string} column - Column name to sort by
     */
    function sort(column) {
        if (sortColumn === column) {
            sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            sortColumn = column;
            sortDirection = 'asc';
        }

        // Re-render with current data (client-side sort)
        if (currentData) {
            render(currentData, currentConfig);
        }
    }

    /**
     * Re-execute the current query and refresh the table.
     * Shows loading indicator during the request.
     */
    async function refresh() {
        if (!currentConfig) return;

        showLoading();

        try {
            const response = await Dashboard.apiRequest('POST', '/dashboard/datasources/query', currentConfig);
            render(response, currentConfig);
        } catch (err) {
            showError(err.message || 'Failed to refresh data');
        }
    }

    /**
     * Render pagination controls.
     * @param {object} response - Query response with pagination metadata
     * @returns {string} HTML string for pagination controls
     */
    function renderPagination(response) {
        const totalPages = response.total_pages || 1;
        const currentPage = response.page || 1;

        if (totalPages <= 1) return '';

        let html = '<div class="result-table-pagination">';

        // Previous button
        const prevDisabled = currentPage <= 1 ? ' disabled' : '';
        html += `<button class="pagination-btn pagination-prev"${prevDisabled} data-page="${currentPage - 1}">← Prev</button>`;

        // Page numbers
        html += '<span class="pagination-pages">';
        const pages = _getPageNumbers(currentPage, totalPages);
        pages.forEach(p => {
            if (p === '...') {
                html += '<span class="pagination-ellipsis">…</span>';
            } else {
                const activeClass = p === currentPage ? ' pagination-active' : '';
                html += `<button class="pagination-btn pagination-num${activeClass}" data-page="${p}">${p}</button>`;
            }
        });
        html += '</span>';

        // Next button
        const nextDisabled = currentPage >= totalPages ? ' disabled' : '';
        html += `<button class="pagination-btn pagination-next"${nextDisabled} data-page="${currentPage + 1}">Next →</button>`;

        html += '</div>';
        return html;
    }

    /**
     * Show loading state in the result container.
     */
    function showLoading() {
        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        container.innerHTML = `
            <div class="result-table-state result-table-loading">
                <div class="loading-spinner"></div>
                <p>Loading data...</p>
            </div>`;
    }

    /**
     * Show empty state when no data matches the query.
     */
    function showEmpty() {
        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        container.innerHTML = `
            <div class="result-table-state result-table-empty">
                <div class="empty-icon">📭</div>
                <p>No data found for the selected criteria</p>
            </div>`;
    }

    /**
     * Show error state with the error message.
     * @param {string} message - Error message to display
     */
    function showError(message) {
        const container = document.getElementById(CONTAINER_ID);
        if (!container) return;

        container.innerHTML = `
            <div class="result-table-state result-table-error">
                <div class="error-icon">⚠️</div>
                <p>${_escapeHtml(message || 'An error occurred while loading data')}</p>
                <button class="btn btn-outline btn-sm result-table-retry-btn">Retry</button>
            </div>`;

        // Bind retry button
        const retryBtn = container.querySelector('.result-table-retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', refresh);
        }
    }

    // --- Private helpers ---

    /**
     * Determine columns from response rows or config attributes.
     */
    function _getColumns(rows, config) {
        // If config specifies attributes, use those in order
        if (config && config.attributes && config.attributes.length > 0) {
            return config.attributes;
        }
        // Otherwise, derive from first row keys
        if (rows.length > 0) {
            return Object.keys(rows[0]);
        }
        return [];
    }

    /**
     * Sort rows by column (client-side).
     */
    function _sortRows(rows, column, direction) {
        return rows.slice().sort((a, b) => {
            let valA = a[column];
            let valB = b[column];

            // Handle null/undefined
            if (valA == null && valB == null) return 0;
            if (valA == null) return direction === 'asc' ? -1 : 1;
            if (valB == null) return direction === 'asc' ? 1 : -1;

            // Numeric comparison
            const numA = parseFloat(valA);
            const numB = parseFloat(valB);
            if (!isNaN(numA) && !isNaN(numB)) {
                return direction === 'asc' ? numA - numB : numB - numA;
            }

            // String comparison
            const strA = String(valA).toLowerCase();
            const strB = String(valB).toLowerCase();
            if (strA < strB) return direction === 'asc' ? -1 : 1;
            if (strA > strB) return direction === 'asc' ? 1 : -1;
            return 0;
        });
    }

    /**
     * Get sort indicator arrow for a column header.
     */
    function _getSortIndicator(column) {
        if (sortColumn !== column) return ' <span class="sort-indicator">⇅</span>';
        if (sortDirection === 'asc') return ' <span class="sort-indicator sort-active">↑</span>';
        return ' <span class="sort-indicator sort-active">↓</span>';
    }

    /**
     * Format a cell value for display.
     * Numbers that look like cost amounts get 2 decimal places.
     */
    function _formatCellValue(column, value) {
        if (value == null || value === '') return '<span class="cell-empty">-</span>';

        // Format cost/amount columns with 2 decimal places
        if (_isCostColumn(column)) {
            const num = parseFloat(value);
            if (!isNaN(num)) {
                return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
        }

        return _escapeHtml(String(value));
    }

    /**
     * Determine if a column is a cost/amount column that should be formatted with decimals.
     */
    function _isCostColumn(column) {
        const costPatterns = ['cost', 'amount', 'price', 'total', 'spend'];
        const colLower = column.toLowerCase();
        return costPatterns.some(pattern => colLower.includes(pattern));
    }

    /**
     * Generate page number array with ellipsis for large page counts.
     */
    function _getPageNumbers(current, total) {
        if (total <= 7) {
            return Array.from({ length: total }, (_, i) => i + 1);
        }

        const pages = [];
        pages.push(1);

        if (current > 3) pages.push('...');

        const start = Math.max(2, current - 1);
        const end = Math.min(total - 1, current + 1);
        for (let i = start; i <= end; i++) {
            pages.push(i);
        }

        if (current < total - 2) pages.push('...');

        pages.push(total);
        return pages;
    }

    /**
     * Bind click handlers to pagination buttons.
     */
    function _bindPaginationHandlers(container) {
        container.querySelectorAll('.pagination-btn[data-page]').forEach(btn => {
            if (btn.hasAttribute('disabled')) return;
            btn.addEventListener('click', () => {
                const page = parseInt(btn.getAttribute('data-page'), 10);
                if (isNaN(page) || page < 1) return;
                _goToPage(page);
            });
        });
    }

    /**
     * Navigate to a specific page by re-querying the backend.
     */
    async function _goToPage(page) {
        if (!currentConfig) return;

        showLoading();

        const queryConfig = Object.assign({}, currentConfig, { page: page });

        try {
            const response = await Dashboard.apiRequest('POST', '/dashboard/datasources/query', queryConfig);
            // Reset sort when changing pages (fresh data from server)
            sortColumn = null;
            sortDirection = 'asc';
            render(response, currentConfig);
        } catch (err) {
            showError(err.message || 'Failed to load page');
        }
    }

    /**
     * Escape HTML to prevent XSS in rendered content.
     */
    function _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    return {
        render,
        sort,
        refresh,
        renderPagination,
        showLoading,
        showEmpty,
        showError
    };
})();
