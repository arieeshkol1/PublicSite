content = open('slashMyBill/index.html', 'r', encoding='utf-8').read()

# ── 1. Fix title ──────────────────────────────────────────────────────────
content = content.replace(
    '<title>Slash My Bill - AI-Powered AWS Bill Analysis | Cloud and AI</title>',
    '<title>SlashMyCloudBill — Stop Overpaying for AWS</title>'
)

# ── 2. Fix asset paths (../X → /X so they work from slashmycloudbill.com/) ─
# These need to work both from eshkolai.com/slashMyBill/ AND slashmycloudbill.com/
# Use absolute paths that work on both domains
content = content.replace('href="../SlashMyBill.png"', 'href="/SlashMyBill.png"')
content = content.replace('src="../SlashMyBill.png"', 'src="/SlashMyBill.png"')
content = content.replace('href="../styles.css"', 'href="/styles.css"')
content = content.replace('href="../smallninja2.png"', 'href="/smallninja2.png"')
content = content.replace('src="../smallninja2.png"', 'src="/smallninja2.png"')

# ── 3. Replace nav with SlashMyBill-only nav ──────────────────────────────
old_nav = '''    <!-- Navigation -->
    <nav class="navbar">
        <div class="container">
            <a href="../index.html" class="nav-brand">
                <img src="/SlashMyBill.png" alt="Slash My Bill Logo">
                <span>Cloud and AI</span>
            </a>
            <button class="hamburger" aria-label="Toggle menu" onclick="this.classList.toggle('active'); document.querySelector('.nav-menu').classList.toggle('active');">
                <span></span>
                <span></span>
                <span></span>
            </button>
            <ul class="nav-menu">
                <li><a href="../index.html#services" onclick="document.querySelector('.hamburger').classList.remove('active'); document.querySelector('.nav-menu').classList.remove('active');">Services</a></li>
                <li><a href="../index.html#expertise" onclick="document.querySelector('.hamburger').classList.remove('active'); document.querySelector('.nav-menu').classList.remove('active');">Expertise</a></li>
                <li><a href="../index.html#results" onclick="document.querySelector('.hamburger').classList.remove('active'); document.querySelector('.nav-menu').classList.remove('active');">Results</a></li>
                <li><a href="../profile-check.html">Profile Check</a></li>
                <li><a href="index.html" class="nav-active">Slash My Bill</a></li>
                <li><a href="../members/">Member Portal</a></li>
                <li><a href="../index.html#contact" class="nav-cta" onclick="document.querySelector('.hamburger').classList.remove('active'); document.querySelector('.nav-menu').classList.remove('active');">Get Started</a></li>
            </ul>
        </div>
    </nav>'''

new_nav = '''    <!-- Navigation -->
    <nav class="navbar">
        <div class="container">
            <a href="/" class="nav-brand">
                <img src="/SlashMyBill.png" alt="SlashMyCloudBill Logo">
                <span>SlashMyCloudBill</span>
            </a>
            <button class="hamburger" aria-label="Toggle menu" onclick="this.classList.toggle('active'); document.querySelector('.nav-menu').classList.toggle('active');">
                <span></span>
                <span></span>
                <span></span>
            </button>
            <ul class="nav-menu">
                <li><a href="/" class="nav-active">Home</a></li>
                <li><a href="/members/">Member Portal</a></li>
                <li><a href="#vmb-form" class="nav-cta" onclick="document.querySelector('.hamburger').classList.remove('active'); document.querySelector('.nav-menu').classList.remove('active');">Analyze My Bill</a></li>
            </ul>
        </div>
    </nav>'''

if old_nav in content:
    content = content.replace(old_nav, new_nav)
    print('Nav replaced')
else:
    print('WARNING: nav not found exactly — trying partial match')
    # Try after the asset path fixes
    content = content.replace(
        '<span>Cloud and AI</span>',
        '<span>SlashMyCloudBill</span>'
    )
    content = content.replace(
        '<a href="../index.html" class="nav-brand">',
        '<a href="/" class="nav-brand">'
    )
    print('Partial nav fixes applied')

# ── 4. Fix footer copyright ───────────────────────────────────────────────
content = content.replace(
    '&copy; 2026 eshkolai cloud and AI services. All rights reserved.',
    '&copy; 2026 SlashMyCloudBill. All rights reserved.'
)
content = content.replace(
    '<span>SlashMyBill</span>',
    '<span>SlashMyCloudBill</span>'
)

# ── 5. Fix member portal link in results offer wall ───────────────────────
content = content.replace(
    "window.location.href = '../members/?email='",
    "window.location.href = '/members/?email='"
)

open('slashMyBill/index.html', 'w', encoding='utf-8').write(content)
print('HTML done')
