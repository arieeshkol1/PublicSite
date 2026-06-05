"""
Intent Classifier for AI Chat Optimization.

Classifies user questions into target categories using keyword matching
and pattern rules. No LLM calls — must execute in under 50ms.

Categories:
  ec2      — Cost Explorer + EC2 DescribeInstances + CloudWatch
  rds      — Cost Explorer + RDS DescribeInstances
  s3       — Cost Explorer + S3 ListBuckets
  lambda   — Cost Explorer + Lambda ListFunctions
  cost-general — Cost Explorer only (no resource APIs)
  network  — Cost Explorer + NAT Gateways + EIPs + VPC Endpoints
  storage  — Cost Explorer + EBS Volumes
  compute  — Cost Explorer + EC2 + RDS
  all      — All available APIs (current behavior)
"""

import re

# ---------------------------------------------------------------------------
# Category keyword definitions
# Each category maps to a set of keywords/phrases that indicate the user's
# question targets that specific service area.
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    'ec2': [
        'ec2', 'virtual machine', 'vm ',
        'ami', 'elastic compute', 'auto scaling', 'autoscaling',
        'launch template', 'spot instance',
        'on-demand', 'on demand',
    ],
    'rds': [
        'rds', 'database', 'db instance', 'aurora', 'mysql', 'postgres',
        'postgresql', 'mariadb', 'sql server', 'oracle db', 'neptune',
        'documentdb', 'relational database',
    ],
    's3': [
        's3', 'bucket', 'object storage', 'glacier', 'storage class',
        'lifecycle policy', 'intelligent-tiering', 'intelligent tiering',
        's3 standard', 's3 infrequent',
    ],
    'lambda': [
        'lambda', 'serverless',
        'invocation', 'invocations', 'cold start', 'concurrency',
    ],
    'commitments': [
        'reserved instance', 'reserved instances', 'savings plan', 'savings plans',
        ' ri ', 'ris', ' sp ', 'sps', 'commitment', 'commitments', 'committment', 'committments',
        'commit', 'reserve', 'reservation', 'coverage', 'utilization',
        'compute savings', 'ec2 savings', 'convertible ri', 'standard ri',
        'no upfront', 'partial upfront', 'all upfront',
    ],
    'cost-general': [
        'total cost', 'overall cost', 'monthly bill', 'bill',
        'spending', 'spend', 'budget', 'forecast', 'trend',
        'cost breakdown', 'how much', 'expensive', 'cheapest',
        'save money', 'reduce cost', 'cut cost',
        'cost optimization', 'optimize cost', 'billing',
        'invoice', 'charge', 'pricing', 'cost',
    ],
    'network': [
        'nat gateway', 'nat', 'elastic ip', 'eip', 'vpc endpoint',
        'vpn', 'transit gateway', 'direct connect', 'data transfer',
        'bandwidth', 'network', 'networking', 'route 53', 'route53',
        'cloudfront', 'cdn', 'load balancer', 'elb', 'alb', 'nlb',
    ],
    'storage': [
        'ebs', 'volume', 'volumes', 'disk', 'gp2', 'gp3', 'io1', 'io2',
        'snapshot', 'snapshots', 'efs', 'fsx', 'storage',
        'block storage',
    ],
    'compute': [
        'compute', 'cpu', 'vcpu', 'processor', 'server', 'servers',
        'workload', 'capacity', 'rightsizing', 'right-sizing',
        'right sizing', 'underutilized', 'over-provisioned',
    ],
}

# Precompile regex patterns for each category for faster matching
_CATEGORY_PATTERNS: dict[str, re.Pattern] = {}
for _cat, _keywords in CATEGORY_KEYWORDS.items():
    # Build alternation pattern; escape special regex chars in keywords
    escaped = [re.escape(kw) for kw in _keywords]
    _CATEGORY_PATTERNS[_cat] = re.compile(
        r'(?:' + '|'.join(escaped) + r')', re.IGNORECASE
    )

# Category-to-API mapping (informational, used by data gatherer)
CATEGORY_API_MAPPING: dict[str, list[str]] = {
    'ec2': ['cost_explorer', 'ec2_describe_instances', 'cloudwatch'],
    'rds': ['cost_explorer', 'rds_describe_instances'],
    's3': ['cost_explorer', 's3_list_buckets'],
    'lambda': ['cost_explorer', 'lambda_list_functions'],
    'commitments': ['cost_explorer', 'sp_ri_coverage'],
    'cost-general': ['cost_explorer'],
    'network': ['cost_explorer', 'nat_gateways', 'eips', 'vpc_endpoints'],
    'storage': ['cost_explorer', 'ebs_volumes'],
    'compute': ['cost_explorer', 'ec2_describe_instances', 'rds_describe_instances'],
    'all': [
        'cost_explorer', 'ec2_describe_instances', 'cloudwatch',
        'rds_describe_instances', 's3_list_buckets', 'lambda_list_functions',
        'nat_gateways', 'eips', 'vpc_endpoints', 'ebs_volumes',
        'sp_ri_coverage',
    ],
}

# Maximum distinct categories before we fall back to 'all'
_MAX_CATEGORIES = 2


def _classify_intent(question: str) -> set[str]:
    """
    Classify a user question into target categories using keyword matching.

    Returns a set of categories from:
        {'ec2', 'rds', 's3', 'lambda', 'cost-general', 'network', 'storage', 'compute'}

    Returns {'all'} if:
        - The question matches more than 2 distinct categories
        - No category can be confidently matched
        - The question is ambiguous or too broad

    Must execute in <50ms (no LLM calls).
    """
    if not question or not question.strip():
        return {'all'}

    question_lower = question.lower()
    matched_categories: set[str] = set()

    for category, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(question_lower):
            matched_categories.add(category)

    # No confident match — return all
    if not matched_categories:
        return {'all'}

    # If 'compute' is matched alongside 'ec2' or 'rds', it's not truly
    # a separate intent — absorb into compute which already covers both
    if 'compute' in matched_categories:
        if 'ec2' in matched_categories or 'rds' in matched_categories:
            matched_categories.discard('ec2')
            matched_categories.discard('rds')

    # If 'commitments' is matched, it's standalone — don't also run ec2 instance enumeration
    # unless the user specifically asked about ec2 instances alongside commitments
    if 'commitments' in matched_categories and 'ec2' in matched_categories:
        matched_categories.discard('ec2')  # commitments doesn't need full instance scan

    # Too many distinct categories — ambiguous, fetch all
    if len(matched_categories) > _MAX_CATEGORIES:
        return {'all'}

    return matched_categories


def get_apis_for_intent(intent: set[str]) -> set[str]:
    """
    Given a set of intent categories, return the union of APIs that should be called.

    If intent is {'all'}, returns the full API set.
    """
    if 'all' in intent:
        return set(CATEGORY_API_MAPPING['all'])

    apis: set[str] = set()
    for category in intent:
        if category in CATEGORY_API_MAPPING:
            apis.update(CATEGORY_API_MAPPING[category])
    return apis
