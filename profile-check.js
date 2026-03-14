// Visibility score tracker
const visibilityFactors = {
    ipDetected: false,
    locationDetected: false,
    ispDetected: false,
    browserDetailed: false,
    platformDetected: false,
    screenDetected: false,
    cookiesEnabled: false,
    languageDetected: false,
    hardwareDetected: false,
    dntDisabled: false,
    canvasFingerprint: false,
    audioFingerprint: false,
    webrtcLeaking: false,
    noAdBlocker: false,
    notIncognito: false,
    connectionExposed: false
};

let vpnDetected = false;

// Common VPN/proxy provider keywords
const VPN_KEYWORDS = [
    'vpn', 'proxy', 'tunnel', 'private', 'express', 'nord', 'surfshark',
    'cyberghost', 'mullvad', 'proton', 'windscribe', 'pia ', 'ipvanish',
    'hotspot', 'hide.me', 'torguard', 'astrill', 'purevpn', 'strongvpn',
    'hosting', 'datacenter', 'data center', 'cloud', 'server', 'colocation',
    'digitalocean', 'linode', 'vultr', 'hetzner', 'ovh', 'amazon', 'google cloud',
    'microsoft azure', 'cloudflare warp', 'warp', 'anonine', 'perfect privacy',
    'zenmate', 'tunnelbear', 'avast', 'kaspersky', 'bitdefender', 'f-secure',
    'freedome', 'encrypt.me', 'getflix', 'unlocator', 'smartdns', 'zscaler',
    'fortinet', 'palo alto', 'cisco', 'anyconnect', 'openconnect',
    'm247', 'datacamp', 'leaseweb', 'choopa', 'frantech', 'buyvm',
    'quadranet', 'psychz', 'cogent', 'zenlayer', 'i2ts', 'tzulo',
    'privax', 'kape', 'aura', 'pango', 'hotspot shield', 'hola',
    'torproject', 'tor exit', 'bright data', 'luminati', 'oxylabs',
    'smartproxy', 'geosurf', 'netnut', 'iproyal', 'webshare'
];

// Known VPN extension IDs (Chrome Web Store)
const VPN_EXTENSION_IDS = [
    { id: 'gkojfkhlekighikafcpjkiklfbnlmeio', name: 'Hola VPN', leaksAPI: true },
    { id: 'bihmplhobchoageeokmgbdihknkjbknd', name: 'Touch VPN' },
    { id: 'jhfklhiamjnhemkbcpjlajfmnhcmpkod', name: 'uVPN' },
    { id: 'eppiocemhmnlbhjplcgkofciiegomcon', name: 'Browsec VPN' },
    { id: 'lnfdkeljbhflnalpdkgmhbhimhcepnkn', name: 'Hotspot Shield' },
    { id: 'fgddmllnllkalaagkghckoinaemmogpe', name: 'Windscribe' },
    { id: 'kpiecbcckbofpmkkkdibbllpinceiihk', name: 'Urban VPN' },
    { id: 'gjknjjomckknofjidppipffbpoekiipm', name: 'Proton VPN' },
    { id: 'hnmpcagpplmpfistknnnfhdbhhnhnljh', name: 'SetupVPN' },
    { id: 'omghfjlpggmjjaagoclmmobgdodcjboh', name: 'Betternet' }
];

function detectVPN(org, ipTimezone, extraData) {
    let reasons = [];
    
    // Check ISP name against known VPN/datacenter keywords
    if (org) {
        const orgLower = org.toLowerCase();
        const matched = VPN_KEYWORDS.find(kw => orgLower.includes(kw));
        if (matched) {
            reasons.push('ISP matches known VPN/datacenter (' + matched + ')');
        }
    }
    
    // Check timezone mismatch: browser timezone vs IP-reported timezone
    if (ipTimezone) {
        const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (browserTz && ipTimezone !== browserTz) {
            reasons.push('Timezone mismatch (browser: ' + browserTz + ', IP: ' + ipTimezone + ')');
        }
    }
    
    // Check extra API flags if available (ipapi.co provides these)
    if (extraData) {
        if (extraData.proxy === true) reasons.push('Proxy flag detected');
        if (extraData.hosting === true) reasons.push('Hosting/datacenter IP');
    }
    
    // Try WebRTC leak detection — if WebRTC is blocked, likely VPN/privacy tool
    try {
        if (typeof RTCPeerConnection === 'undefined' && typeof webkitRTCPeerConnection === 'undefined') {
            reasons.push('WebRTC disabled (privacy tool likely)');
        }
    } catch (e) {
        reasons.push('WebRTC blocked');
    }
    
    // Detect browser-extension VPNs by checking for known extension DOM injections
    try {
        for (const ext of VPN_EXTENSION_IDS) {
            if (document.querySelector(`[src*="${ext.id}"]`) || 
                document.querySelector(`link[href*="${ext.id}"]`) ||
                document.querySelector(`[data-extension-id="${ext.id}"]`)) {
                const leak = ext.leaksAPI ? ' (⚠️ leaks real IP on API calls)' : '';
                reasons.push(ext.name + ' extension detected' + leak);
                break;
            }
        }
        // Check for common VPN extension DOM watermarks
        const vpnSelectors = [
            '[class*="hola"]', '[id*="hola"]',
            '[class*="browsec"]', '[id*="browsec"]',
            '[class*="windscribe"]', '[id*="windscribe"]',
            '[class*="touch-vpn"]', '[id*="touch-vpn"]',
            '[class*="urban-vpn"]', '[id*="urban-vpn"]'
        ];
        for (const sel of vpnSelectors) {
            if (document.querySelector(sel)) {
                const name = sel.match(/\*="([^"]+)"/)[1].replace('-', ' ');
                if (!reasons.some(r => r.toLowerCase().includes(name))) {
                    reasons.push('VPN watermark detected (' + name + ')');
                }
                break;
            }
        }
    } catch (e) { /* ignore */ }
    
    vpnReasons = reasons;
    return reasons.length > 0;
}

let vpnReasons = [];

function calculateVisibilityScore() {
    let score = 0;
    const weights = {
        ipDetected: 15,
        locationDetected: 12,
        ispDetected: 8,
        browserDetailed: 8,
        platformDetected: 5,
        screenDetected: 4,
        cookiesEnabled: 8,
        languageDetected: 3,
        hardwareDetected: 4,
        dntDisabled: 5,
        canvasFingerprint: 8,
        audioFingerprint: 5,
        webrtcLeaking: 5,
        noAdBlocker: 3,
        notIncognito: 2,
        connectionExposed: 3
    };
    for (const [key, detected] of Object.entries(visibilityFactors)) {
        if (detected) score += weights[key] || 0;
    }
    // VPN hides real IP, location, and ISP — reduce those contributions
    if (vpnDetected) {
        if (visibilityFactors.ipDetected) score -= 12;
        if (visibilityFactors.locationDetected) score -= 10;
        if (visibilityFactors.ispDetected) score -= 6;
    }
    return Math.max(0, Math.min(score, 100));
}

function updateMeter() {
    const visibilityScore = calculateVisibilityScore();
    const score = 100 - visibilityScore; // Invert: 100% = invisible, 0% = easy target
    const angle = 90 - (score / 100) * 180;
    const needle = document.getElementById('meter-needle');
    if (needle) {
        needle.setAttribute('transform', `rotate(${angle}, 150, 160)`);
    }

    const label = document.getElementById('meter-score-label');
    const detail = document.getElementById('meter-score-detail');
    if (!label || !detail) return;

    let labelText, detailText, color;
    if (score >= 80) {
        labelText = 'Invisible'; color = '#10b981';
        detailText = 'You are well hidden — very little is exposed';
    } else if (score >= 60) {
        labelText = 'Low Profile'; color = '#84cc16';
        detailText = 'Minimal information is visible about you';
    } else if (score >= 40) {
        labelText = 'Moderate'; color = '#f59e0b';
        detailText = 'A fair amount of your profile is detectable';
    } else if (score >= 20) {
        labelText = 'Exposed'; color = '#f97316';
        detailText = 'Most of your information is visible to websites';
    } else {
        labelText = 'Easy Target'; color = '#ef4444';
        detailText = 'Your full profile is exposed — consider using a VPN';
    }
    label.textContent = `${score}% — ${labelText}`;
    label.style.color = color;
    detail.textContent = vpnDetected
        ? `🛡️ VPN Detected — ${detailText}`
        : detailText;
}

// ─── WebRTC Local IP Leak Detection ───
async function detectWebRTCLeak() {
    return new Promise((resolve) => {
        const ips = [];
        try {
            const PeerConn = window.RTCPeerConnection || window.webkitRTCPeerConnection;
            if (!PeerConn) { resolve({ leaking: false, ips: [], blocked: true }); return; }
            const pc = new PeerConn({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] });
            const timeout = setTimeout(() => { pc.close(); resolve({ leaking: ips.length > 0, ips, blocked: false }); }, 3000);
            pc.onicecandidate = (e) => {
                if (!e || !e.candidate || !e.candidate.candidate) return;
                const parts = e.candidate.candidate.split(' ');
                const ip = parts[4];
                if (ip && !ip.includes(':') && ip !== '0.0.0.0' && !ips.includes(ip)) {
                    ips.push(ip);
                }
            };
            pc.createDataChannel('');
            pc.createOffer().then(offer => pc.setLocalDescription(offer)).catch(() => {
                clearTimeout(timeout); pc.close();
                resolve({ leaking: false, ips: [], blocked: true });
            });
        } catch (e) {
            resolve({ leaking: false, ips: [], blocked: true });
        }
    });
}

// ─── Canvas Fingerprint Detection ───
function getCanvasFingerprint() {
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 200; canvas.height = 50;
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillStyle = '#f60';
        ctx.fillRect(50, 0, 100, 50);
        ctx.fillStyle = '#069';
        ctx.fillText('Fingerprint test 🎨', 2, 15);
        ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
        ctx.fillText('Canvas check', 4, 35);
        const dataUrl = canvas.toDataURL();
        // If canvas returns blank or uniform data, it's being blocked
        const isBlocked = dataUrl === 'data:,' || dataUrl.length < 1000;
        // Generate a simple hash for display
        let hash = 0;
        for (let i = 0; i < dataUrl.length; i++) {
            hash = ((hash << 5) - hash) + dataUrl.charCodeAt(i);
            hash |= 0;
        }
        return { blocked: isBlocked, hash: Math.abs(hash).toString(16).substring(0, 12), unique: !isBlocked };
    } catch (e) {
        return { blocked: true, hash: 'N/A', unique: false };
    }
}

// ─── AudioContext Fingerprint Detection ───
async function getAudioFingerprint() {
    try {
        const AudioCtx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
        if (!AudioCtx) return { blocked: true, hash: 'N/A' };
        const ctx = new AudioCtx(1, 44100, 44100);
        const oscillator = ctx.createOscillator();
        oscillator.type = 'triangle';
        oscillator.frequency.setValueAtTime(10000, ctx.currentTime);
        const compressor = ctx.createDynamicsCompressor();
        oscillator.connect(compressor);
        compressor.connect(ctx.destination);
        oscillator.start(0);
        const buffer = await ctx.startRendering();
        const data = buffer.getChannelData(0);
        let hash = 0;
        for (let i = 4500; i < 5000; i++) {
            hash = ((hash << 5) - hash) + Math.round(data[i] * 1000000);
            hash |= 0;
        }
        return { blocked: false, hash: Math.abs(hash).toString(16).substring(0, 12) };
    } catch (e) {
        return { blocked: true, hash: 'N/A' };
    }
}

// ─── Ad Blocker Detection ───
async function detectAdBlocker() {
    try {
        const testAd = document.createElement('div');
        testAd.innerHTML = '&nbsp;';
        testAd.className = 'adsbox ad-banner ad-placement textads banner-ads';
        testAd.style.cssText = 'position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;';
        document.body.appendChild(testAd);
        await new Promise(r => setTimeout(r, 100));
        const blocked = testAd.offsetHeight === 0 || testAd.clientHeight === 0 ||
            getComputedStyle(testAd).display === 'none';
        document.body.removeChild(testAd);
        if (blocked) return true;
        // Also try fetching a known ad script URL
        try {
            const resp = await fetch('https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js', 
                { method: 'HEAD', mode: 'no-cors' });
            return false;
        } catch (e) {
            return true;
        }
    } catch (e) {
        return false;
    }
}

// ─── Incognito / Private Mode Detection ───
async function detectIncognito() {
    // Method 1: Storage quota (Chrome incognito has limited quota)
    if (navigator.storage && navigator.storage.estimate) {
        try {
            const est = await navigator.storage.estimate();
            if (est.quota && est.quota < 120000000) return true; // ~120MB = incognito
        } catch (e) { /* ignore */ }
    }
    // Method 2: FileSystem API (not available in incognito on older Chrome)
    return new Promise((resolve) => {
        if (window.webkitRequestFileSystem) {
            window.webkitRequestFileSystem(window.TEMPORARY, 100, () => resolve(false), () => resolve(true));
        } else {
            resolve(false);
        }
    });
}

// ─── Connection / Network Info ───
function getConnectionInfo() {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!conn) return null;
    return {
        effectiveType: conn.effectiveType || 'N/A',
        downlink: conn.downlink ? conn.downlink + ' Mbps' : 'N/A',
        rtt: conn.rtt ? conn.rtt + ' ms' : 'N/A',
        saveData: conn.saveData || false
    };
}

// ─── Advanced Privacy Checks (new section) ───
async function runAdvancedChecks() {
    const advDiv = document.getElementById('advanced-info');
    if (!advDiv) return;
    let html = '';

    // WebRTC Leak
    const webrtc = await detectWebRTCLeak();
    let webrtcStatus, webrtcColor;
    if (webrtc.blocked) {
        webrtcStatus = '🛡️ Blocked (protected)'; webrtcColor = '#10b981';
    } else if (webrtc.leaking && webrtc.ips.length > 0) {
        webrtcStatus = '⚠️ Leaking: ' + webrtc.ips.join(', '); webrtcColor = '#ef4444';
        visibilityFactors.webrtcLeaking = true;
    } else {
        webrtcStatus = '✅ No local IPs exposed'; webrtcColor = '#10b981';
    }
    html += `<div class="info-row">
        <span class="info-label">WebRTC IP Leak</span>
        <span class="info-value" style="color:${webrtcColor}">${webrtcStatus}</span>
    </div>`;

    // Canvas Fingerprint
    const canvas = getCanvasFingerprint();
    if (canvas.unique) visibilityFactors.canvasFingerprint = true;
    html += `<div class="info-row">
        <span class="info-label">Canvas Fingerprint</span>
        <span class="info-value" style="color:${canvas.blocked ? '#10b981' : '#ef4444'}">
            ${canvas.blocked ? '🛡️ Blocked' : '⚠️ Trackable (hash: ' + canvas.hash + ')'}
        </span>
    </div>`;

    // Audio Fingerprint
    const audio = await getAudioFingerprint();
    if (!audio.blocked) visibilityFactors.audioFingerprint = true;
    html += `<div class="info-row">
        <span class="info-label">Audio Fingerprint</span>
        <span class="info-value" style="color:${audio.blocked ? '#10b981' : '#f59e0b'}">
            ${audio.blocked ? '🛡️ Blocked' : '⚠️ Detectable (hash: ' + audio.hash + ')'}
        </span>
    </div>`;

    // Ad Blocker
    const adBlocked = await detectAdBlocker();
    if (!adBlocked) visibilityFactors.noAdBlocker = true;
    html += `<div class="info-row">
        <span class="info-label">Ad Blocker</span>
        <span class="info-value" style="color:${adBlocked ? '#10b981' : '#f59e0b'}">
            ${adBlocked ? '🛡️ Active' : '⚠️ Not detected — ads can track you'}
        </span>
    </div>`;

    // Incognito Mode
    const incognito = await detectIncognito();
    if (!incognito) visibilityFactors.notIncognito = true;
    html += `<div class="info-row">
        <span class="info-label">Private / Incognito Mode</span>
        <span class="info-value" style="color:${incognito ? '#10b981' : '#f59e0b'}">
            ${incognito ? '🛡️ Active' : '⚠️ Not in private mode'}
        </span>
    </div>`;

    // Connection Info
    const conn = getConnectionInfo();
    if (conn) {
        visibilityFactors.connectionExposed = true;
        html += `<div class="info-row">
            <span class="info-label">Network Type</span>
            <span class="info-value">${conn.effectiveType}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Downlink Speed</span>
            <span class="info-value">${conn.downlink}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Round-Trip Time</span>
            <span class="info-value">${conn.rtt}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Data Saver</span>
            <span class="info-value">${conn.saveData ? 'Enabled' : 'Disabled'}</span>
        </div>`;
    } else {
        html += `<div class="info-row">
            <span class="info-label">Network Info API</span>
            <span class="info-value" style="color:#10b981">🛡️ Not exposed</span>
        </div>`;
    }

    // Do Not Track
    const dnt = navigator.doNotTrack || window.doNotTrack;
    html += `<div class="info-row">
        <span class="info-label">Do Not Track</span>
        <span class="info-value" style="color:${dnt === '1' ? '#10b981' : '#f59e0b'}">
            ${dnt === '1' ? '🛡️ Enabled' : '⚠️ Disabled — sites can track freely'}
        </span>
    </div>`;

    // HTTPS
    const isHTTPS = window.location.protocol === 'https:';
    html += `<div class="info-row">
        <span class="info-label">HTTPS Connection</span>
        <span class="info-value" style="color:${isHTTPS ? '#10b981' : '#ef4444'}">
            ${isHTTPS ? '✅ Secure' : '⚠️ Not secure — traffic can be intercepted'}
        </span>
    </div>`;

    // Referrer Policy
    const referrer = document.referrer;
    html += `<div class="info-row">
        <span class="info-label">Referrer Exposed</span>
        <span class="info-value" style="color:${referrer ? '#f59e0b' : '#10b981'}">
            ${referrer ? '⚠️ ' + referrer : '✅ No referrer sent'}
        </span>
    </div>`;

    advDiv.innerHTML = html;
    updateMeter();
}

// Fetch IP information - try multiple services and cross-check for VPN leaks
async function getIPInfo() {
    const ipInfoDiv = document.getElementById('ip-info');
    let latitude = null, longitude = null, city = 'Unknown';
    let primaryData = null, secondaryIP = null;
    
    // Primary: fetch-based API (browser-extension VPNs like Hola do NOT proxy fetch)
    try {
        const response = await fetch('https://ipapi.co/json/');
        if (response.ok) primaryData = await response.json();
    } catch (e) { /* will use fallback */ }
    
    if (!primaryData) {
        try {
            const ipResp = await fetch('https://api.ipify.org?format=json');
            const ipData = await ipResp.json();
            const geoResp = await fetch(`https://ip-api.com/json/${ipData.ip}`);
            const geoData = await geoResp.json();
            primaryData = {
                ip: ipData.ip, org: geoData.isp, country_name: geoData.country,
                country: geoData.countryCode, region: geoData.regionName,
                city: geoData.city, timezone: geoData.timezone,
                latitude: geoData.lat, longitude: geoData.lon
            };
        } catch (e) {
            ipInfoDiv.innerHTML = `<div class="info-row"><span class="info-label">Status</span><span class="info-value">Unable to fetch IP information</span></div>`;
            return;
        }
    }
    
    // Secondary: Cloudflare trace (browser-extension VPNs DO proxy page resources)
    try {
        const traceResp = await fetch('https://www.cloudflare.com/cdn-cgi/trace');
        const traceText = await traceResp.text();
        const ipMatch = traceText.match(/ip=(.+)/);
        if (ipMatch) secondaryIP = ipMatch[1].trim();
    } catch (e) { /* Cloudflare trace unavailable */ }
    
    latitude = primaryData.latitude;
    longitude = primaryData.longitude;
    city = primaryData.city || 'Unknown';
    
    // Detect VPN from primary data
    vpnDetected = detectVPN(primaryData.org, primaryData.timezone, primaryData);

    // Cross-check: if secondary IP differs from primary, we have a split-tunnel VPN
    let splitTunnel = false, vpnGeoData = null;
    if (secondaryIP && secondaryIP !== primaryData.ip) {
        splitTunnel = true;
        vpnDetected = true;
        if (!vpnReasons.includes('Split-tunnel detected')) {
            vpnReasons.push('Split-tunnel detected — page proxy IP (' + secondaryIP + ') differs from API IP (' + primaryData.ip + ')');
        }
        try {
            const vpnGeoResp = await fetch(`https://ipapi.co/${secondaryIP}/json/`);
            if (vpnGeoResp.ok) vpnGeoData = await vpnGeoResp.json();
        } catch (e) {
            try {
                const vpnGeoResp2 = await fetch(`https://ip-api.com/json/${secondaryIP}`);
                const d = await vpnGeoResp2.json();
                vpnGeoData = { ip: secondaryIP, country_name: d.country, city: d.city, latitude: d.lat, longitude: d.lon, org: d.isp };
            } catch (e2) { /* ignore */ }
        }
    }
    
    // Build IP info display
    let infoHTML = '';
    if (vpnDetected) {
        infoHTML += `<div class="info-row" style="background: #d1fae5; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
            <span class="info-label" style="color: #065f46;">🛡️ VPN / Proxy Detected</span>
            <span class="info-value" style="color: #065f46; font-family: inherit; font-size: 13px;">${vpnReasons.join(' • ')}</span>
        </div>`;
    }
    if (splitTunnel && vpnGeoData) {
        infoHTML += `<div class="info-row" style="background: #fef3c7; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
            <span class="info-label" style="color: #92400e;">⚠️ VPN Leak Detected</span>
            <span class="info-value" style="color: #92400e; font-family: inherit; font-size: 13px;">Your VPN shows ${vpnGeoData.country_name || 'unknown'} but API calls leak your real IP in ${primaryData.country_name || 'unknown'}</span>
        </div>`;
        infoHTML += `<div class="info-row" style="background: #eff6ff; border-radius: 8px; padding: 8px 12px; margin-bottom: 4px;">
            <span class="info-label" style="color: #1e40af;">🌐 VPN IP</span>
            <span class="info-value" style="color: #1e40af;">${secondaryIP} (${vpnGeoData.country_name || 'N/A'}, ${vpnGeoData.city || 'N/A'})</span>
        </div>`;
    }

    infoHTML += `
        <div class="info-row"><span class="info-label">${splitTunnel ? '🔓 Real IP Address' : 'IP Address'}</span><span class="info-value">${primaryData.ip || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">ISP</span><span class="info-value">${primaryData.org || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">Country</span><span class="info-value">${primaryData.country_name || 'N/A'} (${primaryData.country || 'N/A'})</span></div>
        <div class="info-row"><span class="info-label">Region</span><span class="info-value">${primaryData.region || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">City</span><span class="info-value">${primaryData.city || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">Timezone</span><span class="info-value">${primaryData.timezone || 'N/A'}</span></div>
        <div class="info-row"><span class="info-label">Latitude / Longitude</span><span class="info-value">${primaryData.latitude || 'N/A'} / ${primaryData.longitude || 'N/A'}</span></div>
    `;
    ipInfoDiv.innerHTML = infoHTML;
    
    // Initialize map
    if (splitTunnel && vpnGeoData && vpnGeoData.latitude && vpnGeoData.longitude) {
        initMapDual(
            primaryData.latitude, primaryData.longitude, primaryData.city || 'Unknown',
            vpnGeoData.latitude, vpnGeoData.longitude, vpnGeoData.city || vpnGeoData.country_name || 'VPN'
        );
    } else if (latitude && longitude) {
        initMap(latitude, longitude, city, vpnDetected);
    }
    
    // Update visibility score
    if (primaryData.ip) visibilityFactors.ipDetected = true;
    if (primaryData.city || primaryData.region) visibilityFactors.locationDetected = true;
    if (primaryData.org) visibilityFactors.ispDetected = true;
    updateMeter();
}

// Initialize map with location
function initMap(lat, lon, city, isVPN) {
    try {
        const map = L.map('map').setView([lat, lon], isVPN ? 4 : 10);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(map);

        if (isVPN) {
            const vpnIcon = L.divIcon({
                html: '<div style="background:#f59e0b;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
                iconSize: [16, 16], iconAnchor: [8, 8], className: ''
            });
            L.marker([lat, lon], { icon: vpnIcon }).addTo(map)
                .bindPopup(`<b>🛡️ VPN Server Location</b><br>${city}<br><span style="color:#92400e;font-size:12px;">This is NOT your real location</span>`).openPopup();
            L.circle([lat, lon], { color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.15, radius: 20000, dashArray: '8, 8' }).addTo(map);

            const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const tzCoords = getTimezoneCoords(browserTz);
            if (tzCoords) {
                const realIcon = L.divIcon({
                    html: '<div style="background:#10b981;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
                    iconSize: [16, 16], iconAnchor: [8, 8], className: ''
                });
                L.marker([tzCoords.lat, tzCoords.lon], { icon: realIcon }).addTo(map)
                    .bindPopup(`<b>📍 Estimated Real Location</b><br>${browserTz.replace('_', ' ')}<br><span style="color:#065f46;font-size:12px;">Based on your browser timezone</span>`);
                L.circle([tzCoords.lat, tzCoords.lon], { color: '#10b981', fillColor: '#10b981', fillOpacity: 0.15, radius: 50000 }).addTo(map);
                L.polyline([[lat, lon], [tzCoords.lat, tzCoords.lon]], { color: '#6b7280', weight: 2, dashArray: '6, 8', opacity: 0.6 }).addTo(map);
                map.fitBounds([[lat, lon], [tzCoords.lat, tzCoords.lon]], { padding: [40, 40] });
            }
            const legend = L.control({ position: 'bottomright' });
            legend.onAdd = function() {
                const div = L.DomUtil.create('div');
                div.style.cssText = 'background:white;padding:8px 12px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-size:12px;line-height:1.8;';
                div.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f59e0b;margin-right:6px;"></span>VPN Location<br>' +
                    '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#10b981;margin-right:6px;"></span>Estimated Real';
                return div;
            };
            legend.addTo(map);
        } else {
            L.marker([lat, lon]).addTo(map).bindPopup(`<b>Your Detected Location</b><br>${city}`).openPopup();
            L.circle([lat, lon], { color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.2, radius: 5000 }).addTo(map);
        }
    } catch (error) {
        console.error('Error initializing map:', error);
        document.getElementById('map').innerHTML = '<p style="text-align: center; padding: 20px; color: #6b7280;">Unable to load map</p>';
    }
}

// Dual-location map for split-tunnel VPN (shows real IP + VPN IP)
function initMapDual(realLat, realLon, realCity, vpnLat, vpnLon, vpnCity) {
    try {
        const map = L.map('map').setView([realLat, realLon], 4);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(map);

        const realIcon = L.divIcon({
            html: '<div style="background:#ef4444;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
            iconSize: [16, 16], iconAnchor: [8, 8], className: ''
        });
        L.marker([realLat, realLon], { icon: realIcon }).addTo(map)
            .bindPopup(`<b>🔓 Real IP Location</b><br>${realCity}<br><span style="color:#dc2626;font-size:12px;">Your actual location (leaked via API)</span>`).openPopup();
        L.circle([realLat, realLon], { color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.15, radius: 20000 }).addTo(map);

        const vpnIcon = L.divIcon({
            html: '<div style="background:#3b82f6;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
            iconSize: [16, 16], iconAnchor: [8, 8], className: ''
        });
        L.marker([vpnLat, vpnLon], { icon: vpnIcon }).addTo(map)
            .bindPopup(`<b>🛡️ VPN Location</b><br>${vpnCity}<br><span style="color:#1d4ed8;font-size:12px;">Where your VPN says you are</span>`);
        L.circle([vpnLat, vpnLon], { color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.15, radius: 20000 }).addTo(map);

        L.polyline([[realLat, realLon], [vpnLat, vpnLon]], { color: '#6b7280', weight: 2, dashArray: '6, 8', opacity: 0.6 }).addTo(map);
        map.fitBounds([[realLat, realLon], [vpnLat, vpnLon]], { padding: [40, 40] });

        const legend = L.control({ position: 'bottomright' });
        legend.onAdd = function () {
            const div = L.DomUtil.create('div');
            div.style.cssText = 'background:white;padding:8px 12px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.15);font-size:12px;line-height:1.8;';
            div.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#ef4444;margin-right:6px;"></span>Real Location<br>' +
                '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#3b82f6;margin-right:6px;"></span>VPN Location';
            return div;
        };
        legend.addTo(map);
    } catch (error) {
        console.error('Error initializing dual map:', error);
        document.getElementById('map').innerHTML = '<p style="text-align: center; padding: 20px; color: #6b7280;">Unable to load map</p>';
    }
}

// Map common timezones to approximate coordinates
function getTimezoneCoords(tz) {
    const tzMap = {
        'Asia/Jerusalem': { lat: 31.77, lon: 35.22 },
        'Asia/Tel_Aviv': { lat: 32.07, lon: 34.77 },
        'Europe/London': { lat: 51.51, lon: -0.13 },
        'Europe/Paris': { lat: 48.86, lon: 2.35 },
        'Europe/Berlin': { lat: 52.52, lon: 13.41 },
        'Europe/Amsterdam': { lat: 52.37, lon: 4.90 },
        'Europe/Rome': { lat: 41.90, lon: 12.50 },
        'Europe/Madrid': { lat: 40.42, lon: -3.70 },
        'Europe/Moscow': { lat: 55.76, lon: 37.62 },
        'Europe/Istanbul': { lat: 41.01, lon: 28.98 },
        'Europe/Warsaw': { lat: 52.23, lon: 21.01 },
        'Europe/Zurich': { lat: 47.38, lon: 8.54 },
        'Europe/Vienna': { lat: 48.21, lon: 16.37 },
        'Europe/Stockholm': { lat: 59.33, lon: 18.07 },
        'Europe/Oslo': { lat: 59.91, lon: 10.75 },
        'Europe/Helsinki': { lat: 60.17, lon: 24.94 },
        'Europe/Athens': { lat: 37.98, lon: 23.73 },
        'Europe/Bucharest': { lat: 44.43, lon: 26.10 },
        'Europe/Prague': { lat: 50.08, lon: 14.44 },
        'Europe/Dublin': { lat: 53.35, lon: -6.26 },
        'Europe/Lisbon': { lat: 38.72, lon: -9.14 },
        'America/New_York': { lat: 40.71, lon: -74.01 },
        'America/Chicago': { lat: 41.88, lon: -87.63 },
        'America/Denver': { lat: 39.74, lon: -104.99 },
        'America/Los_Angeles': { lat: 34.05, lon: -118.24 },
        'America/Toronto': { lat: 43.65, lon: -79.38 },
        'America/Vancouver': { lat: 49.28, lon: -123.12 },
        'America/Sao_Paulo': { lat: -23.55, lon: -46.63 },
        'America/Mexico_City': { lat: 19.43, lon: -99.13 },
        'America/Buenos_Aires': { lat: -34.60, lon: -58.38 },
        'America/Bogota': { lat: 4.71, lon: -74.07 },
        'America/Lima': { lat: -12.05, lon: -77.04 },
        'Asia/Tokyo': { lat: 35.68, lon: 139.69 },
        'Asia/Shanghai': { lat: 31.23, lon: 121.47 },
        'Asia/Hong_Kong': { lat: 22.32, lon: 114.17 },
        'Asia/Singapore': { lat: 1.35, lon: 103.82 },
        'Asia/Dubai': { lat: 25.20, lon: 55.27 },
        'Asia/Kolkata': { lat: 22.57, lon: 88.36 },
        'Asia/Seoul': { lat: 37.57, lon: 126.98 },
        'Asia/Bangkok': { lat: 13.76, lon: 100.50 },
        'Asia/Taipei': { lat: 25.03, lon: 121.57 },
        'Australia/Sydney': { lat: -33.87, lon: 151.21 },
        'Australia/Melbourne': { lat: -37.81, lon: 144.96 },
        'Pacific/Auckland': { lat: -36.85, lon: 174.76 },
        'Africa/Cairo': { lat: 30.04, lon: 31.24 },
        'Africa/Johannesburg': { lat: -26.20, lon: 28.05 },
        'Africa/Lagos': { lat: 6.52, lon: 3.38 }
    };
    return tzMap[tz] || null;
}

// Get browser information
function getBrowserInfo() {
    const browserInfoDiv = document.getElementById('browser-info');
    const ua = navigator.userAgent;
    const uaData = navigator.userAgentData;
    
    let browserName = 'Unknown', browserVersion = '';
    if (uaData && uaData.brands) {
        const brand = uaData.brands.find(b => !b.brand.includes('Not'));
        if (brand) { browserName = brand.brand; browserVersion = brand.version; }
    } else {
        if (ua.includes('Firefox/')) { browserName = 'Firefox'; browserVersion = ua.match(/Firefox\/([\d.]+)/)?.[1] || ''; }
        else if (ua.includes('Edg/')) { browserName = 'Edge'; browserVersion = ua.match(/Edg\/([\d.]+)/)?.[1] || ''; }
        else if (ua.includes('Chrome/')) { browserName = 'Chrome'; browserVersion = ua.match(/Chrome\/([\d.]+)/)?.[1] || ''; }
        else if (ua.includes('Safari/')) { browserName = 'Safari'; browserVersion = ua.match(/Version\/([\d.]+)/)?.[1] || ''; }
    }

    let html = `
        <div class="info-row">
            <span class="info-label">Browser</span>
            <span class="info-value">${browserName} ${browserVersion}</span>
        </div>
        <div class="info-row">
            <span class="info-label">User Agent</span>
            <span class="info-value" style="font-size:12px;word-break:break-all;">${ua}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Language</span>
            <span class="info-value">${navigator.language || 'N/A'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Languages</span>
            <span class="info-value">${navigator.languages ? navigator.languages.join(', ') : 'N/A'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Cookies Enabled</span>
            <span class="info-value">${navigator.cookieEnabled ? 'Yes' : 'No'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Do Not Track</span>
            <span class="info-value">${navigator.doNotTrack || 'Not set'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Online Status</span>
            <span class="info-value">${navigator.onLine ? 'Online' : 'Offline'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">PDF Viewer</span>
            <span class="info-value">${navigator.pdfViewerEnabled !== undefined ? (navigator.pdfViewerEnabled ? 'Built-in' : 'None') : 'N/A'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Max Touch Points</span>
            <span class="info-value">${navigator.maxTouchPoints || 0}</span>
        </div>
    `;
    browserInfoDiv.innerHTML = html;

    if (ua && ua.length > 10) visibilityFactors.browserDetailed = true;
    if (navigator.language) visibilityFactors.languageDetected = true;
    const dnt = navigator.doNotTrack || window.doNotTrack;
    if (!dnt || dnt === '0' || dnt === 'unspecified') visibilityFactors.dntDisabled = true;
    updateMeter();
}

// Get system information
function getSystemInfo() {
    const systemInfoDiv = document.getElementById('system-info');
    // Use userAgentData if available (modern replacement for deprecated navigator.platform)
    const uaData = navigator.userAgentData;
    let platformStr = 'N/A';
    if (uaData && uaData.platform) {
        platformStr = uaData.platform;
    } else if (navigator.platform) {
        platformStr = navigator.platform;
    }
    
    let html = `
        <div class="info-row">
            <span class="info-label">Platform</span>
            <span class="info-value">${platformStr}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Screen Resolution</span>
            <span class="info-value">${screen.width} x ${screen.height}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Available Screen</span>
            <span class="info-value">${screen.availWidth} x ${screen.availHeight}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Color Depth</span>
            <span class="info-value">${screen.colorDepth} bits</span>
        </div>
        <div class="info-row">
            <span class="info-label">Pixel Ratio</span>
            <span class="info-value">${window.devicePixelRatio || 1}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Hardware Concurrency</span>
            <span class="info-value">${navigator.hardwareConcurrency || 'N/A'} cores</span>
        </div>
        <div class="info-row">
            <span class="info-label">Device Memory</span>
            <span class="info-value">${navigator.deviceMemory ? navigator.deviceMemory + ' GB' : 'N/A'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">GPU Renderer</span>
            <span class="info-value">${getGPUInfo()}</span>
        </div>
    `;
    systemInfoDiv.innerHTML = html;

    if (platformStr !== 'N/A') visibilityFactors.platformDetected = true;
    if (screen.width && screen.height) visibilityFactors.screenDetected = true;
    if (navigator.hardwareConcurrency) visibilityFactors.hardwareDetected = true;
    updateMeter();
}

// Get GPU info via WebGL
function getGPUInfo() {
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) return 'N/A';
        const ext = gl.getExtension('WEBGL_debug_renderer_info');
        if (!ext) return 'WebGL supported (renderer hidden)';
        const renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
        return renderer || 'N/A';
    } catch (e) {
        return 'N/A';
    }
}

// Get cookie information
function getCookieInfo() {
    const cookieInfoDiv = document.getElementById('cookie-info');
    const cookies = document.cookie.split(';').filter(c => c.trim());
    
    let cookieHTML = `
        <div class="info-row">
            <span class="info-label">Cookies Enabled</span>
            <span class="info-value">${navigator.cookieEnabled ? 'Yes' : 'No'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Total Cookies</span>
            <span class="info-value">${cookies.length}</span>
        </div>
    `;
    
    if (cookies.length === 0) {
        cookieHTML += `<div class="info-row">
            <span class="info-label">Status</span>
            <span class="info-value">No cookies found on this domain</span>
        </div>`;
    } else {
        cookies.forEach((cookie) => {
            const [name, ...valueParts] = cookie.split('=');
            const value = valueParts.join('=').trim();
            const displayValue = value ? (value.length > 40 ? value.substring(0, 40) + '...' : value) : 'empty';
            cookieHTML += `<div class="info-row">
                <span class="info-label">${name.trim()}</span>
                <span class="info-value">${displayValue}</span>
            </div>`;
        });
    }
    
    cookieHTML += `
        <div class="info-row">
            <span class="info-label">Local Storage Items</span>
            <span class="info-value">${localStorage.length}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Session Storage Items</span>
            <span class="info-value">${sessionStorage.length}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Third-Party Cookies</span>
            <span class="info-value">${navigator.cookieEnabled ? 'Enabled' : 'Blocked'}</span>
        </div>
    `;
    
    const dnt = navigator.doNotTrack || navigator.msDoNotTrack || window.doNotTrack;
    cookieHTML += `<div class="info-row">
        <span class="info-label">Do Not Track</span>
        <span class="info-value">${dnt === '1' || dnt === 'yes' ? 'Enabled' : 'Disabled'}</span>
    </div>`;
    
    cookieInfoDiv.innerHTML = cookieHTML;
    if (navigator.cookieEnabled) visibilityFactors.cookiesEnabled = true;
    updateMeter();
}

// Initialize all checks
document.addEventListener('DOMContentLoaded', () => {
    getIPInfo();
    getBrowserInfo();
    getSystemInfo();
    getCookieInfo();
    runAdvancedChecks();
});
