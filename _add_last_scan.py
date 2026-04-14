new_fns = '''

def _save_last_scan(member_email, account_ids, findings, total_savings, scanned_at):
    """Persist top findings to Members table for the Chat widget."""
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        members_table.update_item(
            Key={'email': member_email},
            UpdateExpression='SET lastScan = :s',
            ExpressionAttributeValues={':s': {
                'accountIds': account_ids,
                'findings': findings[:10],
                'totalSavings': str(round(total_savings, 2)),
                'scannedAt': scanned_at,
            }},
        )
    except Exception as e:
        logger.warning(f"Failed to save last scan: {e}")


def handle_get_last_scan(event):
    """Return the cached last scan result for the Chat widget."""
    auth = validate_token(event)
    if isinstance(auth, dict) and 'statusCode' in auth:
        return auth
    member_email = auth['sub']
    try:
        members_table = dynamodb.Table(MEMBERS_TABLE_NAME)
        member = members_table.get_item(Key={'email': member_email}).get('Item') or {}
        last_scan = _decimal_to_native(member.get('lastScan') or {})
        return create_response(200, {'lastScan': last_scan})
    except ClientError as e:
        return create_error_response(500, 'ServerError', 'Failed to load last scan')

'''

content = open('member-handler/lambda_function.py', 'r', encoding='utf-8').read()
marker = '\ndef handle_actions_execute(event):'
idx = content.find(marker)
if idx == -1:
    print('ERROR: marker not found')
else:
    content = content[:idx] + new_fns + content[idx:]
    open('member-handler/lambda_function.py', 'w', encoding='utf-8').write(content)
    print('Functions added OK')
