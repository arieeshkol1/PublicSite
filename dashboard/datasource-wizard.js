/**
 * Data Source Wizard Module
 * Multi-step wizard for building tabular data views from Cost_Cache_Table.
 * Steps: 1) Select Accounts → 2) Choose Attributes → 3) Set Timeframe → 4) Add Filters
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 2.1-2.7, 3.1-3.6, 4.1-4.6, 5.1-5.8, 7.1-7.7
 */

const DataSourceWizard = (() => {
    // Available attributes for data source queries
    const AVAILABLE_ATTRIBUTES = [
        { id: 'date', label: 'Date', type: 'text' },
        { id: 'account_id', label: 'Account ID', type: 'text' },
        { id: 'service', label: 'Service', type: 'text' },
        { id: 'cost_amount', label: 'Cost Amount', type: 'numeric' },
        { id: 'currency', label: 'Currency', type: 'text' },
        { id: 'cloud_provider', label: 'Cloud Provider', type: 'text' }
    ];

    // Default selected attributes
    const DEFAULT_SELECTED_ATTRIBUTES = ['date', 'service', 'cost_amount'];

    // Filter operators by attribute type
    const FILTER_OPERATORS = {
        text: [
            { id: 'equals', label: 'Equals' },
            { id: 'not_equals', label: 'Not Equals' }
        ],
        numeric: [
            { id: 'equals', label: 'Equals' },
            { id: 'not_equals', label: 'Not Equals' },
            { id: 'greater_than', label: 'Greater Than' },
            { id: 'less_than', label: 'Less Than' }
        ]
    };

    // Timeframe presets
    const TIMEFRAME_PRESETS = [
        { id: 'last_7d', label: 'Last 7 days' },
        { id: 'last_30d', label: 'Last 30 days' },
        { id: 'last_90d', label: 'Last 90 days' },
        { id: 'current_month', label: 'Current month' },
        { id: 'previous_month', label: 'Previous month' }
    ];

    const DEFAULT_TIMEFRAME = 'last_30d';
    const TOTAL_STEPS = 4;

    // --- Wizard State ---
    let currentStep = 1;
    let wizardConfig = {
        accounts: [],       // Selected account IDs
        attributes: [...DEFAULT_SELECTED_ATTRIBUTES],
        timeframe: {
            type: 'preset',
            preset: DEFAULT_TIMEFRAME,
            startDate: '',
            endDate: ''
        },
        filters: []         // Array of {attribute, operator, value}
    };
    let accountsList = [];  // All available accounts from API
    let isLoading = false;
    let errorMessage = '';

    // --- Open / Close ---

    function open() {
        resetState();
        const overlay = document.getElementById('datasource-wizard-overlay');
        if (overlay) {
            overlay.hidden = false;
            overlay.style.display = 'flex';
        }
        renderWizard();
        // Fetch accounts immediately for Step 1
        fetchAccounts();
    }

    function close() {
        const overlay = document.getElementById('datasource-wizard-overlay');
        if (overlay) {
            overlay.hidden = true;
            overlay.style.display = 'none';
        }
        resetState();
    }

    function resetState() {
        currentStep = 1;
        wizardConfig = {
            accounts: [],
            attributes: [...DEFAULT_SELECTED_ATTRIBUTES],
            timeframe: {
                type: 'preset',
                preset: DEFAULT_TIMEFRAME,
                startDate: '',
                endDate: ''
            },
            filters: []
        };
        accountsList = [];
        isLoading = false;
        errorMessage = '';
    }

    // --- Rendering ---

    function renderWizard() {
        const overlay = document.getElementById('datasource-wizard-overlay');
        if (!overlay) return;

        let html = '<div class="wizard-panel" role="dialog" aria-label="Data Source Wizard">';
        html += renderHeader();
        html += renderProgressBar();
        html += '<div class="wizard-body">';

        if (isLoading) {
            html += renderLoading();
        } else if (errorMessage) {
            html += renderError();
        } else {
            switch (currentStep) {
                case 1: html += renderStep1_Accounts(); break;
                case 2: html += renderStep2_Attributes(); break;
                case 3: html += renderStep3_Timeframe(); break;
                case 4: html += renderStep4_Filters(); break;
            }
        }

        html += '</div>';
        html += renderFooter();
        html += '</div>';

        overlay.innerHTML = html;
        wireEvents();
    }

    function renderHeader() {
        return `<div class="wizard-header">
            <h3 class="wizard-title">New Data Source</h3>
            <button class="wizard-close-btn" id="wizard-close-btn" aria-label="Close wizard">&times;</button>
        </div>`;
    }

    function renderProgressBar() {
        const stepLabels = ['Accounts', 'Attributes', 'Timeframe', 'Filters'];
        let html = '<div class="wizard-progress">';
        for (let i = 1; i <= TOTAL_STEPS; i++) {
            const state = i < currentStep ? 'completed' : (i === currentStep ? 'active' : '');
            html += `<div class="wizard-step-indicator ${state}">
                <span class="step-number">${i}</span>
                <span class="step-label">${stepLabels[i - 1]}</span>
            </div>`;
            if (i < TOTAL_STEPS) {
                html += '<div class="step-connector ' + (i < currentStep ? 'completed' : '') + '"></div>';
            }
        }
        html += '</div>';
        return html;
    }

    function renderLoading() {
        return '<div class="wizard-loading"><div class="spinner"></div><p>Loading...</p></div>';
    }

    function renderError() {
        return `<div class="wizard-error">
            <p class="error-text">${escapeHtml(errorMessage)}</p>
            <button class="btn btn-outline btn-sm" id="wizard-retry-btn">Retry</button>
        </div>`;
    }

    // --- Step 1: Accounts ---

    function renderStep1_Accounts() {
        let html = '<div class="wizard-step" data-step="1">';
        html += '<h4 class="step-title">Select Accounts</h4>';
        html += '<p class="step-description">Choose which accounts to include in this data source query.</p>';

        if (accountsList.length === 0) {
            html += '<p class="wizard-empty">No connected accounts found.</p>';
            html += '</div>';
            return html;
        }

        // Select All toggle
        const allSelected = wizardConfig.accounts.length === accountsList.length && accountsList.length > 0;
        html += `<label class="wizard-checkbox select-all-toggle">
            <input type="checkbox" id="wizard-select-all" ${allSelected ? 'checked' : ''}>
            <span>Select All (${accountsList.length} accounts)</span>
        </label>`;

        // Account list
        html += '<div class="wizard-account-list">';
        accountsList.forEach(account => {
            const checked = wizardConfig.accounts.includes(account.account_id) ? 'checked' : '';
            const providerIcon = getProviderIcon(account.cloud_provider);
            html += `<label class="wizard-checkbox account-item">
                <input type="checkbox" class="account-cb" value="${escapeHtml(account.account_id)}" ${checked}>
                <span class="account-info">
                    <span class="account-icon">${providerIcon}</span>
                    <span class="account-name">${escapeHtml(account.account_name || account.account_id)}</span>
                    <span class="account-provider">${escapeHtml(account.cloud_provider || '')}</span>
                </span>
            </label>`;
        });
        html += '</div>';
        html += '</div>';
        return html;
    }

    // --- Step 2: Attributes ---

    function renderStep2_Attributes() {
        let html = '<div class="wizard-step" data-step="2">';
        html += '<h4 class="step-title">Select Attributes</h4>';
        html += '<p class="step-description">Choose which data columns to include in the results.</p>';

        html += '<div class="wizard-attribute-list">';
        AVAILABLE_ATTRIBUTES.forEach(attr => {
            const checked = wizardConfig.attributes.includes(attr.id) ? 'checked' : '';
            html += `<label class="wizard-checkbox attribute-item">
                <input type="checkbox" class="attribute-cb" value="${attr.id}" ${checked}>
                <span class="attribute-info">
                    <span class="attribute-name">${escapeHtml(attr.label)}</span>
                    <span class="attribute-type">${attr.type}</span>
                </span>
            </label>`;
        });
        html += '</div>';
        html += '</div>';
        return html;
    }

    // --- Step 3: Timeframe ---

    function renderStep3_Timeframe() {
        let html = '<div class="wizard-step" data-step="3">';
        html += '<h4 class="step-title">Set Timeframe</h4>';
        html += '<p class="step-description">Define the date range for your data query.</p>';

        // Preset radio buttons
        html += '<div class="wizard-timeframe-presets">';
        TIMEFRAME_PRESETS.forEach(preset => {
            const checked = wizardConfig.timeframe.type === 'preset' && wizardConfig.timeframe.preset === preset.id ? 'checked' : '';
            html += `<label class="wizard-radio">
                <input type="radio" name="timeframe-preset" value="${preset.id}" ${checked} class="timeframe-radio">
                <span>${escapeHtml(preset.label)}</span>
            </label>`;
        });

        // Custom date range option
        const customChecked = wizardConfig.timeframe.type === 'custom' ? 'checked' : '';
        html += `<label class="wizard-radio">
            <input type="radio" name="timeframe-preset" value="custom" ${customChecked} class="timeframe-radio">
            <span>Custom range</span>
        </label>`;
        html += '</div>';

        // Custom date range pickers (shown when custom is selected)
        const customDisplay = wizardConfig.timeframe.type === 'custom' ? 'block' : 'none';
        html += `<div class="wizard-custom-dates" id="wizard-custom-dates" style="display:${customDisplay};">
            <div class="date-picker-group">
                <label for="wizard-start-date">Start Date</label>
                <input type="date" id="wizard-start-date" class="config-input" value="${wizardConfig.timeframe.startDate || ''}">
            </div>
            <div class="date-picker-group">
                <label for="wizard-end-date">End Date</label>
                <input type="date" id="wizard-end-date" class="config-input" value="${wizardConfig.timeframe.endDate || ''}">
            </div>
        </div>`;

        html += '</div>';
        return html;
    }

    // --- Step 4: Filters ---

    function renderStep4_Filters() {
        let html = '<div class="wizard-step" data-step="4">';
        html += '<h4 class="step-title">Add Filters</h4>';
        html += '<p class="step-description">Optionally add filters to narrow your data. Filters are applied server-side.</p>';

        // Filter rows
        html += '<div class="wizard-filter-list" id="wizard-filter-list">';
        wizardConfig.filters.forEach((filter, index) => {
            html += renderFilterRow(filter, index);
        });
        html += '</div>';

        // Add Filter button
        html += '<button class="btn btn-outline btn-sm" id="wizard-add-filter-btn">+ Add Filter</button>';

        html += '</div>';
        return html;
    }

    function renderFilterRow(filter, index) {
        // Build attribute select
        let attrOptions = '<option value="">Select attribute</option>';
        AVAILABLE_ATTRIBUTES.forEach(attr => {
            const selected = filter.attribute === attr.id ? 'selected' : '';
            attrOptions += `<option value="${attr.id}" ${selected}>${escapeHtml(attr.label)}</option>`;
        });

        // Build operator select based on attribute type
        const attrType = getAttributeType(filter.attribute);
        const operators = FILTER_OPERATORS[attrType] || FILTER_OPERATORS.text;
        let opOptions = '';
        operators.forEach(op => {
            const selected = filter.operator === op.id ? 'selected' : '';
            opOptions += `<option value="${op.id}" ${selected}>${escapeHtml(op.label)}</option>`;
        });

        return `<div class="wizard-filter-row" data-index="${index}">
            <select class="config-select filter-attr" data-index="${index}">${attrOptions}</select>
            <select class="config-select filter-op" data-index="${index}">${opOptions}</select>
            <input type="text" class="config-input filter-value" data-index="${index}" placeholder="Value" value="${escapeHtml(filter.value || '')}">
            <button class="btn-icon filter-remove-btn" data-index="${index}" aria-label="Remove filter">&times;</button>
        </div>`;
    }

    // --- Footer Navigation ---

    function renderFooter() {
        let html = '<div class="wizard-footer">';

        // Back button (hidden on step 1)
        if (currentStep > 1) {
            html += '<button class="btn btn-outline" id="wizard-prev-btn">← Back</button>';
        } else {
            html += '<span></span>';
        }

        // Right side buttons
        html += '<div class="wizard-footer-right">';
        if (currentStep < TOTAL_STEPS) {
            html += '<button class="btn btn-primary" id="wizard-next-btn">Next →</button>';
        } else {
            // On step 4 (last step), show Run Query and Save buttons
            html += '<button class="btn btn-primary" id="wizard-run-btn">Run Query</button>';
            html += '<button class="btn btn-outline" id="wizard-save-btn">Save Data Source</button>';
        }
        html += '</div>';

        html += '</div>';
        return html;
    }

    // --- Event Wiring ---

    function wireEvents() {
        // Close button
        const closeBtn = document.getElementById('wizard-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', close);

        // Navigation buttons
        const prevBtn = document.getElementById('wizard-prev-btn');
        if (prevBtn) prevBtn.addEventListener('click', prevStep);

        const nextBtn = document.getElementById('wizard-next-btn');
        if (nextBtn) nextBtn.addEventListener('click', nextStep);

        const runBtn = document.getElementById('wizard-run-btn');
        if (runBtn) runBtn.addEventListener('click', runQuery);

        const saveBtn = document.getElementById('wizard-save-btn');
        if (saveBtn) saveBtn.addEventListener('click', saveDataSource);

        // Retry button (error state)
        const retryBtn = document.getElementById('wizard-retry-btn');
        if (retryBtn) retryBtn.addEventListener('click', () => {
            errorMessage = '';
            if (currentStep === 1) fetchAccounts();
            else renderWizard();
        });

        // Step-specific event wiring
        wireStep1Events();
        wireStep2Events();
        wireStep3Events();
        wireStep4Events();

        // Overlay backdrop click to close
        const overlay = document.getElementById('datasource-wizard-overlay');
        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) close();
            });
        }
    }

    function wireStep1Events() {
        if (currentStep !== 1) return;

        // Select All toggle
        const selectAll = document.getElementById('wizard-select-all');
        if (selectAll) {
            selectAll.addEventListener('change', () => {
                if (selectAll.checked) {
                    wizardConfig.accounts = accountsList.map(a => a.account_id);
                } else {
                    wizardConfig.accounts = [];
                }
                // Re-render checkboxes without full re-render
                document.querySelectorAll('.account-cb').forEach(cb => {
                    cb.checked = selectAll.checked;
                });
            });
        }

        // Individual account checkboxes
        document.querySelectorAll('.account-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                const id = cb.value;
                if (cb.checked) {
                    if (!wizardConfig.accounts.includes(id)) {
                        wizardConfig.accounts.push(id);
                    }
                } else {
                    wizardConfig.accounts = wizardConfig.accounts.filter(a => a !== id);
                }
                // Update Select All state
                const allCb = document.getElementById('wizard-select-all');
                if (allCb) {
                    allCb.checked = wizardConfig.accounts.length === accountsList.length;
                }
            });
        });
    }

    function wireStep2Events() {
        if (currentStep !== 2) return;

        document.querySelectorAll('.attribute-cb').forEach(cb => {
            cb.addEventListener('change', () => {
                const id = cb.value;
                if (cb.checked) {
                    if (!wizardConfig.attributes.includes(id)) {
                        wizardConfig.attributes.push(id);
                    }
                } else {
                    wizardConfig.attributes = wizardConfig.attributes.filter(a => a !== id);
                }
            });
        });
    }

    function wireStep3Events() {
        if (currentStep !== 3) return;

        // Timeframe radio buttons
        document.querySelectorAll('.timeframe-radio').forEach(radio => {
            radio.addEventListener('change', () => {
                const value = radio.value;
                if (value === 'custom') {
                    wizardConfig.timeframe.type = 'custom';
                } else {
                    wizardConfig.timeframe.type = 'preset';
                    wizardConfig.timeframe.preset = value;
                }
                // Toggle custom date pickers visibility
                const customDates = document.getElementById('wizard-custom-dates');
                if (customDates) {
                    customDates.style.display = value === 'custom' ? 'block' : 'none';
                }
            });
        });

        // Custom date inputs
        const startInput = document.getElementById('wizard-start-date');
        if (startInput) {
            startInput.addEventListener('change', () => {
                wizardConfig.timeframe.startDate = startInput.value;
            });
        }

        const endInput = document.getElementById('wizard-end-date');
        if (endInput) {
            endInput.addEventListener('change', () => {
                wizardConfig.timeframe.endDate = endInput.value;
            });
        }
    }

    function wireStep4Events() {
        if (currentStep !== 4) return;

        // Add Filter button
        const addBtn = document.getElementById('wizard-add-filter-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                wizardConfig.filters.push({ attribute: '', operator: 'equals', value: '' });
                renderWizard();
            });
        }

        // Filter attribute selects
        document.querySelectorAll('.filter-attr').forEach(select => {
            select.addEventListener('change', () => {
                const idx = parseInt(select.getAttribute('data-index'), 10);
                wizardConfig.filters[idx].attribute = select.value;
                // Reset operator to first valid one for this type
                const attrType = getAttributeType(select.value);
                const ops = FILTER_OPERATORS[attrType] || FILTER_OPERATORS.text;
                wizardConfig.filters[idx].operator = ops[0].id;
                renderWizard();
            });
        });

        // Filter operator selects
        document.querySelectorAll('.filter-op').forEach(select => {
            select.addEventListener('change', () => {
                const idx = parseInt(select.getAttribute('data-index'), 10);
                wizardConfig.filters[idx].operator = select.value;
            });
        });

        // Filter value inputs
        document.querySelectorAll('.filter-value').forEach(input => {
            input.addEventListener('input', () => {
                const idx = parseInt(input.getAttribute('data-index'), 10);
                wizardConfig.filters[idx].value = input.value;
            });
        });

        // Remove filter buttons
        document.querySelectorAll('.filter-remove-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.getAttribute('data-index'), 10);
                wizardConfig.filters.splice(idx, 1);
                renderWizard();
            });
        });
    }
