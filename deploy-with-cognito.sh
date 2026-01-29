#!/bin/bash
# Deploy TAG Video Systems Stack with Cognito Authentication

echo "========================================"
echo "TAG Video Systems - Cognito Deployment"
echo "========================================"
echo ""

# Step 1: Deploy CDK Stack
echo "[1/5] Deploying CDK Stack..."
cdk deploy --require-approval never

if [ $? -ne 0 ]; then
    echo "❌ Failed to deploy CDK stack"
    exit 1
fi

echo "✓ CDK Stack deployed successfully"
echo ""

# Step 2: Get Cognito outputs
echo "[2/5] Retrieving Cognito configuration..."
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name TagVideoProbeStack \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
    --output text)

CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name TagVideoProbeStack \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
    --output text)

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    echo "❌ Could not retrieve Cognito IDs from stack outputs"
    exit 1
fi

echo "✓ Retrieved Cognito configuration"
echo "  User Pool ID: $USER_POOL_ID"
echo "  Client ID: $CLIENT_ID"
echo ""

# Step 3: Update login.html
echo "[3/5] Updating login.html with Cognito configuration..."
sed -i.bak "s/REPLACE_WITH_USER_POOL_ID/$USER_POOL_ID/g" dashboard/login.html
sed -i.bak "s/REPLACE_WITH_CLIENT_ID/$CLIENT_ID/g" dashboard/login.html

echo "✓ login.html updated"
echo ""

# Step 4: Set admin password
echo "[4/5] Setting admin user password..."
aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username admin \
    --password "TagVideo2024!" \
    --permanent \
    --region us-east-1

if [ $? -ne 0 ]; then
    echo "⚠ Could not set password (user might not exist yet)"
    echo "  Creating admin user..."
    
    aws cognito-idp admin-create-user \
        --user-pool-id "$USER_POOL_ID" \
        --username admin \
        --user-attributes Name=email,Value=admin@tagvideo.local \
        --message-action SUPPRESS \
        --region us-east-1
    
    aws cognito-idp admin-set-user-password \
        --user-pool-id "$USER_POOL_ID" \
        --username admin \
        --password "TagVideo2024!" \
        --permanent \
        --region us-east-1
fi

echo "✓ Admin password set"
echo ""

# Step 5: Re-deploy to update S3
echo "[5/5] Re-deploying to update S3 with configured login page..."
cdk deploy --require-approval never

if [ $? -ne 0 ]; then
    echo "❌ Re-deployment failed!"
    exit 1
fi

echo "✓ Re-deployment complete"
echo ""

# Get final outputs
echo "========================================"
echo "Deployment Complete!"
echo "========================================"
echo ""

DASHBOARD_URL=$(aws cloudformation describe-stacks \
    --stack-name TagVideoProbeStack \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='DashboardUrl'].OutputValue" \
    --output text)

API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name TagVideoProbeStack \
    --region us-east-1 \
    --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
    --output text)

echo "Dashboard URL: $DASHBOARD_URL"
echo "API Endpoint: $API_ENDPOINT"
echo ""
echo "Login Credentials:"
echo "  Username: admin"
echo "  Password: TagVideo2024!"
echo ""
echo "Next Steps:"
echo "1. Open the Dashboard URL in your browser"
echo "2. Login with the credentials above"
echo "3. Run the edge simulator to see probe data"
echo ""
