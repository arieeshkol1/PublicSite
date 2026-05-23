#!/usr/bin/env python3
"""Tasks 2-7: Add all Spot management backend handlers to member-handler/lambda_function.py."""

with open('member-handler/lambda_function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Add env vars and table references near the top ──────────────────────
old_tips_table = "TIPS_TABLE_NAME = os.environ.get('TIPS_TABLE_NAME', 'ViewMyBill-CostOptimizationTips')"
new_tips_table = old_tips_table + """
SPOT_LEDGER_TABLE_NAME = os.environ.get('SPOT_LEDGER_TABLE_NAME', 'SpotSavingsLedger')
SPOT_SNS_TOPIC_ARN = os.environ.get('SPOT_SNS_TOPIC_ARN', '')"""
content = content.replace(old_tips_table, new_tips_table)

# ── 2. Add routes to dispatch table ────────────────────────────────────────
old_agent_route = "        'POST /members/agent/invoke': handle_agent_invoke,"
new_agent_route = old_agent_route + """
        'POST /members/spot/config': handle_spot_config,
        'POST /members/spot/qualify': handle_spot_qualify,
        'POST /members/spot/plan': handle_spot_plan,
        'POST /members/spot/migrate': handle_spot_migrate,
        'GET /members/spot/dashboard': handle_spot_dashboard,"""
content = content.replace(old_agent_route, new_agent_route)

# ── 3. Add SNS event detection at the top of lambda_handler ────────────────
old_handler_start = '''    route_key = event.get('routeKey', '')
    logger.info(f"Member API request: {route_key}")'''
new_handler_start = '''    # ── SNS event detection (Spot interruption push pipeline) ──
    records = event.get('Records', [])
    if records and records[0].get('EventSource') == 'aws:sns':
        topic_arn = records[0].get('Sns', {}).get('TopicArn', '')
        if 'SlashMyBill-SpotInterruptions' in topic_arn:
            return _handle_spot_interruption_sns(records[0])
        return create_response(200, {'message': 'SNS event ignored'})

    route_key = event.get('routeKey', '')
    logger.info(f"Member API request: {route_key}")'''
content = content.replace(old_handler_start, new_handler_start)

print("Phase 1: Routes and env vars added")
print(f"File size: {len(content)} chars")

with open('member-handler/lambda_function.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Phase 1 written successfully")
