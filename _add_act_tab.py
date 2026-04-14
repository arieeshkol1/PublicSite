content = open('members/index.html', 'r', encoding='utf-8').read()

# Add the Act tab button after Configure
old_tabs = '<button class="member-tab" data-tab="accounts-tab">Configure</button>\n            </div>'
new_tabs = '<button class="member-tab" data-tab="accounts-tab">Configure</button>\n                <button class="member-tab" data-tab="act-tab">Act</button>\n            </div>'

# Add the Act tab content panel — insert before the accounts-tab div
old_panel = '<div id="accounts-tab" class="member-tab-content" hidden>'
new_panel = '<div id="act-tab" class="member-tab-content" hidden>\n                <div style="padding:40px;color:#e6edf3;font-size:1.1em;">Hello World</div>\n            </div>\n            <div id="accounts-tab" class="member-tab-content" hidden>'

if old_tabs in content and old_panel in content:
    content = content.replace(old_tabs, new_tabs)
    content = content.replace(old_panel, new_panel)
    open('members/index.html', 'w', encoding='utf-8').write(content)
    print('SUCCESS')
else:
    print('NOT FOUND')
    print('tabs found:', old_tabs in content)
    print('panel found:', old_panel in content)
