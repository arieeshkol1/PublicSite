import re

content = open('slashMyBill/index.html', 'r', encoding='utf-8').read()

# Add pipeline.css link
old_css = '    <link rel="stylesheet" href="slashMyBill.css">'
new_css = '    <link rel="stylesheet" href="slashMyBill.css">\n    <link rel="stylesheet" href="pipeline.css">'
content = content.replace(old_css, new_css)

# Update hero section to be more conversion-focused
old_hero = '''    <!-- Hero Section -->
    <section class="hero vmb-hero">
        <div class="hero-content">
            <div class="hero-badge">
                <i class="fas fa-file-invoice-dollar"></i>
                <span>AI-Powered Analysis</span>
            </div>
            <h1>Slash My <span class="gradient-text">Bill</span></h1>
            <p class="hero-subtitle">Upload your AWS invoice and get a detailed analysis with cost-saving recommendations, powered by Amazon Bedrock AI</p>
        </div>
    </section>'''

new_hero = '''    <!-- Hero Section -->
    <section class="hero vmb-hero">
        <div class="hero-content">
            <div class="hero-badge">
                <i class="fas fa-bolt"></i>
                <span>Free AWS Bill Analysis</span>
            </div>
            <h1>Stop Overpaying for <span class="gradient-text">AWS</span></h1>
            <p class="hero-subtitle">Upload your AWS invoice and our AI finds every dollar you're wasting — in minutes. Then choose: fix it yourself free, or let our experts do it for you.</p>
            <div class="vmb-pipeline-stats">
                <div class="vmb-pipeline-stat">
                    <div class="vmb-pipeline-stat-number">30%</div>
                    <div class="vmb-pipeline-stat-label">Average Savings Found</div>
                </div>
                <div class="vmb-pipeline-stat">
                    <div class="vmb-pipeline-stat-number">5 min</div>
                    <div class="vmb-pipeline-stat-label">Analysis Time</div>
                </div>
                <div class="vmb-pipeline-stat">
                    <div class="vmb-pipeline-stat-number">Free</div>
                    <div class="vmb-pipeline-stat-label">No Credit Card</div>
                </div>
            </div>
            <div class="vmb-trust-bar">
                <span class="vmb-trust-item"><i class="fas fa-shield-alt"></i> Bill deleted within 24h</span>
                <span class="vmb-trust-item"><i class="fas fa-lock"></i> HTTPS encrypted</span>
                <span class="vmb-trust-item"><i class="fas fa-eye-slash"></i> Never shared</span>
                <span class="vmb-trust-item"><i class="fas fa-robot"></i> Powered by Amazon Bedrock</span>
            </div>
        </div>
    </section>'''

content = content.replace(old_hero, new_hero)

# Update How It Works to reflect the full pipeline
old_how = '''    <!-- How It Works Section -->
    <section class="vmb-how-it-works">
        <div class="container">
            <div class="section-header">
                <span class="section-tag">Simple Process</span>
                <h2>How It Works</h2>
            </div>
            <div class="vmb-steps">
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-upload"></i>
                        <span class="vmb-step-number">1</span>
                    </div>
                    <h3>Upload</h3>
                    <p>Enter your email and upload your AWS invoice PDF from the AWS Billing Console</p>
                </div>
                <div class="vmb-step-arrow">
                    <i class="fas fa-arrow-right"></i>
                </div>
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-robot"></i>
                        <span class="vmb-step-number">2</span>
                    </div>
                    <h3>Analyze</h3>
                    <p>Our AI reviews your bill, identifies spending patterns, and finds cost-saving opportunities</p>
                </div>
                <div class="vmb-step-arrow">
                    <i class="fas fa-arrow-right"></i>
                </div>
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-download"></i>
                        <span class="vmb-step-number">3</span>
                    </div>
                    <h3>Download</h3>
                    <p>Get a comprehensive PDF report with summaries, explanations, and actionable recommendations</p>
                </div>
            </div>
        </div>
    </section>'''

new_how = '''    <!-- How It Works Section -->
    <section class="vmb-how-it-works">
        <div class="container">
            <div class="section-header">
                <span class="section-tag">Simple Process</span>
                <h2>How It Works</h2>
            </div>
            <div class="vmb-steps">
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-upload"></i>
                        <span class="vmb-step-number">1</span>
                    </div>
                    <h3>Upload Your Bill</h3>
                    <p>Verify your email and upload your AWS invoice PDF. Takes 2 minutes.</p>
                </div>
                <div class="vmb-step-arrow"><i class="fas fa-arrow-right"></i></div>
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-robot"></i>
                        <span class="vmb-step-number">2</span>
                    </div>
                    <h3>AI Finds Savings</h3>
                    <p>Our AI identifies waste, rightsizing opportunities, and pricing model improvements.</p>
                </div>
                <div class="vmb-step-arrow"><i class="fas fa-arrow-right"></i></div>
                <div class="vmb-step">
                    <div class="vmb-step-icon">
                        <i class="fas fa-code-branch"></i>
                        <span class="vmb-step-number">3</span>
                    </div>
                    <h3>Choose Your Path</h3>
                    <p><strong>DIY free:</strong> Join the Member Portal and implement savings yourself. Or <strong>let us do it</strong> for a flat fee.</p>
                </div>
            </div>
        </div>
    </section>'''

content = content.replace(old_how, new_how)

open('slashMyBill/index.html', 'w', encoding='utf-8').write(content)
print('HTML pipeline updates done')
