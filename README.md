# Mobile-to-Cloud Personal Knowledge Assistant

A personal assistant that captures visual and spoken input from an iPhone, processes it through a cloud backend using a user-owned knowledge base, and returns spoken responses.

## Features

- **Camera OCR**: Capture text from laptop screens using iPhone camera
- **Voice Input**: Speak questions naturally in Hebrew or English
- **Knowledge Base**: Store and search your own documents (PDF, TXT, DOCX)
- **Multiple Choice Support**: Optimized for exam-style questions
- **Conversation Mode**: Natural conversational responses
- **Text-to-Speech**: Hear answers read aloud in Hebrew or English
- **Serverless Architecture**: Cost-optimized AWS infrastructure (~$5.50/month)

## Architecture

- **Mobile Client**: iOS Shortcuts (no App Store required)
- **API**: AWS API Gateway with API key authentication
- **Backend**: AWS Lambda (Python 3.11)
- **Storage**: S3 (documents), DynamoDB (knowledge base + transcripts)
- **Services**: AWS Textract (OCR), Transcribe (speech-to-text), Polly (TTS)

## Project Structure

```
.
├── lambda/                      # Lambda function code
│   ├── document_ingestion/      # Process uploaded documents
│   ├── answer_retrieval/        # Search and format responses
│   └── query_handler/           # API Gateway integration
├── cloudformation/              # Infrastructure as Code
│   ├── dynamodb.yaml           # DynamoDB tables
│   ├── s3.yaml                 # S3 bucket
│   ├── iam.yaml                # IAM roles and policies
│   └── master.yaml             # Master stack (coming soon)
├── tests/                       # Unit and property-based tests
├── .kiro/specs/                 # Requirements and design docs
└── requirements.txt             # Python dependencies
```

## Setup

### Prerequisites

- AWS Account (991105135552)
- AWS CLI configured
- Python 3.11+
- iPhone with iOS Shortcuts app

### Deployment

1. **Deploy Infrastructure**
   ```bash
   # Deploy DynamoDB tables
   aws cloudformation deploy \
     --template-file cloudformation/dynamodb.yaml \
     --stack-name mobile-ka-dynamodb \
     --region us-east-1

   # Deploy S3 bucket
   aws cloudformation deploy \
     --template-file cloudformation/s3.yaml \
     --stack-name mobile-ka-s3 \
     --region us-east-1

   # Deploy IAM roles
   aws cloudformation deploy \
     --template-file cloudformation/iam.yaml \
     --stack-name mobile-ka-iam \
     --capabilities CAPABILITY_NAMED_IAM \
     --region us-east-1 \
     --parameter-overrides \
       KnowledgeBaseTableArn=<arn-from-dynamodb-stack> \
       TranscriptsTableArn=<arn-from-dynamodb-stack> \
       DocumentsBucketArn=<arn-from-s3-stack>
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Tests**
   ```bash
   pytest tests/ -v
   ```

## Development Status

- [x] Project structure created
- [x] CloudFormation templates (DynamoDB, S3, IAM)
- [ ] Lambda functions implementation
- [ ] API Gateway setup
- [ ] iOS Shortcuts workflow
- [ ] End-to-end testing

## Cost Estimate

Based on 1000 queries/month:
- API Gateway: ~$3.50
- Lambda: ~$0.20
- DynamoDB: ~$1.25
- S3: ~$0.50
- **Total: ~$5.50/month**

Rate limiting (100 req/hour) caps maximum monthly cost at ~$16.50.

## License

Private project - All rights reserved
