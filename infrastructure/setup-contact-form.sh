#!/bin/bash

# Manual Contact Form Setup
# This script creates the Lambda function and API Gateway

echo "========================================"
echo "Manual Contact Form Setup"
echo "========================================"
echo ""

REGION="us-east-1"
EMAIL="ariel.eshkol@gmail.com"

# Step 1: Verify email in SES
echo "Step 1: Verifying email in SES..."
aws ses verify-email-identity --email-address $EMAIL --region $REGION
echo "✓ Verification email sent to $EMAIL"
echo "  Please check your inbox and click the verification link!"
echo ""

# Step 2: Create IAM role for Lambda
echo "Step 2: Creating IAM role for Lambda..."

cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
    --role-name ContactFormLambdaRole \
    --assume-role-policy-document file://trust-policy.json \
    --region $REGION 2>/dev/null || echo "  Role might already exist, continuing..."

# Attach policies
aws iam attach-role-policy \
    --role-name ContactFormLambdaRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --region $REGION 2>/dev/null

cat > ses-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ContactFormLambdaRole \
    --policy-name SESEmailPolicy \
    --policy-document file://ses-policy.json \
    --region $REGION 2>/dev/null

echo "✓ IAM role and policies configured"
echo ""

# Step 3: Create Lambda function
echo "Step 3: Creating Lambda function..."
echo "  Packaging Lambda code..."

cd contact-form-handler
zip -q ../lambda-package.zip lambda_function.py
cd ..

echo "  Waiting for IAM role to propagate..."
sleep 10

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws lambda create-function \
    --function-name ContactFormHandler \
    --runtime python3.11 \
    --role arn:aws:iam::${ACCOUNT_ID}:role/ContactFormLambdaRole \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda-package.zip \
    --timeout 30 \
    --environment "Variables={RECIPIENT_EMAIL=$EMAIL,SENDER_EMAIL=$EMAIL}" \
    --region $REGION 2>/dev/null

if [ $? -ne 0 ]; then
    echo "  Function might already exist, updating..."
    
    aws lambda update-function-code \
        --function-name ContactFormHandler \
        --zip-file fileb://lambda-package.zip \
        --region $REGION
    
    aws lambda update-function-configuration \
        --function-name ContactFormHandler \
        --environment "Variables={RECIPIENT_EMAIL=$EMAIL,SENDER_EMAIL=$EMAIL}" \
        --region $REGION
fi

echo "✓ Lambda function ready"
echo ""

# Step 4: Create API Gateway
echo "Step 4: Creating API Gateway..."

API_ID=$(aws apigateway get-rest-apis \
    --query "items[?name=='ContactFormAPI'].id" \
    --output text \
    --region $REGION)

if [ -z "$API_ID" ]; then
    API_ID=$(aws apigateway create-rest-api \
        --name ContactFormAPI \
        --description "API for contact form" \
        --endpoint-configuration types=REGIONAL \
        --query 'id' \
        --output text \
        --region $REGION)
    
    echo "✓ API Gateway created: $API_ID"
else
    echo "✓ API Gateway already exists: $API_ID"
fi

# Get root resource
ROOT_ID=$(aws apigateway get-resources \
    --rest-api-id $API_ID \
    --query 'items[?path==`/`].id' \
    --output text \
    --region $REGION)

# Create /contact resource
RESOURCE_ID=$(aws apigateway get-resources \
    --rest-api-id $API_ID \
    --query "items[?pathPart=='contact'].id" \
    --output text \
    --region $REGION)

if [ -z "$RESOURCE_ID" ]; then
    RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id $API_ID \
        --parent-id $ROOT_ID \
        --path-part contact \
        --query 'id' \
        --output text \
        --region $REGION)
fi

# Create POST method
aws apigateway put-method \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --authorization-type NONE \
    --region $REGION 2>/dev/null

# Create OPTIONS method for CORS
aws apigateway put-method \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --authorization-type NONE \
    --region $REGION 2>/dev/null

# Set up Lambda integration
LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:ContactFormHandler"
INTEGRATION_URI="arn:aws:apigateway:${REGION}:lambda:path/2015-03-31/functions/${LAMBDA_ARN}/invocations"

aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri $INTEGRATION_URI \
    --region $REGION 2>/dev/null

# Set up OPTIONS integration for CORS
aws apigateway put-integration \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --type MOCK \
    --request-templates '{"application/json":"{\"statusCode\": 200}"}' \
    --region $REGION 2>/dev/null

aws apigateway put-integration-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":"'"'"'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'"'"'","method.response.header.Access-Control-Allow-Methods":"'"'"'POST,OPTIONS'"'"'","method.response.header.Access-Control-Allow-Origin":"'"'"'*'"'"'"}' \
    --region $REGION 2>/dev/null

aws apigateway put-method-response \
    --rest-api-id $API_ID \
    --resource-id $RESOURCE_ID \
    --http-method OPTIONS \
    --status-code 200 \
    --response-parameters '{"method.response.header.Access-Control-Allow-Headers":true,"method.response.header.Access-Control-Allow-Methods":true,"method.response.header.Access-Control-Allow-Origin":true}' \
    --region $REGION 2>/dev/null

# Add Lambda permission
aws lambda add-permission \
    --function-name ContactFormHandler \
    --statement-id apigateway-access \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT_ID}:${API_ID}/*/*" \
    --region $REGION 2>/dev/null

# Deploy API
aws apigateway create-deployment \
    --rest-api-id $API_ID \
    --stage-name prod \
    --region $REGION 2>/dev/null

echo "✓ API Gateway configured"
echo ""

# Cleanup
rm -f trust-policy.json ses-policy.json lambda-package.zip

# Display results
API_ENDPOINT="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod/contact"

echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "API Endpoint:"
echo "$API_ENDPOINT"
echo ""
echo "NEXT STEPS:"
echo "1. Check $EMAIL for SES verification email and click the link"
echo "2. Update script.js with this API endpoint"
echo "3. Commit and push the changes"
echo ""

echo "$API_ENDPOINT" > api-endpoint.txt
echo "API endpoint saved to api-endpoint.txt"
