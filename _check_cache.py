"""Check cache freshness for a given account."""
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
cache_table = dynamodb.Table('Cost_Cache_Table')
invoices_table = dynamodb.Table('MemberPortal-Invoices')

pk = 'razkofman2013+slashmycloudbill@gmail.com#714045115933'

# Check latest daily cache entries
print("=== Cost_Cache_Table (latest DAILY entries) ===")
resp = cache_table.query(
    KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with('DAILY#2026-06'),
    ScanIndexForward=False,
    Limit=5,
    ProjectionExpression='sk,cost_amount'
)
for item in resp.get('Items', []):
    print(f"  {item['sk']}  cost={item.get('cost_amount', '?')}")

if not resp.get('Items'):
    print("  NO JUNE ENTRIES FOUND!")

# Check invoice cache for current month
print("\n=== MemberPortal-Invoices (June 2026 services) ===")
inv_resp = invoices_table.query(
    KeyConditionExpression=Key('pk').eq(pk) & Key('sk').begins_with('2026-06'),
    Limit=10,
    ProjectionExpression='sk,cost,lastSyncedAt'
)
for item in inv_resp.get('Items', []):
    print(f"  {item['sk']}  cost={item.get('cost', '?')}  synced={item.get('lastSyncedAt', '?')}")

if not inv_resp.get('Items'):
    print("  NO JUNE INVOICE ENTRIES FOUND!")

# Check refresh rate limit record
print("\n=== Refresh Rate Limit ===")
try:
    rl_resp = invoices_table.get_item(Key={'pk': 'REFRESH#714045115933', 'sk': 'RATE_LIMIT'})
    item = rl_resp.get('Item', {})
    print(f"  Last refresh: {item.get('lastRefreshAt', 'NOT FOUND')}")
    print(f"  TTL: {item.get('ttl', 'N/A')}")
except Exception as e:
    print(f"  Error: {e}")
