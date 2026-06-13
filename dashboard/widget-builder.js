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

        // Prompt user for a widget name
        const defaultTitle = getDefaultTitle(type) + ' ' + (currentCount + 1);
        const userTitle = prompt('Widget name:', defaultTitle);
        if (userTitle === null) return null; // User cancelled

        // Create widget config
        const widgetConfig = {
            id: crypto.randomUUID(),
            type: type,
            title: userTitle.trim() || defaultTitle,
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
        const metric = widget.dataSource && widget.dataSource.metric ? widget.dataSource.metric : 'cost';
        const type = widget.type;

        const metricLabels = {
            cost: 'Cost ($)', amount: 'Amount ($)', tokens: 'Tokens',
            requests: 'Requests', coverage: 'Coverage (%)',
            utilization: 'Utilization (%)', units: 'Units'
        };
        const metricLabel = metricLabels[metric] || metric;

        // Pull a numeric metric value from a record, falling back across the
        // common field names so the selected metric drives the Y values.
        const valueOf = (rec) => {
            if (rec == null) return 0;
            if (rec[metric] != null) return rec[metric];
            if (rec.cost != null) return rec.cost;
            if (rec.amount != null) return rec.amount;
            return 0;
        };

        const isPie = type === 'pie';
        let chartData = { labels: [], values: [] };

        if (isPie) {
            // Pie stays a categorical breakdown (by service).
            const services = data.costByService || [];
            chartData.labels = services.slice(0, 10).map(s => s.service || s.name || '');
            chartData.values = services.slice(0, 10).map(valueOf);
        } else {
            // X axis is always DATE; the metric (data itself) is flexible.
            const daily = data.dailyTrend || [];
            chartData.labels = daily.map(d => d.date || d.day || '');
            chartData.values = daily.map(valueOf);
        }

        if (chartData.labels.length === 0) {
            container.innerHTML = '<div class="widget-empty-state"><div class="empty-icon">📭</div><div>No data for this source</div></div>';
            return;
        }

        // Render chart using Chart.js
        container.innerHTML = '<canvas style="width:100%;height:100%;"></canvas>';
        const canvas = container.querySelector('canvas');
        const ctx = canvas.getContext('2d');

        const chartType = (type === 'pie') ? 'pie' : (type === 'line') ? 'line' : 'bar';
        const bgColors = ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4','#84cc16'];
        const isLine = type === 'line';

        let dataset;
        if (isLine) {
            // Real lines: no fill, solid stroke, visible points.
            dataset = {
                label: metricLabel,
                data: chartData.values,
                backgroundColor: '#6366f1',
                borderColor: '#6366f1',
                borderWidth: 2,
                fill: false,
                tension: 0.3,
                pointRadius: 2,
                pointHoverRadius: 4,
                spanGaps: true
            };
        } else {
            dataset = {
                label: metricLabel,
                data: chartData.values,
                backgroundColor: isPie ? bgColors : 'rgba(99,102,241,0.6)',
                borderColor: isPie ? bgColors : '#6366f1',
                borderWidth: 1
            };
        }

        new Chart(ctx, {
            type: chartType,
            data: { labels: chartData.labels, datasets: [dataset] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: isPie } },
                scales: !isPie ? {
                    x: { title: { display: true, text: 'Date' } },
                    y: { beginAtZero: true, title: { display: true, text: metricLabel } }
                } : undefined
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
