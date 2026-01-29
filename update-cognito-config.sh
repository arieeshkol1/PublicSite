#!/bin/bash
# Update Cognito configuration in login.html after deployment

USER_POOL_ID=$1
CLIENT_ID=$2

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    echo "Usage: ./update-cognito-config.sh <USER_POOL_ID> <CLIENT_ID>"
    exit 1
fi

# Update login.html with actual Cognito IDs
sed -i "s/YOUR_USER_POOL_ID/$USER_POOL_ID/g" dashboard/login.html
sed -i "s/YOUR_CLIENT_ID/$CLIENT_ID/g" dashboard/login.html

echo "✓ Updated Cognito configuration in login.html"
echo "  User Pool ID: $USER_POOL_ID"
echo "  Client ID: $CLIENT_ID"
