#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate the me-south-1 variant of viewmybill-stack.yaml.

Changes from the original:
1. Add BedrockRegion and SESRegion parameters (default: us-east-1)
2. Add CognitoUserPoolId and CognitoClientId as parameters (not hardcoded)
3. Change default S3 bucket names for me-south-1
4. Remove SES EmailIdentity resource (SES not available in me-south-1)
5. Update Member Handler env vars to use parameterized Cognito and cross-region refs
6. Update description
"""

import re

with open('viewmybill-stack.yaml', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update description
content = content.replace(
    "Description: 'ViewMyBill - AWS Bill Analysis Tool infrastructure'",
    "Description: 'SlashMyBill - me-south-1 deployment (Bedrock + SES cross-region to us-east-1)'"
)

# 2. Add new parameters after existing ones
new_params = """
  BedrockRegion:
    Type: String
    Default: 'us-east-1'
    Description: Region where Bedrock is available (cross-region from me-south-1)

  SESRegion:
    Type: String
    Default: 'us-east-1'
    Description: Region where SES is available (cross-region from me-south-1)

  CognitoUserPoolId:
    Type: String
    Default: ''
    Description: Cognito User Pool ID (created separately in me-south-1)

  CognitoClientId:
    Type: String
    Default: ''
    Description: Cognito App Client ID (created separately in me-south-1)

"""

# Insert after the last existing parameter
content = content.replace(
    "\nResources:",
    new_params + "\nResources:"
)

# 3. Change default S3 bucket
content = content.replace(
    "Default: 'aws-bill-analyzer-storage-991105135552'",
    "Default: 'slashmybill-storage-me-south-1'"
)

# 4. Remove SES EmailIdentity resource (SES not in me-south-1)
# Find and remove the SES block
ses_start = content.find("  # SES Email Identity")
if ses_start == -1:
    ses_start = content.find("  SESEmailIdentity:")
if ses_start > 0:
    ses_end = content.find("\n  # ====", ses_start + 10)
    if ses_end > ses_start:
        removed = content[ses_start:ses_end]
        content = content.replace(removed, "  # SES EmailIdentity removed - SES not available in me-south-1\n\n")

# 5. Update Member Handler Cognito env vars to use parameters
content = content.replace(
    "COGNITO_USER_POOL_ID: 'us-east-1_FlR2CmFu0'",
    "COGNITO_USER_POOL_ID: !Ref CognitoUserPoolId"
)
content = content.replace(
    "COGNITO_CLIENT_ID: '3shmdb332mm8sjheopdu9sg8o4'",
    "COGNITO_CLIENT_ID: !Ref CognitoClientId"
)

# 6. Add BEDROCK_REGION and SES_REGION env vars to Member Handler
content = content.replace(
    "          BEDROCK_MODEL_ID: !Ref BedrockModelId",
    "          BEDROCK_MODEL_ID: !Ref BedrockModelId\n"
    "          BEDROCK_REGION: !Ref BedrockRegion\n"
    "          SES_REGION: !Ref SESRegion"
)

# 7. Update Cognito resource ARN in IAM policies to be region-agnostic
content = content.replace(
    "Resource: 'arn:aws:cognito-idp:us-east-1:991105135552:userpool/us-east-1_FlR2CmFu0'",
    "Resource: !Sub 'arn:aws:cognito-idp:${AWS::Region}:${AWS::AccountId}:userpool/*'"
)

# 8. Update Bedrock ARNs to use BedrockRegion
content = content.replace(
    "- !Sub 'arn:aws:bedrock:us-east-1::foundation-model/${BedrockModelId}'",
    "- !Sub 'arn:aws:bedrock:${BedrockRegion}::foundation-model/${BedrockModelId}'"
)
content = content.replace(
    "- 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'",
    "- !Sub 'arn:aws:bedrock:${BedrockRegion}::foundation-model/amazon.nova-lite-v1:0'"
)
content = content.replace(
    "- !Sub 'arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:agent/*'",
    "- !Sub 'arn:aws:bedrock:${BedrockRegion}:${AWS::AccountId}:agent/*'"
)
content = content.replace(
    "- !Sub 'arn:aws:bedrock:${AWS::Region}:${AWS::AccountId}:agent-alias/*'",
    "- !Sub 'arn:aws:bedrock:${BedrockRegion}:${AWS::AccountId}:agent-alias/*'"
)

# Write the me-south-1 variant
with open('viewmybill-stack-me-south-1.yaml', 'w', encoding='utf-8') as f:
    f.write(content)

print("Generated viewmybill-stack-me-south-1.yaml")
print()
print("Key differences from original:")
print("  - BedrockRegion, SESRegion, CognitoUserPoolId, CognitoClientId parameters added")
print("  - SES EmailIdentity resource removed (SES not in me-south-1)")
print("  - Cognito pool/client IDs parameterized (not hardcoded)")
print("  - Bedrock ARNs use BedrockRegion parameter")
print("  - BEDROCK_REGION and SES_REGION env vars added to Member Handler")
print("  - Default S3 bucket changed to slashmybill-storage-me-south-1")
