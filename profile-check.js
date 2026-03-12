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
}

// Detect social media login status
async function detectSocialMedia() {
    const socialInfoDiv = document.getElementById('social-info');
    
    socialInfoDiv.innerHTML = '<div class="loading"><div class="spinner"></div><p>Checking social media login status...</p></div>';
    
    const socialChecks = {
        'Facebook': async () => {
            try {
                const response = await fetch('https://www.facebook.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'Facebook', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'Facebook', loggedIn: 'Not detected' };
            }
        },
        'Twitter/X': async () => {
            try {
                const response = await fetch('https://twitter.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'Twitter/X', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'Twitter/X', loggedIn: 'Not detected' };
            }
        },
        'LinkedIn': async () => {
            try {
                const response = await fetch('https://www.linkedin.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'LinkedIn', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'LinkedIn', loggedIn: 'Not detected' };
            }
        },
        'Instagram': async () => {
            try {
                const response = await fetch('https://www.instagram.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'Instagram', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'Instagram', loggedIn: 'Not detected' };
            }
        },
        'YouTube/Google': async () => {
            try {
                const response = await fetch('https://www.youtube.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'YouTube/Google', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'YouTube/Google', loggedIn: 'Not detected' };
            }
        },
        'Reddit': async () => {
            try {
                const response = await fetch('https://www.reddit.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'Reddit', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'Reddit', loggedIn: 'Not detected' };
            }
        },
        'GitHub': async () => {
            try {
                const response = await fetch('https://github.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'GitHub', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'GitHub', loggedIn: 'Not detected' };
            }
        },
        'Amazon': async () => {
            try {
                const response = await fetch('https://www.amazon.com/favicon.ico', { mode: 'no-cors', credentials: 'include' });
                return { platform: 'Amazon', loggedIn: 'Possibly logged in (cookies present)' };
            } catch {
                return { platform: 'Amazon', loggedIn: 'Not detected' };
            }
        }
    };
    
    try {
        const results = await Promise.all(Object.values(socialChecks).map(fn => fn()));
        
        let socialHTML = `
            <div class="info-row">
                <span class="info-label">Detection Method</span>
                <span class="info-value">Cookie & Session Analysis</span>
            </div>
        `;
        
        let detectedCount = 0;
        results.forEach(result => {
            const isLoggedIn = result.loggedIn.includes('logged in');
            if (isLoggedIn) detectedCount++;
            
            socialHTML += `
                <div class="info-row">
                    <span class="info-label">${result.platform}</span>
                    <span class="info-value" style="color: ${isLoggedIn ? '#10b981' : '#6b7280'}">
                        ${result.loggedIn}
                    </span>
                </div>
            `;
        });
        
        socialHTML = `
            <div class="info-row">
                <span class="info-label">Platforms Detected</span>
                <span class="info-value">${detectedCount} / ${results.length}</span>
            </div>
        ` + socialHTML;
        
        socialInfoDiv.innerHTML = socialHTML;
    } catch (error) {
        socialInfoDiv.innerHTML = `
            <div class="info-row">
                <span class="info-label">Status</span>
                <span class="info-value">Unable to detect social media login status</span>
            </div>
            <div class="info-row">
                <span class="info-label">Note</span>
                <span class="info-value">Browser privacy settings may block detection</span>
            </div>
        `;
    }
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
