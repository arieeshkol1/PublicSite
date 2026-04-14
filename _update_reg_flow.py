import re

# ── Update HTML: Step 1 now collects email + password ─────────────────────
content = open('members/index.html', 'r', encoding='utf-8').read()

old_step1 = '''            <!-- Step 1: Email + Get OTP -->
            <div id="reg-step-1">
                <form id="reg-email-form" novalidate>
                    <div class="form-group">
                        <label for="reg-email">Email</label>
                        <input type="email" id="reg-email" placeholder="you@example.com" autocomplete="email" required>
                    </div>
                    <div id="reg-email-error" class="login-error" role="alert"></div>
                    <button type="submit" class="btn btn-primary btn-full">Get OTP</button>
                </form>
            </div>

            <!-- Step 2: OTP Verification -->
            <div id="reg-step-2" hidden>
                <form id="reg-otp-form" novalidate>
                    <p class="reg-step-info">We sent a 6-digit code to <strong id="reg-email-display"></strong></p>
                    <div class="form-group">
                        <label for="reg-otp">Verification Code</label>
                        <input type="text" id="reg-otp" maxlength="6" inputmode="numeric" pattern="[0-9]{6}" placeholder="Enter 6-digit code" autocomplete="one-time-code" required>
                    </div>
                    <div id="reg-otp-error" class="login-error" role="alert"></div>
                    <button type="submit" class="btn btn-primary btn-full">Verify Code</button>
                </form>
            </div>

            <!-- Step 3: Password -->
            <div id="reg-step-3" hidden>
                <form id="reg-password-form" novalidate>
                    <p class="reg-step-info">Set your password</p>
                    <div class="form-group">
                        <label for="reg-password">Password</label>
                        <input type="password" id="reg-password" placeholder="At least 8 characters" autocomplete="new-password" required>
                    </div>
                    <div class="form-group">
                        <label for="reg-confirm">Confirm Password</label>
                        <input type="password" id="reg-confirm" placeholder="Confirm password" autocomplete="new-password" required>
                    </div>
                    <div id="reg-password-error" class="login-error" role="alert"></div>
                    <button type="submit" class="btn btn-primary btn-full">Create Account</button>
                </form>
            </div>'''

new_step1 = '''            <!-- Step 1: Email + Password -->
            <div id="reg-step-1">
                <form id="reg-email-form" novalidate>
                    <div class="form-group">
                        <label for="reg-email">Email</label>
                        <input type="email" id="reg-email" placeholder="you@example.com" autocomplete="email" required>
                    </div>
                    <div class="form-group">
                        <label for="reg-password">Password</label>
                        <input type="password" id="reg-password" placeholder="At least 8 characters" autocomplete="new-password" required>
                    </div>
                    <div class="form-group">
                        <label for="reg-confirm">Confirm Password</label>
                        <input type="password" id="reg-confirm" placeholder="Confirm password" autocomplete="new-password" required>
                    </div>
                    <div id="reg-email-error" class="login-error" role="alert"></div>
                    <button type="submit" class="btn btn-primary btn-full">Create Account</button>
                </form>
            </div>

            <!-- Step 2: OTP Verification -->
            <div id="reg-step-2" hidden>
                <form id="reg-otp-form" novalidate>
                    <p class="reg-step-info">We sent a 6-digit verification code to <strong id="reg-email-display"></strong></p>
                    <div class="form-group">
                        <label for="reg-otp">Verification Code</label>
                        <input type="text" id="reg-otp" maxlength="6" inputmode="numeric" pattern="[0-9]{6}" placeholder="Enter 6-digit code" autocomplete="one-time-code" required>
                    </div>
                    <div id="reg-otp-error" class="login-error" role="alert"></div>
                    <button type="submit" class="btn btn-primary btn-full">Verify &amp; Complete</button>
                    <div style="margin-top:10px;text-align:center;">
                        <a href="#" id="reg-resend-otp" style="font-size:0.85em;color:#6366f1;">Resend code</a>
                    </div>
                </form>
            </div>

            <!-- Step 3: Success (hidden, auto-redirect) -->
            <div id="reg-step-3" hidden>
                <div id="reg-password-error" class="login-error" role="alert"></div>
                <input type="hidden" id="reg-password-hidden">
                <input type="hidden" id="reg-confirm-hidden">
            </div>'''

if old_step1 in content:
    content = content.replace(old_step1, new_step1)
    print('HTML step 1 updated')
else:
    print('ERROR: HTML step 1 not found')

# Bump cache
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('HTML done')
