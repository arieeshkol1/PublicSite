# Mobile-to-Cloud Personal Knowledge Assistant

A serverless mobile application that allows users to capture questions via camera or voice, send them to a cloud-based knowledge system, and receive spoken answers in Hebrew or English.

## Overview

This system enables students and professionals to quickly get answers from their personal knowledge base by:
1. Taking a photo of a question or speaking it
2. Sending it to AWS serverless backend
3. Receiving an answer from indexed documents
4. Hearing the answer via text-to-speech

## Features

- **Camera Capture**: Take photos of text and extract questions using iOS OCR
- **Voice Capture**: Speak questions in Hebrew or English with automatic transcription
- **Dual Mode Support**:
  - Multiple Choice: Get letter answers (A-D) with optional explanations
  - Conversation: Get contextual answers from documents
- **Bilingual**: Full support for Hebrew and English
- **Text-to-Speech**: Hear answers in the appropriate language
- **Serverless**: No fixed costs, pay only for usage
- **Secure**: API key authentication with rate limiting

## Architecture

```
┌─────────────┐
│   iPhone    │
│  (Shortcuts)│
└──────┬──────┘
       │ HTTPS + API Key
       ▼
┌─────────────────┐
│  API Gateway    │
│  (REST API)     │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐      ┌──────────────┐
│ Query Handler   │─────▶│   Answer     │
│    Lambda       │      │  Retrieval   │
└─────────────────┘      │   Lambda     │
                         └──────┬───────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            ┌──────────────┐        ┌─────────────┐
            │  DynamoDB    │        │  DynamoDB   │
            │ KnowledgeBase│        │ Transcripts │
            └──────────────┘        └─────────────┘
                    ▲
                    │
            ┌───────┴────────┐
            │   Document     │
            │   Ingestion    │
            │    Lambda      │
            └───────▲────────┘
                    │
            ┌───────┴────────┐
            │   S3 Bucket    │
            │  (Documents)   │
            └────────────────┘
```

## Technology Stack

- **Mobile**: iOS Shortcuts (no App Store required)
- **API**: AWS API Gateway (REST API)
- **Compute**: AWS Lambda (Python 3.11, arm64)
- **Storage**: Amazon S3, DynamoDB (on-demand)
- **CI/CD**: GitHub Actions
- **Testing**: pytest + Hypothesis

## Prerequisites

- AWS Account (account ID: 991105135552)
- GitHub repository with OIDC configured for AWS
- iPhone with iOS 14+ and Shortcuts app
- Python 3.11+ for local development

## Quick Start

### 1. Deploy Infrastructure

The GitHub Actions workflow automatically deploys all infrastructure when you push to main:

```bash
git push origin main
```

This deploys:
- DynamoDB tables (KnowledgeBase, Transcripts)
- S3 bucket for documents
- IAM roles for Lambda functions
- Lambda functions (Document Ingestion, Answer Retrieval, Query Handler)
- API Gateway with authentication

### 2. Get API Configuration

After deployment, retrieve from CloudFormation outputs:

```bash
# Get API endpoint
aws cloudformation describe-stacks \
  --stack-name mobile-ka-api \
  --query "Stacks[0].Outputs[?OutputKey=='APIEndpoint'].OutputValue" \
  --output text

# Get API key ID
aws cloudformation describe-stacks \
  --stack-name mobile-ka-api \
  --query "Stacks[0].Outputs[?OutputKey=='APIKeyId'].OutputValue" \
  --output text
```

Retrieve API key value from AWS Console:
1. Go to API Gateway > API Keys
2. Find "mobile-ka-api-key"
3. Click "Show" to reveal the key

### 3. Upload Knowledge Documents

Upload documents to S3 bucket under `documents/` prefix:

```bash
# Get bucket name
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name mobile-ka-s3 \
  --query "Stacks[0].Outputs[?OutputKey=='DocumentsBucketName'].OutputValue" \
  --output text)

# Upload documents
aws s3 cp my-questions.txt s3://$BUCKET/documents/
aws s3 cp my-notes.pdf s3://$BUCKET/documents/
aws s3 cp study-guide.docx s3://$BUCKET/documents/
```

Supported formats: TXT, PDF, DOCX

### 4. Set Up iOS Shortcuts

Follow the detailed instructions in [ios-shortcuts/README.md](ios-shortcuts/README.md) to:
1. Create camera capture shortcut
2. Create voice capture shortcut
3. Create API request shortcut
4. Create text-to-speech playback shortcut
5. Create main workflow shortcut

### 5. Test the System

1. Run the "Knowledge Assistant" shortcut on your iPhone
2. Choose Camera or Voice input
3. Capture a question
4. Select mode (Multiple Choice or Conversation)
5. Select format (Short or Long)
6. Receive and hear the answer

## Document Formats

### Multiple Choice Format

```
Question 1: What is the capital of France?
A. London
B. Paris
C. Berlin
D. Madrid
Correct Answer: B
Explanation: Paris is the capital and largest city of France.
Topic: Geography

Question 2: What is 2 + 2?
A. 3
B. 4
C. 5
D. 6
Correct Answer: B
Explanation: Basic arithmetic addition.
Topic: Mathematics
```

### Conversation Format

Plain text documents with contextual information:

```
Python Programming Basics

Variables in Python are created when you assign a value to them.
You don't need to declare their type explicitly.

Example:
x = 5
name = "John"
is_valid = True

Python supports multiple data types including integers, floats,
strings, booleans, lists, tuples, and dictionaries.
```

## API Usage

### POST /query

Request:
```json
{
  "question": "What is the capital of France?",
  "mode": "multiple_choice",
  "format": "short"
}
```

Response:
```json
{
  "answer": "B",
  "language": "en",
  "sourceDocumentId": "doc-123",
  "transcriptId": "trans-456"
}
```

### GET /health

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Configuration

### Rate Limiting

- 100 requests per hour per API key
- 2400 requests per day per API key
- Burst limit: 10 requests
- Rate limit: 100 requests per second (across all users)

### Lambda Timeouts

- Document Ingestion: 300 seconds
- Answer Retrieval: 30 seconds
- Query Handler: 60 seconds

### DynamoDB

- On-demand billing (no fixed costs)
- Transcripts TTL: 90 days
- Language index for efficient queries

### CloudWatch Logs

- Retention: 7 days
- Log level: INFO
- No PII logged (questions not stored in logs)

## Cost Estimation

Based on 1000 queries/month:

| Service | Cost |
|---------|------|
| API Gateway | ~$3.50 |
| Lambda | ~$0.20 |
| DynamoDB | ~$1.25 |
| S3 | ~$0.50 |
| **Total** | **~$5.50/month** |

With rate limiting (100 req/hour), maximum monthly cost is ~$16.50.

## Development

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run specific test
pytest tests/test_document_ingestion.py -v
```

### Manual Lambda Testing

```bash
# Test Document Ingestion
aws lambda invoke \
  --function-name mobile-ka-document-ingestion \
  --payload '{"Records":[{"s3":{"bucket":{"name":"BUCKET"},"object":{"key":"documents/test.txt"}}}]}' \
  response.json

# Test Answer Retrieval
aws lambda invoke \
  --function-name mobile-ka-answer-retrieval \
  --payload '{"question":"What is Python?","language":"en","mode":"conversation","format":"short"}' \
  response.json

# Test Query Handler
aws lambda invoke \
  --function-name mobile-ka-query-handler \
  --payload '{"body":"{\"question\":\"What is Python?\",\"mode\":\"conversation\",\"format\":\"short\"}"}' \
  response.json
```

### Viewing Logs

```bash
# Document Ingestion logs
aws logs tail /aws/lambda/mobile-ka-document-ingestion --follow

# Answer Retrieval logs
aws logs tail /aws/lambda/mobile-ka-answer-retrieval --follow

# Query Handler logs
aws logs tail /aws/lambda/mobile-ka-query-handler --follow

# API Gateway logs
aws logs tail /aws/apigateway/mobile-knowledge-assistant-api --follow
```

## Troubleshooting

### Documents Not Being Indexed

1. Check S3 event notification is configured:
```bash
aws s3api get-bucket-notification-configuration --bucket BUCKET_NAME
```

2. Check Document Ingestion Lambda logs:
```bash
aws logs tail /aws/lambda/mobile-ka-document-ingestion --follow
```

3. Verify documents are in `documents/` prefix with supported extensions (.txt, .pdf, .docx)

### No Answers Found

1. Check DynamoDB table has records:
```bash
aws dynamodb scan --table-name mobile-ka-knowledge-base --limit 10
```

2. Verify language matches (Hebrew questions need Hebrew documents)

3. Try rephrasing the question with more keywords

### API Errors

**401 Unauthorized**: Check API key is correct and enabled

**429 Too Many Requests**: Rate limit exceeded, wait before retrying

**500 Internal Server Error**: Check Lambda logs for errors

**504 Gateway Timeout**: Lambda timeout, check function duration in CloudWatch

### iOS Shortcuts Issues

**OCR Not Working**: Ensure good lighting and clear text in photo

**Voice Recognition Fails**: Check microphone permissions and reduce background noise

**API Connection Fails**: Verify API endpoint URL and API key are correct

## Security

- API key authentication required for all requests
- HTTPS only (TLS 1.2+)
- IAM roles follow least privilege principle
- No PII logged in CloudWatch
- API keys not logged
- Transcripts auto-deleted after 90 days

## Monitoring

CloudWatch alarms are configured for:
- Lambda error rate > 5% over 5 minutes
- API Gateway 5xx error rate > 1% over 5 minutes
- DynamoDB throttling > 10 per minute
- Lambda duration > 80% of timeout

## Project Structure

```
.
├── lambda/                      # Lambda function code
│   ├── document_ingestion/      # Process uploaded documents
│   │   ├── handler.py          # S3 event handler
│   │   └── multiple_choice_parser.py  # Parse MC questions
│   ├── answer_retrieval/        # Search and format responses
│   │   └── handler.py          # Query DynamoDB and format answers
│   └── query_handler/           # API Gateway integration
│       └── handler.py          # Validate requests and route
├── cloudformation/              # Infrastructure as Code
│   ├── dynamodb.yaml           # DynamoDB tables
│   ├── s3.yaml                 # S3 bucket
│   ├── iam.yaml                # IAM roles and policies
│   ├── lambda.yaml             # Lambda functions
│   └── api-gateway.yaml        # API Gateway
├── ios-shortcuts/               # iOS Shortcuts documentation
│   └── README.md               # Detailed setup instructions
├── tests/                       # Unit and property-based tests
│   ├── test_document_ingestion.py
│   └── __init__.py
├── .github/workflows/           # CI/CD
│   └── deploy.yml              # Automated deployment
├── .kiro/specs/                 # Requirements and design docs
│   └── mobile-knowledge-assistant/
│       ├── requirements.md
│       ├── design.md
│       └── tasks.md
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Maintenance

### Updating Lambda Code

Code is automatically deployed via GitHub Actions on push to main.

Manual update:
```bash
# Package Lambda
cd lambda/query_handler
pip install -r ../../requirements.txt -t .
zip -r ../../query-handler.zip .

# Update function
aws lambda update-function-code \
  --function-name mobile-ka-query-handler \
  --zip-file fileb://../../query-handler.zip
```

### Cleaning Up Old Transcripts

Transcripts are automatically deleted after 90 days via DynamoDB TTL.

## Backup and Recovery

### DynamoDB Backup

```bash
# Create on-demand backup
aws dynamodb create-backup \
  --table-name mobile-ka-knowledge-base \
  --backup-name kb-backup-$(date +%Y%m%d)

# List backups
aws dynamodb list-backups --table-name mobile-ka-knowledge-base
```

### S3 Versioning

S3 bucket has versioning enabled. Restore previous version:

```bash
# List versions
aws s3api list-object-versions \
  --bucket BUCKET_NAME \
  --prefix documents/

# Restore version
aws s3api copy-object \
  --bucket BUCKET_NAME \
  --copy-source BUCKET_NAME/documents/file.txt?versionId=VERSION_ID \
  --key documents/file.txt
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Run tests: `pytest tests/ -v`
5. Commit and push
6. Create a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues or questions:
1. Check CloudWatch logs for errors
2. Review troubleshooting section above
3. Open an issue on GitHub
4. Check AWS service health dashboard

## Roadmap

- [ ] Add support for more document formats (Markdown, HTML)
- [ ] Implement semantic search with embeddings
- [ ] Add support for images in answers
- [ ] Create web interface for document management
- [ ] Add analytics dashboard
- [ ] Support for more languages (Arabic, Spanish, French)
- [ ] Offline mode with local caching
- [ ] Integration with popular note-taking apps

## Acknowledgments

- AWS for serverless infrastructure
- iOS Shortcuts for mobile integration
- Python community for excellent libraries
