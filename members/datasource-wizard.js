/**
 * Data Source Wizard Module
 * Multi-step wizard for building custom data views from Cost_Cache_Table
 * Steps: 1) Select Accounts, 2) Choose Attributes, 3) Set Timeframe, 4) Add Filters
 */

const DataSourceWizard = (() => {
  // State
  let currentStep = 1;
  let wizardConfig = {
    account_ids: [],
    attributes: [],
    timeframe: {
      preset: 'last_30d',
      start_date: null,
      end_date: null
    },
    filters: []
  };

  const ATTRIBUTES = [
    { name: 'date', label: 'Date', type: 'date', checked: true },
    { name: 'service', label: 'Service', type: 'string', checked: true },
    { name: 'cost_amount', label: 'Cost Amount', type: 'number', checked: true },
    { name: 'usage_amount', label: 'Usage Amount', type: 'number', checked: false },
    { name: 'region', label: 'Region', type: 'string', checked: false },
    { name: 'account_id', label: 'Account ID', type: 'string', checked: false },
    { name: 'resource_id', label: 'Resource ID', type: 'string', checked: false },
    { name: 'tags', label: 'Tags', type: 'string', checked: false }
  ];

  const TIMEFRAME_PRESETS = [
    { value: 'last_7d', label: 'Last 7 days' },
    { value: 'last_30d', label: 'Last 30 days' },
    { value: 'last_90d', label: 'Last 90 days' },
    { value: 'current_month', label: 'Current month' },
    { value: 'previous_month', label: 'Previous month' },
    { value: 'custom', label: 'Custom date range' }
  ];

  const OPERATORS = {
    string: ['equals', 'not_equals', 'contains'],
    number: ['equals', 'not_equals', 'greater_than', 'less_than'],
    date: ['equals', 'greater_than', 'less_than']
  };

  // Initialize wizard
  function init() {
    const overlay = document.getElementById('datasource-wizard-overlay');
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
      });
    }
  }

  // Open wizard
  function open() {
    const overlay = document.getElementById('datasource-wizard-overlay');
    if (overlay) {
      overlay.hidden = false;
      currentStep = 1;
      wizardConfig = {
        account_ids: [],
        attributes: [],
        timeframe: { preset: 'last_30d', start_date: null, end_date: null },
        filters: []
      };
      renderStep();
    }
  }

  // Close wizard
  function close() {
    const overlay = document.getElementById('datasource-wizard-overlay');
    if (overlay) {
      overlay.hidden = true;
    }
  }

  // Render current step
  function renderStep() {
    const body = document.getElementById('wizard-body');
    if (!body) return;

    body.innerHTML = '';

    let content = '';
    let stepTitle = '';

    switch (currentStep) {
      case 1:
        stepTitle = 'Step 1: Select Accounts';
        content = renderStep1();
        break;
      case 2:
        stepTitle = 'Step 2: Choose Attributes';
        content = renderStep2();
        break;
      case 3:
        stepTitle = 'Step 3: Set Timeframe';
        content = renderStep3();
        break;
      case 4:
        stepTitle = 'Step 4: Add Filters (Optional)';
        content = renderStep4();
        break;
    }

    // Insert step content with title and buttons
    body.innerHTML = `
      <div style="margin-bottom: 20px;">
        <h3 style="margin: 0 0 16px 0; color: #1f2937; font-size: 1.1em;">${stepTitle}</h3>
        ${content}
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 20px; padding-top: 16px; border-top: 1px solid #e5e7eb;">
        <button onclick="DataSourceWizard.prevStep()" class="btn btn-outline" ${currentStep === 1 ? 'disabled' : ''}>← Back</button>
        ${currentStep === 4 ? `
          <button onclick="DataSourceWizard.runQuery()" class="btn btn-primary" style="background: #10b981; border-color: #10b981;">🔍 Run Query</button>
          <button onclick="DataSourceWizard.saveDataSource()" class="btn btn-primary" style="background: #8b5cf6; border-color: #8b5cf6;">💾 Save & Run</button>
        ` : `
          <button onclick="DataSourceWizard.nextStep()" class="btn btn-primary">Next →</button>
        `}
      </div>
    `;

    // Reattach event listeners
    attachStepListeners();
  }

  // Step 1: Select Accounts
  function renderStep1() {
    let html = '<div style="margin-bottom: 16px;">';
    html += '<p style="color: #6b7280; font-size: 0.9em; margin-bottom: 12px;">Select which accounts to query:</p>';
    html += '<div id="account-list" style="max-height: 300px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 6px; padding: 12px;"></div>';
    html += '</div>';
    
    // Fetch and render accounts after setTimeout to allow DOM to attach
    setTimeout(() => {
      fetchAndRenderAccounts();
    }, 0);

    return html;
  }

  // Fetch accounts from API
  async function fetchAndRenderAccounts() {
    try {
      showLoading();

      // Call the member-handler API to get connected accounts
      const res = await api('GET', '/members/accounts');
      if (res.error) {
        showError(res.error);
        return;
      }

      const accounts = res.accounts || [];
      const container = document.getElementById('account-list');
      if (!container) return;

      if (accounts.length === 0) {
        container.innerHTML = '<div style="padding: 16px; color: #6b7280; text-align: center;">No connected accounts found</div>';
        hideLoading();
        return;
      }

      let html = '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #e5e7eb;">';
      html += '<label style="font-weight: 600; color: #374151; font-size: 0.9em;">Select All</label>';
      html += '<input type="checkbox" id="account-select-all" style="cursor: pointer;"/>';
      html += '</div>';

      accounts.forEach(acc => {
        const accId = acc.accountId || acc.account_id || '';
        const accName = acc.accountName || acc.account_name || accId;
        const accProvider = acc.cloudProvider || acc.cloud_provider || 'aws';
        const isChecked = wizardConfig.account_ids.includes(accId);
        html += `
          <div style="display: flex; align-items: center; gap: 12px; padding: 8px; border-radius: 6px; background: #f9fafb; margin-bottom: 8px;">
            <input type="checkbox" class="account-checkbox" value="${accId}" ${isChecked ? 'checked' : ''} style="cursor: pointer;"/>
            <div style="flex: 1;">
              <div style="font-weight: 600; color: #1f2937; font-size: 0.9em;">${accName}</div>
              <div style="color: #6b7280; font-size: 0.8em;">${accId} • ${accProvider}</div>
            </div>
          </div>
        `;
      });

      container.innerHTML = html;
      
      // Wire up select all
      const selectAllCheckbox = document.getElementById('account-select-all');
      if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', (e) => {
          document.querySelectorAll('.account-checkbox').forEach(cb => {
            cb.checked = e.target.checked;
          });
          updateWizardState();
        });
      }

      hideLoading();
    } catch (err) {
      console.error('Error fetching accounts:', err);
      showError('Failed to load accounts');
      hideLoading();
    }
  }

  // Step 2: Choose Attributes
  function renderStep2() {
    let html = '<div style="margin-bottom: 16px;">';
    html += '<p style="color: #6b7280; font-size: 0.9em; margin-bottom: 12px;">Select columns to include in your results:</p>';
    html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;">';

    ATTRIBUTES.forEach(attr => {
      const isChecked = wizardConfig.attributes.length === 0 ? attr.checked : wizardConfig.attributes.includes(attr.name);
      html += `
        <label style="display: flex; align-items: center; gap: 8px; padding: 12px; border: 1px solid #e5e7eb; border-radius: 6px; cursor: pointer; background: ${isChecked ? '#eef2ff' : '#fff'};">
          <input type="checkbox" class="attribute-checkbox" value="${attr.name}" ${isChecked ? 'checked' : ''} style="cursor: pointer;"/>
          <div>
            <div style="font-weight: 600; color: #1f2937; font-size: 0.9em;">${attr.label}</div>
            <div style="color: #6b7280; font-size: 0.75em;">${attr.type}</div>
          </div>
        </label>
      `;
    });

    html += '</div></div>';
    return html;
  }

  // Step 3: Set Timeframe
  function renderStep3() {
    let html = '<div style="margin-bottom: 16px;">';
    html += '<p style="color: #6b7280; font-size: 0.9em; margin-bottom: 12px;">Select a timeframe:</p>';
    html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; margin-bottom: 16px;">';

    TIMEFRAME_PRESETS.forEach(preset => {
      const isSelected = wizardConfig.timeframe.preset === preset.value;
      html += `
        <label style="display: flex; align-items: center; gap: 8px; padding: 12px; border: 2px solid ${isSelected ? '#6366f1' : '#e5e7eb'}; border-radius: 6px; cursor: pointer; background: ${isSelected ? '#eef2ff' : '#fff'};">
          <input type="radio" name="timeframe" value="${preset.value}" ${isSelected ? 'checked' : ''} style="cursor: pointer;"/>
          <span style="font-weight: 600; color: #1f2937; font-size: 0.9em;">${preset.label}</span>
        </label>
      `;
    });

    html += '</div>';

    // Custom date range (hidden by default)
    html += `<div id="custom-date-range" style="display: ${wizardConfig.timeframe.preset === 'custom' ? 'block' : 'none'}; padding: 12px; background: #f3f4f6; border-radius: 6px; margin-top: 12px;">`;
    html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">';
    html += '<div>';
    html += '<label style="font-size: 0.9em; color: #374151; display: block; margin-bottom: 4px;">Start Date</label>';
    html += `<input type="date" id="custom-start-date" style="width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.9em;" value="${wizardConfig.timeframe.start_date || ''}"/>`;
    html += '</div>';
    html += '<div>';
    html += '<label style="font-size: 0.9em; color: #374151; display: block; margin-bottom: 4px;">End Date</label>';
    html += `<input type="date" id="custom-end-date" style="width: 100%; padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.9em;" value="${wizardConfig.timeframe.end_date || ''}"/>`;
    html += '</div>';
    html += '</div></div>';

    html += '</div>';
    return html;
  }

  // Step 4: Add Filters
  function renderStep4() {
    let html = '<div style="margin-bottom: 16px;">';
    html += '<p style="color: #6b7280; font-size: 0.9em; margin-bottom: 12px;">Add filters to narrow your results (optional):</p>';
    html += '<div id="filters-list" style="margin-bottom: 12px;"></div>';
    html += '<button onclick="DataSourceWizard.addFilter()" class="btn btn-outline btn-sm" style="width: 100%; margin-bottom: 12px;">+ Add Filter</button>';
    html += '</div>';

    // Render existing filters
    setTimeout(() => {
      renderFilters();
    }, 0);

    return html;
  }

  // Render filters list
  function renderFilters() {
    const container = document.getElementById('filters-list');
    if (!container) return;

    if (wizardConfig.filters.length === 0) {
      container.innerHTML = '<div style="padding: 16px; text-align: center; color: #6b7280; font-size: 0.9em;">No filters added yet</div>';
      return;
    }

    let html = '';
    wizardConfig.filters.forEach((filter, idx) => {
      const attribute = ATTRIBUTES.find(a => a.name === filter.attribute);
      const attributeType = attribute ? attribute.type : 'string';
      const operators = OPERATORS[attributeType] || OPERATORS.string;

      html += `
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 8px; margin-bottom: 8px; padding: 12px; background: #f9fafb; border-radius: 6px;">
          <select class="filter-attr" data-idx="${idx}" style="padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.9em;">
            ${ATTRIBUTES.filter(a => a.name !== 'date').map(a => `<option value="${a.name}" ${a.name === filter.attribute ? 'selected' : ''}>${a.label}</option>`).join('')}
          </select>
          <select class="filter-op" data-idx="${idx}" style="padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.9em;">
            ${operators.map(op => `<option value="${op}" ${op === filter.operator ? 'selected' : ''}>${op}</option>`).join('')}
          </select>
          <input type="text" class="filter-val" data-idx="${idx}" placeholder="Value" value="${filter.value}" style="padding: 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 0.9em;"/>
          <button onclick="DataSourceWizard.removeFilter(${idx})" class="btn btn-outline btn-sm" style="padding: 6px 10px;">✕</button>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  // Add filter
  function addFilter() {
    wizardConfig.filters.push({
      attribute: 'service',
      operator: 'equals',
      value: ''
    });
    renderFilters();
  }

  // Remove filter
  function removeFilter(idx) {
    wizardConfig.filters.splice(idx, 1);
    renderFilters();
  }

  // Attach event listeners for current step
  function attachStepListeners() {
    // Step 1: Account selection
    document.querySelectorAll('.account-checkbox').forEach(cb => {
      cb.addEventListener('change', updateWizardState);
    });

    // Step 2: Attribute selection
    document.querySelectorAll('.attribute-checkbox').forEach(cb => {
      cb.addEventListener('change', updateWizardState);
    });

    // Step 3: Timeframe selection
    document.querySelectorAll('input[name="timeframe"]').forEach(rb => {
      rb.addEventListener('change', (e) => {
        wizardConfig.timeframe.preset = e.target.value;
        const customRange = document.getElementById('custom-date-range');
        if (customRange) {
          customRange.style.display = e.target.value === 'custom' ? 'block' : 'none';
        }
      });
    });

    document.getElementById('custom-start-date')?.addEventListener('change', (e) => {
      wizardConfig.timeframe.start_date = e.target.value;
    });

    document.getElementById('custom-end-date')?.addEventListener('change', (e) => {
      wizardConfig.timeframe.end_date = e.target.value;
    });

    // Step 4: Filter updates
    document.querySelectorAll('.filter-attr').forEach(sel => {
      sel.addEventListener('change', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        wizardConfig.filters[idx].attribute = e.target.value;
      });
    });

    document.querySelectorAll('.filter-op').forEach(sel => {
      sel.addEventListener('change', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        wizardConfig.filters[idx].operator = e.target.value;
      });
    });

    document.querySelectorAll('.filter-val').forEach(inp => {
      inp.addEventListener('change', (e) => {
        const idx = parseInt(e.target.dataset.idx);
        wizardConfig.filters[idx].value = e.target.value;
      });
    });
  }

  // Update wizard state from form inputs
  function updateWizardState() {
    // Update selected accounts
    wizardConfig.account_ids = Array.from(document.querySelectorAll('.account-checkbox:checked')).map(cb => cb.value);

    // Update selected attributes (default to pre-checked if none selected)
    wizardConfig.attributes = Array.from(document.querySelectorAll('.attribute-checkbox:checked')).map(cb => cb.value);
    if (wizardConfig.attributes.length === 0) {
      wizardConfig.attributes = ATTRIBUTES.filter(a => a.checked).map(a => a.name);
    }
  }

  // Validate current step
  function validateStep() {
    if (currentStep === 1) {
      if (wizardConfig.account_ids.length === 0) {
        showError('Please select at least one account');
        return false;
      }
    } else if (currentStep === 2) {
      if (wizardConfig.attributes.length === 0) {
        showError('Please select at least one attribute');
        return false;
      }
    } else if (currentStep === 3) {
      if (wizardConfig.timeframe.preset === 'custom') {
        if (!wizardConfig.timeframe.start_date || !wizardConfig.timeframe.end_date) {
          showError('Please enter start and end dates for custom range');
          return false;
        }
      }
    }
    return true;
  }

  // Next step
  function nextStep() {
    updateWizardState();
    if (!validateStep()) return;
    if (currentStep < 4) {
      currentStep++;
      renderStep();
    }
  }

  // Previous step
  function prevStep() {
    if (currentStep > 1) {
      currentStep--;
      renderStep();
    }
  }

  // Run query
  async function runQuery() {
    updateWizardState();
    if (wizardConfig.account_ids.length === 0) {
      showError('Please select at least one account');
      return;
    }
    if (wizardConfig.attributes.length === 0) {
      showError('Please select at least one attribute');
      return;
    }

    try {
      showLoading();
      const response = await api('POST', '/dashboard/datasources/query', { query_config: wizardConfig });
      hideLoading();

      if (response.error) {
        showError(response.error);
        return;
      }

      // Show results in table
      close();
      ResultTable.render(response.rows, response.columns, wizardConfig);
      notify('Query executed successfully', 'success');
    } catch (err) {
      hideLoading();
      console.error('Query error:', err);
      showError('Failed to execute query');
    }
  }

  // Save data source
  async function saveDataSource() {
    updateWizardState();
    if (wizardConfig.account_ids.length === 0) {
      showError('Please select at least one account');
      return;
    }

    const name = prompt('Enter a name for this data source:', 'My Data Source');
    if (!name) return;

    if (name.length < 1 || name.length > 100) {
      showError('Name must be between 1 and 100 characters');
      return;
    }

    try {
      showLoading();
      const saveResponse = await api('PUT', '/dashboard/datasources', {
        name: name,
        query_config: wizardConfig
      });
      hideLoading();

      if (saveResponse.error) {
        showError(saveResponse.error);
        return;
      }

      notify(`Data source "${name}" saved successfully`, 'success');

      // Run the query
      const response = await api('POST', '/dashboard/datasources/query', { query_config: wizardConfig });
      
      if (response.error) {
        showError(response.error);
        return;
      }

      // Show results
      close();
      ResultTable.render(response.rows, response.columns, wizardConfig);
      
      // Refresh saved datasources list
      if (window.SavedDataSources) {
        SavedDataSources.render();
      }
    } catch (err) {
      hideLoading();
      console.error('Save error:', err);
      showError('Failed to save data source');
    }
  }

  // Utility functions
  function showError(msg) {
    notify(msg, 'error');
  }

  function showLoading() {
    if (window.showLoading) window.showLoading();
  }

  function hideLoading() {
    if (window.hideLoading) window.hideLoading();
  }

  // Public API
  return {
    init,
    open,
    close,
    nextStep,
    prevStep,
    addFilter,
    removeFilter,
    runQuery,
    saveDataSource
  };
})();

// Initialize immediately — script loads after DOM is ready (at bottom of body)
DataSourceWizard.init();
