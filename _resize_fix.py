#!/usr/bin/env python3
"""Fix: Add list-instances endpoint and update JS to use it."""

# 1. Add backend handler
with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'handle_server_list_instances' not in content:
    # Add route
    content = content.replace(
        "'POST /members/servers/resize': handle_server_resize,",
        "'POST /members/servers/resize': handle_server_resize,\n"
        "        'POST /members/servers/list-instances': handle_server_list_instances,"
    )
    # Append handler
    with open('_resize_fix.txt', 'r', encoding='utf-8') as f:
        code = f.read()
    content += code
    with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Backend: list-instances endpoint added")
else:
    print("Backend: already present")

# 2. Fix JS to use the new endpoint
with open('members/members.js', 'r', encoding='utf-8') as f:
    js = f.read()

old_js = """        var data = await api('POST', '/members/accounts/execute', {
            accountId: acctSelect.value,
            command: 'list-ec2'
        });
        instSelect.innerHTML = '<option value="">Select instance...</option>';
        var instances = data.instances || data.results || [];
        if (Array.isArray(instances)) {
            instances.forEach(function(inst) {
                var iid = inst.InstanceId || inst.instanceId || '';
                var itype = inst.InstanceType || inst.instanceType || '';
                var state = (inst.State && inst.State.Name) || inst.state || '';
                var name = '';
                (inst.Tags || []).forEach(function(t) { if (t.Key === 'Name') name = t.Value; });
                if (!name) name = iid;
                var opt = document.createElement('option');
                opt.value = iid;
                opt.textContent = name + ' (' + itype + ', ' + state + ')';
                instSelect.appendChild(opt);
            });
        }"""

new_js = """        var data = await api('POST', '/members/servers/list-instances', {
            accountId: acctSelect.value
        });
        instSelect.innerHTML = '<option value="">Select instance...</option>';
        var instances = data.instances || [];
        instances.forEach(function(inst) {
            var opt = document.createElement('option');
            opt.value = inst.instanceId;
            opt.textContent = inst.name + ' (' + inst.instanceType + ', ' + inst.state + ')' + (inst.inASG ? ' [ASG]' : '');
            instSelect.appendChild(opt);
        });"""

if old_js in js:
    js = js.replace(old_js, new_js)
    # Also fix the empty state message
    js = js.replace(
        "instSelect.innerHTML = '<option value=\"\">No EC2 instances found</option>';",
        "if (instances.length === 0) instSelect.innerHTML = '<option value=\"\">No EC2 instances in this account</option>';"
    )
    # Fix the error message
    js = js.replace(
        "instSelect.innerHTML = '<option value=\"\">Error loading instances</option>';",
        "instSelect.innerHTML = '<option value=\"\">No instances found</option>';"
    )
    with open('members/members.js', 'w', encoding='utf-8') as f:
        f.write(js)
    print("JS: Fixed to use /members/servers/list-instances")
else:
    print("JS: Could not find old code to replace")
