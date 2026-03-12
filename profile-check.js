// Fetch IP information from ipapi.co
async function getIPInfo() {
    try {
        const response = await fetch('https://ipapi.co/json/');
        const data = await response.json();
        
        const ipInfoDiv = document.getElementById('ip-info');
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
    } catch (error) {
        document.getElementById('ip-info').innerHTML = `
            <div class="info-row">
                <span class="info-label">Error</span>
                <span class="info-value">Unable to fetch IP information</span>
            </div>
        `;
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
    
    if (cookies.length === 0) {
        cookieInfoDiv.innerHTML = `
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value">No cookies found</span>
            </div>
            <div class="info-row">
                <span class="info-label">Cookies Enabled</span>
                <span class="info-value">${navigator.cookieEnabled ? 'Yes' : 'No'}</span>
            </div>
        `;
    } else {
        let cookieHTML = `
            <div class="info-row">
                <span class="info-label">Total Cookies</span>
                <span class="info-value">${cookies.length}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Cookies Enabled</span>
                <span class="info-value">${navigator.cookieEnabled ? 'Yes' : 'No'}</span>
            </div>
        `;
        
        cookies.forEach((cookie, index) => {
            const [name, value] = cookie.split('=').map(c => c.trim());
            cookieHTML += `
                <div class="info-row">
                    <span class="info-label">Cookie ${index + 1}</span>
                    <span class="info-value">${name}: ${value ? value.substring(0, 30) + (value.length > 30 ? '...' : '') : 'empty'}</span>
                </div>
            `;
        });
        
        cookieInfoDiv.innerHTML = cookieHTML;
    }
    
    // Add localStorage and sessionStorage info
    const localStorageCount = localStorage.length;
    const sessionStorageCount = sessionStorage.length;
    
    cookieInfoDiv.innerHTML += `
        <div class="info-row">
            <span class="info-label">Local Storage Items</span>
            <span class="info-value">${localStorageCount}</span>
        </div>
        <div class="info-row">
            <span class="info-label">Session Storage Items</span>
            <span class="info-value">${sessionStorageCount}</span>
        </div>
    `;
}

// Detect social media presence
function detectSocialMedia() {
    const socialInfoDiv = document.getElementById('social-info');
    
    // Check for common social media tracking pixels/scripts
    const socialChecks = {
        'Facebook': () => {
            return !!(window.FB || window.fbq || document.querySelector('[src*="facebook.com"]') || document.querySelector('[src*="fbcdn.net"]'));
        },
        'Twitter/X': () => {
            return !!(window.twttr || document.querySelector('[src*="twitter.com"]') || document.querySelector('[src*="twimg.com"]'));
        },
        'LinkedIn': () => {
            return !!(window.IN || document.querySelector('[src*="linkedin.com"]') || document.querySelector('[src*="licdn.com"]'));
        },
        'Google Analytics': () => {
            return !!(window.ga || window.gtag || document.querySelector('[src*="google-analytics.com"]') || document.querySelector('[src*="googletagmanager.com"]'));
        },
        'Instagram': () => {
            return !!(document.querySelector('[src*="instagram.com"]') || document.querySelector('[src*="cdninstagram.com"]'));
        },
        'TikTok': () => {
            return !!(window.ttq || document.querySelector('[src*="tiktok.com"]'));
        },
        'Pinterest': () => {
            return !!(window.pintrk || document.querySelector('[src*="pinterest.com"]'));
        },
        'YouTube': () => {
            return !!(document.querySelector('[src*="youtube.com"]') || document.querySelector('[src*="ytimg.com"]'));
        }
    };
    
    let socialHTML = '';
    let detectedCount = 0;
    
    for (const [platform, checkFn] of Object.entries(socialChecks)) {
        const detected = checkFn();
        if (detected) detectedCount++;
        
        socialHTML += `
            <div class="info-row">
                <span class="info-label">${platform}</span>
                <span class="info-value" style="color: ${detected ? '#10b981' : '#ef4444'}">
                    ${detected ? '✓ Detected' : '✗ Not detected'}
                </span>
            </div>
        `;
    }
    
    socialHTML = `
        <div class="info-row">
            <span class="info-label">Total Detected</span>
            <span class="info-value">${detectedCount} / ${Object.keys(socialChecks).length}</span>
        </div>
    ` + socialHTML;
    
    // Check for third-party cookies
    socialHTML += `
        <div class="info-row">
            <span class="info-label">Third-Party Cookies</span>
            <span class="info-value">${navigator.cookieEnabled ? 'Allowed' : 'Blocked'}</span>
        </div>
    `;
    
    socialInfoDiv.innerHTML = socialHTML;
}

// Initialize all checks
document.addEventListener('DOMContentLoaded', () => {
    getIPInfo();
    getBrowserInfo();
    getSystemInfo();
    getHeadersInfo();
    getCookieInfo();
    detectSocialMedia();
});
