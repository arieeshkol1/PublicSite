/**
 * result-table.js - Tabular Display Logic for Member Portal
 * 
 * Provides a reusable data table component with:
 * - Dynamic column rendering from query responses
 * - Client-side sorting on column headers
 * - Pagination controls for large result sets
 * - Loading, empty, and error state displays
 * - Row count display from API responses
 * 
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */

/**
 * ResultTable - Encapsulates all table functionality
 * @param {Object} options - Configuration
 * @param {string} options.containerId - ID of container for the table
 * @param {Array} options.columns - Column definitions [{ key, label, format }]
 * @param {Function} options.onRefresh - Called when refresh is triggered
 * @param {number} options.pageSize - Rows per page (default: 25)
 */
function ResultTable(options) {
    this.containerId = options.containerId;
    this.columns = options.columns || [];
    this.onRefresh = options.onRefresh || function() {};
    this.pageSize = options.pageSize || 25;
    
    // State
    this.rows = [];
    this.totalCount = 0;
    this.currentPage = 1;
    this.sortColumn = null;
    this.sortAscending = true;
    this.isLoading = false;
    this.error = null;
    
    this.container = document.getElementById(this.containerId);
    if (!this.container) {
        console.error('ResultTable: Container not found', this.containerId);
        return;
    }
    
    this._init();
}

/**
 * Initialize the table container HTML structure
 */
ResultTable.prototype._init = function() {
    var self = this;
    
    // Build wrapper
    this.container.innerHTML = '';
    this.container.className = 'result-table-wrapper';
    
    // Header with row count and refresh
    var header = document.createElement('div');
    header.className = 'result-table-header';
    header.innerHTML = 
        '<div class="result-table-header-left">' +
            '<span class="result-table-row-count">Rows: <strong id="result-row-count">0</strong></span>' +
        '</div>' +
        '<div class="result-table-header-right">' +
            '<button class="result-table-refresh-btn" id="result-refresh-btn" title="Refresh">🔄</button>' +
        '</div>';
    this.container.appendChild(header);
    
    // Table
    var tableWrapper = document.createElement('div');
    tableWrapper.className = 'table-wrapper';
    
    this.tableEl = document.createElement('table');
    this.tableEl.className = 'data-table result-table';
    this.tableEl.innerHTML = '<thead></thead><tbody></tbody>';
    
    tableWrapper.appendChild(this.tableEl);
    this.container.appendChild(tableWrapper);
    
    // Pagination
    var pagination = document.createElement('div');
    pagination.className = 'result-table-pagination';
    pagination.id = 'result-pagination';
    this.container.appendChild(pagination);
    
    // Loading overlay
    this.loadingOverlay = document.createElement('div');
    this.loadingOverlay.className = 'result-table-loading-overlay';
    this.loadingOverlay.hidden = true;
    this.loadingOverlay.innerHTML = 
        '<div class="result-table-loading-spinner"></div>' +
        '<div class="result-table-loading-text">Loading...</div>';
    this.container.appendChild(this.loadingOverlay);
    
    // Empty state
    this.emptyState = document.createElement('div');
    this.emptyState.className = 'result-table-empty-state';
    this.emptyState.hidden = true;
    this.emptyState.innerHTML = '<p>No data available</p>';
    this.container.appendChild(this.emptyState);
    
    // Error state
    this.errorState = document.createElement('div');
    this.errorState.className = 'result-table-error-state';
    this.errorState.hidden = true;
    this.errorState.innerHTML = '<p class="result-table-error-message"></p>';
    this.container.appendChild(this.errorState);
    
    // Event listeners
    var refreshBtn = document.getElementById('result-refresh-btn');
    if (refreshBtn) {
        refreshBtn.onclick = function() { self.refresh(); };
    }
    
    // Table header click for sorting
    var thead = this.tableEl.querySelector('thead');
    thead.onclick = function(e) {
        var th = e.target.closest('th');
        if (th && th.dataset.sortable === 'true') {
            var columnKey = th.dataset.column;
            self.sort(columnKey);
        }
    };
};

/**
 * Render the table from data
 * @param {Array} rows - Array of row objects
 * @param {number} totalCount - Total row count from response
 */
ResultTable.prototype.render = function(rows, totalCount) {
    this.rows = rows || [];
    this.totalCount = totalCount || this.rows.length;
    this.currentPage = 1;
    this.error = null;
    
    this._updateDisplay();
};

/**
 * Update all display elements based on current state
 */
ResultTable.prototype._updateDisplay = function() {
    if (this.error) {
        this.showError(this.error);
        return;
    }
    
    if (this.isLoading) {
        this.showLoading();
        return;
    }
    
    if (this.rows.length === 0) {
        this.showEmpty();
        return;
    }
    
    this._hideAllStates();
    
    // Render headers
    this._renderHeaders();
    
    // Render rows for current page
    this._renderRows();
    
    // Render pagination
    this._renderPagination();
    
    // Update row count
    var rowCountEl = document.getElementById('result-row-count');
    if (rowCountEl) {
        rowCountEl.textContent = this.totalCount;
    }
};

/**
 * Render table headers with sort indicators
 */
ResultTable.prototype._renderHeaders = function() {
    var self = this;
    var thead = this.tableEl.querySelector('thead');
    var tr = document.createElement('tr');
    
    this.columns.forEach(function(col) {
        var th = document.createElement('th');
        th.className = 'result-table-header-cell';
        th.dataset.column = col.key;
        th.dataset.sortable = col.sortable !== false ? 'true' : 'false';
        
        var label = col.label || col.key;
        var html = label;
        
        // Add sort indicator
        if (col.sortable !== false) {
            th.style.cursor = 'pointer';
            if (self.sortColumn === col.key) {
                var indicator = self.sortAscending ? ' ▲' : ' ▼';
                html = label + '<span class="result-table-sort-indicator">' + indicator + '</span>';
            }
        }
        
        th.innerHTML = html;
        tr.appendChild(th);
    });
    
    thead.innerHTML = '';
    thead.appendChild(tr);
};

/**
 * Render table rows for current page
 */
ResultTable.prototype._renderRows = function() {
    var self = this;
    var tbody = this.tableEl.querySelector('tbody');
    tbody.innerHTML = '';
    
    // Get rows for current page
    var startIdx = (this.currentPage - 1) * this.pageSize;
    var endIdx = startIdx + this.pageSize;
    var pageRows = this.rows.slice(startIdx, endIdx);
    
    pageRows.forEach(function(row) {
        var tr = document.createElement('tr');
        tr.className = 'result-table-row';
        
        self.columns.forEach(function(col) {
            var td = document.createElement('td');
            td.className = 'result-table-cell';
            
            var value = row[col.key];
            var displayValue = value;
            
            // Apply custom formatter if provided
            if (col.format && typeof col.format === 'function') {
                displayValue = col.format(value, row);
            }
            
            // Safe HTML escape for text content
            if (typeof displayValue === 'string') {
                td.textContent = displayValue;
            } else if (displayValue === null || displayValue === undefined) {
                td.textContent = '-';
            } else {
                td.textContent = String(displayValue);
            }
            
            tr.appendChild(td);
        });
        
        tbody.appendChild(tr);
    });
};

/**
 * Sort table by column
 * @param {string} columnKey - Column key to sort by
 */
ResultTable.prototype.sort = function(columnKey) {
    // Toggle sort direction if same column clicked
    if (this.sortColumn === columnKey) {
        this.sortAscending = !this.sortAscending;
    } else {
        this.sortColumn = columnKey;
        this.sortAscending = true;
    }
    
    // Find column definition
    var col = null;
    for (var i = 0; i < this.columns.length; i++) {
        if (this.columns[i].key === columnKey) {
            col = this.columns[i];
            break;
        }
    }
    
    if (!col) return;
    
    var self = this;
    var direction = this.sortAscending ? 1 : -1;
    
    // Client-side sort
    this.rows.sort(function(a, b) {
        var aVal = a[columnKey];
        var bVal = b[columnKey];
        
        // Handle nulls
        if (aVal == null && bVal == null) return 0;
        if (aVal == null) return 1 * direction;
        if (bVal == null) return -1 * direction;
        
        // Numeric comparison
        if (typeof aVal === 'number' && typeof bVal === 'number') {
            return (aVal - bVal) * direction;
        }
        
        // String comparison
        if (typeof aVal === 'string' && typeof bVal === 'string') {
            var result = aVal.localeCompare(bVal);
            return result * direction;
        }
        
        // Fallback: convert to string
        var aStr = String(aVal);
        var bStr = String(bVal);
        return aStr.localeCompare(bStr) * direction;
    });
    
    this.currentPage = 1;
    this._updateDisplay();
};

/**
 * Refresh data by calling the onRefresh callback
 */
ResultTable.prototype.refresh = function() {
    this.showLoading();
    var self = this;
    
    // Call the refresh callback
    Promise.resolve(this.onRefresh()).then(function() {
        self.hideLoading();
        self._updateDisplay();
    }).catch(function(err) {
        self.showError(err.message || 'Refresh failed');
    });
};

/**
 * Render pagination controls
 */
ResultTable.prototype._renderPagination = function() {
    var self = this;
    var paginationEl = document.getElementById('result-pagination');
    if (!paginationEl) return;
    
    var totalPages = Math.ceil(this.rows.length / this.pageSize);
    if (totalPages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }
    
    var html = '<div class="result-pagination-controls">';
    
    // Previous button
    html += '<button class="result-pagination-btn" ' + (this.currentPage === 1 ? 'disabled' : '') + 
            ' onclick="' + this._getPageFunctionName() + '.goToPage(' + (this.currentPage - 1) + ')">← Prev</button>';
    
    // Page numbers
    var startPage = Math.max(1, this.currentPage - 2);
    var endPage = Math.min(totalPages, this.currentPage + 2);
    
    if (startPage > 1) {
        html += '<button class="result-pagination-btn" onclick="' + this._getPageFunctionName() + '.goToPage(1)">1</button>';
        if (startPage > 2) html += '<span class="result-pagination-dots">...</span>';
    }
    
    for (var i = startPage; i <= endPage; i++) {
        var activeClass = i === this.currentPage ? ' result-pagination-active' : '';
        html += '<button class="result-pagination-btn' + activeClass + '" onclick="' + this._getPageFunctionName() + 
                '.goToPage(' + i + ')">' + i + '</button>';
    }
    
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) html += '<span class="result-pagination-dots">...</span>';
        html += '<button class="result-pagination-btn" onclick="' + this._getPageFunctionName() + '.goToPage(' + totalPages + ')">' + totalPages + '</button>';
    }
    
    // Next button
    html += '<button class="result-pagination-btn" ' + (this.currentPage === totalPages ? 'disabled' : '') + 
            ' onclick="' + this._getPageFunctionName() + '.goToPage(' + (this.currentPage + 1) + ')">Next →</button>';
    
    html += '</div>';
    paginationEl.innerHTML = html;
};

/**
 * Get global function name for this table (for onclick handlers)
 */
ResultTable.prototype._getPageFunctionName = function() {
    // Store reference globally if needed
    if (!window._resultTableInstances) window._resultTableInstances = {};
    var id = this.containerId;
    window._resultTableInstances[id] = this;
    return 'window._resultTableInstances["' + id + '"]';
};

/**
 * Navigate to a specific page
 * @param {number} pageNum - Page number to go to
 */
ResultTable.prototype.goToPage = function(pageNum) {
    var totalPages = Math.ceil(this.rows.length / this.pageSize);
    if (pageNum < 1 || pageNum > totalPages) return;
    
    this.currentPage = pageNum;
    this._updateDisplay();
};

/**
 * Show loading state
 */
ResultTable.prototype.showLoading = function() {
    this.isLoading = true;
    this._hideAllStates();
    this.loadingOverlay.hidden = false;
};

/**
 * Hide loading state
 */
ResultTable.prototype.hideLoading = function() {
    this.isLoading = false;
    if (this.loadingOverlay) {
        this.loadingOverlay.hidden = true;
    }
};

/**
 * Show empty state
 */
ResultTable.prototype.showEmpty = function() {
    this._hideAllStates();
    if (this.emptyState) {
        this.emptyState.hidden = false;
    }
};

/**
 * Show error state
 * @param {string} message - Error message to display
 */
ResultTable.prototype.showError = function(message) {
    this.error = message;
    this._hideAllStates();
    
    if (this.errorState) {
        var msgEl = this.errorState.querySelector('.result-table-error-message');
        if (msgEl) msgEl.textContent = message || 'An error occurred';
        this.errorState.hidden = false;
    }
};

/**
 * Hide all overlay states
 */
ResultTable.prototype._hideAllStates = function() {
    if (this.loadingOverlay) this.loadingOverlay.hidden = true;
    if (this.emptyState) this.emptyState.hidden = true;
    if (this.errorState) this.errorState.hidden = true;
};

/**
 * Set data without rendering immediately
 * @param {Array} rows - Data rows
 * @param {number} totalCount - Total count from API
 */
ResultTable.prototype.setData = function(rows, totalCount) {
    this.rows = rows || [];
    this.totalCount = totalCount || this.rows.length;
};

/**
 * Get current page rows
 */
ResultTable.prototype.getPageRows = function() {
    var startIdx = (this.currentPage - 1) * this.pageSize;
    var endIdx = startIdx + this.pageSize;
    return this.rows.slice(startIdx, endIdx);
};

/**
 * Get total page count
 */
ResultTable.prototype.getTotalPages = function() {
    return Math.ceil(this.rows.length / this.pageSize);
};

/**
 * Clear all data
 */
ResultTable.prototype.clear = function() {
    this.rows = [];
    this.totalCount = 0;
    this.currentPage = 1;
    this.sortColumn = null;
    this.sortAscending = true;
    this.error = null;
    this._updateDisplay();
};

/**
 * Update configuration
 * @param {Object} options - New options to merge
 */
ResultTable.prototype.update = function(options) {
    if (options.columns) this.columns = options.columns;
    if (options.pageSize) this.pageSize = options.pageSize;
    if (options.onRefresh) this.onRefresh = options.onRefresh;
    
    this._updateDisplay();
};

/**
 * Export visible data as CSV
 */
ResultTable.prototype.exportAsCSV = function() {
    if (this.rows.length === 0) return '';
    
    var lines = [];
    
    // Header row
    var headerRow = this.columns.map(function(col) {
        return '"' + (col.label || col.key).replace(/"/g, '""') + '"';
    }).join(',');
    lines.push(headerRow);
    
    // Data rows
    this.rows.forEach(function(row) {
        var cells = this.columns.map(function(col) {
            var value = row[col.key];
            if (value == null) value = '';
            return '"' + String(value).replace(/"/g, '""') + '"';
        });
        lines.push(cells.join(','));
    }, this);
    
    return lines.join('\n');
};

/**
 * Trigger CSV download
 * @param {string} filename - Filename for download
 */
ResultTable.prototype.downloadCSV = function(filename) {
    filename = filename || 'data.csv';
    var csv = this.exportAsCSV();
    if (!csv) return;
    
    var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    var link = document.createElement('a');
    var url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
};
