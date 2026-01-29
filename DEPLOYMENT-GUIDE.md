# TAG Video Systems - Deployment Guide

## Prerequisites

- AWS Account: 991105135552
- AWS CLI configured
- Python 3.11+
- Node.js 18+
- Git

## Step-by-Step Deployment

### 1. Install Lambda Dependencies

```bash
cd infrastructure/lambda
npm install
cd ../..
```

### 2. Install CDK Dependencies

```bash
pip install -r infrastructure/requirements.txt
```

### 3. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap aws://991105135552/us-east-1
```

### 4. Deploy Infrastructure

```bash
cdk deploy
```

**Expected Output:**
```
✅  TagVideoProbeStack

Outputs:
TagVideoProbeStack.UserPoolId = us-east-1_XXXXXXXXX
TagVideoProbeStack.UserPoolClientId = XXXXXXXXXXXXXXXXXXXXXXXXXX
TagVideoProbeStack.ApiEndpoint = https://xxx.execute-api.us-east-1.amazonaws.com/prod/
TagVideoProbeStack.DashboardUrl = http://xxx.s3-website-us-east-1.amazonaws.com
TagVideoProbeStack.QueueUrl = https://sqs.us-east-1.amazonaws.com/991105135552/xxx
TagVideoProbeStack.TableName = TagVideoProbeStack-ProbeStatusTableXXX
```

**Save these outputs!** You'll need them for the next steps.

### 5. Configure Cognito in Login Page

After the first deployment, you'll get Cognito outputs. Update the login page:

**Windows (PowerShell):**
```powershell
.\update-cognito-config.ps1 -UserPoolId "<USER_POOL_ID>" -ClientId "<CLIENT_ID>"
```

**Linux/Mac:**
```bash
chmod +x update-cognito-config.sh
./update-cognito-config.sh <USER_POOL_ID> <CLIENT_ID>
```

### 6. Set Admin User Password

The admin user is created automatically but needs a permanent password:

```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id <USER_POOL_ID> \
  --username admin \
  --password "TagVideo2024!" \
  --permanent \
  --region us-east-1
```

### 7. Re-deploy Dashboard with Cognito Configuration

```bash
cdk deploy
```

This will update the S3 bucket with the configured login page.

### 8. Access Dashboard

1. Open the **DashboardUrl** in your browser
2. You'll be redirected to the login page
3. Login with:
   - Username: `admin`
   - Password: `TagVideo2024!`
4. After successful login, you'll see the monitoring dashboard

### 8. Run Edge Simulator

```bash
cd edge-simulator
pip install -r requirements.txt

# Replace with your actual API endpoint
export API_ENDPOINT="https://xxx.execute-api.us-east-1.amazonaws.com/prod"

# Run demo with 2 probes
chmod +x run-demo.sh
./run-demo.sh $API_ENDPOINT
```

### 7. Verify System

1. **Login Page**: Should show TAG branding and login form
2. **Dashboard**: Should show 2 green probes after login (Probe-A-Encoder, Probe-B-CDN)
3. **CloudWatch Logs**: Check Lambda logs for processing
4. **DynamoDB**: Verify probe records exist
5. **Logout**: Test logout button functionality

## Testing Chaos Engineering

### Inject FPS Drop (Critical State)

```bash
# Run probe with low FPS
python3 probe_simulator.py \
  --api $API_ENDPOINT \
  --probe-id "Probe-Test-Critical" \
  --fps 15 \
  --interval 1
```

**Expected**: Dashboard shows red indicator within 5 seconds

### Enable Jitter and Packet Loss

```bash
python3 probe_simulator.py \
  --api $API_ENDPOINT \
  --probe-id "Probe-Chaos" \
  --fps 28 \
  --chaos --jitter --packet-loss \
  --interval 1
```

**Expected**: Dashboard shows intermittent red/green as FPS fluctuates

## Monitoring

### CloudWatch Logs

```bash
# View Lambda processor logs
aws logs tail /aws/lambda/TagVideoProbeStack-TelemetryProcessor --follow

# View Lambda reader logs
aws logs tail /aws/lambda/TagVideoProbeStack-ProbeReader --follow
```

### SQS Queue Metrics

```bash
# Check queue depth
aws sqs get-queue-attributes \
  --queue-url <YOUR_QUEUE_URL> \
  --attribute-names ApproximateNumberOfMessages
```

### DynamoDB Table

```bash
# Scan all probes
aws dynamodb scan \
  --table-name <YOUR_TABLE_NAME> \
  --region us-east-1
```

## Troubleshooting

### Issue: Dashboard shows "No probes detected"

**Solution:**
1. Verify API endpoint is correct
2. Check if simulator is running
3. Check Lambda logs for errors

### Issue: API returns 500 error

**Solution:**
1. Check Lambda has DynamoDB permissions
2. Verify table name in Lambda environment variables
3. Check CloudWatch logs for Lambda errors

### Issue: Dashboard not updating

**Solution:**
1. Check browser console for errors
2. Verify CORS is enabled on API Gateway
3. Clear browser cache and reload

### Issue: Simulator connection refused

**Solution:**
1. Verify API endpoint URL is correct
2. Check API Gateway is deployed
3. Verify security groups allow HTTPS traffic

## Performance Validation

### End-to-End Latency Test

1. Start simulator with timestamp logging
2. Note timestamp when FPS drops below 25
3. Check dashboard for red indicator
4. Calculate latency (should be < 5 seconds)

### Throughput Test

```bash
# Run multiple probes simultaneously
for i in {1..10}; do
  python3 probe_simulator.py \
    --api $API_ENDPOINT \
    --probe-id "Probe-Load-$i" \
    --fps 30 \
    --interval 0.5 &
done
```

**Expected**: System handles all probes without errors

## Cleanup

### Delete Stack

```bash
cdk destroy
```

### Manual Cleanup (if needed)

```bash
# Delete S3 bucket contents
aws s3 rm s3://<BUCKET_NAME> --recursive

# Delete DynamoDB table
aws dynamodb delete-table --table-name <TABLE_NAME>

# Delete SQS queue
aws sqs delete-queue --queue-url <QUEUE_URL>
```

## Cost Estimation

**Monthly Cost (Assuming 2 probes, 1-second intervals, 24/7):**

| Service | Usage | Cost |
|---------|-------|------|
| API Gateway | ~5.2M requests | $18.20 |
| SQS | ~5.2M requests | $2.08 |
| Lambda | ~5.2M invocations | $1.04 |
| DynamoDB | 2 items, on-demand | $0.25 |
| S3 | Static hosting | $0.02 |
| **Total** | | **~$21.59/month** |

**Free Tier Benefits:**
- Lambda: First 1M requests free
- DynamoDB: First 25GB free
- SQS: First 1M requests free

**Actual cost with free tier: ~$10-15/month**

## Next Steps

1. ✅ Deploy infrastructure
2. ✅ Configure dashboard
3. ✅ Run edge simulator
4. ✅ Validate end-to-end flow
5. ✅ Test chaos engineering
6. ✅ Review CloudWatch logs
7. ✅ Present demo to stakeholders

## Support

For issues or questions:
- Check CloudWatch Logs
- Review CDK stack events
- Verify IAM permissions
- Contact: Ariel Eshkol
