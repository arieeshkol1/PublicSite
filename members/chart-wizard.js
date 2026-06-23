/**
 * Chart Wizard & Chart Dashboard Module
 * Builds visual charts (Pie, Bar, Stacked Bar, Line) from saved data sources
 * using ECharts. Charts are persisted via the dashboard-data proxy (chart_* actions)
 * and rendered into the Custom Dashboard area where they can be resized, refreshed,
 * and edited.
 *
 * Cloud-agnostic: no provider/service names are hard-coded here.
 */

/* ===================== Chart Wizard (create/edit modal) ===================== */
const ChartWizard = (() => {
  // Working state
  var editingChartId = null;
  var datasourceId = null;
  var datasourceName = '';
  var availableColumns = [];   // column names from a sample query
  var config = _defaultConfig();

  var CHART_TYPES = [
    { value: 'pie', label: 'Pie', icon: '🥧' },
    { value: 'bar', label: 'Bar', icon: '📊' },
    { value: 'stacked_bar', label: 'Stacked Bar', icon: '🧱' },
    { value: 'line', label: 'Line', icon: '📈' }
  ];

  function _defaultConfig() {
    return {
      type: 'bar',
      category_field: '',
      value_field: '',
      series_field: '',
      data_labels: true,
      grid_lines: true
    };
  }

  function init() {
    var overlay = document.getElementById('chart-wizard-overlay');
    if (overlay) {
      overlay.addEventListener('click', function(e) {
        if (e.target === overlay) close();
      });
    }
  }

  // Open the wizard for a given datasource (create mode)
  async function openForDatasource(dsId, dsName) {
    editingChartId = null;
    datasourceId = dsId;
    datasourceName = dsName || '';
    config = _defaultConfig();
    await _loadColumnsAndShow();
  }

  // Open the wizard to edit an existing chart
  async function openWithChart(chart) {
    editingChartId = chart.chart_id;
    datasourceId = chart.datasource_id;
    datasourceName = chart.name || '';
    config = Object.assign(_defaultConfig(), chart.chart_config || {});
    await _loadColumnsAndShow();
  }

  // Resolve datasource config, run a sample query to discover columns, then render
  async function _loadColumnsAndShow() {
    var overlay = document.getElementById('chart-wizard-overlay');
    if (overlay) overlay.hidden = false;

    var body = document.getElementById('chart-wizard-body');
    if (body) body.innerHTML = '<div style="padding:32px;text-align:center;color:#6b7280;">Loading data source fields…</div>';

    try {
      showLoading();
      var listResp = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      var datasources = (listResp && listResp.datasources) || [];
      var ds = datasources.find(function(d) { return d.datasource_id === datasourceId; });
      if (!ds) {
        hideLoading();
        if (body) body.innerHTML = '<div style="padding:24px;color:#991b1b;">Data source not found. It may have been deleted.</div>';
        return;
      }
      if (!datasourceName) datasourceName = ds.name;

      var queryResp = await api('POST', '/members/dashboard-data', {
        action: 'datasource_query',
        query_config: ds.query_config
      });
      hideLoading();

      availableColumns = (queryResp && queryResp.columns) || [];
      ChartDashboard._cacheRows(datasourceId, queryResp && queryResp.rows ? queryResp.rows : [], availableColumns);

      // Pick sensible defaults for fields if not already set
      if (!config.category_field) config.category_field = _guessCategory(availableColumns);
      if (!config.value_field) config.value_field = _guessValue(availableColumns, (queryResp && queryResp.rows) || []);

      renderForm();
    } catch (err) {
      hideLoading();
      console.error('Chart wizard load error:', err);
      if (body) body.innerHTML = '<div style="padding:24px;color:#991b1b;">Failed to load data source fields.</div>';
    }
  }

  function _guessCategory(cols) {
    var prefer = ['date', 'service', 'region', 'account_id', 'resource_id'];
    for (var i = 0; i < prefer.length; i++) {
      if (cols.indexOf(prefer[i]) !== -1) return prefer[i];
    }
    return cols[0] || '';
  }

  function _guessValue(cols, rows) {
    var prefer = ['cost_amount', 'usage_amount', 'cost', 'usage', 'amount'];
    for (var i = 0; i < prefer.length; i++) {
      if (cols.indexOf(prefer[i]) !== -1) return prefer[i];
    }
    // Fall back to first numeric column based on first row
    if (rows && rows.length) {
      for (var c = 0; c < cols.length; c++) {
        var v = rows[0][cols[c]];
        if (typeof v === 'number' || (!isNaN(parseFloat(v)) && isFinite(v))) return cols[c];
      }
    }
    return cols[cols.length - 1] || '';
  }

  function renderForm() {
    var body = document.getElementById('chart-wizard-body');
    if (!body) return;

    var isPie = config.type === 'pie';
    var isStacked = config.type === 'stacked_bar';

    var typeButtons = CHART_TYPES.map(function(t) {
      var active = config.type === t.value;
      return '<button type="button" class="chart-type-btn' + (active ? ' active' : '') + '" data-type="' + t.value + '" ' +
        'style="flex:1;min-width:110px;display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 8px;border:2px solid ' +
        (active ? '#6366f1' : '#e5e7eb') + ';border-radius:8px;background:' + (active ? '#eef2ff' : '#fff') + ';cursor:pointer;">' +
        '<span style="font-size:1.6em;">' + t.icon + '</span>' +
        '<span style="font-weight:600;color:#1f2937;font-size:0.9em;">' + t.label + '</span>' +
      '</button>';
    }).join('');

    var colOptions = function(selected) {
      return availableColumns.map(function(c) {
        var label = c.replace(/_/g, ' ').replace(/\b\w/g, function(m){ return m.toUpperCase(); });
        return '<option value="' + c + '"' + (c === selected ? ' selected' : '') + '>' + label + '</option>';
      }).join('');
    };

    var seriesRow = isStacked ?
      '<div style="margin-bottom:14px;">' +
        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">Series field (stack by)</label>' +
        '<select id="cw-series" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' +
          '<option value="">— None —</option>' + colOptions(config.series_field) +
        '</select>' +
      '</div>' : '';

    var gridOption = isPie ? '' :
      '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
        '<input type="checkbox" id="cw-grid"' + (config.grid_lines ? ' checked' : '') + '/>' +
        '<span style="color:#374151;font-size:0.9em;">Show grid lines</span>' +
      '</label>';

    body.innerHTML =
      '<div style="margin-bottom:18px;">' +
        '<div style="margin-bottom:12px;padding:8px 12px;background:#eef2ff;border:1px solid #c7d2fe;border-radius:6px;font-size:0.9em;color:#4338ca;font-weight:600;">' +
          'Data source: ' + _esc(datasourceName) +
        '</div>' +
        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">Chart name</label>' +
        '<input type="text" id="cw-name" value="' + _escAttr(datasourceName) + '" placeholder="My Chart" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;margin-bottom:18px;"/>' +

        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:8px;">Chart type</label>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px;">' + typeButtons + '</div>' +

        '<div style="margin-bottom:14px;">' +
          '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">' +
            (isPie ? 'Label field' : 'Category field (X axis)') +
          '</label>' +
          '<select id="cw-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + colOptions(config.category_field) + '</select>' +
        '</div>' +

        '<div style="margin-bottom:14px;">' +
          '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">Value field (numeric)</label>' +
          '<select id="cw-value" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + colOptions(config.value_field) + '</select>' +
        '</div>' +

        seriesRow +

        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin:18px 0 8px;">Display options</label>' +
        '<div style="display:flex;flex-direction:column;gap:10px;padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;">' +
          '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
            '<input type="checkbox" id="cw-labels"' + (config.data_labels ? ' checked' : '') + '/>' +
            '<span style="color:#374151;font-size:0.9em;">Show data labels</span>' +
          '</label>' +
          gridOption +
        '</div>' +
      '</div>' +

      '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px;padding-top:16px;border-top:1px solid #e5e7eb;">' +
        '<button onclick="ChartWizard.previewChart()" class="btn btn-outline">👁️ Preview</button>' +
        '<button onclick="ChartWizard.saveChart()" class="btn btn-primary" style="background:#8b5cf6;border-color:#8b5cf6;">💾 Save Chart</button>' +
      '</div>' +

      '<div id="cw-preview" style="margin-top:18px;height:320px;display:none;border:1px solid #e5e7eb;border-radius:8px;"></div>';

    _attachFormListeners();
  }

  function _attachFormListeners() {
    document.querySelectorAll('.chart-type-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        config.type = btn.getAttribute('data-type');
        _readForm();
        renderForm(); // re-render so series/grid options toggle
      });
    });
  }

  function _readForm() {
    var name = document.getElementById('cw-name');
    var cat = document.getElementById('cw-category');
    var val = document.getElementById('cw-value');
    var ser = document.getElementById('cw-series');
    var lab = document.getElementById('cw-labels');
    var grid = document.getElementById('cw-grid');
    if (name) datasourceName = name.value || datasourceName;
    if (cat) config.category_field = cat.value;
    if (val) config.value_field = val.value;
    if (ser) config.series_field = ser.value;
    if (lab) config.data_labels = lab.checked;
    if (grid) config.grid_lines = grid.checked;
  }

  function previewChart() {
    _readForm();
    var preview = document.getElementById('cw-preview');
    if (!preview) return;
    preview.style.display = 'block';
    var rows = ChartDashboard._getCachedRows(datasourceId);
    var option = ChartDashboard.buildOption(config, rows);
    var inst = echarts.getInstanceByDom(preview) || echarts.init(preview);
    inst.setOption(option, true);
    inst.resize();
  }

  async function saveChart() {
    _readForm();
    if (!config.category_field || !config.value_field) {
      notify('Please choose a category field and a value field', 'error');
      return;
    }
    var name = (datasourceName || 'Chart').trim();
    if (name.length < 1 || name.length > 100) {
      notify('Chart name must be between 1 and 100 characters', 'error');
      return;
    }
    try {
      showLoading();
      var payload = {
        action: 'chart_save',
        name: name,
        datasource_id: datasourceId,
        chart_config: config
      };
      if (editingChartId) payload.chart_id = editingChartId;
      var resp = await api('POST', '/members/dashboard-data', payload);
      hideLoading();
      if (resp.error) { notify(resp.error, 'error'); return; }
      notify('Chart "' + name + '" saved', 'success');
      close();
      if (window.ChartDashboard) ChartDashboard.render();
    } catch (err) {
      hideLoading();
      console.error('Chart save error:', err);
      notify('Failed to save chart', 'error');
    }
  }

  function close() {
    var overlay = document.getElementById('chart-wizard-overlay');
    if (overlay) overlay.hidden = true;
    editingChartId = null;
  }

  function showLoading() { if (window.showLoading) window.showLoading(); }
  function hideLoading() { if (window.hideLoading) window.hideLoading(); }

  function _esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function(m) {
      return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;' }[m];
    });
  }
  function _escAttr(t) {
    return String(t == null ? '' : t).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  return {
    init: init,
    openForDatasource: openForDatasource,
    openWithChart: openWithChart,
    previewChart: previewChart,
    saveChart: saveChart,
    close: close
  };
})();

window.ChartWizard = ChartWizard;

/* ===================== Chart Dashboard (render saved charts) ===================== */
const ChartDashboard = (() => {
  var instances = {};            // chart_id -> echarts instance
  var rowCache = {};             // datasource_id -> { rows, columns }
  var resizeBound = false;

  var PALETTE = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16','#f97316','#14b8a6'];

  function _container() {
    return document.getElementById('observe-saved-charts-container');
  }

  function _cacheRows(dsId, rows, columns) {
    rowCache[dsId] = { rows: rows || [], columns: columns || [] };
  }
  function _getCachedRows(dsId) {
    return (rowCache[dsId] && rowCache[dsId].rows) || [];
  }

  function _toNumber(v) {
    if (typeof v === 'number') return v;
    var n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  /**
   * Aggregate rows into ECharts option based on chart config.
   */
  function buildOption(config, rows) {
    rows = rows || [];
    var labels = (config.data_labels !== false);
    var grid = (config.grid_lines !== false);
    var cat = config.category_field;
    var val = config.value_field;

    if (config.type === 'pie') {
      var sums = {};
      rows.forEach(function(r) {
        var k = String(r[cat] == null ? '—' : r[cat]);
        sums[k] = (sums[k] || 0) + _toNumber(r[val]);
      });
      var data = Object.keys(sums).map(function(k) { return { name: k, value: sums[k] }; });
      return {
        color: PALETTE,
        tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
        legend: { type: 'scroll', bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['35%', '70%'],
          data: data,
          label: { show: labels, formatter: '{b}: {d}%' }
        }]
      };
    }

    // Bar / Stacked Bar / Line share x-axis category aggregation
    var isStacked = config.type === 'stacked_bar';
    var baseType = (config.type === 'line') ? 'line' : 'bar';

    // Unique, sorted categories
    var catSet = [];
    var seen = {};
    rows.forEach(function(r) {
      var k = String(r[cat] == null ? '—' : r[cat]);
      if (!seen[k]) { seen[k] = true; catSet.push(k); }
    });
    catSet.sort();

    var series = [];
    if (isStacked && config.series_field) {
      // One series per unique series_field value
      var seriesKeys = [];
      var skSeen = {};
      rows.forEach(function(r) {
        var sk = String(r[config.series_field] == null ? '—' : r[config.series_field]);
        if (!skSeen[sk]) { skSeen[sk] = true; seriesKeys.push(sk); }
      });
      seriesKeys.sort();
      seriesKeys.forEach(function(sk) {
        var byCat = {};
        rows.forEach(function(r) {
          if (String(r[config.series_field] == null ? '—' : r[config.series_field]) !== sk) return;
          var k = String(r[cat] == null ? '—' : r[cat]);
          byCat[k] = (byCat[k] || 0) + _toNumber(r[val]);
        });
        series.push({
          name: sk,
          type: 'bar',
          stack: 'total',
          label: { show: labels },
          data: catSet.map(function(k) { return byCat[k] || 0; })
        });
      });
    } else {
      var sums2 = {};
      rows.forEach(function(r) {
        var k = String(r[cat] == null ? '—' : r[cat]);
        sums2[k] = (sums2[k] || 0) + _toNumber(r[val]);
      });
      series.push({
        name: val,
        type: baseType,
        label: { show: labels, position: baseType === 'bar' ? 'top' : 'top' },
        smooth: baseType === 'line',
        data: catSet.map(function(k) { return sums2[k] || 0; })
      });
    }

    return {
      color: PALETTE,
      tooltip: { trigger: 'axis' },
      legend: (isStacked && config.series_field) ? { type: 'scroll', top: 0 } : { show: false },
      grid: { left: 50, right: 20, top: 40, bottom: 60, containLabel: true },
      xAxis: {
        type: 'category',
        data: catSet,
        axisLabel: { rotate: catSet.length > 6 ? 35 : 0 },
        splitLine: { show: grid }
      },
      yAxis: { type: 'value', splitLine: { show: grid } },
      series: series
    };
  }

  function _cardHTML(chart) {
    return '' +
      '<div class="chart-card" data-chart-id="' + chart.chart_id + '">' +
        '<div class="chart-card-header">' +
          '<span class="chart-card-title">' + _esc(chart.name) + '</span>' +
          '<span class="chart-card-actions">' +
            '<button class="chart-action-refresh" title="Refresh">🔄</button>' +
            '<button class="chart-action-edit" title="Edit">✏️</button>' +
            '<button class="chart-action-delete" title="Delete">🗑️</button>' +
          '</span>' +
        '</div>' +
        '<div class="chart-card-body" id="chart-body-' + chart.chart_id + '"></div>' +
      '</div>';
  }

  async function render() {
    var container = _container();
    if (!container) return;
    try {
      var resp = await api('POST', '/members/dashboard-data', { action: 'chart_list' });
      var charts = (resp && resp.charts) || [];

      // Dispose existing instances
      Object.keys(instances).forEach(function(id) {
        try { instances[id].dispose(); } catch (e) {}
      });
      instances = {};

      if (charts.length === 0) {
        container.innerHTML =
          '<div style="padding:24px;text-align:center;color:#6b7280;border:1px dashed #d1d5db;border-radius:8px;">' +
            '<div style="font-size:1.5em;margin-bottom:8px;">📈</div>' +
            '<div style="font-weight:600;color:#1f2937;margin-bottom:4px;">No charts yet</div>' +
            '<div style="font-size:0.9em;">Click the 📈 button on a saved data source to build a chart</div>' +
          '</div>';
        return;
      }

      var grid = document.createElement('div');
      grid.className = 'chart-card-grid';
      grid.innerHTML = charts.map(_cardHTML).join('');
      container.innerHTML = '';
      container.appendChild(grid);

      // Wire actions + render each chart
      charts.forEach(function(chart) {
        var card = container.querySelector('.chart-card[data-chart-id="' + chart.chart_id + '"]');
        if (!card) return;
        card.querySelector('.chart-action-refresh').onclick = function() { refreshChart(chart); };
        card.querySelector('.chart-action-edit').onclick = function() { ChartWizard.openWithChart(chart); };
        card.querySelector('.chart-action-delete').onclick = function() { deleteChart(chart); };
        _renderOne(chart);
      });

      _bindResize();
    } catch (err) {
      console.error('Chart dashboard render error:', err);
    }
  }

  async function _renderOne(chart) {
    var el = document.getElementById('chart-body-' + chart.chart_id);
    if (!el) return;
    var rows = await _ensureRows(chart.datasource_id);
    var inst = echarts.getInstanceByDom(el) || echarts.init(el);
    inst.setOption(buildOption(chart.chart_config || {}, rows), true);
    inst.resize();
    instances[chart.chart_id] = inst;

    // Resize chart when the card body is manually resized
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function() { try { inst.resize(); } catch (e) {} });
      ro.observe(el);
    }
  }

  // Fetch + cache rows for a datasource (used by charts)
  async function _ensureRows(dsId) {
    if (rowCache[dsId]) return rowCache[dsId].rows;
    try {
      var listResp = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      var datasources = (listResp && listResp.datasources) || [];
      var ds = datasources.find(function(d) { return d.datasource_id === dsId; });
      if (!ds) { _cacheRows(dsId, [], []); return []; }
      var q = await api('POST', '/members/dashboard-data', { action: 'datasource_query', query_config: ds.query_config });
      _cacheRows(dsId, (q && q.rows) || [], (q && q.columns) || []);
      return rowCache[dsId].rows;
    } catch (err) {
      console.error('ensureRows error:', err);
      _cacheRows(dsId, [], []);
      return [];
    }
  }

  async function refreshChart(chart) {
    // Invalidate cache and re-run query for this datasource
    delete rowCache[chart.datasource_id];
    if (window.showLoading) window.showLoading();
    try {
      await _renderOne(chart);
      notify('Chart refreshed', 'success');
    } finally {
      if (window.hideLoading) window.hideLoading();
    }
  }

  async function deleteChart(chart) {
    if (!confirm('Delete chart "' + chart.name + '"?\n\nThis cannot be undone.')) return;
    try {
      if (window.showLoading) window.showLoading();
      var resp = await api('POST', '/members/dashboard-data', { action: 'chart_delete', chart_id: chart.chart_id });
      if (window.hideLoading) window.hideLoading();
      if (resp.error) { notify(resp.error, 'error'); return; }
      notify('Chart deleted', 'success');
      render();
    } catch (err) {
      if (window.hideLoading) window.hideLoading();
      console.error('Chart delete error:', err);
      notify('Failed to delete chart', 'error');
    }
  }

  function _bindResize() {
    if (resizeBound) return;
    resizeBound = true;
    window.addEventListener('resize', function() {
      Object.keys(instances).forEach(function(id) {
        try { instances[id].resize(); } catch (e) {}
      });
    });
  }

  function _esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function(m) {
      return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;' }[m];
    });
  }

  return {
    render: render,
    buildOption: buildOption,
    _cacheRows: _cacheRows,
    _getCachedRows: _getCachedRows
  };
})();

window.ChartDashboard = ChartDashboard;

// Initialize wizard listeners (script loads after DOM is ready, at bottom of body)
ChartWizard.init();
