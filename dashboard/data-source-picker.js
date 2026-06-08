/**
 * Data Source Picker Module
 * Handles data source selection, account picker, date range, filters, and aggregation config.
 */

const DataSourcePicker = (() => {
    const SOURCES = [
        { id: 'cost_cache', label: 'Cost Cache (Daily Costs)', icon: '💰' },
        { id: 'invoices', label: 'Invoices', icon: '🧾' },
        { id: 'openai_usage', label: 'OpenAI Usage', icon: '🤖' },
        { id: 'commitments', label: 'Commitments', icon: '📋' },
        { id: 'business_metrics', label: 'Business Metrics', icon: '📊' }
    ];

    const RELATIVE_RANGES = ['7d', '30d', '90d', '12m'];
    const AGGREGATION_TYPES = ['sum', 'avg', 'max', 'min', 'count'];
    const FILTER_OPERATORS = ['eq', 'neq', 'gt', 'lt', 'contains'];
    const DIMENSION_OPTIONS = ['service', 'date', 'account', 'provider', 'tag_key'];

    let currentWidget = null;
    let onApplyCallback = null;

    function show(widgetConfig, callback) {
        currentWidget = { ...widgetConfig };
        onApplyCallback = callback;

        renderSourcePicker();
        renderDateRange();
        renderFilterBuilder();
        renderDimensionSelector();
        renderAggregationSelector();
        renderDisplayOptions();

        // Wire apply button
        const applyBtn = document.getElementById('config-apply-btn');
        if (applyBtn) {
            applyBtn.onclick = () => {
                if (onApplyCallback) onApplyCallback(currentWidget);
            };
        }
    }

    function renderSourcePicker() {
        const container = document.getElementById('data-source-picker-container');
        if (!container) return;

        const currentSource = currentWidget.dataSource ? currentWidget.dataSource.source : '';

        let html = '<div class="source-picker">';
        html += '<label class="config-label">Source</label>';
        html += '<div class="source-options">';
        SOURCES.forEach(s => {
            const selected = s.id === currentSource ? 'selected' : '';
            html += `<button class="source-option ${selected}" data-source="${s.id}">
                <span>${s.icon}</span> ${s.label}
            </button>`;
        });
        html += '</div>';

        // Info: accounts are inherited from the member portal
        html += '<p style="margin-top:12px;font-size:0.8em;color:#6b7280;">Data is fetched from all your connected accounts.</p>';

        html += '</div>';
        container.innerHTML = html;

        // Wire source option clicks
        container.querySelectorAll('.source-option').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.source-option').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                if (!currentWidget.dataSource) {
                    currentWidget.dataSource = { source: '', accountIds: [], dateRange: { type: 'relative', relative: '30d' } };
                }
                currentWidget.dataSource.source = btn.getAttribute('data-source');
            });
        });
    }

    function renderDateRange() {
        const container = document.getElementById('data-source-picker-container');
        if (!container) return;

        const dateRange = currentWidget.dataSource ? currentWidget.dataSource.dateRange : null;
        const rangeType = dateRange ? dateRange.type : 'relative';
        const relativeVal = dateRange ? dateRange.relative : '30d';

        let html = '<div class="date-range-section" style="margin-top:16px;">';
        html += '<label class="config-label">Date Range</label>';
        html += '<div class="date-range-toggle">';
        html += `<button class="range-type-btn ${rangeType === 'relative' ? 'active' : ''}" data-range-type="relative">Relative</button>`;
        html += `<button class="range-type-btn ${rangeType === 'absolute' ? 'active' : ''}" data-range-type="absolute">Absolute</button>`;
        html += '</div>';

        // Relative options
        html += '<div id="relative-range-options" style="margin-top:8px;">';
        RELATIVE_RANGES.forEach(r => {
            const selected = r === relativeVal ? 'selected' : '';
            html += `<button class="range-option ${selected}" data-range="${r}">${r}</button>`;
        });
        html += '</div>';

        // Absolute options
        html += `<div id="absolute-range-options" style="margin-top:8px;display:${rangeType === 'absolute' ? 'block' : 'none'};">`;
        html += `<input type="date" id="date-range-start" class="config-input" value="${dateRange && dateRange.start ? dateRange.start : ''}">`;
        html += `<span style="margin:0 8px;color:#6b7280;">to</span>`;
        html += `<input type="date" id="date-range-end" class="config-input" value="${dateRange && dateRange.end ? dateRange.end : ''}">`;
        html += '</div>';

        html += '</div>';
        container.insertAdjacentHTML('beforeend', html);
    }

    function renderFilterBuilder() {
        const container = document.getElementById('filter-builder-container');
        if (!container) return;

        const filters = currentWidget.filters || [];

        let html = '<div class="filter-builder">';
        html += '<div id="filter-list">';
        filters.forEach((f, i) => {
            html += renderFilterRow(f, i);
        });
        html += '</div>';
        html += '<button class="btn btn-outline btn-sm" id="add-filter-btn">+ Add Filter</button>';
        html += '</div>';
        container.innerHTML = html;

        // Wire add filter
        const addBtn = container.querySelector('#add-filter-btn');
        if (addBtn) {
            addBtn.addEventListener('click', () => {
                if (!currentWidget.filters) currentWidget.filters = [];
                if (currentWidget.filters.length >= 20) {
                    alert('Maximum 20 filters per query');
                    return;
                }
                currentWidget.filters.push({ field: '', operator: 'eq', value: '' });
                renderFilterBuilder();
            });
        }
    }

    function renderFilterRow(filter, index) {
        let html = `<div class="filter-row" data-index="${index}">`;
        html += `<input type="text" class="config-input filter-field" placeholder="Field" value="${filter.field || ''}">`;
        html += '<select class="config-select filter-op">';
        FILTER_OPERATORS.forEach(op => {
            html += `<option value="${op}" ${filter.operator === op ? 'selected' : ''}>${op}</option>`;
        });
        html += '</select>';
        html += `<input type="text" class="config-input filter-value" placeholder="Value" value="${filter.value || ''}">`;
        html += `<button class="btn-icon filter-remove" data-index="${index}">&times;</button>`;
        html += '</div>';
        return html;
    }

    function renderDimensionSelector() {
        const container = document.getElementById('dimension-selector-container');
        if (!container) return;

        const dims = currentWidget.dimensions || [];

        let html = '<div class="dimension-selector">';
        html += '<p class="config-hint">Select up to 3 dimensions for grouping</p>';
        DIMENSION_OPTIONS.forEach(d => {
            const checked = dims.includes(d) ? 'checked' : '';
            html += `<label class="dimension-option">
                <input type="checkbox" value="${d}" ${checked} class="dim-checkbox"> ${d}
            </label>`;
        });
        html += '</div>';
        container.innerHTML = html;

        // Wire checkboxes
        container.querySelectorAll('.dim-checkbox').forEach(cb => {
            cb.addEventListener('change', () => {
                const selected = [...container.querySelectorAll('.dim-checkbox:checked')].map(c => c.value);
                if (selected.length > 3) {
                    cb.checked = false;
                    alert('Maximum 3 dimensions per query');
                    return;
                }
                currentWidget.dimensions = selected;
            });
        });
    }

    function renderAggregationSelector() {
        const container = document.getElementById('aggregation-selector-container');
        if (!container) return;

        const current = currentWidget.aggregation || 'sum';

        let html = '<div class="aggregation-selector">';
        AGGREGATION_TYPES.forEach(agg => {
            const selected = agg === current ? 'selected' : '';
            html += `<button class="agg-option ${selected}" data-agg="${agg}">${agg.toUpperCase()}</button>`;
        });
        html += '</div>';
        container.innerHTML = html;

        // Wire clicks
        container.querySelectorAll('.agg-option').forEach(btn => {
            btn.addEventListener('click', () => {
                container.querySelectorAll('.agg-option').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                currentWidget.aggregation = btn.getAttribute('data-agg');
            });
        });
    }

    function renderDisplayOptions() {
        const container = document.getElementById('display-options-container');
        if (!container) return;

        const display = currentWidget.display || {};

        let html = '<div class="display-options">';
        html += `<label class="config-checkbox-label">
            <input type="checkbox" id="opt-legend" ${display.showLegend !== false ? 'checked' : ''}> Show Legend
        </label>`;
        html += `<label class="config-checkbox-label">
            <input type="checkbox" id="opt-stacked" ${display.stacked ? 'checked' : ''}> Stacked
        </label>`;
        html += '</div>';
        container.innerHTML = html;
    }

    function getAvailableSources() {
        return SOURCES;
    }

    return {
        show,
        getAvailableSources,
        SOURCES,
        AGGREGATION_TYPES,
        FILTER_OPERATORS,
        DIMENSION_OPTIONS
    };
})();
