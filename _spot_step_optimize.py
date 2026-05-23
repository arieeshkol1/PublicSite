#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wire the Act > Optimize 'Scan for Savings' button."""

with open('members/members.js', 'r', encoding='utf-8') as f:
    content = f.read()

if '_runOptimizeScan' in content:
    print("Optimize scan already wired -- skipping")
else:
    # Add the optimize scan logic
    optimize_js = r'''

// ============================================================
// Act > Service Optimization -- Scan + Render
// ============================================================

// Tip IDs that belong to "optimization" (active services, pay less)
var OPTIMIZE_TIP_IDS = {
    'ec2-001':1, 'ec2-003':1, 'ec2-009':1, 'ec2-006':1,
    'rds-001':1, 'rds-006':1, 'ebs-001':1,
    'ec2-004':1, 'ec2-011':1, 'ec2-013':1,
    's3-001':1, 's3-004':1, 'lambda-001':1, 'rds-007':1
};

async function _runOptimizeScan() {
    var status = document.getElementById('act-optimize-status');
    var grid = document.getElementById('act-optimize-cards');
    var empty = document.getElementById('act-optimize-empty');
    var btn = document.getElementById('act-optimize-scan-btn');

    if (status) status.textContent = 'Scanning for optimization opportunities...';
    if (grid) grid.innerHTML = '';
    if (empty) empty.style.display = 'none';
    if (btn) { btn.disabled = true; btn.textContent = 'Scanning...'; }

    try {
        _syncActSelection();
        var accountIds = getActSelectedAccountIds();
        var data = await api('POST', '/members/actions/scan', { accountIds: accountIds });

        // Filter findings to optimization-only
        var optFindings = (data.findings || []).filter(function(f) {
            return OPTIMIZE_TIP_IDS[f.tipId] && f.status === 'found';
        });

        // Filter cards to optimization-only
        var optCards = (data.cards || []).filter(function(c) {
            // Cards from optimization checks: ec2-idle (rightsizing), advisory (spot/graviton), etc.
            var t = c.type || '';
            return t === 'ec2-idle' || t === 'advisory' || t === 'rds-idle';
        });

        if (status) {
            var ts = new Date(data.scannedAt || Date.now()).toLocaleTimeString();
            status.textContent = 'Scanned ' + (data.scannedAccounts || 0) + ' account(s) at ' + ts +
                ' \u00b7 ' + optFindings.length + ' optimization finding(s)';
        }

        if (optFindings.length === 0 && optCards.length === 0) {
            if (empty) empty.style.display = 'block';
            if (grid) grid.innerHTML = '<div style="text-align:center;padding:40px;color:#059669;font-size:1.1em;">All services are optimally configured \u2705</div>';
        } else {
            // Render optimization cards
            optCards.forEach(function(card) {
                if (grid) grid.appendChild(_actBuildCard(card));
            });

            // Render findings that don't have cards (newer checks)
            var cardTipIds = {};
            optCards.forEach(function(c) { if (c.tipId) cardTipIds[c.tipId] = true; });

            optFindings.forEach(function(f) {
                if (cardTipIds[f.tipId]) return; // Already rendered as card
                var el = document.createElement('div');
                el.style.cssText = 'background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;';
                var savings = f.savingsUsd ? ' \u00b7 ~$' + f.savingsUsd.toFixed(2) + '/mo' : '';
                el.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                    + '<span style="font-weight:600;color:#1f2937;">' + (f.tipTitle || f.tipId) + '</span>'
                    + '<span style="font-size:0.8em;background:#dbeafe;color:#1e40af;padding:2px 8px;border-radius:4px;">' + (f.service || '') + '</span>'
                    + '</div>'
                    + '<div style="color:#6b7280;font-size:0.9em;">' + (f.message || f.evidence || '') + savings + '</div>';
                if (f.resources && f.resources.length > 0) {
                    var resHtml = '<div style="margin-top:8px;font-size:0.85em;">';
                    f.resources.slice(0, 5).forEach(function(r) {
                        resHtml += '<div style="padding:3px 0;border-top:1px solid #f3f4f6;">'
                            + (r.resourceId || r.id || '') + ' <span style="color:#6b7280;">' + (r.detail || r.resourceType || '') + '</span>'
                            + (r.monthlySavings ? ' <span style="color:#059669;font-weight:600;">~$' + r.monthlySavings.toFixed(2) + '/mo</span>' : '')
                            + '</div>';
                    });
                    if (f.resources.length > 5) resHtml += '<div style="color:#6b7280;">+' + (f.resources.length - 5) + ' more</div>';
                    resHtml += '</div>';
                    el.innerHTML += resHtml;
                }
                if (grid) grid.appendChild(el);
            });
        }
    } catch(err) {
        if (status) status.textContent = 'Scan failed: ' + (err.message || 'Unknown error');
        if (empty) empty.style.display = 'block';
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '\u26a1 Scan for Savings'; }
    }
}

// Wire the button
(function() {
    var btn = document.getElementById('act-optimize-scan-btn');
    if (btn) btn.onclick = _runOptimizeScan;
})();
'''
    content += optimize_js
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Optimize scan button wired and rendering logic added")
