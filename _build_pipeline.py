import re

# ── Update slashMyBill/index.html ─────────────────────────────────────────
content = open('slashMyBill/index.html', 'r', encoding='utf-8').read()

# Replace the results section with the new offer wall
old_results = '''    <!-- Results Section -->
    <section id="vmb-results" class="vmb-results" hidden>
        <div class="container">
            <div class="vmb-results-content">
                <div class="vmb-success-icon">
                    <i class="fas fa-check-circle"></i>
                </div>
                <h3>Your report is ready!</h3>
                <p id="vmb-summary" class="vmb-summary"></p>
                <a id="vmb-download" href="#" class="btn btn-primary vmb-download" target="_blank" rel="noopener">
                    <i class="fas fa-download"></i>
                    <span>Download Report (PDF)</span>
                </a>
            </div>
        </div>
    </section>'''

new_results = '''    <!-- Results Section — Offer Wall -->
    <section id="vmb-results" class="vmb-results" hidden>
        <div class="container">
            <!-- Summary + Download -->
            <div class="vmb-results-header">
                <div class="vmb-success-icon">
                    <i class="fas fa-check-circle"></i>
                </div>
                <h3>Your analysis is ready!</h3>
                <p id="vmb-summary" class="vmb-summary"></p>
                <a id="vmb-download" href="#" class="btn btn-outline vmb-download" target="_blank" rel="noopener">
                    <i class="fas fa-download"></i>
                    <span>Download Full Report (PDF)</span>
                </a>
            </div>

            <!-- Savings Banner -->
            <div id="vmb-savings-banner" class="vmb-savings-banner" style="display:none;">
                <div class="vmb-savings-amount">
                    <span class="vmb-savings-label">Potential Monthly Savings Identified</span>
                    <span id="vmb-savings-value" class="vmb-savings-number">$0</span>
                </div>
            </div>

            <!-- Offer Wall -->
            <div class="vmb-offer-wall">
                <h3 class="vmb-offer-title">What would you like to do next?</h3>
                <div class="vmb-offer-cards">

                    <!-- Option A: Self-service Member Portal -->
                    <div class="vmb-offer-card vmb-offer-card-primary">
                        <div class="vmb-offer-badge">Most Popular</div>
                        <div class="vmb-offer-icon"><i class="fas fa-rocket"></i></div>
                        <h4>Do It Yourself</h4>
                        <p class="vmb-offer-subtitle">Free Member Portal</p>
                        <ul class="vmb-offer-features">
                            <li><i class="fas fa-check"></i> Connect your AWS account securely</li>
                            <li><i class="fas fa-check"></i> AI-powered ongoing cost monitoring</li>
                            <li><i class="fas fa-check"></i> Real-time waste detection &amp; alerts</li>
                            <li><i class="fas fa-check"></i> One-click cleanup actions</li>
                            <li><i class="fas fa-check"></i> FinOps dashboard &amp; reports</li>
                        </ul>
                        <div class="vmb-offer-price">
                            <span class="vmb-price-amount">Free</span>
                            <span class="vmb-price-note">No credit card required</span>
                        </div>
                        <button id="vmb-join-member" class="btn btn-primary vmb-offer-btn">
                            <i class="fas fa-user-plus"></i>
                            <span>Join as Member — Free</span>
                        </button>
                    </div>

                    <!-- Option B: Managed one-time service -->
                    <div class="vmb-offer-card vmb-offer-card-secondary">
                        <div class="vmb-offer-icon"><i class="fas fa-briefcase"></i></div>
                        <h4>Let Us Do It</h4>
                        <p class="vmb-offer-subtitle">One-Time Bill Slashing Service</p>
                        <ul class="vmb-offer-features">
                            <li><i class="fas fa-check"></i> Expert review of your full environment</li>
                            <li><i class="fas fa-check"></i> We implement all optimizations for you</li>
                            <li><i class="fas fa-check"></i> Guaranteed savings or money back</li>
                            <li><i class="fas fa-check"></i> Full audit report &amp; documentation</li>
                            <li><i class="fas fa-check"></i> 30-day post-implementation support</li>
                        </ul>
                        <div class="vmb-offer-price">
                            <span class="vmb-price-amount" id="vmb-service-price">$299</span>
                            <span class="vmb-price-note" id="vmb-service-price-note">or 20% of savings — whichever is less</span>
                        </div>
                        <button id="vmb-book-service" class="btn btn-secondary vmb-offer-btn">
                            <i class="fas fa-calendar-check"></i>
                            <span>Book a Free Consultation</span>
                        </button>
                    </div>

                </div>
            </div>

            <!-- Consultation Form (hidden, shown when Option B clicked) -->
            <div id="vmb-consult-form-wrapper" class="vmb-consult-form-wrapper" style="display:none;">
                <h4><i class="fas fa-calendar-check"></i> Book Your Free Consultation</h4>
                <p>We'll review your analysis and discuss how we can implement the savings for you.</p>
                <form id="vmb-consult-form" class="vmb-consult-form">
                    <div class="form-group">
                        <label>Preferred contact method</label>
                        <div class="vmb-radio-group">
                            <label><input type="radio" name="contact_method" value="email" checked> Email</label>
                            <label><input type="radio" name="contact_method" value="phone"> Phone call</label>
                            <label><input type="radio" name="contact_method" value="video"> Video call</label>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="vmb-consult-notes">Anything specific you'd like to discuss?</label>
                        <textarea id="vmb-consult-notes" rows="3" placeholder="e.g. We have 50 EC2 instances and want to reduce our monthly bill of $8,000..."></textarea>
                    </div>
                    <div id="vmb-consult-status" class="vmb-consult-status"></div>
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-paper-plane"></i>
                        <span>Send Request</span>
                    </button>
                    <button type="button" id="vmb-consult-cancel" class="btn btn-outline" style="margin-left:8px;">Cancel</button>
                </form>
            </div>

        </div>
    </section>'''

if old_results in content:
    content = content.replace(old_results, new_results)
    print('Results section replaced')
else:
    print('ERROR: results section not found')

open('slashMyBill/index.html', 'w', encoding='utf-8').write(content)
print('HTML done')
