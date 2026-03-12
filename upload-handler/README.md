# Upload Handler Lambda Function

This Lambda function handles AWS bill file uploads from the frontend.

## Functionality

- Validates file size (max 10MB)
- Validates file type (.csv, .pdf only)
- Generates unique session IDs (UUID v4)
- Stores files in S3 with session-based keys
- Adds metadata and tags to S3 objects
- Returns session ID to frontend

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BILL_STORAGE_BUCKET` | `aws-bill-analyzer-storage-991105135552` | S3 bucket for bill storage |
| `MAX_FILE_SIZE_MB` | `10` | Maximum file size in megabytes |
| `ALLOWED_EXTENSIONS` | `.csv,.pdf` | Comma-separated list of allowed extensions |

## IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectTagging"
      ],
      "Resource": "arn:aws:s3:::aws-bill-analyzer-storage-991105135552/bills/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:991105135552:log-group:/aws/lambda/aws-bill-analyzer-upload-handler:*"
    }
  ]
}
```

## Request Format

### API Gateway Event

```json
{
  "body": "<base64-encoded-multipart-form-data>",
  "isBase64Encoded": true,
  "headers": {
    "content-type": "multipart/form-data; boundary=----WebKitFormBoundary..."
  }
}
```

### Multipart Form Data

```
------WebKitFormBoundary...
Content-Disposition: form-data; name="file"; filename="aws-bill.csv"
Content-Type: text/csv

<file-content>
------WebKitFormBoundary...--
```

## Response Format

### Success Response (200)

```json
{
  "sessionId": "550e8400-e29b-41d4-a716-446655440000",
  "message": "File uploaded successfully",
  "fileName": "aws-bill-january-2026.csv",
  "timestamp": "2026-02-22T10:30:00Z"
}
```

### Error Responses

#### Invalid File Type (400)

```json
{
  "error": "InvalidFileType",
  "message": "Invalid file type. Only .csv, .pdf files are supported. You uploaded a .txt file.",
  "code": 400,
  "retryable": false
}
```

#### File Too Large (413)

```json
{
  "error": "FileTooLarge",
  "message": "File size (12.5 MB) exceeds the maximum allowed size of 10 MB. Please upload a smaller file.",
  "code": 413,
  "retryable": false
}
```

#### Server Error (500)

```json
{
  "error": "ServerError",
  "message": "Failed to store file. Please try again.",
  "code": 500,
  "retryable": true
}
```

## S3 Storage Structure

### Object Key Pattern

```
bills/{session_id}/{filename}
```

### Example

```
bills/550e8400-e29b-41d4-a716-446655440000/aws-bill-january-2026.csv
```

### Object Metadata

```json
{
  "session-id": "550e8400-e29b-41d4-a716-446655440000",
  "upload-timestamp": "2026-02-22T10:30:00Z",
  "original-filename": "aws-bill-january-2026.csv"
}
```

### Object Tags

```
session-id=550e8400-e29b-41d4-a716-446655440000
upload-timestamp=2026-02-22T10:30:00Z
expiration=24h
```

## Local Testing

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Test Event

Create `test-event.json`:

```json
{
  "body": "LS0tLS1XZWJLaXRGb3JtQm91bmRhcnk...",
  "isBase64Encoded": true,
  "headers": {
    "content-type": "multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW"
  }
}
```

### Run Locally

```python
from lambda_function import lambda_handler
import json

with open('test-event.json') as f:
    event = json.load(f)

response = lambda_handler(event, None)
print(json.dumps(response, indent=2))
```

## Deployment

### Package Function

```bash
cd upload-handler
pip install -r requirements.txt -t .
zip -r ../upload-handler.zip .
```

### Deploy to AWS

```bash
aws lambda create-function \
    --function-name aws-bill-analyzer-upload-handler \
    --runtime python3.11 \
    --role arn:aws:iam::991105135552:role/aws-bill-analyzer-upload-role \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://../upload-handler.zip \
    --timeout 30 \
    --memory-size 512 \
    --environment Variables="{BILL_STORAGE_BUCKET=aws-bill-analyzer-storage-991105135552,MAX_FILE_SIZE_MB=10,ALLOWED_EXTENSIONS=.csv,.pdf}" \
    --region us-east-1
```

### Update Function

```bash
aws lambda update-function-code \
    --function-name aws-bill-analyzer-upload-handler \
    --zip-file fileb://../upload-handler.zip \
    --region us-east-1
```

## Monitoring

### CloudWatch Logs

Logs are sent to: `/aws/lambda/aws-bill-analyzer-upload-handler`

### Key Metrics

- Invocation count
- Error rate
- Duration
- Throttles

### Sample Log Output

```
START RequestId: abc123...
Received upload request
Generated session ID: 550e8400-e29b-41d4-a716-446655440000
File uploaded successfully to s3://aws-bill-analyzer-storage-991105135552/bills/550e8400-e29b-41d4-a716-446655440000/aws-bill.csv
END RequestId: abc123...
REPORT RequestId: abc123... Duration: 1234.56 ms Billed Duration: 1300 ms Memory Size: 512 MB Max Memory Used: 128 MB
```

## Error Handling

The function handles the following error scenarios:

1. **Missing file data**: Returns 400 error
2. **Invalid file type**: Returns 400 error with supported formats
3. **File too large**: Returns 413 error with size limit
4. **Empty file**: Returns 400 error
5. **S3 upload failure**: Returns 500 error with retry suggestion
6. **Unexpected errors**: Returns 500 error with generic message

All errors are logged to CloudWatch for debugging.
