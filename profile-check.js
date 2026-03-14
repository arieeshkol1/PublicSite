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
    dntDisabled: false
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
    'privax', 'kape', 'aura', 'pango', 'hotspot shield', 'hola'
];

function detectVPN(org, ipTimezone, extraData) {
    let reasons = [];
    
    // Check ISP name against known VPN/datacenter keywords
    if (org) {
        const orgLower = org.toLowerCase();
        if (VPN_KEYWORDS.some(kw => orgLower.includes(kw))) {
            reasons.push('ISP matches known VPN/datacenter');
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
            reasons.push('WebRTC disabled');
        }
    } catch (e) {
        reasons.push('WebRTC blocked');
    }
    
    // Detect browser-extension VPNs (Hola, etc.) by checking for known extensions
    try {
        const holaExtIds = ['gkojfkhlekighikafcpjkiklfbnlmeio'];
        for (const extId of holaExtIds) {
            if (document.querySelector(`[src*="${extId}"]`) || 
                document.querySelector(`link[href*="${extId}"]`)) {
                reasons.push('Hola VPN extension detected (⚠️ leaks real IP on API calls)');
                break;
            }
        }
        // Also check if Hola injects its watermark
        if (document.querySelector('[class*="hola"]') || document.querySelector('[id*="hola"]')) {
            reasons.push('Hola VPN watermark detected');
        }
    } catch (e) { /* ignore */ }
    
    vpnReasons = reasons;
    return reasons.length > 0;
}

let vpnReasons = [];

function calculateVisibilityScore() {
    let score = 0;
    const weights = {
        ipDetected: 20,
        locationDetected: 15,
        ispDetected: 10,
        browserDetailed: 10,
        platformDetected: 10,
        screenDetected: 5,
        cookiesEnabled: 10,
        languageDetected: 5,
        hardwareDetected: 5,
        dntDisabled: 10
    };
    for (const [key, detected] of Object.entries(visibilityFactors)) {
        if (detected) score += weights[key] || 0;
    }
    // VPN hides real IP, location, and ISP — reduce those contributions
    if (vpnDetected) {
        if (visibilityFactors.ipDetected) score -= 15;      // IP is masked
        if (visibilityFactors.locationDetected) score -= 12; // Location is fake
        if (visibilityFactors.ispDetected) score -= 8;       // ISP is VPN provider
    }
    return Math.max(0, Math.min(score, 100));
}

function updateMeter() {
    const visibilityScore = calculateVisibilityScore();
    const score = 100 - visibilityScore; // Invert: 100% = invisible, 0% = easy target
    // Map 0-100 score to -90 to 90 degrees rotation
    // 0% (easy target) = right side (90°), 100% (invisible) = left side (-90°)
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

// Fetch IP information - try multiple services for reliability
async function getIPInfo() {
    const ipInfoDiv = document.getElementById('ip-info');
    let latitude = null;
    let longitude = null;
    let city = 'Unknown';
    
    try {
        // Try ipapi.co first
        const response = await fetch('https://ipapi.co/json/');
        
        if (!response.ok) {
            throw new Error('ipapi.co failed');
        }
        
        const data = await response.json();
        latitude = data.latitude;
        longitude = data.longitude;
        city = data.city || 'Unknown';
        
        ipInfoDiv.innerHTML = `
            <div class="info-row">
                <span class="info-label">IP Address</span>
                <span class="info-value">${data.ip || 'N/A'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">ISP</span>
                <span class="info-value">${data.org || 'N/A'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Country</span>
                <span class="info-value">${data.country_name || 'N/A'} (${data.country || 'N/A'})</span>
            </div>
            <div class="info-row">
                <span class="info-label">Region</span>
                <span class="info-value">${data.region || 'N/A'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">City</span>
                <span class="info-value">${data.city || 'N/A'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Timezone</span>
                <span class="info-value">${data.timezone || 'N/A'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Latitude / Longitude</span>
                <span class="info-value">${data.latitude || 'N/A'} / ${data.longitude || 'N/A'}</span>
            </div>
        `;
        
        // Detect VPN first (before map)
        vpnDetected = detectVPN(data.org, data.timezone, data);
        
        // Initialize map if we have coordinates
        if (latitude && longitude) {
            initMap(latitude, longitude, city, vpnDetected);
        }

        if (vpnDetected) {
            ipInfoDiv.innerHTML = `
                <div class="info-row" style="background: #d1fae5; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                    <span class="info-label" style="color: #065f46;">🛡️ VPN / Proxy Detected</span>
                    <span class="info-value" style="color: #065f46; font-family: inherit; font-size: 13px;">${vpnReasons.join(' • ')}</span>
                </div>
            ` + ipInfoDiv.innerHTML;
        }

        // Update visibility score
        if (data.ip) visibilityFactors.ipDetected = true;
        if (data.city || data.region) visibilityFactors.locationDetected = true;
        if (data.org) visibilityFactors.ispDetected = true;
        updateMeter();
    } catch (error) {
        // Fallback to ipify + ip-api.com
        try {
            const ipResponse = await fetch('https://api.ipify.org?format=json');
            const ipData = await ipResponse.json();
            const ip = ipData.ip;
            
            const geoResponse = await fetch(`https://ip-api.com/json/${ip}`);
            const geoData = await geoResponse.json();
            
            latitude = geoData.lat;
            longitude = geoData.lon;
            city = geoData.city || 'Unknown';
            
            ipInfoDiv.innerHTML = `
                <div class="info-row">
                    <span class="info-label">IP Address</span>
                    <span class="info-value">${ip || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">ISP</span>
                    <span class="info-value">${geoData.isp || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Country</span>
                    <span class="info-value">${geoData.country || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Region</span>
                    <span class="info-value">${geoData.regionName || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">City</span>
                    <span class="info-value">${geoData.city || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Timezone</span>
                    <span class="info-value">${geoData.timezone || 'N/A'}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Latitude / Longitude</span>
                    <span class="info-value">${geoData.lat || 'N/A'} / ${geoData.lon || 'N/A'}</span>
                </div>
            `;
            
            // Detect VPN first (before map)
            vpnDetected = detectVPN(geoData.isp, geoData.timezone, geoData);
            
            // Initialize map if we have coordinates
            if (latitude && longitude) {
                initMap(latitude, longitude, city, vpnDetected);
            }

            if (vpnDetected) {
                ipInfoDiv.innerHTML = `
                    <div class="info-row" style="background: #d1fae5; border-radius: 8px; padding: 12px; margin-bottom: 8px;">
                        <span class="info-label" style="color: #065f46;">🛡️ VPN / Proxy Detected</span>
                        <span class="info-value" style="color: #065f46; font-family: inherit; font-size: 13px;">${vpnReasons.join(' • ')}</span>
                    </div>
                ` + ipInfoDiv.innerHTML;
            }

            // Update visibility score
            if (ip) visibilityFactors.ipDetected = true;
            if (geoData.city || geoData.regionName) visibilityFactors.locationDetected = true;
            if (geoData.isp) visibilityFactors.ispDetected = true;
            updateMeter();
        } catch (fallbackError) {
            ipInfoDiv.innerHTML = `
                <div class="info-row">
                    <span class="info-label">Status</span>
                    <span class="info-value">Unable to fetch IP information</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Note</span>
                    <span class="info-value">API service may be temporarily unavailable</span>
                </div>
            `;
        }
    }
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
            // VPN location marker (orange)
            const vpnIcon = L.divIcon({
                html: '<div style="background:#f59e0b;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
                iconSize: [16, 16], iconAnchor: [8, 8], className: ''
            });
            const vpnMarker = L.marker([lat, lon], { icon: vpnIcon }).addTo(map);
            vpnMarker.bindPopup(`<b>🛡️ VPN Server Location</b><br>${city}<br><span style="color:#92400e;font-size:12px;">This is NOT your real location</span>`).openPopup();
            
            L.circle([lat, lon], {
                color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 0.15, radius: 20000,
                dashArray: '8, 8'
            }).addTo(map);

            // Try to estimate real location from browser timezone
            const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
            const tzCoords = getTimezoneCoords(browserTz);
            if (tzCoords) {
                const realIcon = L.divIcon({
                    html: '<div style="background:#10b981;width:16px;height:16px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.3);"></div>',
                    iconSize: [16, 16], iconAnchor: [8, 8], className: ''
                });
                const realMarker = L.marker([tzCoords.lat, tzCoords.lon], { icon: realIcon }).addTo(map);
                realMarker.bindPopup(`<b>📍 Estimated Real Location</b><br>${browserTz.replace('_', ' ')}<br><span style="color:#065f46;font-size:12px;">Based on your browser timezone</span>`);
                
                L.circle([tzCoords.lat, tzCoords.lon], {
                    color: '#10b981', fillColor: '#10b981', fillOpacity: 0.15, radius: 50000
                }).addTo(map);

                // Draw dashed line between VPN and real location
                L.polyline([[lat, lon], [tzCoords.lat, tzCoords.lon]], {
                    color: '#6b7280', weight: 2, dashArray: '6, 8', opacity: 0.6
                }).addTo(map);

                // Fit map to show both markers
                map.fitBounds([[lat, lon], [tzCoords.lat, tzCoords.lon]], { padding: [40, 40] });
            }

            // Add legend
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
            // Normal (no VPN) marker
            const marker = L.marker([lat, lon]).addTo(map);
            marker.bindPopup(`<b>Your Detected Location</b><br>${city}`).openPopup();
            
            L.circle([lat, lon], {
                color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.2, radius: 5000
            }).addTo(map);
        }
    } catch (error) {
        console.error('Error initializing map:', error);
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
    
    browserInfoDiv.innerHTML = `
        <div class="info-row">
            <span class="info-label">User Agent</span>
            <span class="info-value">${ua}</span>
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
    `;

    // Update visibility score
    if (ua && ua.length > 10) visibilityFactors.browserDetailed = true;
    if (navigator.language) visibilityFactors.languageDetected = true;
    const dnt = navigator.doNotTrack || window.doNotTrack;
    if (!dnt || dnt === '0' || dnt === 'unspecified') visibilityFactors.dntDisabled = true;
    updateMeter();
}

// Get system information
function getSystemInfo() {
    const systemInfoDiv = document.getElementById('system-info');
    
    systemInfoDiv.innerHTML = `
        <div class="info-row">
            <span class="info-label">Platform</span>
            <span class="info-value">${navigator.platform || 'N/A'}</span>
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
    `;

    // Update visibility score
    if (navigator.platform) visibilityFactors.platformDetected = true;
    if (screen.width && screen.height) visibilityFactors.screenDetected = true;
    if (navigator.hardwareConcurrency) visibilityFactors.hardwareDetected = true;
    updateMeter();
}

// Get HTTP headers information
function getHeadersInfo() {
    const headersInfoDiv = document.getElementById('headers-info');
    
    headersInfoDiv.innerHTML = `
        <div class="info-row">
            <span class="info-label">Referrer</span>
            <span class="info-value">${document.referrer || 'Direct visit'}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Current URL</span>
            <span class="info-value">${window.location.href}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Protocol</span>
            <span class="info-value">${window.location.protocol}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Host</span>
            <span class="info-value">${window.location.host}</span>
        </div>
    `;
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
        cookieHTML += `
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value">No cookies found on this domain</span>
            </div>
        `;
    } else {
        cookies.forEach((cookie, index) => {
            const [name, ...valueParts] = cookie.split('=');
            const value = valueParts.join('=').trim();
            const displayValue = value ? (value.length > 40 ? value.substring(0, 40) + '...' : value) : 'empty';
            
            cookieHTML += `
                <div class="info-row">
                    <span class="info-label">${name.trim()}</span>
                    <span class="info-value">${displayValue}</span>
                </div>
            `;
        });
    }
    
    // Add localStorage and sessionStorage info
    const localStorageCount = localStorage.length;
    const sessionStorageCount = sessionStorage.length;
    
    cookieHTML += `
        <div class="info-row">
            <span class="info-label">Local Storage Items</span>
            <span class="info-value">${localStorageCount}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Session Storage Items</span>
            <span class="info-value">${sessionStorageCount}</span>
        </div>
    `;
    
    // Show if third-party cookies are blocked
    cookieHTML += `
        <div class="info-row">
            <span class="info-label">Third-Party Cookies</span>
            <span class="info-value">${navigator.cookieEnabled ? 'Enabled' : 'Blocked'}</span>
        </div>
    `;
    
    // Check for Do Not Track
    const dnt = navigator.doNotTrack || navigator.msDoNotTrack || window.doNotTrack;
    cookieHTML += `
        <div class="info-row">
            <span class="info-label">Do Not Track</span>
            <span class="info-value">${dnt === '1' || dnt === 'yes' ? 'Enabled' : 'Disabled'}</span>
        </div>
    `;
    
    cookieInfoDiv.innerHTML = cookieHTML;

    // Update visibility score
    if (navigator.cookieEnabled) visibilityFactors.cookiesEnabled = true;
    updateMeter();
}

// Initialize all checks
document.addEventListener('DOMContentLoaded', () => {
    getIPInfo();
    getBrowserInfo();
    getSystemInfo();
    getCookieInfo();
});
