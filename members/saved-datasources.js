/**
 * Saved Data Sources Module
 * Displays and manages saved data source configurations
 */

const SavedDataSources = (() => {
  // Determine container based on context (Observe tab or Act tab)
  let CONTAINER_ID = 'observe-saved-datasources-container';
  let RESULT_TABLE_CONTAINER_ID = 'observe-saved-datasources-result-table';
  
  // If Observe containers don't exist, fall back to Act containers
  if (!document.getElementById(CONTAINER_ID)) {
    CONTAINER_ID = 'saved-datasources-container';
    RESULT_TABLE_CONTAINER_ID = 'saved-datasources-result-table';
  }

  /**
   * Render the saved data sources panel
   */
  async function render() {
    const container = document.getElementById(CONTAINER_ID);
    if (!container) return;

    try {
      showLoading();
      const response = await api('GET', '/dashboard/datasources');
      hideLoading();

      if (response.error) {
        container.innerHTML = `
          <div style="padding: 16px; background: #fee2e2; border: 1px solid #fecaca; border-radius: 6px; color: #991b1b;">
            <strong>Error:</strong> ${response.error}
          </div>
        `;
        return;
      }

      const datasources = response.datasources || [];

      if (datasources.length === 0) {
        container.innerHTML = `
          <div style="padding: 24px; text-align: center; color: #6b7280;">
            <div style="font-size: 1.5em; margin-bottom: 8px;">📚</div>
            <div style="font-weight: 600; color: #1f2937; margin-bottom: 4px;">No saved data sources yet</div>
            <div style="font-size: 0.9em;">Create your first data source using the wizard above</div>
          </div>
        `;
        return;
      }

      let html = '<div style="margin-top: 20px;">';
      html += `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
          <h3 style="margin: 0; color: #1f2937; font-size: 1.05em;">📚 Saved Data Sources (${datasources.length})</h3>
          <button onclick="SavedDataSources.render()" class="btn btn-outline btn-sm">🔄 Refresh</button>
        </div>
      `;

      html += '<div style="display: grid; gap: 12px;">';

      datasources.forEach(ds => {
        const createdAt = new Date(ds.created_at).toLocaleDateString();
        html += `
          <div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; background: #fff; hover:shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px;">
              <div style="flex: 1;">
                <div style="font-weight: 600; color: #1f2937; font-size: 1em; margin-bottom: 4px;">${escapeHtml(ds.name)}</div>
                <div style="font-size: 0.85em; color: #6b7280;">
                  Created: <strong>${createdAt}</strong> | 
                  ID: <code style="background: #f3f4f6; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">${ds.datasource_id}</code>
                </div>
              </div>
              <div style="display: flex; gap: 8px;">
                <button onclick="SavedDataSources.runSaved('${escapeAttr(ds.datasource_id)}')" class="btn btn-primary btn-sm" style="background: #10b981; border-color: #10b981;">
                  🔍 Run
                </button>
                <button onclick="SavedDataSources.deleteSaved('${escapeAttr(ds.datasource_id)}', '${escapeAttr(ds.name)}')" class="btn btn-outline btn-sm" style="color: #ef4444; border-color: #fca5a5;">
                  🗑️
                </button>
              </div>
            </div>

            <!-- Query Config Summary -->
            <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px; font-size: 0.85em; color: #6b7280;">
              <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;">
                <div>
                  <div style="color: #9ca3af; font-size: 0.75em; text-transform: uppercase;">Accounts</div>
                  <div style="color: #1f2937; font-weight: 600;">${ds.query_config?.account_ids?.length || 0} account(s)</div>
                </div>
                <div>
                  <div style="color: #9ca3af; font-size: 0.75em; text-transform: uppercase;">Attributes</div>
                  <div style="color: #1f2937; font-weight: 600;">${ds.query_config?.attributes?.length || 0} column(s)</div>
                </div>
                <div>
                  <div style="color: #9ca3af; font-size: 0.75em; text-transform: uppercase;">Timeframe</div>
                  <div style="color: #1f2937; font-weight: 600;">${ds.query_config?.timeframe?.preset || 'unknown'}</div>
                </div>
                <div>
                  <div style="color: #9ca3af; font-size: 0.75em; text-transform: uppercase;">Filters</div>
                  <div style="color: #1f2937; font-weight: 600;">${ds.query_config?.filters?.length || 0} filter(s)</div>
                </div>
              </div>
            </div>
          </div>
        `;
      });

      html += '</div></div>';
      container.innerHTML = html;
    } catch (err) {
      hideLoading();
      console.error('Error rendering saved datasources:', err);
      container.innerHTML = `
        <div style="padding: 16px; background: #fee2e2; border: 1px solid #fecaca; border-radius: 6px; color: #991b1b;">
          <strong>Error:</strong> Failed to load saved data sources
        </div>
      `;
    }
  }

  /**
   * Run a saved data source query
   */
  async function runSaved(datasourceId) {
    try {
      showLoading();

      // First, get the saved datasource to retrieve its config
      const response = await api('GET', '/dashboard/datasources');
      if (response.error) {
        hideLoading();
        showError(response.error);
        return;
      }

      const datasources = response.datasources || [];
      const datasource = datasources.find(ds => ds.datasource_id === datasourceId);

      if (!datasource) {
        hideLoading();
        showError('Data source not found');
        return;
      }

      // Execute the query with the saved config
      const queryResponse = await api('POST', '/dashboard/datasources/query', {
        query_config: datasource.query_config
      });
      hideLoading();

      if (queryResponse.error) {
        showError(queryResponse.error);
        return;
      }

      // Render results
      ResultTable.render(
        queryResponse.rows,
        queryResponse.columns,
        datasource.query_config
      );

      notify(`Executed "${datasource.name}"`, 'success');
    } catch (err) {
      hideLoading();
      console.error('Error running saved datasource:', err);
      showError('Failed to execute saved data source');
    }
  }

  /**
   * Delete a saved data source
   */
  async function deleteSaved(datasourceId, datasourceName) {
    const confirmed = confirm(`Are you sure you want to delete "${datasourceName}"?\n\nThis cannot be undone.`);
    if (!confirmed) return;

    try {
      showLoading();
      const response = await api('DELETE', `/dashboard/datasources/${datasourceId}`);
      hideLoading();

      if (response.error) {
        showError(response.error);
        return;
      }

      notify(`Data source "${datasourceName}" deleted`, 'success');
      render(); // Refresh list
    } catch (err) {
      hideLoading();
      console.error('Error deleting datasource:', err);
      showError('Failed to delete data source');
    }
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
   * Show error message
   */
  function showError(msg) {
    notify(msg, 'error');
  }

  /**
   * Escape HTML special characters
   */
  function escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
  }

  /**
   * Escape attribute value
   */
  function escapeAttr(text) {
    return text.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // Public API
  return {
    render,
    runSaved,
    deleteSaved
  };
})();

// Render on page load (only if container exists and is visible)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    // Wait for full page to load before attempting render
    setTimeout(() => {
      const container = document.getElementById(CONTAINER_ID);
      if (container && container.offsetParent !== null) { // offsetParent === null means hidden
        SavedDataSources.render();
      }
    }, 500);
  });
} else {
  setTimeout(() => {
    const container = document.getElementById(CONTAINER_ID);
    if (container && container.offsetParent !== null) {
      SavedDataSources.render();
    }
  }, 500);
}
