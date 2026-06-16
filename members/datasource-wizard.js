/* Data Source Wizard - SlashMyBill Custom Dashboard */

// Wizard state management
var DSWizard = {
  currentStep: 1,
  config: {
    accountIds: [],
    attributes: [],
    timeframe: { preset: 'last_30d', startDate: null, endDate: null },
    filters: [],
    name: null
  },
  overlay: null,
  modal: null,
  initialized: false
};

/**
 * Initialize wizard DOM elements and attach event listeners.
 * Must be called once after page load.
 */
function initDataSourceWizard() {
  if (DSWizard.initialized) return;
  
  // Create overlay container if not exists
  var existing = document.getElementById('datasource-wizard-overlay');
  if (existing) {
    DSWizard.overlay = existing;
  } else {
    DSWizard.overlay = document.createElement('div');
    DSWizard.overlay.id = 'datasource-wizard-overlay';
    DSWizard.overlay.className = 'modal-overlay';
    DSWizard.overlay.hidden = true;
    document.body.appendChild(DSWizard.overlay);
  }
  
  DSWizard.initialized = true;
}

/**
 * Open the wizard modal and show Step 1.
 */
function openDataSourceWizard() {
  if (!DSWizard.initialized) initDataSourceWizard();
  
  // Reset state
  DSWizard.currentStep = 1;
  DSWizard.config = {
    accountIds: [],
    attributes: [],
    timeframe: { preset: 'last_30d', startDate: null, endDate: null },
    filters: [],
    name: null
  };
  
  // Render the wizard modal structure
  renderDataSourceWizard();
  DSWizard.overlay.hidden = false;
  
  // Fetch and render Step 1
  renderStep1_Accounts();
}

/**
 * Close the wizard modal.
 */
function closeDataSourceWizard() {
  DSWizard.overlay.hidden = true;
}

/**
 * Render the main wizard modal structure.
 */
function renderDataSourceWizard() {
  var html = `
    <div class="modal-card" style="max-width:600px;max-height:90vh;overflow:hidden;display:flex;flex-direction:column;">
      <div class="modal-header" style="display:flex;justify-content:space-between;align-items:center;">
        <h2 style="margin:0;">Data Source Wizard</h2>
        <button onclick="closeDataSourceWizard();" class="modal-close">&times;</button>
      </div>
      
      <!-- Progress indicator -->
      <div style="padding:12px 20px;border-bottom:1px solid #e5e7eb;display:flex;gap:8px;justify-content:center;font-size:0.85em;">
        <div class="wizard-step-indicator" data-step="1">Step 1: Accounts</div>
        <div style="color:#d1d5db;">→</div>
        <div class="wizard-step-indicator" data-step="2">Step 2: Attributes</div>
        <div style="color:#d1d5db;">→</div>
        <div class="wizard-step-indicator" data-step="3">Step 3: Timeframe</div>
        <div style="color:#d1d5db;">→</div>
        <div class="wizard-step-indicator" data-step="4">Step 4: Review</div>
      </div>
      
      <!-- Wizard content area -->
      <div id="datasource-wizard-content" style="flex:1;overflow-y:auto;padding:20px;"></div>
      
      <!-- Footer buttons -->
      <div class="modal-footer" style="border-top:1px solid #e5e7eb;">
        <button id="wizard-prev-btn" onclick="prevDataSourceStep();" class="btn btn-outline">← Back</button>
        <button id="wizard-next-btn" onclick="nextDataSourceStep();" class="btn btn-primary">Next →</button>
      </div>
    </div>
  `;
  
  DSWizard.overlay.innerHTML = html;
  updateWizardStepIndicators();
}

/**
 * Update the visual progress indicator.
 */
function updateWizardStepIndicators() {
  var indicators = document.querySelectorAll('.wizard-step-indicator');
  indicators.forEach(function(ind) {
    var step = parseInt(ind.getAttribute('data-step'));
    if (step === DSWizard.currentStep) {
      ind.style.fontWeight = '700';
      ind.style.color = '#6366f1';
    } else if (step < DSWizard.currentStep) {
      ind.style.fontWeight = '500';
      ind.style.color = '#16a34a';
    } else {
      ind.style.fontWeight = '400';
      ind.style.color = '#9ca3af';
    }
  });
  
  // Update button visibility
  var prevBtn = document.getElementById('wizard-prev-btn');
  var nextBtn = document.getElementById('wizard-next-btn');
  
  if (prevBtn) prevBtn.hidden = DSWizard.currentStep === 1;
  if (nextBtn) {
    if (DSWizard.currentStep === 4) {
      nextBtn.textContent = 'Save Data Source';
    } else {
      nextBtn.textContent = 'Next →';
    }
  }
}

/**
 * Navigate to the next step with validation.
 */
function nextDataSourceStep() {
  // Validate current step
  if (!validateDataSourceStep(DSWizard.currentStep)) return;
  
  if (DSWizard.currentStep < 4) {
    DSWizard.currentStep++;
    renderCurrentWizardStep();
  } else if (DSWizard.currentStep === 4) {
    // Save the data source
    saveDataSource();
  }
}

/**
 * Navigate to the previous step.
 */
function prevDataSourceStep() {
  if (DSWizard.currentStep > 1) {
    DSWizard.currentStep--;
    renderCurrentWizardStep();
  }
}

/**
 * Go to a specific step.
 */
function goToDataSourceStep(step) {
  if (step >= 1 && step <= 4) {
    DSWizard.currentStep = step;
    renderCurrentWizardStep();
  }
}

/**
 * Render the current step's content.
 */
function renderCurrentWizardStep() {
  updateWizardStepIndicators();
  
  switch (DSWizard.currentStep) {
    case 1:
      renderStep1_Accounts();
      break;
    case 2:
      renderStep2_Attributes();
      break;
    case 3:
      renderStep3_Timeframe();
      break;
    case 4:
      renderStep4_Review();
      break;
  }
}

/**
 * Validate data for the current step.
 */
function validateDataSourceStep(step) {
  switch (step) {
    case 1:
      if (DSWizard.config.accountIds.length === 0) {
        notify('Please select at least one account', 'error');
        return false;
      }
      return true;
    case 2:
      if (DSWizard.config.attributes.length === 0) {
        notify('Please select at least one attribute', 'error');
        return false;
      }
      return true;
    case 3:
      return true; // Timeframe always has defaults
    case 4:
      return true; // Review step doesn't need validation
    default:
      return true;
  }
}

/**
 * Step 1: Select accounts to include in the data source.
 */
async function renderStep1_Accounts() {
  var content = document.getElementById('datasource-wizard-content');
  content.innerHTML = '<div style="text-align:center;padding:40px;"><div style="font-size:0.9em;color:#6b7280;">Loading accounts...</div></div>';
  
  try {
    var data = await api('GET', '/dashboard/accounts', null);
    var accounts = data.accounts || [];
    
    var html = '<div>';
    html += '<h3 style="margin-top:0;color:#1f2937;">Select Accounts</h3>';
    html += '<p style="color:#6b7280;font-size:0.9em;">Choose which accounts\' data to include in this source.</p>';
    
    // Select All toggle
    html += '<div style="margin-bottom:16px;display:flex;align-items:center;gap:8px;">';
    html += '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-weight:500;">';
    html += '<input type="checkbox" id="wizard-account-select-all" onchange="toggleSelectAllWizardAccounts();"> Select All';
    html += '</label>';
    html += '</div>';
    
    // Account list with checkboxes
    html += '<div style="border:1px solid #e5e7eb;border-radius:6px;max-height:300px;overflow-y:auto;">';
    
    if (accounts.length === 0) {
      html += '<div style="padding:20px;text-align:center;color:#6b7280;">No accounts available</div>';
    } else {
      accounts.forEach(function(account) {
        var isSelected = DSWizard.config.accountIds.indexOf(account.accountId) >= 0;
        html += '<div style="padding:12px;border-bottom:1px solid #f3f4f6;display:flex;align-items:center;gap:12px;">';
        html += '<input type="checkbox" class="wizard-account-checkbox" value="' + esc(account.accountId) + '" ' + (isSelected ? 'checked' : '') + ' onchange="updateWizardAccountSelection();">';
        html += '<div>';
        html += '<div style="font-weight:500;color:#1f2937;">' + esc(account.accountName || account.accountId) + '</div>';
        html += '<div style="font-size:0.8em;color:#6b7280;">' + esc(account.cloudProvider) + '</div>';
        html += '</div>';
        html += '</div>';
      });
    }
    
    html += '</div>';
    html += '</div>';
    
    content.innerHTML = html;
    
    // Restore selection if already set
    document.querySelectorAll('.wizard-account-checkbox').forEach(function(cb) {
      if (DSWizard.config.accountIds.indexOf(cb.value) >= 0) {
        cb.checked = true;
      }
    });
    
  } catch (err) {
    content.innerHTML = '<div style="color:#ef4444;padding:20px;">Error loading accounts: ' + esc(err.message) + '</div>';
  }
}

/**
 * Update selected accounts from checkboxes.
 */
function updateWizardAccountSelection() {
  var checkboxes = document.querySelectorAll('.wizard-account-checkbox:checked');
  DSWizard.config.accountIds = [];
  checkboxes.forEach(function(cb) {
    DSWizard.config.accountIds.push(cb.value);
  });
}

/**
 * Toggle "Select All" for accounts.
 */
function toggleSelectAllWizardAccounts() {
  var selectAllCb = document.getElementById('wizard-account-select-all');
  var checkboxes = document.querySelectorAll('.wizard-account-checkbox');
  var shouldSelect = selectAllCb.checked;
  
  checkboxes.forEach(function(cb) {
    cb.checked = shouldSelect;
  });
  
  updateWizardAccountSelection();
}

/**
 * Step 2: Select attributes to include in results.
 */
function renderStep2_Attributes() {
  var content = document.getElementById('datasource-wizard-content');
  
  // Default attributes available
  var availableAttributes = [
    { id: 'date', label: 'Date', defaultSelected: true },
    { id: 'service', label: 'Service', defaultSelected: true },
    { id: 'cost_amount', label: 'Cost Amount', defaultSelected: true },
    { id: 'currency', label: 'Currency', defaultSelected: false },
    { id: 'tag_breakdown', label: 'Tag Breakdown', defaultSelected: false }
  ];
  
  var html = '<div>';
  html += '<h3 style="margin-top:0;color:#1f2937;">Select Attributes</h3>';
  html += '<p style="color:#6b7280;font-size:0.9em;">Choose which columns to display in results.</p>';
  html += '<div style="border:1px solid #e5e7eb;border-radius:6px;padding:12px;">';
  
  availableAttributes.forEach(function(attr) {
    var isSelected = DSWizard.config.attributes.indexOf(attr.id) >= 0;
    var shouldDefault = isSelected || (attr.defaultSelected && DSWizard.config.attributes.length === 0);
    
    html += '<div style="padding:10px 0;display:flex;align-items:center;gap:8px;">';
    html += '<input type="checkbox" class="wizard-attribute-checkbox" value="' + attr.id + '" ' + (shouldDefault ? 'checked' : '') + ' onchange="updateWizardAttributeSelection();">';
    html += '<label style="cursor:pointer;font-weight:500;flex:1;">' + attr.label + '</label>';
    html += '</div>';
  });
  
  html += '</div>';
  html += '</div>';
  
  content.innerHTML = html;
  
  // Ensure defaults are selected on first load
  if (DSWizard.config.attributes.length === 0) {
    document.querySelectorAll('.wizard-attribute-checkbox').forEach(function(cb) {
      var shouldDefault = ['date', 'service', 'cost_amount'].indexOf(cb.value) >= 0;
      cb.checked = shouldDefault;
    });
    updateWizardAttributeSelection();
  }
}

/**
 * Update selected attributes.
 */
function updateWizardAttributeSelection() {
  var checkboxes = document.querySelectorAll('.wizard-attribute-checkbox:checked');
  DSWizard.config.attributes = [];
  checkboxes.forEach(function(cb) {
    DSWizard.config.attributes.push(cb.value);
  });
}

/**
 * Step 3: Configure timeframe (preset or custom date range).
 */
function renderStep3_Timeframe() {
  var content = document.getElementById('datasource-wizard-content');
  
  var presets = [
    { id: 'last_7d', label: 'Last 7 days' },
    { id: 'last_30d', label: 'Last 30 days' },
    { id: 'last_90d', label: 'Last 90 days' },
    { id: 'current_month', label: 'Current month' },
    { id: 'previous_month', label: 'Previous month' },
    { id: 'custom', label: 'Custom date range' }
  ];
  
  var selectedPreset = DSWizard.config.timeframe.preset || 'last_30d';
  
  var html = '<div>';
  html += '<h3 style="margin-top:0;color:#1f2937;">Select Timeframe</h3>';
  html += '<p style="color:#6b7280;font-size:0.9em;">Choose the date range for data to include.</p>';
  html += '<div style="border:1px solid #e5e7eb;border-radius:6px;padding:16px;">';
  
  presets.forEach(function(preset) {
    html += '<div style="padding:8px 0;display:flex;align-items:center;gap:8px;">';
    html += '<input type="radio" name="wizard-timeframe" value="' + preset.id + '" ' + (selectedPreset === preset.id ? 'checked' : '') + ' onchange="updateWizardTimeframePreset();">';
    html += '<label style="cursor:pointer;flex:1;">' + preset.label + '</label>';
    html += '</div>';
  });
  
  html += '</div>';
  
  // Custom date range (shown if custom selected)
  var showCustom = selectedPreset === 'custom' ? '' : 'display:none;';
  html += '<div id="wizard-custom-dates" style="' + showCustom + 'margin-top:16px;border:1px solid #e5e7eb;border-radius:6px;padding:16px;">';
  html += '<div style="margin-bottom:12px;">';
  html += '<label style="display:block;margin-bottom:4px;font-weight:500;color:#374151;font-size:0.9em;">Start Date</label>';
  html += '<input type="date" id="wizard-start-date" value="' + (DSWizard.config.timeframe.startDate || '') + '" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.9em;">';
  html += '</div>';
  html += '<div>';
  html += '<label style="display:block;margin-bottom:4px;font-weight:500;color:#374151;font-size:0.9em;">End Date</label>';
  html += '<input type="date" id="wizard-end-date" value="' + (DSWizard.config.timeframe.endDate || '') + '" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;font-size:0.9em;">';
  html += '</div>';
  html += '</div>';
  
  html += '</div>';
  
  content.innerHTML = html;
  
  // Attach event listeners
  document.querySelectorAll('input[name="wizard-timeframe"]').forEach(function(radio) {
    radio.addEventListener('change', updateWizardTimeframePreset);
  });
}

/**
 * Update timeframe selection.
 */
function updateWizardTimeframePreset() {
  var selected = document.querySelector('input[name="wizard-timeframe"]:checked');
  if (selected) {
    DSWizard.config.timeframe.preset = selected.value;
    
    // Show/hide custom date inputs
    var customDiv = document.getElementById('wizard-custom-dates');
    if (selected.value === 'custom') {
      customDiv.style.display = 'block';
    } else {
      customDiv.style.display = 'none';
    }
  }
}

/**
 * Step 4: Review configuration before saving.
 */
function renderStep4_Review() {
  var content = document.getElementById('datasource-wizard-content');
  
  var timeframeLabel = 'Last 30 days';
  var presetMap = {
    'last_7d': 'Last 7 days',
    'last_30d': 'Last 30 days',
    'last_90d': 'Last 90 days',
    'current_month': 'Current month',
    'previous_month': 'Previous month',
    'custom': 'Custom range'
  };
  timeframeLabel = presetMap[DSWizard.config.timeframe.preset] || 'Last 30 days';
  
  var html = '<div>';
  html += '<h3 style="margin-top:0;color:#1f2937;">Review Configuration</h3>';
  html += '<p style="color:#6b7280;font-size:0.9em;">Review your data source setup before saving.</p>';
  
  // Summary cards
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">';
  
  html += '<div style="background:#f3f4f6;border-radius:8px;padding:12px;border:1px solid #e5e7eb;">';
  html += '<div style="font-size:0.75em;color:#6b7280;text-transform:uppercase;margin-bottom:4px;">Accounts</div>';
  html += '<div style="font-size:1.1em;font-weight:700;color:#1f2937;">' + DSWizard.config.accountIds.length + ' selected</div>';
  html += '</div>';
  
  html += '<div style="background:#f3f4f6;border-radius:8px;padding:12px;border:1px solid #e5e7eb;">';
  html += '<div style="font-size:0.75em;color:#6b7280;text-transform:uppercase;margin-bottom:4px;">Attributes</div>';
  html += '<div style="font-size:1.1em;font-weight:700;color:#1f2937;">' + DSWizard.config.attributes.length + ' columns</div>';
  html += '</div>';
  
  html += '</div>';
  
  html += '<div style="background:#f0fdf4;border-radius:8px;padding:16px;border:1px solid #bbf7d0;margin-bottom:20px;">';
  html += '<div style="margin-bottom:12px;">';
  html += '<div style="font-size:0.9em;font-weight:600;color:#166534;margin-bottom:8px;">Configuration Details</div>';
  html += '<ul style="margin:0;padding:0;list-style:none;font-size:0.9em;color:#166534;">';
  html += '<li style="padding:4px 0;">📅 Timeframe: ' + timeframeLabel + '</li>';
  html += '<li style="padding:4px 0;">🎯 Attributes: ' + DSWizard.config.attributes.join(', ') + '</li>';
  html += '<li style="padding:4px 0;">📊 Data will be queried and ready to view</li>';
  html += '</ul>';
  html += '</div>';
  html += '</div>';
  
  html += '<div>';
  html += '<label style="display:block;margin-bottom:8px;font-weight:600;color:#1f2937;">Data Source Name</label>';
  html += '<input type="text" id="wizard-datasource-name" placeholder="e.g. My Cost Analysis" value="' + (DSWizard.config.name || '') + '" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:6px;font-size:0.9em;box-sizing:border-box;">';
  html += '<div style="font-size:0.8em;color:#6b7280;margin-top:4px;">Give your data source a descriptive name</div>';
  html += '</div>';
  
  html += '</div>';
  
  content.innerHTML = html;
  
  // Focus on name input
  setTimeout(function() {
    var nameInput = document.getElementById('wizard-datasource-name');
    if (nameInput && !nameInput.value) nameInput.focus();
  }, 100);
}

/**
 * Save the data source and execute the query.
 */
async function saveDataSource() {
  var nameInput = document.getElementById('wizard-datasource-name');
  var name = (nameInput ? nameInput.value : '').trim();
  
  if (!name) {
    notify('Please enter a data source name', 'error');
    return;
  }
  
  if (name.length > 100) {
    notify('Data source name must be 100 characters or less', 'error');
    return;
  }
  
  showLoading();
  
  try {
    // Save the data source configuration
    var saveResponse = await api('PUT', '/dashboard/datasources', {
      name: name,
      accounts: DSWizard.config.accountIds,
      attributes: DSWizard.config.attributes,
      timeframe: DSWizard.config.timeframe,
      filters: DSWizard.config.filters
    });
    
    DSWizard.config.name = saveResponse.name;
    
    // Execute the query to get results
    var queryResponse = await runDataSourceQuery();
    
    hideLoading();
    closeDataSourceWizard();
    
    notify('Data source created and data loaded successfully!', 'success');
    
    // Optionally: display results in result table
    // This would be handled by result-table.js module
    
  } catch (err) {
    hideLoading();
    notify('Error saving data source: ' + (err.message || 'Unknown error'), 'error');
  }
}

/**
 * Execute a query with the current wizard configuration.
 */
async function runDataSourceQuery() {
  showLoading();
  
  try {
    var response = await api('POST', '/dashboard/datasources/query', {
      accounts: DSWizard.config.accountIds,
      attributes: DSWizard.config.attributes,
      timeframe: DSWizard.config.timeframe,
      filters: DSWizard.config.filters,
      sort: { column: 'date', order: 'desc' },
      pagination: { page: 1, pageSize: 500 }
    });
    
    hideLoading();
    return response;
    
  } catch (err) {
    hideLoading();
    notify('Error executing query: ' + (err.message || 'Unknown error'), 'error');
    throw err;
  }
}

/**
 * Add a filter row to the configuration.
 */
function addDataSourceFilter() {
  DSWizard.config.filters.push({
    attribute: '',
    operator: 'equals',
    value: ''
  });
  
  renderStep4_Filters();
}

/**
 * Remove a filter row.
 */
function removeDataSourceFilter(index) {
  DSWizard.config.filters.splice(index, 1);
  renderStep4_Filters();
}

/**
 * Update a filter value.
 */
function updateDataSourceFilter(index, field, value) {
  if (DSWizard.config.filters[index]) {
    DSWizard.config.filters[index][field] = value;
  }
}

/**
 * Helper: escape HTML special characters
 */
function esc(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
