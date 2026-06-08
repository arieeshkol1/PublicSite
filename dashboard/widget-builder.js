/**
 * Widget Builder Module
 * Handles widget type selection from palette and widget instance creation.
 */

const WidgetBuilder = (() => {
    const SUPPORTED_TYPES = ['bar', 'line', 'pie', 'table', 'kpi', 'gauge'];
    const MAX_WIDGETS = 20;

    function init() {
        // Wire up palette item clicks
        const paletteItems = document.querySelectorAll('.palette-item[data-widget-type]');
        paletteItems.forEach(item => {
            item.addEventListener('click', () => {
                const type = item.getAttribute('data-widget-type');
                addWidget(type);
            });
        });
    }

    function addWidget(type) {
        // Validate widget type
        if (!SUPPORTED_TYPES.includes(type)) {
            console.error(`Unsupported widget type: ${type}`);
            return null;
        }

        // Check widget limit
        const currentCount = GridManager.getWidgetCount();
        if (currentCount >= MAX_WIDGETS) {
            alert('Maximum widget limit reached (20). Please remove a widget before adding a new one.');
            return null;
        }

        // Create widget config
        const widgetConfig = {
            id: crypto.randomUUID(),
            type: type,
            title: getDefaultTitle(type),
            dataSource: null,
            dimensions: [],
            filters: [],
            aggregation: 'sum',
            display: {
                colorScheme: 'default',
                showLegend: true,
                stacked: false,
                threshold: null
            },
            gridPosition: null // Will be set by GridManager
        };

        // Add to grid
        GridManager.addWidget(widgetConfig);
        updateWidgetCount();

        // Hide empty state
        const emptyState = document.getElementById('grid-empty-state');
        if (emptyState) emptyState.hidden = true;

        return widgetConfig;
    }

    function removeWidget(widgetId) {
        GridManager.removeWidget(widgetId);
        updateWidgetCount();

        // Show empty state if no widgets
        if (GridManager.getWidgetCount() === 0) {
            const emptyState = document.getElementById('grid-empty-state');
            if (emptyState) emptyState.hidden = false;
        }
    }

    function openConfigPanel(widgetId) {
        const widget = GridManager.getWidgetConfig(widgetId);
        if (!widget) return;

        document.getElementById('config-panel-title').textContent = `Configure: ${widget.title}`;
        document.getElementById('config-panel-overlay').hidden = false;

        // Initialize data source picker for this widget
        DataSourcePicker.show(widget, (updatedConfig) => {
            GridManager.updateWidgetConfig(widgetId, updatedConfig);
            closeConfigPanel();
            // Fetch data and render
            fetchAndRender(widgetId);
        });

        // Wire close button
        document.getElementById('config-panel-close').onclick = closeConfigPanel;
        document.getElementById('config-cancel-btn').onclick = closeConfigPanel;
    }

    function closeConfigPanel() {
        document.getElementById('config-panel-overlay').hidden = true;
    }

    async function fetchAndRender(widgetId) {
        const widget = GridManager.getWidgetConfig(widgetId);
        if (!widget || !widget.dataSource) return;

        const container = document.querySelector(`[data-widget-id="${widgetId}"] .widget-card-body`);
        if (!container) return;

        // Don't attempt fetch if offline
        if (Dashboard.isNetworkOffline()) {
            container.innerHTML = `
                <div class="widget-empty-state">
                    <div class="empty-icon">📡</div>
                    <div>Offline – waiting for connection</div>
                </div>`;
            return;
        }

        try {
            container.innerHTML = '<div class="widget-loading">Loading...</div>';

            const data = await Dashboard.apiRequest('POST', '/dashboard/query', {
                widget_config: widget
            });

            // Check for empty data (no results for period)
            if (isEmptyResponse(data)) {
                container.innerHTML = `
                    <div class="widget-empty-state">
                        <div class="empty-icon">📭</div>
                        <div>No data available</div>
                        <button class="btn btn-outline btn-sm" onclick="WidgetBuilder.fetchAndRender('${widgetId}')" style="margin-top:8px;">Retry</button>
                    </div>`;
                return;
            }

            // Render available data
            WidgetRenderer.render(container, widget, data);

            // Check for partial response (some providers failed)
            if (data.metadata && data.metadata.failed_providers && data.metadata.failed_providers.length > 0) {
                renderPartialDataWarning(container, data.metadata.failed_providers);
            }
        } catch (err) {
            container.innerHTML = `
                <div class="widget-empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div>Failed to load data</div>
                    <button class="btn btn-outline btn-sm" onclick="WidgetBuilder.fetchAndRender('${widgetId}')" style="margin-top:8px;">Retry</button>
                </div>`;
        }
    }

    /**
     * Checks if the API response contains no usable data.
     */
    function isEmptyResponse(data) {
        if (!data) return true;
        if (!data.labels || data.labels.length === 0) return true;
        if (!data.datasets || data.datasets.length === 0) return true;
        // Check if all dataset data arrays are empty or all zeroes
        const allEmpty = data.datasets.every(ds =>
            !ds.data || ds.data.length === 0 || ds.data.every(v => v === 0)
        );
        return allEmpty;
    }

    /**
     * Renders an inline warning banner below the chart when some providers failed.
     * The widget still shows partial data from successful providers.
     */
    function renderPartialDataWarning(container, failedProviders) {
        const providerNames = failedProviders.map(fp =>
            typeof fp === 'string' ? fp : (fp.provider || fp.source || 'Unknown')
        ).join(', ');

        const warningEl = document.createElement('div');
        warningEl.className = 'widget-partial-warning';
        warningEl.setAttribute('role', 'alert');
        warningEl.innerHTML = `
            <span class="partial-warning-icon">⚠️</span>
            <span class="partial-warning-text">Some data unavailable: <strong>${providerNames}</strong></span>`;
        container.appendChild(warningEl);
    }

    function updateWidgetCount() {
        const countEl = document.getElementById('widget-count');
        if (countEl) {
            countEl.textContent = GridManager.getWidgetCount();
        }
    }

    function getDefaultTitle(type) {
        const titles = {
            bar: 'Bar Chart',
            line: 'Line Chart',
            pie: 'Pie Chart',
            table: 'Data Table',
            kpi: 'KPI Card',
            gauge: 'Gauge'
        };
        return titles[type] || 'Widget';
    }

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', init);

    return {
        addWidget,
        removeWidget,
        openConfigPanel,
        closeConfigPanel,
        fetchAndRender,
        SUPPORTED_TYPES,
        MAX_WIDGETS
    };
})();
