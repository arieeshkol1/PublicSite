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

        // Chart wizard widgets carry a `chartType` and are fed raw query results
        // ({ rows, columns }) rather than the legacy { labels, datasets } shape.
        if (widgetConfig.type === 'chart') {
            renderWizardChart(containerEl, widgetConfig, data);
            return;
        }

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

    /**
     * Render a chart-wizard widget (pie | bar | stackedBar | line) from raw
     * query results ({ rows, columns }), honoring the data-labels and
     * grid-lines display options. stackedBar uses a base Chart.js type of
     * 'bar' with stacked axes. Grid lines are never shown for pie.
     */
    function renderWizardChart(containerEl, widgetConfig, data) {
        const chartType = widgetConfig.chartType || 'bar';
        const displayOptions = widgetConfig.displayOptions || {};

        // Build the Chart.js config. Prefer the shared ChartWizard helper so
        // the wizard preview and the rendered widget stay in sync; fall back to
        // an internal mapping when ChartWizard is not loaded (e.g. unit tests).
        let config;
        if (typeof ChartWizard !== 'undefined' && ChartWizard.buildChartJsConfig) {
            config = ChartWizard.buildChartJsConfig(chartType, displayOptions, data);
        } else {
            config = buildLocalChartConfig(chartType, displayOptions, data);
        }

        const labels = (config.data && config.data.labels) || [];
        const datasets = (config.data && config.data.datasets) || [];
        if (labels.length === 0 && datasets.length === 0) {
            renderEmptyState(containerEl, 'No data available');
            return;
        }

        // Clear any retained error banner / previous markup and add a canvas.
        containerEl.innerHTML = '<canvas></canvas>';
        const canvas = containerEl.querySelector('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        const ctx = canvas.getContext('2d');

        const isPie = chartType === 'pie';

        // Apply the colour palette to datasets that arrive without colours.
        config.data.datasets = datasets.map((ds, i) => {
            const colored = Object.assign({}, ds);
            if (isPie) {
                colored.backgroundColor = ds.backgroundColor || getDefaultColors(labels.length);
            } else if (chartType === 'line') {
                const lineColor = ds.borderColor || PALETTE[i % PALETTE.length];
                colored.backgroundColor = ds.backgroundColor || lineColor;
                colored.borderColor = lineColor;
                colored.borderWidth = ds.borderWidth || 2;
                colored.fill = false;
                colored.tension = 0.3;
            } else {
                colored.backgroundColor = ds.backgroundColor || PALETTE[i % PALETTE.length];
            }
            return colored;
        });

        // Data labels: use the datalabels plugin when it is registered,
        // otherwise fall back to an inline afterDatasetsDraw hook so the toggle
        // still behaves correctly without the plugin.
        const wantLabels = !!displayOptions.dataLabels;
        const pluginPresent = typeof ChartDataLabels !== 'undefined';
        const localPlugins = [];
        if (wantLabels && !pluginPresent) {
            localPlugins.push(buildInlineDataLabelsPlugin());
        }

        const chart = new Chart(ctx, {
            type: config.type,
            data: config.data,
            options: config.options,
            plugins: localPlugins
        });

        chartInstances[widgetConfig.id] = chart;
    }

    /**
     * Internal {rows, columns} → Chart.js config mapping used only when the
     * shared ChartWizard helper is unavailable. Mirrors ChartWizard.buildChartJsConfig.
     */
    function buildLocalChartConfig(chartType, displayOptions, queryData) {
        const rows = (queryData && queryData.rows) || [];
        const cols = (queryData && queryData.columns) || [];
        const isPie = chartType === 'pie';
        const isStacked = chartType === 'stackedBar';
        const baseType = isPie ? 'pie' : (chartType === 'line' ? 'line' : 'bar');

        function isNumeric(col) {
            let seen = false;
            for (let i = 0; i < rows.length; i++) {
                const v = rows[i] ? rows[i][col] : undefined;
                if (v === null || v === undefined || v === '') continue;
                seen = true;
                if (typeof v === 'number') { if (!Number.isFinite(v)) return false; continue; }
                if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) continue;
                return false;
            }
            return seen;
        }

        const labelCol = cols.find(c => !isNumeric(c)) || cols[0];
        const valueCols = cols.filter(c => c !== labelCol && isNumeric(c));
        const labels = rows.map(r => String(r && r[labelCol] != null ? r[labelCol] : ''));
        const usedCols = isPie ? valueCols.slice(0, 1) : valueCols;
        const datasets = usedCols.map(c => ({
            label: c,
            data: rows.map(r => Number(r && r[c]) || 0)
        }));

        const showGrid = chartType !== 'pie' && !!displayOptions.gridLines;

        return {
            type: baseType,
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true },
                    datalabels: { display: !!displayOptions.dataLabels }
                },
                scales: isPie ? undefined : {
                    x: { stacked: isStacked, grid: { display: showGrid } },
                    y: { stacked: isStacked, beginAtZero: true, grid: { display: showGrid } }
                }
            }
        };
    }

    /**
     * Inline data-labels plugin used when the Chart.js datalabels plugin is not
     * loaded. Draws each value next to its point/segment.
     */
    function buildInlineDataLabelsPlugin() {
        return {
            id: 'inlineDataLabels',
            afterDatasetsDraw(chart) {
                const ctx = chart.ctx;
                ctx.save();
                ctx.font = '11px sans-serif';
                ctx.fillStyle = '#374151';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                chart.data.datasets.forEach((dataset, di) => {
                    const meta = chart.getDatasetMeta(di);
                    if (!meta || meta.hidden) return;
                    meta.data.forEach((element, i) => {
                        const value = dataset.data[i];
                        if (value === null || value === undefined) return;
                        const pos = element.tooltipPosition ? element.tooltipPosition() : element;
                        ctx.fillText(String(value), pos.x, pos.y - 2);
                    });
                });
                ctx.restore();
            }
        };
    }

    /**
     * Render an error state for a chart widget. When `lastData` is provided and
     * a previously rendered chart canvas is present, the existing chart is
     * retained and a non-destructive error banner is shown over it (Req 5.4).
     * Otherwise a full error state replaces the widget body (Req 5.3).
     */
    function renderError(containerEl, message, lastData) {
        if (!containerEl) return;

        if (lastData) {
            const existingCanvas = containerEl.querySelector('canvas');
            if (existingCanvas) {
                let banner = containerEl.querySelector('.widget-error-banner');
                if (!banner) {
                    banner = document.createElement('div');
                    banner.className = 'widget-error-banner';
                    containerEl.appendChild(banner);
                }
                banner.textContent = '⚠️ ' + message;
                return;
            }
        }

        containerEl.innerHTML = `
            <div class="widget-error-state widget-empty-state">
                <div class="empty-icon">⚠️</div>
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
        resize,
        renderError
    };
})();
