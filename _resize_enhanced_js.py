#!/usr/bin/env python3
"""Enhance resize JS: full spec card + sortable alternatives table."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Replace the analysis rendering with full spec card
old_analysis_render = """        // Render analysis
        var analysisEl = document.getElementById('resize-analysis');
        if (analysisEl) {
            var m = data.metrics || {};
            var html = '<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;">';
            html += '<div style="font-weight:600;margin-bottom:8px;">Usage Analysis: ' + data.instanceName + '</div>';
            html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;">';
            html += '<div style="text-align:center;"><div style="font-size:1.5em;font-weight:700;color:' + (m.cpu_avg < 20 ? '#059669' : m.cpu_avg < 50 ? '#d97706' : '#dc2626') + ';">' + (m.cpu_avg || 0) + '%</div><div style="font-size:0.75em;color:#6b7280;">CPU Avg</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.5em;font-weight:700;">' + (m.cpu_max || 0) + '%</div><div style="font-size:0.75em;color:#6b7280;">CPU Max</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.5em;font-weight:700;">' + (m.mem_avg !== null ? m.mem_avg + '%' : 'N/A') + '</div><div style="font-size:0.75em;color:#6b7280;">Memory Avg</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.5em;font-weight:700;">$' + (data.currentSpecs.monthlyRate || 0) + '</div><div style="font-size:0.75em;color:#6b7280;">Current/mo</div></div>';"""

new_analysis_render = """        // Render analysis - full spec card
        var analysisEl = document.getElementById('resize-analysis');
        if (analysisEl) {
            var m = data.metrics || {};
            var s = data.currentSpecs || {};
            var html = '<div style="background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;">';
            html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">';
            html += '<div style="font-weight:700;font-size:1.1em;">' + data.instanceName + ' <span style="color:#6b7280;font-weight:400;">(' + data.currentType + ')</span></div>';
            html += '<div style="font-size:1.3em;font-weight:700;color:#1f2937;">$' + (s.monthlyRate || 0) + '<span style="font-size:0.5em;color:#6b7280;">/mo</span></div>';
            html += '</div>';
            // Full specs grid
            html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;font-size:0.85em;">';
            var specs = [
                ['vCPU', s.vcpu || 0],
                ['Memory', (s.memory || 0) + ' GB'],
                ['Platform', data.platform || ''],
                ['Architecture', data.architecture || ''],
                ['Network', s.networkPerformance || 'N/A'],
                ['EBS Optimized', s.ebsOptimized || 'N/A'],
                ['EBS Max IOPS', s.ebsMaxIops ? s.ebsMaxIops.toLocaleString() : 'N/A'],
                ['EBS Bandwidth', s.ebsMaxBandwidthMbps ? s.ebsMaxBandwidthMbps + ' Mbps' : 'N/A'],
                ['Processor', s.processorManufacturer || 'N/A'],
                ['Clock Speed', s.processor ? s.processor + ' GHz' : 'N/A'],
                ['Burstable', s.burstable ? 'Yes' : 'No'],
                ['Storage', s.instanceStorageSupported ? s.instanceStorageGB + ' GB ' + s.instanceStorageType : 'EBS only'],
                ['Hypervisor', s.hypervisor || 'N/A'],
                ['Generation', s.currentGeneration ? 'Current' : 'Previous'],
                ['Free Tier', s.freeTierEligible ? 'Yes' : 'No'],
                ['State', data.state || ''],
            ];
            specs.forEach(function(sp) {
                html += '<div><span style="color:#6b7280;">' + sp[0] + ':</span> <strong>' + sp[1] + '</strong></div>';
            });
            html += '</div>';
            // Usage metrics
            html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding:8px 0;border-top:1px solid #e5e7eb;font-size:0.85em;">';
            html += '<div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;color:' + (m.cpu_avg < 20 ? '#059669' : m.cpu_avg < 50 ? '#d97706' : '#dc2626') + ';">' + (m.cpu_avg || 0) + '%</div><div style="font-size:0.75em;color:#6b7280;">CPU Avg (30d)</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">' + (m.cpu_max || 0) + '%</div><div style="font-size:0.75em;color:#6b7280;">CPU Max</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">' + (m.mem_avg !== null ? m.mem_avg + '%' : 'N/A') + '</div><div style="font-size:0.75em;color:#6b7280;">Memory Avg</div></div>';
            html += '<div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">' + (m.mem_max !== null ? m.mem_max + '%' : 'N/A') + '</div><div style="font-size:0.75em;color:#6b7280;">Memory Max</div></div>';"""

if old_analysis_render in js:
    js = js.replace(old_analysis_render, new_analysis_render)
    print("1. Analysis rendering enhanced with full spec card")
else:
    print("1. WARNING: Could not find old analysis render")

# Replace the recommendations rendering with a sortable table
old_recs_render = """        // Render recommendations
        var recsEl = document.getElementById('resize-recommendations');
        if (recsEl) {
            var recs = data.recommendations || [];
            if (recs.length === 0) {
                recsEl.innerHTML = '<div style="padding:16px;background:#f9fafb;border-radius:8px;text-align:center;color:#6b7280;">This instance is already optimally sized. No cheaper options available.</div>';
            } else {
                var html = '<div style="font-weight:600;margin-bottom:8px;">Recommended Sizes</div>';
                html += '<div style="display:grid;gap:8px;">';
                recs.forEach(function(r, i) {
                    var border = i === 0 ? 'border:2px solid #059669;' : 'border:1px solid #e5e7eb;';
                    html += '<div style="background:#fff;' + border + 'border-radius:8px;padding:12px;display:flex;justify-content:space-between;align-items:center;">';
                    html += '<div>';
                    html += '<div style="font-weight:600;">' + r.instanceType + (r.isGraviton ? ' <span style="background:#dbeafe;color:#1e40af;padding:1px 6px;border-radius:4px;font-size:0.75em;">Graviton</span>' : '') + '</div>';
                    html += '<div style="font-size:0.8em;color:#6b7280;">' + r.vcpu + ' vCPU, ' + r.memory + ' GB RAM - $' + r.monthlyRate + '/mo</div>';
                    if (r.warning) html += '<div style="font-size:0.75em;color:#b45309;">' + r.warning + '</div>';
                    html += '</div>';
                    html += '<div style="text-align:right;">';
                    html += '<div style="font-weight:700;color:#059669;font-size:1.1em;">-$' + r.monthlySavings + '/mo</div>';
                    html += '<div style="font-size:0.75em;color:#6b7280;">(' + r.savingsPercent + '% savings)</div>';
                    html += '<button class="btn btn-primary btn-sm" style="margin-top:4px;font-size:0.8em;padding:4px 12px;" onclick="_resizeExecute(\'' + r.instanceType + '\')">Resize</button>';
                    html += '</div></div>';
                });
                html += '</div>';
                recsEl.innerHTML = html;
            }
        }"""

new_recs_render = r"""        // Render recommendations as sortable table
        var recsEl = document.getElementById('resize-recommendations');
        if (recsEl) {
            var recs = data.recommendations || [];
            if (recs.length === 0) {
                recsEl.innerHTML = '<div style="padding:16px;background:#f9fafb;border-radius:8px;text-align:center;color:#6b7280;">This instance is already optimally sized. No cheaper options available.</div>';
            } else {
                window._resizeRecs = recs;
                window._resizeSortCol = 'monthlyRate';
                window._resizeSortAsc = true;
                _renderResizeTable();
            }
        }"""

if old_recs_render in js:
    js = js.replace(old_recs_render, new_recs_render)
    print("2. Recommendations rendering replaced with sortable table")
else:
    print("2. WARNING: Could not find old recs render")

# Add the sortable table rendering function
table_fn = r"""

function _renderResizeTable() {
    var el = document.getElementById('resize-recommendations');
    if (!el || !window._resizeRecs) return;
    var recs = window._resizeRecs.slice();
    var col = window._resizeSortCol || 'monthlyRate';
    var asc = window._resizeSortAsc;
    recs.sort(function(a, b) {
        var va = a[col] || 0, vb = b[col] || 0;
        if (typeof va === 'string') { va = va.toLowerCase(); vb = (vb||'').toLowerCase(); }
        return asc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
    var cols = [
        {key:'instanceType', label:'Type', w:'120px'},
        {key:'vcpu', label:'vCPU', w:'50px'},
        {key:'memory', label:'RAM (GB)', w:'65px'},
        {key:'monthlyRate', label:'$/mo', w:'65px'},
        {key:'monthlySavings', label:'Savings', w:'70px'},
        {key:'networkPerformance', label:'Network', w:'90px'},
        {key:'ebsMaxIops', label:'EBS IOPS', w:'70px'},
        {key:'burstable', label:'Burst', w:'45px'},
        {key:'processorManufacturer', label:'CPU', w:'60px'},
    ];
    var html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">';
    html += '<div style="font-weight:600;">Alternative Instance Types</div>';
    html += '<div style="font-size:0.75em;color:#6b7280;">Click column headers to sort</div></div>';
    html += '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:0.82em;">';
    html += '<thead><tr style="background:#f9fafb;">';
    cols.forEach(function(c) {
        var arrow = col === c.key ? (asc ? ' \u25B2' : ' \u25BC') : '';
        html += '<th style="padding:6px 8px;text-align:left;cursor:pointer;white-space:nowrap;border-bottom:2px solid #e5e7eb;font-weight:600;color:#374151;" onclick="_resizeSort(\'' + c.key + '\')">' + c.label + arrow + '</th>';
    });
    html += '<th style="padding:6px 8px;border-bottom:2px solid #e5e7eb;"></th></tr></thead><tbody>';
    recs.forEach(function(r, i) {
        var bg = i === 0 ? 'background:#f0fdf4;' : (i % 2 === 0 ? 'background:#fff;' : 'background:#f9fafb;');
        html += '<tr style="' + bg + '">';
        html += '<td style="padding:6px 8px;font-weight:600;border-bottom:1px solid #f3f4f6;">' + r.instanceType;
        if (r.isGraviton) html += ' <span style="background:#dbeafe;color:#1e40af;padding:0 4px;border-radius:3px;font-size:0.8em;">ARM</span>';
        html += '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">' + r.vcpu + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">' + r.memory + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;font-weight:600;">$' + r.monthlyRate + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;color:#059669;font-weight:600;">-$' + r.monthlySavings + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;font-size:0.9em;">' + (r.networkPerformance || 'N/A') + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">' + (r.ebsMaxIops ? r.ebsMaxIops.toLocaleString() : 'N/A') + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;">' + (r.burstable ? 'Yes' : 'No') + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;font-size:0.9em;">' + (r.processorManufacturer || '') + '</td>';
        html += '<td style="padding:6px 8px;border-bottom:1px solid #f3f4f6;"><button class="btn btn-primary btn-sm" style="font-size:0.75em;padding:3px 10px;" onclick="_resizeExecute(\'' + r.instanceType + '\')">Resize</button></td>';
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
}

function _resizeSort(col) {
    if (window._resizeSortCol === col) {
        window._resizeSortAsc = !window._resizeSortAsc;
    } else {
        window._resizeSortCol = col;
        window._resizeSortAsc = true;
    }
    _renderResizeTable();
}
"""

if '_renderResizeTable' not in js:
    js += table_fn
    print("3. Sortable table functions added")
else:
    print("3. Table functions already present")

# Rename the button from "Analyze Usage" to "Optimize"
js = js.replace(
    "'>&#128270; Analyze Usage</button>",
    "'>&#128270; Optimize</button>"
)

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(js)

print("JS enhanced - done")
