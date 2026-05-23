#!/usr/bin/env python3
"""Integrate AWS Free Tier API into resize analysis, tips, and agent instructions."""

# 1. Add free tier helper to member-handler
with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the free tier helper function before handle_server_analyze
freetier_fn = '''

def _get_free_tier_usage(creds=None):
    """Query AWS Free Tier usage via freetier:GetFreeTierUsage API."""
    try:
        if creds:
            ft_client = _make_client_from_creds('freetier', creds, region_name='us-east-1')
        else:
            ft_client = boto3.client('freetier', region_name='us-east-1')
        
        usage_items = []
        paginator = ft_client.get_paginator('get_free_tier_usage')
        for page in paginator.paginate():
            usage_items.extend(page.get('freeTierUsages', []))
        
        result = {}
        for item in usage_items:
            service = item.get('service', '')
            desc = item.get('description', '')
            usage_type = item.get('usageType', '')
            limit = item.get('limit', {})
            limit_amount = float(limit.get('amount', 0))
            limit_unit = limit.get('unit', '')
            actual = float(item.get('actualUsageAmount', 0))
            forecast = float(item.get('forecastedUsageAmount', 0))
            free_tier_type = item.get('freeTierType', '')  # ALWAYS_FREE, 12_MONTHS_FREE, etc.
            
            result[usage_type] = {
                'service': service,
                'description': desc,
                'usageType': usage_type,
                'limit': limit_amount,
                'limitUnit': limit_unit,
                'actualUsage': actual,
                'forecastedUsage': forecast,
                'freeTierType': free_tier_type,
                'percentUsed': round(actual / limit_amount * 100, 1) if limit_amount > 0 else 0,
            }
        return result
    except Exception as e:
        logger.warning(f"Free Tier API failed: {e}")
        return {}

'''

# Insert before handle_server_analyze
if '_get_free_tier_usage' not in content:
    content = content.replace(
        'def handle_server_analyze(event):',
        freetier_fn + 'def handle_server_analyze(event):'
    )
    print("1. Free tier helper function added")
else:
    print("1. Free tier helper already present")

# 2. Add free tier data to the analyze response
# Find where we build the response and add free tier info
old_return = "    return create_response(200, {\n        'instanceId': instance_id,"
new_return = """    # Get free tier usage for this account
    free_tier = {}
    try:
        ft_data = _get_free_tier_usage(creds)
        # Find EC2-related free tier entries
        for key, val in ft_data.items():
            if 'EC2' in val.get('service', '') or 'ec2' in key.lower():
                free_tier[key] = val
    except Exception:
        pass

    return create_response(200, {
        'instanceId': instance_id,"""

if "'instanceId': instance_id," in content and 'free_tier' not in content.split("return create_response(200, {\n        'instanceId': instance_id,")[0][-200:]:
    content = content.replace(old_return, new_return, 1)
    # Add freeTier to the response dict
    old_analysis = "        'analysis': {"
    new_analysis = "        'freeTier': free_tier,\n        'analysis': {"
    # Only replace the first occurrence in handle_server_analyze
    idx = content.find("'freeTier': free_tier")
    if idx == -1:
        content = content.replace(old_analysis, new_analysis, 1)
    print("2. Free tier data added to analyze response")
else:
    print("2. Skipping - may already be present or structure changed")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

# 3. Update JS to show free tier info
with open('members/members.js', 'r', encoding='utf-8') as f:
    js = f.read()

# Add free tier display after the current monthly cost gauge
old_gauge = "html += '<div style=\"text-align:center;\"><div style=\"font-size:1.5em;font-weight:700;\">$' + (data.currentSpecs.monthlyRate || 0) + '</div><div style=\"font-size:0.75em;color:#6b7280;\">Current/mo</div></div>';"
new_gauge = old_gauge + """
            html += '</div>';
            // Free tier info
            var ft = data.freeTier || {};
            var ftKeys = Object.keys(ft);
            if (ftKeys.length > 0) {
                html += '<div style="margin-top:8px;padding:8px 12px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;font-size:0.85em;">';
                html += '<span style="font-weight:600;color:#1e40af;">Free Tier Status:</span> ';
                ftKeys.forEach(function(k) {
                    var f = ft[k];
                    html += '<span style="color:#1e40af;">' + f.service + '</span>: ' + f.actualUsage + '/' + f.limit + ' ' + f.limitUnit + ' (' + f.percentUsed + '% used, ' + f.freeTierType.replace('_', ' ') + ') ';
                });
                html += '</div>';
            }
            html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;display:none;">';"""

if old_gauge in js and 'Free Tier Status' not in js:
    js = js.replace(old_gauge, new_gauge)
    # Remove the duplicate grid opening that was there before
    js = js.replace(
        "html += '</div>';\n            var a = data.analysis",
        "var a = data.analysis"
    )
    print("3. Free tier display added to JS")
else:
    print("3. JS update skipped - structure may have changed")

with open('members/members.js', 'w', encoding='utf-8') as f:
    f.write(js)

# 4. Add free tier tip to knowledge base
import json
with open('knowledge-base/aws-cost-optimization-tips.json', 'r', encoding='utf-8') as f:
    tips_data = json.load(f)

# Check if free tier tip already exists
tip_ids = [t.get('id') for t in tips_data.get('tips', [])]
if 'general-015' not in tip_ids:
    tips_data['tips'].append({
        "id": "general-015",
        "service": "General",
        "category": "free-tier",
        "title": "Monitor Free Tier usage to avoid unexpected charges",
        "description": "Use the AWS Free Tier API (freetier:GetFreeTierUsage) to track usage against monthly limits. Set up billing alerts at 85% of free tier limits. Common free tier services: 750 hrs/mo t2.micro EC2, 5 GB S3 storage, 25 GB DynamoDB, 1M Lambda requests. Free tier expires 12 months after account creation for most services.",
        "estimatedSavings": "varies",
        "difficulty": "easy",
        "automatedCheck": "freetier:GetFreeTierUsage -> check percentUsed for each service. Alert if > 80%.",
        "checkImplemented": False,
        "actionType": "advisory",
        "actionLabel": "Check Free Tier",
        "level": 1,
        "serviceKey": "General",
        "implementedInAct": False
    })
    with open('knowledge-base/aws-cost-optimization-tips.json', 'w', encoding='utf-8') as f:
        json.dump(tips_data, f, indent=2)
    print("4. Free tier tip added to knowledge base")
else:
    print("4. Free tier tip already exists")

# 5. Update agent instructions to mention free tier
with open('agent-action/agent-instructions.md', 'r', encoding='utf-8') as f:
    agent_md = f.read()

if 'Free Tier' not in agent_md:
    agent_md += """

## Free Tier Awareness
- When analyzing costs for small instances (t2.micro, t3.micro, t2.nano), check if the account is within the AWS Free Tier period (12 months from account creation).
- The Free Tier covers 750 hours/month of t2.micro or t3.micro Linux instances, 5 GB S3 standard storage, 25 GB DynamoDB storage, 1 million Lambda requests, and more.
- If a service shows $0 actual cost but has on-demand pricing, mention that it may be covered by Free Tier.
- Use the resize wizard in Act > Optimize to analyze instance usage and find rightsizing opportunities.
"""
    with open('agent-action/agent-instructions.md', 'w', encoding='utf-8') as f:
        f.write(agent_md)
    print("5. Agent instructions updated with Free Tier awareness")
else:
    print("5. Agent instructions already mention Free Tier")

print("Done - Free Tier integration complete")
