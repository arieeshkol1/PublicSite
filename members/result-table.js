/**
 * Result Table Module
 * Displays query results in a tabular format with sorting, pagination, and controls
 */

const ResultTable = (() => {
  let currentData = {
    rows: [],
    columns: [],
    config: {},
    currentPage: 1,
    pageSize: 50
  };

  // Resolve wrapper container at render time, not load time
  function _getWrapperId() {
    if (document.getElementById('observe-saved-datasources-result-table')) {
      return 'observe-saved-datasources-result-table';
    }
    return 'saved-datasources-result-table';
  }

  /**
   * Render the result table
   */
  function render(rows, columns, config) {
    currentData = {
      rows: rows || [],
      columns: columns || [],
      config: config || {},
      currentPage: 1,
      pageSize: 50
    };

    const wrapper = document.getElementById(_getWrapperId());
    if (!wrapper) return;

    if (!rows || rows.length === 0) {
      showEmpty();
      return;
    }

    wrapper.innerHTML = buildTableHTML();
    attachEventListeners();
  }

  /**
   * Build table HTML with pagination
   */
  function buildTableHTML() {
    const startIdx = (currentData.currentPage - 1) * currentData.pageSize;
    const endIdx = startIdx + currentData.pageSize;
    const pageRows = currentData.rows.slice(startIdx, endIdx);
    const totalPages = Math.ceil(currentData.rows.length / currentData.pageSize);

    let html = '<div style="margin-top: 20px;">';

    // Header with info
    html += `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
        <div style="font-weight: 600; color: #1f2937;">
          Results: <span style="color: #6366f1;">${currentData.rows.length}</span> rows
        </div>
        <div style="display: flex; gap: 8px;">
          <button onclick="ResultTable.promptSave()" class="btn btn-primary btn-sm" style="background:#8b5cf6;border-color:#8b5cf6;">💾 Save Query</button>
          <button onclick="ResultTable.refresh()" class="btn btn-outline btn-sm">🔄 Refresh</button>
          <button onclick="ResultTable.exportCSV()" class="btn btn-outline btn-sm">📥 CSV</button>
          <button onclick="ResultTable.exportJSON()" class="btn btn-outline btn-sm">📋 JSON</button>
        </div>
      </div>
      <div id="rt-save-bar" style="display:none;margin-bottom:12px;padding:12px;gap:8px;align-items:center;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;">
        <input type="text" id="rt-save-name" placeholder="Enter a name for this query" style="flex:1;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.9em;"/>
        <button onclick="ResultTable.doSave()" class="btn btn-primary btn-sm" style="background:#8b5cf6;border-color:#8b5cf6;">Save</button>
        <button onclick="ResultTable.cancelSave()" class="btn btn-outline btn-sm">Cancel</button>
      </div>
    `;

    // Table
    html += '<div style="overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 8px;">';
    html += '<table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">';

    // Header row with sortable columns
    html += '<thead style="background: #f3f4f6; border-bottom: 1px solid #e5e7eb;">';
    html += '<tr>';
    currentData.columns.forEach(col => {
      html += `
        <th style="padding: 12px; text-align: left; font-weight: 600; color: #374151; cursor: pointer; user-select: none;" onclick="ResultTable.toggleSort('${col}')">
          ${col} <span class="sort-indicator" data-col="${col}" style="display: none; margin-left: 4px;">▲</span>
        </th>
      `;
    });
    html += '</tr>';
    html += '</thead>';

    // Data rows
    html += '<tbody>';
    pageRows.forEach((row, idx) => {
      const bgColor = idx % 2 === 0 ? '#fff' : '#f9fafb';
      html += `<tr style="background: ${bgColor}; border-bottom: 1px solid #e5e7eb; hover:background: #f3f4f6;">`;

      currentData.columns.forEach(col => {
        const value = row[col];
        const display = formatValue(value);
        html += `<td style="padding: 12px; color: #1f2937;">${display}</td>`;
      });

      html += '</tr>';
    });
    html += '</tbody>';

    html += '</table>';
    html += '</div>';

    // Pagination
    if (totalPages > 1) {
      html += buildPaginationHTML(totalPages);
    }

    html += '</div>';

    return html;
  }

  /**
   * Build pagination controls
   */
  function buildPaginationHTML(totalPages) {
    let html = '<div style="display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 16px;">';

    // Previous
    html += `
      <button onclick="ResultTable.goToPage(${Math.max(1, currentData.currentPage - 1)})" 
              class="btn btn-outline btn-sm" 
              ${currentData.currentPage === 1 ? 'disabled' : ''}>
        ← Previous
      </button>
    `;

    // Page numbers
    const startPage = Math.max(1, currentData.currentPage - 2);
    const endPage = Math.min(totalPages, currentData.currentPage + 2);

    if (startPage > 1) {
      html += `<button onclick="ResultTable.goToPage(1)" class="btn btn-outline btn-sm">1</button>`;
      if (startPage > 2) html += '<span style="color: #9ca3af;">...</span>';
    }

    for (let i = startPage; i <= endPage; i++) {
      const isActive = i === currentData.currentPage;
      html += `
        <button onclick="ResultTable.goToPage(${i})" 
                class="btn ${isActive ? 'btn-primary' : 'btn-outline'} btn-sm"
                style="${isActive ? 'background: #6366f1; border-color: #6366f1;' : ''}">
          ${i}
        </button>
      `;
    }

    if (endPage < totalPages) {
      if (endPage < totalPages - 1) html += '<span style="color: #9ca3af;">...</span>';
      html += `<button onclick="ResultTable.goToPage(${totalPages})" class="btn btn-outline btn-sm">${totalPages}</button>`;
    }

    // Next
    html += `
      <button onclick="ResultTable.goToPage(${Math.min(totalPages, currentData.currentPage + 1)})" 
              class="btn btn-outline btn-sm"
              ${currentData.currentPage === totalPages ? 'disabled' : ''}>
        Next →
      </button>
    `;

    html += '</div>';

    return html;
  }

  /**
   * Format cell value for display
   */
  function formatValue(value) {
    if (value === null || value === undefined) {
      return '<span style="color: #d1d5db; font-style: italic;">—</span>';
    }

    if (typeof value === 'number') {
      if (Number.isInteger(value)) {
        return value.toLocaleString();
      }
      return value.toFixed(2);
    }

    if (typeof value === 'boolean') {
      return value ? '<span style="color: #10b981; font-weight: 600;">Yes</span>' : '<span style="color: #ef4444; font-weight: 600;">No</span>';
    }

    if (typeof value === 'object') {
      return JSON.stringify(value);
    }

    const str = String(value);
    if (str.length > 80) {
      return `<span title="${str}">${str.substring(0, 80)}...</span>`;
    }

    return str;
  }

  /**
   * Toggle sort on column
   */
  function toggleSort(column) {
    // Simple sort toggle: no sort → ascending → descending → no sort
    const currentSort = currentData.config._sort;
    
    if (currentSort?.column === column) {
      if (currentSort.direction === 'asc') {
        currentData.config._sort = { column, direction: 'desc' };
      } else {
        currentData.config._sort = null;
      }
    } else {
      currentData.config._sort = { column, direction: 'asc' };
    }

    applySorting();
    render(currentData.rows, currentData.columns, currentData.config);
  }

  /**
   * Apply sorting to rows
   */
  function applySorting() {
    const sort = currentData.config._sort;
    if (!sort) return;

    currentData.rows.sort((a, b) => {
      const aVal = a[sort.column];
      const bVal = b[sort.column];

      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      let comparison = 0;
      if (typeof aVal === 'string') {
        comparison = aVal.localeCompare(bVal);
      } else if (typeof aVal === 'number') {
        comparison = aVal - bVal;
      } else {
        comparison = String(aVal).localeCompare(String(bVal));
      }

      return sort.direction === 'asc' ? comparison : -comparison;
    });
  }

  /**
   * Go to specific page
   */
  function goToPage(page) {
    currentData.currentPage = page;
    const wrapper = document.getElementById(_getWrapperId());
    if (wrapper) {
      wrapper.innerHTML = buildTableHTML();
      attachEventListeners();
    }
  }

  /**
   * Export to JSON
   */
  function exportJSON() {
    const data = {
      columns: currentData.columns,
      rows: currentData.rows,
      exported_at: new Date().toISOString(),
      total_rows: currentData.rows.length
    };

    const jsonStr = JSON.stringify(data, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `export_${Date.now()}.json`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    notify('Data exported to JSON', 'success');
  }

  /**
   * Refresh query
   */
  async function refresh() {
    try {
      showLoading();
      const response = await api('POST', '/members/dashboard-data', {
        query_config: currentData.config,
        action: 'datasource_query'
      });
      hideLoading();

      if (response.error) {
        showError(response.error);
        return;
      }

      render(response.rows, response.columns, currentData.config);
      notify('Query refreshed', 'success');
    } catch (err) {
      hideLoading();
      console.error('Refresh error:', err);
      showError('Failed to refresh query');
    }
  }

  /**
   * Export to CSV
   */
  function exportCSV() {
    const headers = currentData.columns;
    const rows = currentData.rows;

    let csv = headers.join(',') + '\n';
    rows.forEach(row => {
      const values = headers.map(col => {
        const val = row[col];
        if (val === null || val === undefined) return '';
        if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
          return `"${val.replace(/"/g, '""')}"`;
        }
        return val;
      });
      csv += values.join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `export_${Date.now()}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    notify('Data exported to CSV', 'success');
  }

  /**
   * Show empty state
   */
  function showEmpty() {
    const wrapper = document.getElementById(_getWrapperId());
    if (!wrapper) return;

    wrapper.innerHTML = `
      <div style="text-align: center; padding: 40px 20px; color: #6b7280;">
        <div style="font-size: 2em; margin-bottom: 12px;">📭</div>
        <div style="font-size: 1em; color: #1f2937; margin-bottom: 6px;">No results</div>
        <div style="font-size: 0.9em;">Your query returned no matching records. Try adjusting your filters or date range.</div>
      </div>
    `;
  }

  /**
   * Show loading state
   */
  function showLoading() {
    if (window.showLoading) window.showLoading();
  }

  /**
   * Hide loading state
   */
  function hideLoading() {
    if (window.hideLoading) window.hideLoading();
  }

  /**
   * Show error
   */
  function showError(msg) {
    notify(msg, 'error');
  }

  /**
   * Attach event listeners
   */
  function attachEventListeners() {
    document.querySelectorAll('[onclick*="ResultTable"]').forEach(el => {
      // Event listeners already inline
    });
  }

  /**
   * Show inline save bar to name and persist the current query
   */
  function promptSave() {
    const bar = document.getElementById('rt-save-bar');
    if (!bar) return;
    bar.style.display = 'flex';
    const input = document.getElementById('rt-save-name');
    if (input) {
      if (!input.value) input.value = currentData.config && currentData.config.name ? currentData.config.name : 'My Data Source';
      input.focus();
      input.select();
      input.onkeydown = function(e) { if (e.key === 'Enter') doSave(); if (e.key === 'Escape') cancelSave(); };
    }
  }

  function cancelSave() {
    const bar = document.getElementById('rt-save-bar');
    if (bar) bar.style.display = 'none';
  }

  /**
   * Persist the current query config under the given name
   */
  async function doSave() {
    const input = document.getElementById('rt-save-name');
    const name = input ? input.value.trim() : '';
    if (!name) { showError('Please enter a name'); return; }
    if (name.length > 100) { showError('Name must be 100 characters or fewer'); return; }

    // Strip internal/runtime-only fields before saving
    const configToSave = JSON.parse(JSON.stringify(currentData.config || {}));
    delete configToSave._sort;
    delete configToSave._discoveredFields;
    delete configToSave.name;

    try {
      showLoading();
      const resp = await api('PUT', '/members/dashboard-data', {
        action: 'datasource_save',
        name: name,
        query_config: configToSave
      });
      hideLoading();
      if (resp.error) { showError(resp.error); return; }
      cancelSave();
      notify('Query "' + name + '" saved', 'success');
      if (window.SavedDataSources && typeof window.SavedDataSources.render === 'function') {
        window.SavedDataSources.render();
      }
    } catch (err) {
      hideLoading();
      console.error('Save query error:', err);
      showError('Failed to save query');
    }
  }

  // Public API
  return {
    render,
    toggleSort,
    goToPage,
    refresh,
    exportCSV,
    exportJSON,
    showEmpty,
    promptSave,
    cancelSave,
    doSave
  };
})();
