/**
 * Grid Manager Module
 * Manages the 12-column drag-and-drop grid using Gridstack.js.
 * Handles widget placement, overlap prevention, and boundary enforcement.
 */

const GridManager = (() => {
    const GRID_COLS = 12;
    const MAX_ROWS = 48;
    const MAX_WIDGETS = 20;

    let grid = null;
    let widgets = {}; // widgetId -> widgetConfig

    function init() {
        const containerEl = document.getElementById('grid-container');
        if (!containerEl) return;

        grid = GridStack.init({
            column: GRID_COLS,
            maxRow: MAX_ROWS,
            cellHeight: 80,
            margin: 8,
            float: true,
            animate: true,
            disableOneColumnMode: true,
            removable: false
        }, containerEl);

        // Listen for grid changes to update widget positions
        grid.on('change', (event, items) => {
            if (items) {
                items.forEach(item => {
                    const widgetId = item.el ? item.el.getAttribute('data-widget-id') : null;
                    if (widgetId && widgets[widgetId]) {
                        widgets[widgetId].gridPosition = {
                            x: item.x,
                            y: item.y,
                            w: item.w,
                            h: item.h
                        };
                    }
                });
            }
        });
    }

    function addWidget(widgetConfig) {
        if (Object.keys(widgets).length >= MAX_WIDGETS) {
            return false;
        }

        // Default grid position for new widgets
        const defaultPos = findNextAvailablePosition();
        widgetConfig.gridPosition = widgetConfig.gridPosition || defaultPos;

        const { x, y, w, h } = widgetConfig.gridPosition;

        // Validate bounds
        if (x + w > GRID_COLS || y + h > MAX_ROWS) {
            console.error('Widget exceeds grid boundaries');
            return false;
        }

        // Create widget HTML content
        const content = createWidgetContent(widgetConfig);

        // Add to gridstack
        const gridItem = grid.addWidget({
            x: x,
            y: y,
            w: w,
            h: h,
            content: content,
            id: widgetConfig.id
        });

        // Set data attribute for later lookup
        if (gridItem) {
            gridItem.setAttribute('data-widget-id', widgetConfig.id);
        }

        widgets[widgetConfig.id] = widgetConfig;
        return true;
    }

    function removeWidget(widgetId) {
        const el = document.querySelector(`[data-widget-id="${widgetId}"]`);
        if (el && grid) {
            grid.removeWidget(el);
        }
        delete widgets[widgetId];
    }

    function createWidgetContent(widgetConfig) {
        return `
            <div class="widget-card-header">
                <span class="widget-card-title" onclick="GridManager.renameWidget('${widgetConfig.id}')" style="cursor:pointer;" title="Click to rename">${widgetConfig.title || 'Widget'}</span>
                <div class="widget-card-actions">
                    <button onclick="WidgetBuilder.openConfigPanel('${widgetConfig.id}')" title="Configure">⚙️</button>
                    <button onclick="WidgetBuilder.removeWidget('${widgetConfig.id}')" title="Remove">🗑️</button>
                </div>
            </div>
            <div class="widget-card-body" data-widget-id="${widgetConfig.id}">
                <div class="widget-empty-state">
                    <div class="empty-icon">${getTypeIcon(widgetConfig.type)}</div>
                    <div>No data source configured</div>
                    <div style="font-size:0.8em;color:#9ca3af;margin-top:4px;">Click ⚙️ to configure</div>
                </div>
            </div>`;
    }

    function getTypeIcon(type) {
        const icons = { bar: '📊', line: '📈', pie: '🥧', table: '📋', kpi: '🎯', gauge: '⏱️' };
        return icons[type] || '📊';
    }

    function findNextAvailablePosition() {
        // Simple placement strategy: stack widgets in rows of 2 (6 cols each)
        const count = Object.keys(widgets).length;
        const col = (count % 2) * 6;
        const row = Math.floor(count / 2) * 4;
        return { x: col, y: row, w: 6, h: 4 };
    }

    function getWidgets() {
        return Object.values(widgets).map(w => ({
            ...w,
            gridPosition: w.gridPosition
        }));
    }

    function getWidgetCount() {
        return Object.keys(widgets).length;
    }

    function getWidgetConfig(widgetId) {
        return widgets[widgetId] || null;
    }

    function updateWidgetConfig(widgetId, updatedConfig) {
        if (widgets[widgetId]) {
            widgets[widgetId] = { ...widgets[widgetId], ...updatedConfig };
        }
    }

    function clearGrid() {
        if (grid) {
            grid.removeAll();
        }
        widgets = {};

        // Show empty state
        const emptyState = document.getElementById('grid-empty-state');
        if (emptyState) emptyState.hidden = false;

        // Update count
        const countEl = document.getElementById('widget-count');
        if (countEl) countEl.textContent = '0';
    }

    function renameWidget(widgetId) {
        const widget = widgets[widgetId];
        if (!widget) return;
        const newName = prompt('Rename widget:', widget.title);
        if (newName === null || newName.trim() === '') return;
        widget.title = newName.trim();
        // Update the title in the DOM
        const el = document.querySelector(`[data-widget-id="${widgetId}"] .widget-card-title`);
        if (!el) {
            // Try parent grid item
            const gridEl = document.querySelector(`.grid-stack-item[data-widget-id="${widgetId}"] .widget-card-title`);
            if (gridEl) gridEl.textContent = widget.title;
        } else {
            el.textContent = widget.title;
        }
    }

    function loadLayout(layoutData) {
        clearGrid();

        if (!layoutData || !layoutData.widgets) return;

        layoutData.widgets.forEach(widgetData => {
            addWidget(widgetData);
        });

        // Hide empty state if widgets were loaded
        if (Object.keys(widgets).length > 0) {
            const emptyState = document.getElementById('grid-empty-state');
            if (emptyState) emptyState.hidden = true;
        }

        // Update count
        const countEl = document.getElementById('widget-count');
        if (countEl) countEl.textContent = Object.keys(widgets).length;
    }

    return {
        init,
        addWidget,
        removeWidget,
        renameWidget,
        getWidgets,
        getWidgetCount,
        getWidgetConfig,
        updateWidgetConfig,
        clearGrid,
        loadLayout,
        GRID_COLS,
        MAX_ROWS,
        MAX_WIDGETS
    };
})();
