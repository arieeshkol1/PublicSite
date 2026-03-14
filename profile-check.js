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
    return Math.min(score, 100);
}

function updateMeter() {
    const score = calculateVisibilityScore();
    // Map 0-100 score to -90 to 90 degrees rotation
    const angle = -90 + (score / 100) * 180;
    const needle = document.getElementById('meter-needle');
    if (needle) {
        needle.setAttribute('transform', `rotate(${angle}, 150, 160)`);
    }

    const label = document.getElementById('meter-score-label');
    const detail = document.getElementById('meter-score-detail');
    if (!label || !detail) return;

    let labelText, detailText, color;
    if (score <= 20) {
        labelText = 'Invisible'; color = '#10b981';
        detailText = 'You are well hidden — very little is exposed';
    } else if (score <= 40) {
        labelText = 'Low Profile'; color = '#84cc16';
        detailText = 'Minimal information is visible about you';
    } else if (score <= 60) {
        labelText = 'Moderate'; color = '#f59e0b';
        detailText = 'A fair amount of your profile is detectable';
    } else if (score <= 80) {
        labelText = 'Exposed'; color = '#f97316';
        detailText = 'Most of your information is visible to websites';
    } else {
        labelText = 'Easy Target'; color = '#ef4444';
        detailText = 'Your full profile is exposed — consider using a VPN';
    }
    label.textContent = `${score}% — ${labelText}`;
    label.style.color = color;
    detail.textContent = detailText;
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
        
        // Initialize map if we have coordinates
        if (latitude && longitude) {
            initMap(latitude, longitude, city);
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
            
            // Initialize map if we have coordinates
            if (latitude && longitude) {
                initMap(latitude, longitude, city);
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
function initMap(lat, lon, city) {
    try {
        // Create map centered on the location
        const map = L.map('map').setView([lat, lon], 10);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19
        }).addTo(map);
        
        // Add marker at the location
        const marker = L.marker([lat, lon]).addTo(map);
        marker.bindPopup(`<b>Your Estimated Location</b><br>${city}`).openPopup();
        
        // Add circle to show approximate area
        L.circle([lat, lon], {
            color: '#0066ff',
            fillColor: '#0066ff',
            fillOpacity: 0.2,
            radius: 5000 // 5km radius
        }).addTo(map);
    } catch (error) {
        console.error('Error initializing map:', error);
        document.getElementById('map').innerHTML = '<p style="text-align: center; padding: 20px; color: #6b7280;">Unable to load map</p>';
    }
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
