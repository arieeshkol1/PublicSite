# Implementation Plan: ViewMyBill

## Overview

This plan implements the ViewMyBill feature — a self-service AWS bill analysis tool. The implementation follows the design's single-Lambda architecture with PDF-only input, DynamoDB-based RAG, and merged PDF output (original invoice + analysis pages).

## Tasks

- [ ] 1. Set up infrastructure and DynamoDB knowledge base
  - [x] 1.1 Create CloudFormation stack (`infrastructure/viewmybill-stack.yaml`)
    - Define DynamoDB table `ViewMyBill-CostOptimizationTips` with `service` (PK) and `tipId` (SK)
    - Define Bill Analyzer Lambda function with Python 3.12 runtime, 512MB memory, 120s timeout
    - Define IAM role with S3 read/write, Bedrock invoke, DynamoDB read permissions
    - Define HTTP API Gateway with `/upload` and `/analyze` routes
    - Configure CORS for `https://eshkolai.com` and `https://www.eshkolai.com`
    - Add S3 lifecycle rule for `reports/` prefix (1-day expiration)
    - _Requirements: 2.6, 6.7, 6.8, 10.1, 10.3_

  - [x] 1.2 Create DynamoDB seed script (`knowledge-base/seed-dynamodb.py`)
    - Read tips from `knowledge-base/aws-cost-optimization-tips.json`
    - Batch write items to DynamoDB table
    - Handle existing items (update or skip)
    - _Requirements: 5.4_

  - [ ] 1.3 Deploy infrastructure stack and seed DynamoDB
    - Deploy CloudFormation stack to AWS account 991105135552
    - Run seed script to populate cost optimization tips
    - Verify API Gateway endpoint is accessible
    - _Requirements: 5.4_

- [ ] 2. Checkpoint - Infrastructure ready
  - Ensure CloudFormation stack deployed successfully, ask the user if questions arise.

- [-] 3. Implement Bill Analyzer Lambda
  - [x] 3.1 Create Lambda project structure (`bill-analyzer/`)
    - Create `lambda_function.py` with handler skeleton
    - Create `requirements.txt` with pdfplumber, reportlab, PyPDF2
    - Create `bill_parser.py` module for PDF parsing
    - Create `pdf_generator.py` module for report generation
    - Create `bedrock_client.py` module for AI analysis
    - _Requirements: 4.1, 5.1, 6.1_

  - [x] 3.2 Implement PDF bill parser (`bill-analyzer/bill_parser.py`)
    - Use pdfplumber to extract text and tables from AWS invoice PDFs
    - Parse service names, costs, billing dates from extracted content
    - Calculate total cost and aggregate by service
    - Extract invoice number, account ID, billing period
    - Return ParsedBill dict matching design schema
    - Raise ValueError with descriptive message for unparseable files
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 3.3 Write property tests for bill parser
    - **Property 7: PDF bill parsing extracts required fields**
    - **Property 8: Parse error produces descriptive message**
    - **Property 9: Total cost equals sum of line items**
    - **Property 10: Billing period date ordering**
    - **Validates: Requirements 4.1, 4.3, 4.4, 4.5**

  - [x] 3.4 Implement Bedrock client (`bill-analyzer/bedrock_client.py`)
    - Query DynamoDB for tips matching detected services + "General" tips
    - Construct analysis prompt with bill data and retrieved tips
    - Invoke Bedrock Nova Lite model (`amazon.nova-lite-v1:0`)
    - Parse JSON response into AIAnalysis dict
    - Handle Bedrock throttling (429) and unavailability (503) errors
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.5 Write property tests for AI analysis
    - **Property 11: AI analysis response structure completeness**
    - **Validates: Requirements 5.2, 5.3, 5.4**

  - [x] 3.6 Implement PDF report generator (`bill-analyzer/pdf_generator.py`)
    - Use PyPDF2 to read original invoice PDF pages
    - Use ReportLab to generate analysis pages (header, explanations, recommendations)
    - Style analysis pages to match AWS invoice look (fonts, colors, tables)
    - Merge original pages + analysis pages into single PDF
    - Include eshkolai.com branding and generation timestamp
    - Return merged PDF as bytes
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 3.7 Write property tests for PDF generator
    - **Property 12: PDF report content completeness**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6**

  - [x] 3.8 Implement Lambda handler (`bill-analyzer/lambda_function.py`)
    - Parse request body for sessionId and email
    - Retrieve bill PDF from S3 using sessionId
    - Call bill parser, Bedrock client, PDF generator in sequence
    - Upload generated PDF to S3 `reports/{sessionId}/report.pdf`
    - Generate pre-signed URL with 24-hour expiry
    - Return downloadUrl and summary in response
    - Handle all error cases with appropriate HTTP codes and messages
    - _Requirements: 4.1, 5.1, 6.7, 6.8, 7.1, 9.1, 9.2, 9.3, 9.4_

  - [ ]* 3.9 Write property tests for error handling
    - **Property 14: Error responses do not leak technical details**
    - **Validates: Requirements 9.4**

- [ ] 4. Checkpoint - Lambda implementation complete
  - Ensure all Lambda tests pass, ask the user if questions arise.

- [-] 5. Update Upload Handler Lambda
  - [x] 5.1 Modify existing upload handler to store email in S3 metadata
    - Add `user-email` to S3 object metadata on PutObject
    - Ensure email is passed through from multipart form data
    - _Requirements: 1.4_

  - [ ]* 5.2 Write property test for email storage
    - **Property 13: Email storage round trip**
    - **Validates: Requirements 1.4**

- [x] 6. Implement Frontend
  - [x] 6.1 Create frontend page structure (`viewMyBill/index.html`)
    - Create HTML with email input, file picker, Revise button
    - Add loading indicator (hidden by default)
    - Add download link container (hidden by default)
    - Add error message container
    - Add privacy notice text
    - Add instructions explaining the bill analysis process
    - Match eshkolai.com branding
    - _Requirements: 1.1, 2.1, 3.1, 7.1, 8.1, 8.2, 8.4, 8.5_

  - [x] 6.2 Create frontend styles (`viewMyBill/viewMyBill.css`)
    - Style form elements consistent with main site
    - Style loading indicator
    - Style error and success messages
    - Ensure responsive design for desktop and mobile
    - _Requirements: 8.2, 8.3_

  - [x] 6.3 Implement frontend logic (`viewMyBill/viewMyBill.js`)
    - Implement email validation (HTML5 + regex)
    - Implement file type validation (PDF only)
    - Implement file size validation (< 10 MB)
    - Display selected filename after selection
    - Manage Revise button enabled/disabled state
    - Show loading indicator on submit, disable button
    - Call POST /upload with email + file
    - Call POST /analyze with sessionId + email
    - Display download link on success
    - Display error messages with retry option on failure
    - Hide loading indicator on completion
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 7.1, 7.2, 7.3, 7.4, 7.5, 9.1, 9.2, 9.3_

  - [ ]* 6.4 Write property tests for frontend validation
    - **Property 1: Email validation correctness**
    - **Property 4: Filename display after selection**
    - **Property 6: Revise button enabled state**
    - **Validates: Requirements 1.1, 1.2, 2.5, 3.2, 3.3**

  - [ ]* 6.5 Write unit tests for frontend
    - Test page contains instructions text
    - Test page contains privacy notice
    - Test loading indicator shown on submit
    - Test button disabled after click
    - Test download link displayed on success
    - Test error message with retry on failure
    - _Requirements: 3.4, 3.5, 7.1, 7.2, 7.4, 7.5, 8.4, 8.5, 9.1, 9.2, 9.3_

- [ ] 7. Checkpoint - Frontend implementation complete
  - Ensure all frontend tests pass, ask the user if questions arise.

- [x] 8. Implement validation utilities
  - [x] 8.1 Create shared validation module (`bill-analyzer/validation.py`)
    - Implement email format validation
    - Implement file extension validation (PDF only)
    - Implement file size validation (10 MB limit)
    - Generate UUID v4 session identifiers
    - _Requirements: 1.1, 1.2, 2.2, 2.3, 2.6, 10.5_

  - [ ]* 8.2 Write property tests for validation
    - **Property 2: Unsupported file type rejection**
    - **Property 3: File size limit enforcement**
    - **Property 5: Session ID uniqueness and format**
    - **Validates: Requirements 2.2, 2.3, 2.6, 10.5**

- [x] 9. Integration and deployment
  - [x] 9.1 Package and deploy Bill Analyzer Lambda
    - Create deployment package with dependencies
    - Update CloudFormation stack with Lambda code
    - Verify Lambda can access S3, DynamoDB, Bedrock
    - _Requirements: 4.1, 5.1, 6.1_

  - [x] 9.2 Deploy frontend to S3
    - Upload `viewMyBill/` folder to S3 website bucket
    - Update `viewMyBill.js` with API Gateway URL
    - Invalidate CloudFront cache for `/viewMyBill/*`
    - _Requirements: 8.1_

  - [x] 9.3 Update GitHub Actions workflow
    - Add `viewMyBill/` folder to S3 sync in `deploy.yml`
    - _Requirements: 8.1_

- [ ] 10. Final checkpoint - End-to-end verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python 3.12 with Hypothesis for property testing
- Frontend uses JavaScript with fast-check for property testing
