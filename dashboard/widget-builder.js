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
        const overlay = document.getElementById('config-panel-overlay');
        overlay.removeAttribute('hidden');
        overlay.classList.add('active');

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
        const overlay = document.getElementById('config-panel-overlay');
        overlay.classList.remove('active');
        overlay.setAttribute('hidden', '');
    }

    async function fetchAndRender(widgetId) {
        const widget = GridManager.getWidgetConfig(widgetId);
        if (!widget || !widget.dataSource) return;

        const container = document.querySelector(`[data-widget-id="${widgetId}"] .widget-card-body`);
        if (!container) return;

        try {
            container.innerHTML = '<div class="widget-loading">Loading...</div>';

            // Use the working member-handler API instead of the non-existent dashboard-handler
            const data = await Dashboard.apiRequest('GET', '/members/dashboard-data');

            if (!data) {
                container.innerHTML = '<div class="widget-empty-state"><div class="empty-icon">📭</div><div>No data available</div></div>';
                return;
            }

            // Render based on widget type and selected data source
            _renderWidgetFromDashData(container, widget, data);

        } catch (err) {
            container.innerHTML = `
                <div class="widget-empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div>Failed to load data</div>
                    <button class="btn btn-outline btn-sm" onclick="WidgetBuilder.fetchAndRender('${widgetId}')" style="margin-top:8px;">Retry</button>
                </div>`;
        }
    }

    function _renderWidgetFromDashData(container, widget, data) {
        const source = widget.dataSource ? widget.dataSource.source : 'cost_cache';
        const type = widget.type;

        // Extract data based on source
        let chartData = { labels: [], values: [] };
        if (source === 'cost_cache' || source === 'business_metrics') {
            const daily = data.dailyTrend || [];
            chartData.labels = daily.map(d => d.date || d.day || '');
            chartData.values = daily.map(d => d.cost || d.amount || 0);
        } else if (source === 'invoices') {
            const services = data.costByService || [];
            chartData.labels = services.slice(0, 10).map(s => s.service || s.name || '');
            chartData.values = services.slice(0, 10).map(s => s.cost || s.amount || 0);
        } else if (source === 'commitments') {
            const monthly = data.monthlyTrend || {};
            if (Array.isArray(monthly)) {
                chartData.labels = monthly.map(m => m.month || m.date || '');
                chartData.values = monthly.map(m => m.cost || m.amount || 0);
            } else if (monthly.months) {
                chartData.labels = monthly.months;
                chartData.values = monthly.costs || [];
            }
        } else if (source === 'openai_usage') {
            const regions = data.costByRegion || [];
            chartData.labels = regions.slice(0, 8).map(r => r.region || r.name || '');
            chartData.values = regions.slice(0, 8).map(r => r.cost || r.amount || 0);
        }

        if (chartData.labels.length === 0) {
            container.innerHTML = '<div class="widget-empty-state"><div class="empty-icon">📭</div><div>No data for this source</div></div>';
            return;
        }

        // Render chart using Chart.js
        container.innerHTML = '<canvas style="width:100%;height:100%;"></canvas>';
        const canvas = container.querySelector('canvas');
        const ctx = canvas.getContext('2d');

        const chartType = (type === 'pie') ? 'pie' : (type === 'line') ? 'line' : (type === 'kpi') ? 'bar' : 'bar';
        const bgColors = ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16'];

        new Chart(ctx, {
            type: chartType,
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: source.replace('_', ' '),
                    data: chartData.values,
                    backgroundColor: chartType === 'pie' ? bgColors : 'rgba(99,102,241,0.6)',
                    borderColor: chartType === 'pie' ? bgColors : '#6366f1',
                    borderWidth: 1,
                    fill: type === 'line'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: type === 'pie' } }
            }
        });
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
