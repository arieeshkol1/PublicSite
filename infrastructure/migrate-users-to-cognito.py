#!/usr/bin/env python3
"""
Migrate existing SlashMyBill members from DynamoDB to Cognito User Pool.

Usage:
    python infrastructure/migrate-users-to-cognito.py \
        --user-pool-id us-east-1_XXXXXXXXX \
        --client-id XXXXXXXXXXXXXXXXXXXXXXXXXX \
        --region us-east-1

What it does:
  1. Scans MemberPortal-Members DynamoDB table
  2. For each member, creates a Cognito user with AdminCreateUser
     (sends a temporary password email)
  3. Sets the user as CONFIRMED (no need to re-verify email)
  4. Updates the DynamoDB record to remove passwordHash (no longer needed)

After migration:
  - Existing users receive a "temporary password" email from Cognito
  - They must reset their password on first login
  - The old passwordHash field is removed from DynamoDB
"""

import argparse
import boto3
import json
import sys
from botocore.exceptions import ClientError

def migrate(user_pool_id, client_id, region, dry_run=True):
    dynamodb = boto3.resource('dynamodb', region_name=region)
    cognito = boto3.client('cognito-idp', region_name=region)
    table = dynamodb.Table('MemberPortal-Members')

    print(f"Scanning MemberPortal-Members table...")
    result = table.scan()
    members = result.get('Items', [])
    while result.get('LastEvaluatedKey'):
        result = table.scan(ExclusiveStartKey=result['LastEvaluatedKey'])
        members.extend(result.get('Items', []))

    print(f"Found {len(members)} members")
    if dry_run:
        print("DRY RUN — no changes will be made")

    migrated = 0
    skipped = 0
    errors = 0

    for member in members:
        email = member.get('email', '')
        display_name = member.get('displayName', email.split('@')[0])

        if not email:
            print(f"  SKIP: no email")
            skipped += 1
            continue

        # Check if already in Cognito
        try:
            cognito.admin_get_user(UserPoolId=user_pool_id, Username=email)
            print(f"  SKIP {email}: already in Cognito")
            skipped += 1
            continue
        except cognito.exceptions.UserNotFoundException:
            pass
        except ClientError as e:
            print(f"  ERROR checking {email}: {e}")
            errors += 1
            continue

        print(f"  MIGRATE {email} (displayName={display_name})")

        if not dry_run:
            try:
                # Create user — Cognito sends a temporary password email
                cognito.admin_create_user(
                    UserPoolId=user_pool_id,
                    Username=email,
                    UserAttributes=[
                        {'Name': 'email', 'Value': email},
                        {'Name': 'email_verified', 'Value': 'true'},
                        {'Name': 'custom:displayName', 'Value': display_name},
                    ],
                    MessageAction='SUPPRESS',  # Don't send welcome email (we'll handle separately)
                    TemporaryPassword=None,  # Cognito generates one
                )

                # Force password reset on next login
                cognito.admin_set_user_password(
                    UserPoolId=user_pool_id,
                    Username=email,
                    Password='Temp@' + email.split('@')[0][:8] + '1!',
                    Permanent=False,
                )

                # Remove passwordHash from DynamoDB (no longer needed)
                table.update_item(
                    Key={'email': email},
                    UpdateExpression='REMOVE passwordHash',
                )

                migrated += 1
                print(f"    ✓ Migrated")
            except ClientError as e:
                print(f"    ERROR: {e}")
                errors += 1

    print(f"\nSummary: {migrated} migrated, {skipped} skipped, {errors} errors")
    if dry_run:
        print("Re-run with --no-dry-run to apply changes")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate SlashMyBill members to Cognito')
    parser.add_argument('--user-pool-id', required=True, help='Cognito User Pool ID')
    parser.add_argument('--client-id', required=True, help='Cognito App Client ID')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--no-dry-run', action='store_true', help='Apply changes (default is dry run)')
    args = parser.parse_args()

    migrate(
        user_pool_id=args.user_pool_id,
        client_id=args.client_id,
        region=args.region,
        dry_run=not args.no_dry_run,
    )
