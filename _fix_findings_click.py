import re

# ── 1. Fix HTML: rename "Try asking" → "General questions" ──────────────────
content = open('members/index.html', 'r', encoding='utf-8').read()

content = content.replace(
    '<p style="color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">Try asking:</p>',
    '<p style="color:#8b949e;font-size:0.8em;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px;">General questions:</p>'
)

# Bump cache
m = re.search(r'members\.js\?v=(\d+)', content)
if m:
    old_v = int(m.group(1)); new_v = old_v + 1
    content = content.replace('members.js?v=' + str(old_v), 'members.js?v=' + str(new_v))
    content = content.replace('members.css?v=' + str(old_v), 'members.css?v=' + str(new_v))
    print(f'Cache v{old_v} -> v{new_v}')

open('members/index.html', 'w', encoding='utf-8').write(content)
print('HTML updated')

# ── 2. Fix JS: finding click → populate input only (no auto-submit) ──────────
js = open('members/members.js', 'r', encoding='utf-8').read()

# Replace the finding button onclick to just fill the input and focus it
old_onclick = '''    // Wire up finding buttons — set input AND submit
    list.querySelectorAll('.ai-finding-btn').forEach(function(btn) {
        btn.onclick = function() {
            var q = btn.dataset.question;
            if (aiQuestionInput) aiQuestionInput.value = q;
            // Hide welcome screen and submit
            var welcome = $('ai-welcome-screen');
            if (welcome) welcome.style.display = 'none';
            askAI();
        };
    });'''

new_onclick = '''    // Wire up finding buttons — populate input and focus (same as code click)
    list.querySelectorAll('.ai-finding-btn').forEach(function(btn) {
        btn.onclick = function() {
            var q = btn.dataset.question;
            if (aiQuestionInput) {
                aiQuestionInput.value = q;
                aiQuestionInput.focus();
            }
        };
    });'''

if old_onclick in js:
    js = js.replace(old_onclick, new_onclick)
    print('JS finding click fixed')
else:
    print('WARNING: onclick pattern not found')

# Also revert the code-click change that auto-submitted — restore to fill+focus only
old_code_click = '''    if (e.target.tagName === 'CODE' && e.target.closest('.lab-examples')) {
        aiQuestionInput.value = e.target.textContent;
        var welcome = $('ai-welcome-screen');
        if (welcome) welcome.style.display = 'none';
        askAI();
    }
};'''

new_code_click = '''    if (e.target.tagName === 'CODE' && e.target.closest('.lab-examples')) {
        aiQuestionInput.value = e.target.textContent;
        aiQuestionInput.focus();
    }
};'''

if old_code_click in js:
    js = js.replace(old_code_click, new_code_click)
    print('Code click reverted to fill+focus')
else:
    print('WARNING: code click pattern not found')

open('members/members.js', 'w', encoding='utf-8').write(js)
print('Done')
