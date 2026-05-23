#!/usr/bin/env python3
"""Task 1: Add SpotSavingsLedger DynamoDB table, SNS topic, and env vars to CF template."""

import re

# Read the CF template
with open('infrastructure/viewmybill-stack.yaml', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add SpotSavingsLedger DynamoDB table + SNS topic before Outputs
spot_resources = '''
  # ============================================================
  # DynamoDB Table - Spot Savings Ledger (Gainshare Billing)
  # ============================================================
  SpotSavingsLedgerTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: SpotSavingsLedger
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: pk
          AttributeType: S
        - AttributeName: sk
          AttributeType: S
        - AttributeName: memberEmail
          AttributeType: S
        - AttributeName: recordedAt
          AttributeType: S
      KeySchema:
        - AttributeName: pk
          KeyType: HASH
        - AttributeName: sk
          KeyType: RANGE
      GlobalSecondaryIndexes:
        - IndexName: MemberTimeIndex
          KeySchema:
            - AttributeName: memberEmail
              KeyType: HASH
            - AttributeName: recordedAt
              KeyType: RANGE
          Projection:
            ProjectionType: ALL
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true
      SSESpecification:
        SSEEnabled: true
      Tags:
        - Key: Project
          Value: ViewMyBill

  # ============================================================
  # SNS Topic - Spot Interruption Notifications (Push Pipeline)
  # ============================================================
  SpotInterruptionsTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: SlashMyBill-SpotInterruptions
      Tags:
        - Key: Project
          Value: ViewMyBill

  SpotInterruptionsTopicPolicy:
    Type: AWS::SNS::TopicPolicy
    Properties:
      Topics:
        - !Ref SpotInterruptionsTopic
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: AllowEventBridgeCrossAccountPublish
            Effect: Allow
            Principal:
              Service: events.amazonaws.com
            Action: sns:Publish
            Resource: !Ref SpotInterruptionsTopic

  SpotInterruptionsSubscription:
    Type: AWS::SNS::Subscription
    Properties:
      TopicArn: !Ref SpotInterruptionsTopic
      Protocol: lambda
      Endpoint: !GetAtt MemberHandlerFunction.Arn

  SpotInterruptionsSNSPermission:
    Type: AWS::Lambda::Permission
    Properties:
      FunctionName: !Ref MemberHandlerFunction
      Action: lambda:InvokeFunction
      Principal: sns.amazonaws.com
      SourceArn: !Ref SpotInterruptionsTopic

'''

# Insert before Outputs
content = content.replace('\nOutputs:', spot_resources + '\nOutputs:')

# 2. Add SPOT_LEDGER_TABLE_NAME and SPOT_SNS_TOPIC_ARN env vars to Member Handler Lambda
old_env = "          COGNITO_CLIENT_ID: '3shmdb332mm8sjheopdu9sg8o4'"
new_env = """          COGNITO_CLIENT_ID: '3shmdb332mm8sjheopdu9sg8o4'
          SPOT_LEDGER_TABLE_NAME: !Ref SpotSavingsLedgerTable
          SPOT_SNS_TOPIC_ARN: !Ref SpotInterruptionsTopic"""
content = content.replace(old_env, new_env)

# 3. Add DynamoDB access for SpotSavingsLedger to MemberHandlerRole
# Find the EventBridgeSchedulerAccess policy and add after it
old_scheduler_policy = """        - PolicyName: EventBridgeSchedulerAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - scheduler:CreateSchedule
                  - scheduler:DeleteSchedule
                  - scheduler:UpdateSchedule
                  - scheduler:GetSchedule
                Resource: '*'
              - Effect: Allow
                Action:
                  - iam:PassRole
                Resource:
                  - !GetAtt EventBridgeSchedulerRole.Arn"""

new_scheduler_policy = old_scheduler_policy + """
        - PolicyName: DynamoDBSpotLedgerAccess
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - dynamodb:GetItem
                  - dynamodb:PutItem
                  - dynamodb:UpdateItem
                  - dynamodb:Query
                  - dynamodb:BatchWriteItem
                Resource:
                  - !GetAtt SpotSavingsLedgerTable.Arn
                  - !Sub '${SpotSavingsLedgerTable.Arn}/index/*'
        - PolicyName: SNSSpotPublish
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - sns:Publish
                Resource:
                  - !Ref SpotInterruptionsTopic"""

content = content.replace(old_scheduler_policy, new_scheduler_policy)

# 4. Add Outputs for new resources
old_outputs_end = """  AgentFeedbackTableArn:
    Description: DynamoDB Agent Feedback table ARN
    Value: !GetAtt AgentFeedbackTable.Arn"""

new_outputs_end = old_outputs_end + """

  SpotSavingsLedgerTableName:
    Description: DynamoDB table name for Spot savings ledger
    Value: !Ref SpotSavingsLedgerTable

  SpotSavingsLedgerTableArn:
    Description: DynamoDB Spot Savings Ledger table ARN
    Value: !GetAtt SpotSavingsLedgerTable.Arn

  SpotInterruptionsTopicArn:
    Description: SNS topic ARN for Spot interruption notifications
    Value: !Ref SpotInterruptionsTopic"""

content = content.replace(old_outputs_end, new_outputs_end)

with open('infrastructure/viewmybill-stack.yaml', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Task 1.1: SpotSavingsLedger DynamoDB table added")
print("✅ Task 1.3: SNS topic SlashMyBill-SpotInterruptions added")
print("✅ Environment variables SPOT_LEDGER_TABLE_NAME and SPOT_SNS_TOPIC_ARN added to Member Handler")
print("✅ IAM policies for SpotLedger and SNS added to MemberHandlerRole")
print("✅ Outputs added for new resources")
