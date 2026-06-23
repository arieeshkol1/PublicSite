/**
 * Chart Wizard & Chart Dashboard Module
 * Builds visual charts (Pie, Bar, Stacked Bar, Line) from saved data sources
 * using ECharts. Charts are persisted via the dashboard-data proxy (chart_* actions)
 * and rendered into the Custom Dashboard area where they can be resized, refreshed,
 * and edited.
 *
 * Cloud-agnostic: no provider/service names are hard-coded here.
 */

/* ===================== Number formatting (Excel-style) ===================== */
var ChartFormat = (function () {
  var FORMATS = [
    { value: 'comma', label: '1,234' },
    { value: 'comma2', label: '1,234.56' },
    { value: 'abbrev', label: '1.2K / 3.4M' },
    { value: 'currency', label: '$1,234' },
    { value: 'currency2', label: '$1,234.56' },
    { value: 'general', label: 'General (raw)' }
  ];

  function _commas(n, decimals) {
    var parts = Math.abs(n).toFixed(decimals).split('.');
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (n < 0 ? '-' : '') + parts.join('.');
  }

  function format(value, fmt) {
    var n = (typeof value === 'number') ? value : parseFloat(value);
    if (isNaN(n)) return value == null ? '' : String(value);
    switch (fmt) {
      case 'general': return String(n);
      case 'comma': return _commas(n, 0);
      case 'comma2': return _commas(n, 2);
      case 'currency': return '$' + _commas(n, 0);
      case 'currency2': return '$' + _commas(n, 2);
      case 'abbrev': {
        var abs = Math.abs(n), sign = n < 0 ? '-' : '';
        if (abs >= 1e9) return sign + (abs / 1e9).toFixed(abs % 1e9 === 0 ? 0 : 1) + 'B';
        if (abs >= 1e6) return sign + (abs / 1e6).toFixed(abs % 1e6 === 0 ? 0 : 1) + 'M';
        if (abs >= 1e3) return sign + (abs / 1e3).toFixed(abs % 1e3 === 0 ? 0 : 1) + 'K';
        return sign + abs.toFixed(0);
      }
      default: return _commas(n, 0);
    }
  }

  return { FORMATS: FORMATS, format: format };
})();
window.ChartFormat = ChartFormat;

/* ===================== Chart Wizard (create/edit modal) ===================== */
const ChartWizard = (() => {
  var editingChartId = null;
  var datasourceId = null;
  var datasourceName = '';
  var availableColumns = [];
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
      value_fields: [],     // up to 3 for bar; others use [0]
      series_field: '',
      show_as: 'value',     // pie: 'value' | 'percent'
      show_values: false,   // stacked bar: show labels (else values appear on hover)
      data_labels: true,    // bar / line
      grid_lines: true,
      number_format: 'comma'
    };
  }

  function _normalize(cfg) {
    cfg = Object.assign(_defaultConfig(), cfg || {});
    if ((!cfg.value_fields || !cfg.value_fields.length) && cfg.value_field) {
      cfg.value_fields = [cfg.value_field];
    }
    if (!cfg.value_fields) cfg.value_fields = [];
    return cfg;
  }

  function init() {
    var overlay = document.getElementById('chart-wizard-overlay');
    if (overlay) {
      overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
    }
  }

  async function openForDatasource(dsId, dsName) {
    editingChartId = null;
    datasourceId = dsId;
    datasourceName = dsName || '';
    config = _defaultConfig();
    await _loadColumnsAndShow();
  }

  async function openWithChart(chart) {
    editingChartId = chart.chart_id;
    datasourceId = chart.datasource_id;
    datasourceName = chart.name || '';
    config = _normalize(chart.chart_config);
    await _loadColumnsAndShow();
  }

  async function _loadColumnsAndShow() {
    var overlay = document.getElementById('chart-wizard-overlay');
    if (overlay) overlay.hidden = false;
    var body = document.getElementById('chart-wizard-body');
    if (body) body.innerHTML = '<div style="padding:32px;text-align:center;color:#6b7280;">Loading data source fields…</div>';

    try {
      showLoading();
      var listResp = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      var datasources = (listResp && listResp.datasources) || [];
      var ds = datasources.find(function (d) { return d.datasource_id === datasourceId; });
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
      var rows = (queryResp && queryResp.rows) || [];
      ChartDashboard._cacheRows(datasourceId, rows, availableColumns);

      if (!config.category_field) config.category_field = _guessCategory(availableColumns);
      if (!config.value_fields.length) {
        var v = _guessValue(availableColumns, rows);
        if (v) config.value_fields = [v];
      }
      renderForm();
    } catch (err) {
      hideLoading();
      console.error('Chart wizard load error:', err);
      if (body) body.innerHTML = '<div style="padding:24px;color:#991b1b;">Failed to load data source fields.</div>';
    }
  }

  function _guessCategory(cols) {
    var prefer = ['date', 'service', 'region', 'account_id', 'resource_id'];
    for (var i = 0; i < prefer.length; i++) if (cols.indexOf(prefer[i]) !== -1) return prefer[i];
    return cols[0] || '';
  }
  function _guessValue(cols, rows) {
    var prefer = ['cost_amount', 'usage_amount', 'cost', 'usage', 'amount'];
    for (var i = 0; i < prefer.length; i++) if (cols.indexOf(prefer[i]) !== -1) return prefer[i];
    if (rows && rows.length) {
      for (var c = 0; c < cols.length; c++) {
        var v = rows[0][cols[c]];
        if (typeof v === 'number' || (!isNaN(parseFloat(v)) && isFinite(v))) return cols[c];
      }
    }
    return cols[cols.length - 1] || '';
  }

  function _label(c) {
    return c.replace(/_/g, ' ').replace(/\b\w/g, function (m) { return m.toUpperCase(); });
  }
  function _colOptions(selected, includeNone) {
    var html = includeNone ? '<option value="">— None —</option>' : '';
    html += availableColumns.map(function (c) {
      return '<option value="' + c + '"' + (c === selected ? ' selected' : '') + '>' + _label(c) + '</option>';
    }).join('');
    return html;
  }
  function _formatSelect() {
    var opts = ChartFormat.FORMATS.map(function (f) {
      return '<option value="' + f.value + '"' + (f.value === config.number_format ? ' selected' : '') + '>' + f.label + '</option>';
    }).join('');
    return '<div style="margin-bottom:14px;">' +
      '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">Number format</label>' +
      '<select id="cw-format" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + opts + '</select>' +
    '</div>';
  }

  function renderForm() {
    var body = document.getElementById('chart-wizard-body');
    if (!body) return;

    var typeButtons = CHART_TYPES.map(function (t) {
      var active = config.type === t.value;
      return '<button type="button" class="chart-type-btn' + (active ? ' active' : '') + '" data-type="' + t.value + '" ' +
        'style="flex:1;min-width:110px;display:flex;flex-direction:column;align-items:center;gap:6px;padding:14px 8px;border:2px solid ' +
        (active ? '#6366f1' : '#e5e7eb') + ';border-radius:8px;background:' + (active ? '#eef2ff' : '#fff') + ';cursor:pointer;">' +
        '<span style="font-size:1.6em;">' + t.icon + '</span>' +
        '<span style="font-weight:600;color:#1f2937;font-size:0.9em;">' + t.label + '</span>' +
      '</button>';
    }).join('');

    body.innerHTML =
      '<div style="margin-bottom:18px;">' +
        '<div style="margin-bottom:12px;padding:8px 12px;background:#eef2ff;border:1px solid #c7d2fe;border-radius:6px;font-size:0.9em;color:#4338ca;font-weight:600;">' +
          'Data source: ' + _esc(datasourceName) +
        '</div>' +
        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">Chart name</label>' +
        '<input type="text" id="cw-name" value="' + _escAttr(datasourceName) + '" placeholder="My Chart" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;margin-bottom:18px;"/>' +
        '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:8px;">Chart type</label>' +
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px;">' + typeButtons + '</div>' +
        _typeFields() +
      '</div>' +
      '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px;padding-top:16px;border-top:1px solid #e5e7eb;">' +
        '<button onclick="ChartWizard.previewChart()" class="btn btn-outline">👁️ Preview</button>' +
        '<button onclick="ChartWizard.saveChart()" class="btn btn-primary" style="background:#8b5cf6;border-color:#8b5cf6;">💾 Save Chart</button>' +
      '</div>' +
      '<div id="cw-preview" style="margin-top:18px;height:320px;display:none;border:1px solid #e5e7eb;border-radius:8px;"></div>';

    _attachFormListeners();
  }

  // Per-chart-type field controls
  function _typeFields() {
    var v0 = config.value_fields[0] || '';
    if (config.type === 'pie') {
      return _field('Group by', '<select id="cw-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.category_field, false) + '</select>') +
        _field('Value', '<select id="cw-value0" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v0, false) + '</select>') +
        _field('Show as', '<select id="cw-showas" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' +
          '<option value="value"' + (config.show_as === 'value' ? ' selected' : '') + '>Total Value</option>' +
          '<option value="percent"' + (config.show_as === 'percent' ? ' selected' : '') + '>Total %</option>' +
        '</select>') +
        _formatSelect();
    }

    if (config.type === 'bar') {
      var v1 = config.value_fields[1] || '';
      var v2 = config.value_fields[2] || '';
      return _field('Category (X axis)', '<select id="cw-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.category_field, false) + '</select>') +
        _field('Value 1', '<select id="cw-value0" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v0, false) + '</select>') +
        _field('Value 2 (optional)', '<select id="cw-value1" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v1, true) + '</select>') +
        _field('Value 3 (optional)', '<select id="cw-value2" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v2, true) + '</select>') +
        _formatSelect() +
        _displayOptions(true, true, false);
    }

    if (config.type === 'stacked_bar') {
      return _field('Category (X axis)', '<select id="cw-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.category_field, false) + '</select>') +
        _field('Value', '<select id="cw-value0" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v0, false) + '</select>') +
        _field('Series (stack by)', '<select id="cw-series" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.series_field, true) + '</select>') +
        _formatSelect() +
        '<div style="display:flex;flex-direction:column;gap:10px;padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;">' +
          '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
            '<input type="checkbox" id="cw-showvalues"' + (config.show_values ? ' checked' : '') + '/>' +
            '<span style="color:#374151;font-size:0.9em;">Show values on chart (otherwise values appear on hover)</span>' +
          '</label>' +
          '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
            '<input type="checkbox" id="cw-grid"' + (config.grid_lines ? ' checked' : '') + '/>' +
            '<span style="color:#374151;font-size:0.9em;">Show grid lines</span>' +
          '</label>' +
        '</div>';
    }

    // line
    return _field('X axis', '<select id="cw-category" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.category_field, false) + '</select>') +
      _field('Value', '<select id="cw-value0" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(v0, false) + '</select>') +
      _field('Series (absolute, optional)', '<select id="cw-series" style="width:100%;padding:8px;border:1px solid #d1d5db;border-radius:6px;">' + _colOptions(config.series_field, true) + '</select>') +
      _formatSelect() +
      _displayOptions(true, true, false);
  }

  function _field(label, control) {
    return '<div style="margin-bottom:14px;">' +
      '<label style="display:block;font-weight:600;color:#374151;font-size:0.9em;margin-bottom:6px;">' + label + '</label>' +
      control + '</div>';
  }

  function _displayOptions(showLabels, showGrid) {
    var html = '<div style="display:flex;flex-direction:column;gap:10px;padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;">';
    if (showLabels) {
      html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
        '<input type="checkbox" id="cw-labels"' + (config.data_labels ? ' checked' : '') + '/>' +
        '<span style="color:#374151;font-size:0.9em;">Show data labels</span></label>';
    }
    if (showGrid) {
      html += '<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">' +
        '<input type="checkbox" id="cw-grid"' + (config.grid_lines ? ' checked' : '') + '/>' +
        '<span style="color:#374151;font-size:0.9em;">Show grid lines</span></label>';
    }
    html += '</div>';
    return html;
  }

  function _attachFormListeners() {
    document.querySelectorAll('.chart-type-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        _readForm();
        config.type = btn.getAttribute('data-type');
        renderForm();
      });
    });
  }

  function _readForm() {
    var g = function (id) { return document.getElementById(id); };
    if (g('cw-name')) datasourceName = g('cw-name').value || datasourceName;
    if (g('cw-category')) config.category_field = g('cw-category').value;
    var vals = [];
    ['cw-value0', 'cw-value1', 'cw-value2'].forEach(function (id) {
      var el = g(id);
      if (el && el.value) vals.push(el.value);
    });
    if (vals.length) config.value_fields = vals;
    if (g('cw-series')) config.series_field = g('cw-series').value;
    if (g('cw-showas')) config.show_as = g('cw-showas').value;
    if (g('cw-showvalues')) config.show_values = g('cw-showvalues').checked;
    if (g('cw-labels')) config.data_labels = g('cw-labels').checked;
    if (g('cw-grid')) config.grid_lines = g('cw-grid').checked;
    if (g('cw-format')) config.number_format = g('cw-format').value;
  }

  function previewChart() {
    _readForm();
    if (!config.value_fields.length) { notify('Please select a value field', 'error'); return; }
    var preview = document.getElementById('cw-preview');
    if (!preview) return;
    preview.style.display = 'block';
    var rows = ChartDashboard._getCachedRows(datasourceId);
    var inst = echarts.getInstanceByDom(preview) || echarts.init(preview);
    inst.setOption(ChartDashboard.buildOption(config, rows), true);
    inst.resize();
  }

  async function saveChart() {
    _readForm();
    if (!config.category_field || !config.value_fields.length) {
      notify('Please choose a category/group field and at least one value field', 'error');
      return;
    }
    var name = (datasourceName || 'Chart').trim();
    if (name.length < 1 || name.length > 100) { notify('Chart name must be 1–100 characters', 'error'); return; }
    try {
      showLoading();
      var payload = { action: 'chart_save', name: name, datasource_id: datasourceId, chart_config: config };
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
  function _esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (m) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]; }); }
  function _escAttr(t) { return String(t == null ? '' : t).replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }

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

  function _container() { return document.getElementById('observe-saved-charts-container'); }
  function _cacheRows(dsId, rows, columns) { rowCache[dsId] = { rows: rows || [], columns: columns || [] }; }
  function _getCachedRows(dsId) { return (rowCache[dsId] && rowCache[dsId].rows) || []; }
  function _num(v) { if (typeof v === 'number') return v; var n = parseFloat(v); return isNaN(n) ? 0 : n; }
  function _fmt(v, cfg) { return ChartFormat.format(v, (cfg && cfg.number_format) || 'comma'); }

  function _uniqueSorted(rows, field) {
    var out = [], seen = {};
    rows.forEach(function (r) {
      var k = String(r[field] == null ? '—' : r[field]);
      if (!seen[k]) { seen[k] = true; out.push(k); }
    });
    out.sort();
    return out;
  }

  /**
   * Build an ECharts option from a chart config + rows.
   */
  function buildOption(config, rows) {
    rows = rows || [];
    config = config || {};
    var fmt = config.number_format || 'comma';
    var valueFields = config.value_fields && config.value_fields.length
      ? config.value_fields
      : (config.value_field ? [config.value_field] : []);
    var cat = config.category_field;
    var grid = (config.grid_lines !== false);

    // ----- Pie -----
    if (config.type === 'pie') {
      var vf = valueFields[0];
      var sums = {};
      rows.forEach(function (r) {
        var k = String(r[cat] == null ? '—' : r[cat]);
        sums[k] = (sums[k] || 0) + _num(r[vf]);
      });
      var data = Object.keys(sums).map(function (k) { return { name: k, value: sums[k] }; });
      var asPercent = (config.show_as === 'percent');
      return {
        color: PALETTE,
        tooltip: {
          trigger: 'item',
          formatter: function (p) {
            return p.name + ': ' + (asPercent ? p.percent + '%' : ChartFormat.format(p.value, fmt)) +
              ' (' + (asPercent ? ChartFormat.format(p.value, fmt) : p.percent + '%') + ')';
          }
        },
        legend: { type: 'scroll', bottom: 0 },
        series: [{
          type: 'pie',
          radius: ['35%', '70%'],
          data: data,
          label: {
            show: true,
            formatter: function (p) { return p.name + ': ' + (asPercent ? p.percent + '%' : ChartFormat.format(p.value, fmt)); }
          }
        }]
      };
    }

    var categories = _uniqueSorted(rows, cat);
    var labelsOn = (config.data_labels !== false);
    var axisTooltip = {
      trigger: 'axis',
      valueFormatter: function (v) { return ChartFormat.format(v, fmt); }
    };
    var baseAxes = {
      grid: { left: 50, right: 20, top: 40, bottom: 70, containLabel: true },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: categories.length > 6 ? 35 : 0 }, splitLine: { show: grid } },
      yAxis: { type: 'value', splitLine: { show: grid }, axisLabel: { formatter: function (v) { return ChartFormat.format(v, fmt); } } }
    };
    var dataLabel = { show: labelsOn, formatter: function (p) { return ChartFormat.format(p.value, fmt); } };

    // ----- Stacked Bar -----
    if (config.type === 'stacked_bar') {
      var vfS = valueFields[0];
      var series = [];
      var showVals = !!config.show_values;
      if (config.series_field) {
        var seriesKeys = _uniqueSorted(rows, config.series_field);
        seriesKeys.forEach(function (sk) {
          var byCat = {};
          rows.forEach(function (r) {
            if (String(r[config.series_field] == null ? '—' : r[config.series_field]) !== sk) return;
            var k = String(r[cat] == null ? '—' : r[cat]);
            byCat[k] = (byCat[k] || 0) + _num(r[vfS]);
          });
          series.push({
            name: sk, type: 'bar', stack: 'total',
            label: { show: showVals, formatter: function (p) { return ChartFormat.format(p.value, fmt); } },
            data: categories.map(function (k) { return byCat[k] || 0; })
          });
        });
      } else {
        var sums2 = {};
        rows.forEach(function (r) { var k = String(r[cat] == null ? '—' : r[cat]); sums2[k] = (sums2[k] || 0) + _num(r[vfS]); });
        series.push({ name: vfS, type: 'bar', stack: 'total',
          label: { show: showVals, formatter: function (p) { return ChartFormat.format(p.value, fmt); } },
          data: categories.map(function (k) { return sums2[k] || 0; }) });
      }
      return Object.assign({ color: PALETTE, tooltip: axisTooltip, legend: { type: 'scroll', top: 0 }, series: series }, baseAxes);
    }

    // ----- Line -----
    if (config.type === 'line') {
      var vfL = valueFields[0];
      var lineSeries = [];
      if (config.series_field) {
        var lkeys = _uniqueSorted(rows, config.series_field);
        lkeys.forEach(function (sk) {
          var byCat2 = {};
          rows.forEach(function (r) {
            if (String(r[config.series_field] == null ? '—' : r[config.series_field]) !== sk) return;
            var k = String(r[cat] == null ? '—' : r[cat]);
            byCat2[k] = (byCat2[k] || 0) + _num(r[vfL]);
          });
          lineSeries.push({ name: sk, type: 'line', smooth: true, label: dataLabel,
            data: categories.map(function (k) { return byCat2[k] || 0; }) });
        });
      } else {
        var sums3 = {};
        rows.forEach(function (r) { var k = String(r[cat] == null ? '—' : r[cat]); sums3[k] = (sums3[k] || 0) + _num(r[vfL]); });
        lineSeries.push({ name: vfL, type: 'line', smooth: true, label: dataLabel,
          data: categories.map(function (k) { return sums3[k] || 0; }) });
      }
      return Object.assign({ color: PALETTE, tooltip: axisTooltip,
        legend: config.series_field ? { type: 'scroll', top: 0 } : { show: false }, series: lineSeries }, baseAxes);
    }

    // ----- Bar (grouped, up to 3 value fields) -----
    var barSeries = valueFields.map(function (vf2) {
      var byCat3 = {};
      rows.forEach(function (r) { var k = String(r[cat] == null ? '—' : r[cat]); byCat3[k] = (byCat3[k] || 0) + _num(r[vf2]); });
      return { name: vf2.replace(/_/g, ' '), type: 'bar',
        label: { show: labelsOn, position: 'top', formatter: function (p) { return ChartFormat.format(p.value, fmt); } },
        data: categories.map(function (k) { return byCat3[k] || 0; }) };
    });
    return Object.assign({ color: PALETTE, tooltip: axisTooltip,
      legend: barSeries.length > 1 ? { type: 'scroll', top: 0 } : { show: false }, series: barSeries }, baseAxes);
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

      Object.keys(instances).forEach(function (id) { try { instances[id].dispose(); } catch (e) {} });
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

      charts.forEach(function (chart) {
        var card = container.querySelector('.chart-card[data-chart-id="' + chart.chart_id + '"]');
        if (!card) return;
        card.querySelector('.chart-action-refresh').onclick = function () { refreshChart(chart); };
        card.querySelector('.chart-action-edit').onclick = function () { ChartWizard.openWithChart(chart); };
        card.querySelector('.chart-action-delete').onclick = function () { deleteChart(chart); };
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
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(function () { try { inst.resize(); } catch (e) {} });
      ro.observe(el);
    }
  }

  async function _ensureRows(dsId) {
    if (rowCache[dsId]) return rowCache[dsId].rows;
    try {
      var listResp = await api('POST', '/members/dashboard-data', { action: 'datasource_list' });
      var datasources = (listResp && listResp.datasources) || [];
      var ds = datasources.find(function (d) { return d.datasource_id === dsId; });
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
    delete rowCache[chart.datasource_id];
    if (window.showLoading) window.showLoading();
    try { await _renderOne(chart); notify('Chart refreshed', 'success'); }
    finally { if (window.hideLoading) window.hideLoading(); }
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
    window.addEventListener('resize', function () {
      Object.keys(instances).forEach(function (id) { try { instances[id].resize(); } catch (e) {} });
    });
  }

  function _esc(t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (m) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]; }); }

  return {
    render: render,
    buildOption: buildOption,
    _cacheRows: _cacheRows,
    _getCachedRows: _getCachedRows
  };
})();

window.ChartDashboard = ChartDashboard;

ChartWizard.init();
