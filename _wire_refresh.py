content = open('members/members.js', 'r', encoding='utf-8').read()

old = """if (aiFontIncBtn) aiFontIncBtn.onclick = function() {
    aiFontSize = Math.min(28, aiFontSize + 1);
    applyAIFontSize();
};
applyAIFontSize();"""

new = """if (aiFontIncBtn) aiFontIncBtn.onclick = function() {
    aiFontSize = Math.min(28, aiFontSize + 1);
    applyAIFontSize();
};
applyAIFontSize();

// Refresh Findings button — always visible in chat header
var aiRefreshFindingsBtn = $('ai-refresh-findings-btn');
if (aiRefreshFindingsBtn) {
    aiRefreshFindingsBtn.onclick = async function() {
        aiRefreshFindingsBtn.disabled = true;
        aiRefreshFindingsBtn.textContent = '⏳ Scanning…';
        try {
            await _runScanFromChat();
        } finally {
            aiRefreshFindingsBtn.disabled = false;
            aiRefreshFindingsBtn.innerHTML = '&#8635; Refresh Findings';
        }
    };
}"""

if old in content:
    content = content.replace(old, new)
    print('Refresh button wired OK')
else:
    print('ERROR: pattern not found')

open('members/members.js', 'w', encoding='utf-8').write(content)
