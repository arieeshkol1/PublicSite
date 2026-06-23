/**
 * Saved Data Sources Module
 * Displays and manages saved data source configurations as a card grid
 */

const SavedDataSources = (() => {
  // Container IDs - resolved at render time, not at load time
  function _getContainerId() {
    if (document.getElementById('observe-saved-datasources-container')) {
      return 'observe-saved-datasources-container';
    }
    return 'saved-datasources-container';
  }

  function _getResultTableId() {
    if (document.getElementById('observe-saved-datasources-result-table')) {
      return 'observe-saved-datasources-result-table';
    }
    return 'saved-datasources-result-table';
  }

  /**
   * Determine a contextual icon based on query_config attributes
   */
  function getIconForConfig(config) {
    if (!config || !config.attributes) return '📋';
    var attrs = config.attributes;
    for (var i = 0; i < attrs.length; i++) {
      if (attrs[i] === 'cost_amount' || attrs[i] === 'cost' || attrs[i].indexOf('cost') !== -1) {
        return '💰';
      }
    }
    for (var j = 0; j < attrs.length; j++) {
      if (attrs[j] === 'usage_amount' || attrs[j] === 'usage' || attrs[j].indexOf('usage') !== -1) {
        return '📊';
      }
    }
    return '📋';
  }

  /**
   * Build a single card DOM element for a datasource
   */
  function buildCard(ds) {
    var card = document.createElement('div');
    card.className = 'ds-card';
    card.setAttribute('data-datasource-id', ds.datasource_id);
    card.innerHTML =
      '<div class="ds-card-header">' +
        '<span class="ds-card-icon">' + getIconForConfig(ds.query_config) + '</span>' +
        '<span class="ds-card-name">' + escapeHtml(ds.name) + '</span>' +
      '</div>' +
      '<div class="ds-card-actions">' +
        '<button class="ds-action-edit" title="Edit">✏️</button>' +
        '<button class="ds-action-run" title="Run">▶️</button>' +
        '<button class="ds-action-delete" title="Delete">🗑️</button>' +
        '<span class="ds-action-slot-chart">' +
          '<button class="ds-action-chart" title="Build chart">📈</button>' +
        '</span>' +
      '</div>';

    // Wire action handlers
    card.querySelector('.ds-action-edit').onclick = function() { editSaved(ds); };
    card.querySelector('.ds-action-run').onclick = function() { runSaved(ds.datasource_id); };
    card.querySelector('.ds-action-delete').onclick = function() { deleteSaved(ds.datasource_id, ds.name); };
    var chartBtn = card.querySelector('.ds-action-chart');
    if (chartBtn) {
      chartBtn.onclick = function() {
        if (window.ChartWizard) ChartWizard.openForDatasource(ds.datasource_id, ds.name);
      };
    }

    // Touch support: toggle active class
    card.addEventListener('touchstart', function() { card.classList.toggle('ds-card-active'); });

    return card;
  }

  /**
   * Render the saved data sources panel as a card grid
   */
  async function render() {
    var CONTAINER_ID = _getContainerId();
    var container = document.getElementById(CONTAINER_ID);
    if (!container) return;

    try {
      showLoading();
      var response = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      hideLoading();

      if (response.error) {
        container.innerHTML =
          '<div style="padding: 16px; background: #fee2e2; border: 1px solid #fecaca; border-radius: 6px; color: #991b1b;">' +
            '<strong>Error:</strong> ' + esc(response.error) +
          '</div>';
        return;
      }

      var datasources = response.datasources || [];

      if (datasources.length === 0) {
        container.innerHTML =
          '<div style="padding: 24px; text-align: center; color: #6b7280;">' +
            '<div style="font-size: 1.5em; margin-bottom: 8px;">📚</div>' +
            '<div style="font-weight: 600; color: #1f2937; margin-bottom: 4px;">No saved data sources yet</div>' +
            '<div style="font-size: 0.9em;">Create your first data source using the wizard above</div>' +
          '</div>';
        return;
      }

      var grid = document.createElement('div');
      grid.className = 'ds-card-grid';
      datasources.forEach(function(ds) {
        grid.appendChild(buildCard(ds));
      });

      container.innerHTML = '';
      container.appendChild(grid);
    } catch (err) {
      hideLoading();
      console.error('Error rendering saved datasources:', err);
      var CONTAINER_ID2 = _getContainerId();
      var container2 = document.getElementById(CONTAINER_ID2);
      if (container2) {
        container2.innerHTML = '';
      }
    }
  }

  /**
   * Edit a saved data source – opens wizard pre-filled
   */
  function editSaved(ds) {
    DataSourceWizard.openWithConfig(ds.datasource_id, ds.query_config, ds.name);
  }

  /**
   * Run a saved data source query
   */
  async function runSaved(datasourceId) {
    try {
      showLoading();

      // First, get the saved datasource to retrieve its config
      var response = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      if (response.error) {
        hideLoading();
        showError(response.error);
        return;
      }

      var datasources = response.datasources || [];
      var datasource = datasources.find(function(ds) { return ds.datasource_id === datasourceId; });

      if (!datasource) {
        hideLoading();
        showError('Data source not found');
        return;
      }

      // Execute the query with the saved config
      var queryResponse = await api('POST', '/members/dashboard-data', {
        action: 'datasource_query',
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

      notify('Executed "' + datasource.name + '"', 'success');
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
    var confirmed = confirm('Are you sure you want to delete "' + datasourceName + '"?\n\nThis cannot be undone.');
    if (!confirmed) return;

    try {
      showLoading();
      var response = await api('POST', '/members/dashboard-data', {
        action: 'datasource_delete',
        datasource_id: datasourceId
      });
      hideLoading();

      if (response.error) {
        showError(response.error);
        return;
      }

      notify('Data source "' + datasourceName + '" deleted', 'success');
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
    var map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
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
    deleteSaved,
    editSaved
  };
})();

// Expose on window so other modules (e.g. datasource-wizard.js) and the
// Observe section switcher can call SavedDataSources.render() after save.
window.SavedDataSources = SavedDataSources;

// Render on page load (only if container exists and is visible)
// Note: Don't auto-render on page load - let _switchObserveSection() call render() when needed
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() {
    // Defer initialization until page is fully loaded
    // render() will be called explicitly by _switchObserveSection() in members.js
  });
}
