# Cost Optimization Guide

This document details all cost optimization settings and strategies for the Mobile Knowledge Assistant.

## Overview

The system is designed to minimize costs while maintaining performance and reliability. All services use serverless, pay-per-use pricing models with no fixed monthly fees.

## Cost Breakdown

### Monthly Cost Estimate (1000 queries/month)

| Service | Usage | Unit Cost | Monthly Cost |
|---------|-------|-----------|--------------|
| API Gateway | 1000 requests | $3.50 per million | $0.0035 |
| Lambda (Query Handler) | 1000 invocations × 1s | $0.20 per million | $0.0002 |
| Lambda (Answer Retrieval) | 1000 invocations × 0.5s | $0.20 per million | $0.0001 |
| Lambda (Document Ingestion) | 10 documents × 5s | $0.20 per million | $0.00001 |
| DynamoDB (Reads) | 1000 queries × 2 RCU | $0.25 per million | $0.0005 |
| DynamoDB (Writes) | 1000 transcripts | $1.25 per million | $0.00125 |
| S3 (Storage) | 1 GB | $0.023 per GB | $0.023 |
| S3 (Requests) | 10 uploads | $0.005 per 1000 | $0.00005 |
| CloudWatch Logs | 100 MB | $0.50 per GB | $0.05 |
| **Total** | | | **~$0.08/month** |

### Maximum Cost with Rate Limiting

With rate limiting at 100 requests/hour:
- Maximum daily requests: 2400
- Maximum monthly requests: 72,000
- Maximum monthly cost: **~$5.76**

## Cost Optimization Settings

### 1. API Gateway

**Rate Limiting**:
```yaml
Quota:
  Limit: 2400        # Daily limit
  Period: DAY
Throttle:
  BurstLimit: 10     # Concurrent requests
  RateLimit: 100     # Requests per second
```

**Benefits**:
- Prevents runaway costs from abuse or bugs
- Caps maximum monthly cost at predictable level
- Protects backend services from overload

**Cost Impact**: Limits maximum API Gateway cost to $0.25/month

---

### 2. Lambda Functions

**Memory Allocation**:
```yaml
QueryHandler: 256 MB      # Minimal for API routing
AnswerRetrieval: 256 MB   # Sufficient for DynamoDB queries
DocumentIngestion: 512 MB # Needed for PDF/DOCX parsing
```

**Timeout Settings**:
```yaml
QueryHandler: 60 seconds       # API Gateway timeout
AnswerRetrieval: 30 seconds    # Query + format time
DocumentIngestion: 300 seconds # Large document processing
```

**Architecture**:
```yaml
Architectures: arm64  # 20% cheaper than x86_64
```

**Benefits**:
- arm64 provides 20% cost savings vs x86
- Right-sized memory reduces per-invocation cost
- Appropriate timeouts prevent hanging functions

**Cost Impact**: Saves ~$0.04/month vs x86 with 512MB memory

---

### 3. DynamoDB

**Billing Mode**:
```yaml
BillingMode: PAY_PER_REQUEST  # On-demand pricing
```

**Benefits**:
- No fixed monthly costs
- Automatic scaling
- Pay only for actual reads/writes
- No capacity planning needed

**Alternative (Provisioned)**:
- Provisioned capacity: $0.00065/hour per RCU = $0.47/month minimum
- On-demand: $0.00 base cost
- Break-even: ~720 RCU-hours/month = ~24 reads/hour

**Cost Impact**: Saves $0.47/month vs minimum provisioned capacity

**TTL Configuration**:
```yaml
Transcripts:
  TimeToLiveAttribute: expiresAt
  TTL: 90 days
```

**Benefits**:
- Automatic deletion of old transcripts
- No storage costs for expired data
- No manual cleanup needed

**Cost Impact**: Prevents unbounded storage growth

---

### 4. S3

**Lifecycle Policies**:
```yaml
Rules:
  - Id: DeleteOldLambdaPackages
    Prefix: lambda/
    ExpirationInDays: 90
    Status: Enabled
  
  - Id: TransitionOldDocuments
    Prefix: documents/
    Transitions:
      - Days: 90
        StorageClass: STANDARD_IA
      - Days: 180
        StorageClass: GLACIER
```

**Versioning**:
```yaml
VersioningConfiguration:
  Status: Enabled
NoncurrentVersionExpiration:
  NoncurrentDays: 30
```

**Benefits**:
- Old Lambda packages auto-deleted after 90 days
- Infrequently accessed documents moved to cheaper storage
- Old versions deleted after 30 days
- Prevents unbounded storage growth

**Cost Impact**: 
- Standard IA: 50% cheaper than Standard ($0.0125 vs $0.023 per GB)
- Glacier: 80% cheaper than Standard ($0.004 vs $0.023 per GB)
- Saves ~$0.01/month per GB after 90 days

---

### 5. CloudWatch Logs

**Retention Settings**:
```yaml
LogGroups:
  - /aws/lambda/mobile-ka-document-ingestion
    RetentionInDays: 7
  - /aws/lambda/mobile-ka-answer-retrieval
    RetentionInDays: 7
  - /aws/lambda/mobile-ka-query-handler
    RetentionInDays: 7
  - /aws/apigateway/mobile-knowledge-assistant-api
    RetentionInDays: 7
```

**Benefits**:
- Logs auto-deleted after 7 days
- Sufficient for debugging recent issues
- Prevents unbounded log storage costs

**Cost Impact**: Saves ~$0.50/month vs indefinite retention

**Log Level**:
```python
# Only log essential information
print(f"Request metadata: mode={mode}, format={format_type}, language={language}")
# Do NOT log full question content (privacy + cost)
```

**Benefits**:
- Reduces log volume
- Protects user privacy
- Lower CloudWatch costs

---

### 6. Lambda Cold Starts

**Optimization Strategy**:
```yaml
# Use arm64 for faster cold starts
Architectures: arm64

# Minimal dependencies
requirements.txt:
  - boto3 (included in Lambda runtime)
  - langdetect (small library)
  - PyPDF2 (only for document ingestion)
  - python-docx (only for document ingestion)
```

**Benefits**:
- Faster cold starts = lower duration costs
- Smaller deployment packages
- Better user experience

**Cost Impact**: Reduces average invocation time by ~200ms = ~$0.01/month

---

### 7. API Gateway Caching (Optional)

**Not Currently Enabled** (to minimize costs), but can be enabled if needed:

```yaml
CacheClusterEnabled: true
CacheClusterSize: '0.5'  # Smallest size
CacheTtlInSeconds: 300   # 5 minutes
```

**Cost**: $0.02/hour = $14.40/month

**When to Enable**:
- If same questions asked repeatedly
- If response time is critical
- If query volume exceeds 10,000/month

**Break-even**: ~50,000 queries/month

---

## Cost Monitoring

### CloudWatch Alarms

Set up billing alarms to prevent unexpected costs:

```bash
# Create billing alarm for $10/month
aws cloudwatch put-metric-alarm \
  --alarm-name mobile-ka-billing-alarm \
  --alarm-description "Alert when monthly costs exceed $10" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 21600 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=Currency,Value=USD
```

### Cost Explorer

Monitor costs by service:

```bash
# Get current month costs
aws ce get-cost-and-usage \
  --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE
```

### Usage Tracking

Track API usage:

```bash
# Get API Gateway usage
aws apigateway get-usage \
  --usage-plan-id USAGE_PLAN_ID \
  --start-date $(date -d "30 days ago" +%Y-%m-%d) \
  --end-date $(date +%Y-%m-%d)
```

---

## Cost Reduction Strategies

### 1. Reduce Lambda Memory (if possible)

Test with lower memory settings:

```bash
# Test with 128 MB
aws lambda update-function-configuration \
  --function-name mobile-ka-query-handler \
  --memory-size 128

# Monitor performance
aws logs tail /aws/lambda/mobile-ka-query-handler --follow
```

**Potential Savings**: 50% reduction in Lambda costs

---

### 2. Optimize DynamoDB Queries

Use efficient query patterns:

```python
# Good: Query with GSI
response = table.query(
    IndexName='language-index',
    KeyConditionExpression='language = :lang',
    ExpressionAttributeValues={':lang': 'en'}
)

# Bad: Scan entire table
response = table.scan()  # Expensive!
```

**Potential Savings**: 90% reduction in DynamoDB costs

---

### 3. Batch Operations

Process multiple items in single request:

```python
# Good: Batch write
with table.batch_writer() as batch:
    for item in items:
        batch.put_item(Item=item)

# Bad: Individual writes
for item in items:
    table.put_item(Item=item)  # Multiple requests!
```

**Potential Savings**: 50% reduction in DynamoDB write costs

---

### 4. Compress Lambda Packages

Reduce deployment package size:

```bash
# Remove unnecessary files
zip -r function.zip . -x "*.pyc" -x "__pycache__/*" -x "tests/*"

# Use Lambda layers for common dependencies
aws lambda publish-layer-version \
  --layer-name common-dependencies \
  --zip-file fileb://layer.zip
```

**Potential Savings**: Faster deployments, lower storage costs

---

### 5. Use Reserved Capacity (High Volume Only)

If query volume exceeds 100,000/month, consider:

**DynamoDB Reserved Capacity**:
- 1-year commitment: 43% savings
- 3-year commitment: 76% savings

**Savings Calculator**:
- 100,000 queries/month = 200,000 RCU-hours
- On-demand: $50/month
- Reserved (1-year): $28.50/month
- Reserved (3-year): $12/month

**Break-even**: ~50,000 queries/month

---

## Cost Comparison

### vs Traditional Server

**EC2 t3.micro (24/7)**:
- Instance: $7.50/month
- EBS: $1/month
- Data transfer: $1/month
- **Total: $9.50/month**

**Serverless (1000 queries/month)**:
- **Total: $0.08/month**

**Savings**: 99% cheaper for low volume

**Break-even**: ~120,000 queries/month

---

### vs Managed Services

**AWS Kendra (Managed Search)**:
- Developer edition: $810/month
- Enterprise edition: $1,008/month

**Serverless (1000 queries/month)**:
- **Total: $0.08/month**

**Savings**: 99.99% cheaper

---

## Recommendations

### For Low Volume (<10,000 queries/month)
✅ Use current configuration (on-demand, serverless)
✅ Keep rate limiting at 100 req/hour
✅ Monitor costs monthly
❌ Don't enable API Gateway caching
❌ Don't use reserved capacity

### For Medium Volume (10,000-100,000 queries/month)
✅ Keep current configuration
✅ Consider increasing rate limits
✅ Monitor DynamoDB query patterns
✅ Optimize Lambda memory if needed
❌ Don't use reserved capacity yet

### For High Volume (>100,000 queries/month)
✅ Consider DynamoDB reserved capacity
✅ Enable API Gateway caching
✅ Use Lambda reserved concurrency
✅ Implement more aggressive caching
✅ Consider CloudFront for API distribution

---

## Cost Optimization Checklist

- [x] Use arm64 Lambda architecture
- [x] Right-size Lambda memory allocations
- [x] Set appropriate Lambda timeouts
- [x] Use DynamoDB on-demand billing
- [x] Configure DynamoDB TTL for transcripts
- [x] Set CloudWatch log retention to 7 days
- [x] Enable S3 lifecycle policies
- [x] Configure S3 versioning with expiration
- [x] Implement API Gateway rate limiting
- [x] Use efficient DynamoDB query patterns
- [x] Batch DynamoDB operations
- [x] Minimize CloudWatch log volume
- [x] Set up billing alarms
- [ ] Monitor costs monthly
- [ ] Review and optimize based on usage patterns

---

## Additional Resources

- [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/)
- [DynamoDB Pricing](https://aws.amazon.com/dynamodb/pricing/)
- [API Gateway Pricing](https://aws.amazon.com/api-gateway/pricing/)
- [S3 Pricing](https://aws.amazon.com/s3/pricing/)
- [AWS Cost Explorer](https://aws.amazon.com/aws-cost-management/aws-cost-explorer/)
- [AWS Pricing Calculator](https://calculator.aws/)
