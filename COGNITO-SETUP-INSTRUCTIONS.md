# Cognito Authentication Setup Instructions

## Step 1: Deploy the Stack

Make sure you're using the correct AWS account (991105135552):

```bash
# Set AWS credentials for account 991105135552
export AWS_PROFILE=your-profile-name
# OR
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key

# Deploy the stack
cdk deploy
```

## Step 2: Get Cognito Outputs

After deployment, note the outputs:

```
TagVideoProbeStack.UserPoolId = us-east-1_XXXXXXXXX
TagVideoProbeStack.UserPoolClientId = XXXXXXXXXXXXXXXXXXXXXXXXXX
```

## Step 3: Update Login Page Configuration

**Windows PowerShell:**
```powershell
.\update-cognito-config.ps1 -UserPoolId "us-east-1_XXXXXXXXX" -ClientId "XXXXXXXXXXXXXXXXXXXXXXXXXX"
```

**Linux/Mac:**
```bash
chmod +x update-cognito-config.sh
./update-cognito-config.sh us-east-1_XXXXXXXXX XXXXXXXXXXXXXXXXXXXXXXXXXX
```

## Step 4: Set Admin Password

```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username admin \
  --password "TagVideo2024!" \
  --permanent \
  --region us-east-1
```

## Step 5: Re-deploy to Update S3

```bash
cdk deploy
```

## Step 6: Test Login

1. Open the Dashboard URL from CDK outputs
2. You should see the login page
3. Login with:
   - Username: `admin`
   - Password: `TagVideo2024!`
4. You should be redirected to the monitoring dashboard

## Troubleshooting

### Error: "Cognito not configured"
- Make sure you ran the update-cognito-config script
- Check that dashboard/login.html has the actual Cognito IDs (not REPLACE_WITH_...)
- Re-deploy with `cdk deploy`

### Error: "User does not exist"
- The Cognito User Pool was created but the user wasn't
- Create user manually:
```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username admin \
  --user-attributes Name=email,Value=admin@tagvideo.local \
  --temporary-password "TempPass123!" \
  --region us-east-1

aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username admin \
  --password "TagVideo2024!" \
  --permanent \
  --region us-east-1
```

### Error: "Password does not conform to policy"
- Password must have: 8+ chars, uppercase, lowercase, digits
- Use: `TagVideo2024!`

### Error: "net::ERR_NAME_NOT_RESOLVED"
- The Cognito IDs in login.html are still placeholders
- Run the update-cognito-config script again
- Verify the file was updated: `cat dashboard/login.html | grep UserPoolId`

## Additional Users

To create more users:

```bash
# Create operator user
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username operator \
  --user-attributes Name=email,Value=operator@tagvideo.local \
  --region us-east-1

# Set permanent password
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_XXXXXXXXX \
  --username operator \
  --password "Operator123!" \
  --permanent \
  --region us-east-1
```

## Verification

After setup, verify:

1. ✅ CDK deployed successfully
2. ✅ Cognito User Pool exists in AWS Console
3. ✅ Admin user exists in User Pool
4. ✅ login.html has real Cognito IDs (not placeholders)
5. ✅ S3 bucket updated with new login.html
6. ✅ Login page loads without errors
7. ✅ Can login with admin/TagVideo2024!
8. ✅ Redirected to dashboard after login
9. ✅ Logout button works

## Architecture

```
User → S3 (login.html) → Cognito User Pool → Authentication
                                ↓
                         JWT Tokens stored in sessionStorage
                                ↓
                         S3 (index.html) → Dashboard
```

The authentication is fully serverless using AWS Cognito with no additional backend required.
