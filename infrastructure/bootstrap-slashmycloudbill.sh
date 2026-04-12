#!/bin/bash
# bootstrap-slashmycloudbill.sh
# Run this ONCE in AWS CloudShell to:
#   1. Fix eshkolai.com SSL (restore eshkolai cert on shared distribution)
#   2. Deploy the dedicated slashmycloudbill.com CloudFront stack
#   3. Update GitHubDeployRole so future GitHub Actions deploys work
#
# Usage: bash ~/bootstrap-slashmycloudbill.sh

set -e

ACCOUNT_ID="991105135552"
SHARED_DIST_ID="E12JIHGHK40OLE"
ESHKOLAI_CERT="arn:aws:acm:us-east-1:${ACCOUNT_ID}:certificate/26f3508f-ef03-4b6a-a48c-9f810ea5260c"
SMB_CERT="arn:aws:acm:us-east-1:${ACCOUNT_ID}:certificate/5f9cd85b-591f-4787-963b-8f616c448588"
SMB_HOSTED_ZONE="Z08610352PUNQ7MUZTRVI"
ROLE_NAME="GitHubDeployRole"

echo "============================================"
echo " SlashMyCloudBill Bootstrap Script"
echo "============================================"
echo ""

# ── STEP 1: Restore eshkolai.com on shared distribution ──────────────────────
echo "STEP 1: Restoring eshkolai.com SSL on shared CloudFront distribution..."

ETAG=$(aws cloudfront get-distribution-config --id "$SHARED_DIST_ID" --query "ETag" --output text)
aws cloudfront get-distribution-config --id "$SHARED_DIST_ID" \
  --query "DistributionConfig" --output json > /tmp/cf_eshkolai.json

python3 - <<PYEOF
import json

with open('/tmp/cf_eshkolai.json') as f:
    c = json.load(f)

# Keep only eshkolai aliases on the shared distribution
items = [i for i in c.get('Aliases', {}).get('Items', []) if 'eshkolai' in i]
c['Aliases'] = {'Quantity': len(items), 'Items': items}

# Use the eshkolai.com cert (covers both eshkolai.com and www.eshkolai.com)
c['ViewerCertificate'] = {
    'ACMCertificateArn': '${ESHKOLAI_CERT}',
    'SSLSupportMethod': 'sni-only',
    'MinimumProtocolVersion': 'TLSv1.2_2021',
    'CloudFrontDefaultCertificate': False
}

# Remove SlashMyCloudBill routing function (not needed on eshkolai distribution)
dcb = c.get('DefaultCacheBehavior', {})
fa = dcb.get('FunctionAssociations', {'Quantity': 0, 'Items': []})
fn_items = [x for x in fa.get('Items', []) if 'SlashMyCloudBill' not in x.get('FunctionARN', '')]
dcb['FunctionAssociations'] = {'Quantity': len(fn_items), 'Items': fn_items}
c['DefaultCacheBehavior'] = dcb

with open('/tmp/cf_eshkolai_new.json', 'w') as f:
    json.dump(c, f)

print('Aliases kept:', items)
PYEOF

aws cloudfront update-distribution \
  --id "$SHARED_DIST_ID" \
  --distribution-config file:///tmp/cf_eshkolai_new.json \
  --if-match "$ETAG" > /dev/null

echo "✓ eshkolai.com SSL restored on shared distribution"
echo ""

# ── STEP 2: Ensure CloudFront function exists ─────────────────────────────────
echo "STEP 2: Creating/updating SlashMyCloudBill-Router CloudFront function..."

# Create the function code inline (same as infrastructure/cf-function-slashmycloudbill.js)
cat > /tmp/cf-router.js << 'JSEOF'
function handler(event) {
    var request = event.request;
    var host = (request.headers.host && request.headers.host.value) || '';
    var uri = request.uri;

    // Redirect www to root domain
    if (host.startsWith('www.')) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                location: { value: 'https://slashmycloudbill.com' + uri }
            }
        };
    }

    // If requesting a file with extension, serve as-is
    var ext = uri.split('.').pop().toLowerCase();
    var staticExts = ['css','js','png','jpg','jpeg','gif','svg','ico','woff','woff2','ttf','map','json','pdf','html'];
    if (staticExts.indexOf(ext) !== -1) {
        return request;
    }

    if (uri === '/' || uri === '') {
        request.uri = '/index.html';
        return request;
    }

    if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
        return request;
    }

    if (uri.startsWith('/members')) {
        request.uri = '/members/index.html';
        return request;
    }

    if (uri.startsWith('/admin')) {
        request.uri = '/admin/index.html';
        return request;
    }

    request.uri = '/index.html';
    return request;
}
JSEOF

# Create or update the function
EXISTING_FN=$(aws cloudfront describe-function --name "SlashMyCloudBill-Router" --query "FunctionSummary.Name" --output text 2>/dev/null || echo "")

if [ -z "$EXISTING_FN" ]; then
  aws cloudfront create-function \
    --name "SlashMyCloudBill-Router" \
    --function-config 'Comment=Routes slashmycloudbill.com,Runtime=cloudfront-js-2.0' \
    --function-code fileb:///tmp/cf-router.js > /dev/null
  echo "  Function created"
else
  FN_ETAG=$(aws cloudfront describe-function --name "SlashMyCloudBill-Router" --query "ETag" --output text)
  aws cloudfront update-function \
    --name "SlashMyCloudBill-Router" \
    --if-match "$FN_ETAG" \
    --function-config 'Comment=Routes slashmycloudbill.com,Runtime=cloudfront-js-2.0' \
    --function-code fileb:///tmp/cf-router.js > /dev/null
  echo "  Function updated"
fi

FN_ETAG2=$(aws cloudfront describe-function --name "SlashMyCloudBill-Router" --query "ETag" --output text)
aws cloudfront publish-function --name "SlashMyCloudBill-Router" --if-match "$FN_ETAG2" > /dev/null
echo "✓ SlashMyCloudBill-Router function ready"
echo ""

# ── STEP 3: Deploy dedicated slashmycloudbill.com stack ──────────────────────
echo "STEP 3: Deploying dedicated slashmycloudbill.com CloudFront stack..."

# Check cert status first
CERT_STATUS=$(aws acm describe-certificate \
  --certificate-arn "$SMB_CERT" \
  --region us-east-1 \
  --query "Certificate.Status" --output text)

echo "  slashmycloudbill.com cert status: $CERT_STATUS"

if [ "$CERT_STATUS" != "ISSUED" ]; then
  echo "  ⚠ Certificate not yet ISSUED (status: $CERT_STATUS)"
  echo "  The stack will still deploy but CloudFront may fail."
  echo "  Re-run this script after the cert is ISSUED."
fi

# Download the stack template from the repo (or use local copy if available)
TEMPLATE_PATH="infrastructure/slashmycloudbill-site-stack.yaml"
if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "  Template not found locally. Please run from repo root or upload the file."
  exit 1
fi

aws cloudformation deploy \
  --template-file "$TEMPLATE_PATH" \
  --stack-name slashmycloudbill-site \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
    CertificateArn="$SMB_CERT" \
    HostedZoneId="$SMB_HOSTED_ZONE" \
  --tags Project=SlashMyCloudBill

echo "✓ slashmycloudbill-site stack deployed"
echo ""

# ── STEP 3: Get new distribution ID and copy files ───────────────────────────
echo "STEP 4: Getting new distribution details..."

SMB_DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name slashmycloudbill-site \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
  --output text)

SMB_DIST_DOMAIN=$(aws cloudformation describe-stacks \
  --stack-name slashmycloudbill-site \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionDomain'].OutputValue" \
  --output text)

echo "  New distribution ID:     $SMB_DIST_ID"
echo "  New distribution domain: $SMB_DIST_DOMAIN"
echo ""

# ── STEP 4: Copy SlashMyBill files to new bucket ─────────────────────────────
echo "STEP 5: Copying SlashMyBill files to slashmycloudbill.com bucket..."

# Copy from existing www.eshkolai.com bucket (slashMyBill folder → root)
aws s3 sync s3://www.eshkolai.com/slashMyBill/ s3://slashmycloudbill.com/ \
  --cache-control "no-cache, no-store, must-revalidate" || true

# Copy shared assets
for asset in SlashMyBill.png styles.css; do
  aws s3 cp s3://www.eshkolai.com/$asset s3://slashmycloudbill.com/$asset \
    --cache-control "max-age=2592000" 2>/dev/null || true
done

# Copy members and admin
aws s3 sync s3://www.eshkolai.com/members/ s3://slashmycloudbill.com/members/ \
  --cache-control "no-cache, no-store, must-revalidate" || true
aws s3 sync s3://www.eshkolai.com/admin/ s3://slashmycloudbill.com/admin/ \
  --cache-control "no-cache, no-store, must-revalidate" || true

echo "✓ Files copied to slashmycloudbill.com bucket"
echo ""

# ── STEP 6: Update GitHubDeployRole permissions ───────────────────────────────
echo "STEP 6: Updating GitHubDeployRole with CloudFormation permissions..."

# Check if the role exists
ROLE_EXISTS=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.RoleName" --output text 2>/dev/null || echo "")

if [ -z "$ROLE_EXISTS" ]; then
  echo "  ⚠ Role $ROLE_NAME not found. Skipping IAM update."
  echo "  GitHub Actions may use a different role name."
else
  # Add inline policy for slashmycloudbill CloudFormation
  aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "SlashMyCloudBillCFPermissions" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"cloudformation:CreateStack\",
            \"cloudformation:UpdateStack\",
            \"cloudformation:DeleteStack\",
            \"cloudformation:DescribeStacks\",
            \"cloudformation:DescribeStackEvents\",
            \"cloudformation:DescribeStackResources\",
            \"cloudformation:GetTemplate\",
            \"cloudformation:ValidateTemplate\",
            \"cloudformation:ListStacks\",
            \"cloudformation:ListStackResources\",
            \"cloudformation:CreateChangeSet\",
            \"cloudformation:DescribeChangeSet\",
            \"cloudformation:ExecuteChangeSet\",
            \"cloudformation:DeleteChangeSet\",
            \"cloudformation:GetTemplateSummary\"
          ],
          \"Resource\": [
            \"arn:aws:cloudformation:us-east-1:${ACCOUNT_ID}:stack/slashmycloudbill-site/*\",
            \"arn:aws:cloudformation:us-east-1:${ACCOUNT_ID}:stack/aws-bill-analyzer-*/*\"
          ]
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"cloudfront:CreateDistribution\",
            \"cloudfront:UpdateDistribution\",
            \"cloudfront:DeleteDistribution\",
            \"cloudfront:GetDistribution\",
            \"cloudfront:GetDistributionConfig\",
            \"cloudfront:ListDistributions\",
            \"cloudfront:CreateInvalidation\",
            \"cloudfront:CreateFunction\",
            \"cloudfront:UpdateFunction\",
            \"cloudfront:PublishFunction\",
            \"cloudfront:DescribeFunction\",
            \"cloudfront:ListFunctions\",
            \"cloudfront:TagResource\"
          ],
          \"Resource\": \"*\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"route53:ChangeResourceRecordSets\",
            \"route53:GetHostedZone\",
            \"route53:ListResourceRecordSets\"
          ],
          \"Resource\": \"arn:aws:route53:::hostedzone/${SMB_HOSTED_ZONE}\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [
            \"s3:CreateBucket\",
            \"s3:PutBucketPolicy\",
            \"s3:PutBucketWebsite\",
            \"s3:PutBucketPublicAccessBlock\",
            \"s3:PutBucketTagging\",
            \"s3:ListBucket\",
            \"s3:PutObject\",
            \"s3:GetObject\",
            \"s3:DeleteObject\",
            \"s3:GetBucketLocation\"
          ],
          \"Resource\": [
            \"arn:aws:s3:::slashmycloudbill.com\",
            \"arn:aws:s3:::slashmycloudbill.com/*\"
          ]
        }
      ]
    }"
  echo "✓ GitHubDeployRole updated with slashmycloudbill permissions"
fi

echo ""
echo "============================================"
echo " Bootstrap Complete!"
echo "============================================"
echo ""
echo "Distribution ID:  $SMB_DIST_ID"
echo "Distribution URL: https://$SMB_DIST_DOMAIN"
echo ""
echo "DNS is already pointing to the new distribution (Route 53 updated by CF stack)."
echo "Wait 5-15 minutes for CloudFront to deploy, then test:"
echo "  https://slashmycloudbill.com"
echo ""
echo "eshkolai.com is restored and should work at:"
echo "  https://www.eshkolai.com"
echo "  https://eshkolai.com"
echo ""
echo "Next: push any change to main branch to trigger GitHub Actions"
echo "and verify the full deploy pipeline works end-to-end."
