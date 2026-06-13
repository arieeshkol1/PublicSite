/**
 * Widget Renderer Module
 * Renders widget data using Chart.js for charts, and custom HTML for table/KPI/gauge.
 */

const WidgetRenderer = (() => {
    const chartInstances = {};
    const PALETTE = [
        '#6366f1', '#f59e0b', '#10b981', '#ef4444',
        '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6',
        '#f97316', '#06b6d4', '#84cc16', '#a855f7'
    ];

    function render(containerEl, widgetConfig, data) {
        // Destroy existing chart if present
        destroy(widgetConfig.id);

        if (!data || (!data.labels && !data.datasets)) {
            renderEmptyState(containerEl, 'No data available');
            return;
        }

        switch (widgetConfig.type) {
            case 'bar':
            case 'line':
            case 'pie':
                renderChart(containerEl, widgetConfig, data);
                break;
            case 'table':
                renderTable(containerEl, widgetConfig, data);
                break;
            case 'kpi':
                renderKPI(containerEl, widgetConfig, data);
                break;
            case 'gauge':
                renderGauge(containerEl, widgetConfig, data);
                break;
            default:
                renderEmptyState(containerEl, 'Unsupported widget type');
        }
    }

    function renderChart(containerEl, widgetConfig, data) {
        containerEl.innerHTML = '<canvas></canvas>';
        const canvas = containerEl.querySelector('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '100%';

        const ctx = canvas.getContext('2d');
        const isLine = widgetConfig.type === 'line';
        const isPie = widgetConfig.type === 'pie';
        const labelCount = data.labels ? data.labels.length : 0;

        const chart = new Chart(ctx, {
            type: widgetConfig.type,
            data: {
                labels: data.labels || [],
                datasets: (data.datasets || []).map((ds, i) => {
                    const lineColor = ds.borderColor || PALETTE[i % PALETTE.length];
                    if (isLine) {
                        // Real lines: no fill, solid stroke, visible points.
                        return {
                            label: ds.label || '',
                            data: ds.data || [],
                            backgroundColor: lineColor,
                            borderColor: lineColor,
                            borderWidth: ds.borderWidth || 2,
                            fill: false,
                            tension: 0.3,
                            pointRadius: 2,
                            pointHoverRadius: 4,
                            spanGaps: true
                        };
                    }
                    return {
                        label: ds.label || '',
                        data: ds.data || [],
                        backgroundColor: ds.backgroundColor || (isPie ? getDefaultColors(labelCount) : PALETTE[i % PALETTE.length]),
                        borderColor: ds.borderColor || undefined,
                        borderWidth: ds.borderWidth || 1
                    };
                })
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: widgetConfig.display ? widgetConfig.display.showLegend : true
                    }
                },
                scales: !isPie ? {
                    x: {
                        // X axis is always the date dimension.
                        title: { display: true, text: 'Date' }
                    },
                    y: { beginAtZero: true }
                } : undefined
            }
        });

        chartInstances[widgetConfig.id] = chart;
    }

    function renderTable(containerEl, widgetConfig, data) {
        if (!data.labels || data.labels.length === 0) {
            renderEmptyState(containerEl, 'No data available');
            return;
        }

        let html = '<div class="widget-table-wrap"><table class="widget-table"><thead><tr><th>Category</th>';
        (data.datasets || []).forEach(ds => {
            html += `<th>${ds.label || 'Value'}</th>`;
        });
        html += '</tr></thead><tbody>';

        data.labels.forEach((label, i) => {
            html += `<tr><td>${label}</td>`;
            (data.datasets || []).forEach(ds => {
                const val = ds.data && ds.data[i] != null ? ds.data[i].toLocaleString() : '-';
                html += `<td>${val}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table></div>';
        containerEl.innerHTML = html;
    }

    function renderKPI(containerEl, widgetConfig, data) {
        const value = data.datasets && data.datasets[0] && data.datasets[0].data
            ? data.datasets[0].data.reduce((a, b) => a + b, 0)
            : 0;
        const label = data.datasets && data.datasets[0] ? data.datasets[0].label : 'Value';

        containerEl.innerHTML = `
            <div class="widget-kpi">
                <div class="widget-kpi-value">${formatNumber(value)}</div>
                <div class="widget-kpi-label">${label}</div>
            </div>`;
    }

    function renderGauge(containerEl, widgetConfig, data) {
        const value = data.datasets && data.datasets[0] && data.datasets[0].data
            ? data.datasets[0].data[0] || 0
            : 0;
        const threshold = widgetConfig.display ? widgetConfig.display.threshold : null;
        const maxVal = threshold || 100;
        const pct = Math.min((value / maxVal) * 100, 100);
        const color = pct > 80 ? '#ef4444' : pct > 60 ? '#f59e0b' : '#10b981';

        containerEl.innerHTML = `
            <div class="widget-gauge">
                <div class="gauge-ring" style="background: conic-gradient(${color} ${pct * 3.6}deg, #e5e7eb ${pct * 3.6}deg)"></div>
                <div class="gauge-value">${formatNumber(value)}</div>
                <div class="gauge-label">${threshold ? `/ ${formatNumber(threshold)}` : ''}</div>
            </div>`;
    }

    function renderEmptyState(containerEl, message) {
        containerEl.innerHTML = `
            <div class="widget-empty-state">
                <div class="empty-icon">📭</div>
                <div>${message}</div>
            </div>`;
    }

    function destroy(widgetId) {
        if (chartInstances[widgetId]) {
            chartInstances[widgetId].destroy();
            delete chartInstances[widgetId];
        }
    }

    function resize(widgetId, width, height) {
        if (chartInstances[widgetId]) {
            chartInstances[widgetId].resize(width, height);
        }
    }

    function getDefaultColors(count) {
        return Array.from({ length: count }, (_, i) => PALETTE[i % PALETTE.length]);
    }

    function formatNumber(val) {
        if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M';
        if (val >= 1000) return (val / 1000).toFixed(1) + 'K';
        return typeof val === 'number' ? val.toFixed(2) : val;
    }

    return {
        render,
        destroy,
        resize
    };
})();
