# Implementation Plan: AWS Bill Analyzer

## Overview

This implementation plan breaks down the AWS Bill Analyzer feature into discrete coding tasks. The feature adds bill upload and AI-powered analysis capabilities to an existing static website using AWS Lambda (Python 3.11), API Gateway, S3, and Amazon Bedrock Nova Lite.

The implementation follows a bottom-up approach: infrastructure setup, backend Lambda functions with parsing logic, API Gateway configuration, and finally frontend integration. Each task builds on previous work to ensure incremental progress with no orphaned code.

## Tasks

- [x] 1. Set up AWS infrastructure and IAM roles
  - Create S3 bucket `aws-bill-analyzer-storage-991105135552` in us-east-1 with encryption enabled
  - Configure S3 lifecycle policy to delete objects in `bills/` prefix after 1 day
  - Create IAM role `aws-bill-analyzer-upload-role` with S3 PutObject permissions for bills/* prefix
  - Create IAM role `aws-bill-analyzer-question-role` with S3 GetObject and Bedrock InvokeModel permissions
  - Verify Amazon Bedrock model access for `amazon.nova-lite-v1:0` in us-east-1
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_

- [x] 2. Implement Upload Handler Lambda function
  - [x] 2.1 Create upload handler with file validation and S3 storage
    - Create `upload-handler/lambda_function.py` with handler function
    - Implement file size validation (max 10MB) and extension validation (.csv, .pdf)
    - Generate UUID v4 session IDs for each upload
    - Store files in S3 with key pattern `bills/{session_id}/{filename}`
    - Add S3 object metadata: upload-timestamp, content-type, session-id
    - Return JSON response with sessionId and success message
    - Implement error handling for oversized files, invalid types, and S3 failures
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 13.1, 13.2, 13.3_
  
  - [ ]* 2.2 Write property test for file size enforcement
    - **Property 2: File Size Enforcement**
    - **Validates: Requirements 2.6, 2.7**
    - Test that files under 10MB are accepted and files at/over 10MB are rejected with appropriate error message
  
  - [ ]* 2.3 Write property test for unique session generation
    - **Property 3: Unique Session Generation**
    - **Validates: Requirements 2.3, 13.1, 13.2, 13.3**
    - Test that multiple uploads generate unique session IDs
  
  - [ ]* 2.4 Write unit tests for upload handler
    - Test successful CSV upload
    - Test successful PDF upload
    - Test rejection of .txt file
    - Test rejection of 10.1MB file
    - Test S3 upload failure handling
    - Test UUID v4 format for session IDs
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 3. Implement bill parser module
  - [x] 3.1 Create CSV parser for AWS Cost and Usage Reports
    - Create `question-processor/bill_parser.py` with BillParser base class
    - Implement CSVBillParser class with parse() method
    - Extract line items with service, usage_type, cost, date fields
    - Map CSV columns: lineItem/ProductCode, lineItem/UsageType, lineItem/UnblendedCost, lineItem/UsageStartDate
    - Use Decimal type for cost precision (2 decimal places)
    - Calculate total_cost and aggregate service_totals
    - Return structured dict with line_items, total_cost, currency, period_start, period_end
    - Handle missing or malformed rows gracefully
    - _Requirements: 3.1, 3.2, 3.4, 3.5_
  
  - [ ]* 3.2 Write property test for cost precision preservation
    - **Property 8: Cost Precision Preservation**
    - **Validates: Requirements 3.4**
    - Test round-trip: format then parse cost values maintain 2 decimal places
  
  - [ ]* 3.3 Write property test for CSV structured output
    - **Property 9: Structured Output Format**
    - **Validates: Requirements 3.5**
    - Test that parsed CSV contains required fields: line_items, total_cost, currency, period_start, period_end
  
  - [x] 3.4 Implement PDF parser for AWS bills
    - Implement PDFBillParser class using pdfplumber library
    - Extract text from all pages in PDF
    - Use regex patterns to identify service names, cost values, dates, totals
    - Build structured data matching CSV parser output format
    - Handle multi-page documents
    - Fallback to basic text extraction if structured parsing fails
    - _Requirements: 4.1, 4.2, 4.4, 4.5_
  
  - [ ]* 3.5 Write property test for PDF text extraction
    - **Property 10: PDF Text Extraction**
    - **Validates: Requirements 4.1, 4.4**
    - Test that valid PDFs produce non-empty text from all pages
  
  - [x] 3.6 Add error handling for both parsers
    - Implement error handling for malformed CSV (missing headers, invalid structure)
    - Implement error handling for corrupted/encrypted PDFs
    - Return descriptive error messages without crashing
    - _Requirements: 3.3, 4.3_
  
  - [ ]* 3.7 Write property test for CSV error handling
    - **Property 7: CSV Error Handling**
    - **Validates: Requirements 3.3**
    - Test that malformed CSVs return descriptive errors without crashing
  
  - [ ]* 3.8 Write property test for PDF error handling
    - **Property 12: PDF Error Handling**
    - **Validates: Requirements 4.3**
    - Test that unparseable PDFs return descriptive errors without crashing
  
  - [x] 3.9 Create parser factory function
    - Implement get_parser(file_extension) factory function
    - Return appropriate parser based on file extension
    - Create requirements.txt with boto3>=1.34.0, pdfplumber==0.10.3
    - _Requirements: 3.1, 4.1_

- [ ] 4. Checkpoint - Ensure parser tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Question Processor Lambda function
  - [x] 5.1 Create question processor with session retrieval
    - Create `question-processor/lambda_function.py` with handler function
    - Extract sessionId and question from API Gateway event body
    - Validate required parameters (return 400 if missing)
    - Retrieve bill file from S3 using session ID
    - Return 404 error for invalid/expired session IDs
    - _Requirements: 5.3, 5.4, 5.5, 13.4_
  
  - [ ]* 5.2 Write property test for session data retrieval
    - **Property 13: Session Data Retrieval**
    - **Validates: Requirements 5.5, 13.4**
    - Test that valid session IDs retrieve data and invalid IDs return 404
  
  - [x] 5.3 Implement bill parsing integration
    - Determine file type from S3 object key extension
    - Invoke appropriate parser (CSV or PDF) with file content
    - Handle parsing errors and return 400 with format error message
    - _Requirements: 5.5, 3.1, 4.1_
  
  - [x] 5.4 Implement Bedrock prompt construction and invocation
    - Construct prompt with template: "You are an AWS billing assistant. Analyze the following bill data and answer the user's question accurately.\n\nBill Data:\n{parsed_bill_data}\n\nUser Question: {question}\n\nProvide a clear, concise answer based only on the bill data provided."
    - Invoke Bedrock Nova Lite model (amazon.nova-lite-v1:0) with prompt
    - Configure invocation: max_tokens=2000, temperature=0.7, top_p=0.9
    - Extract response text from Bedrock output
    - _Requirements: 5.6, 5.7, 6.1, 6.3, 6.4_
  
  - [ ]* 5.5 Write property test for prompt construction
    - **Property 14: Prompt Construction**
    - **Validates: Requirements 5.6**
    - Test that prompts contain both question text and bill data
  
  - [ ]* 5.6 Write property test for AI response generation
    - **Property 15: AI Response Generation**
    - **Validates: Requirements 6.1, 6.4**
    - Test that valid prompts to Bedrock return non-empty responses
  
  - [x] 5.7 Create response formatter module
    - Create `question-processor/response_formatter.py` with ResponseFormatter class
    - Implement format_response() to extract text from Bedrock response structure
    - Implement sanitize_output() to remove problematic formatting
    - Truncate responses longer than 2000 characters
    - Add timestamp metadata to response
    - _Requirements: 6.6_
  
  - [ ]* 5.8 Write property test for response formatting
    - **Property 17: Response Formatting**
    - **Validates: Requirements 6.6**
    - Test that formatted responses are displayable (non-null, proper encoding, under 2000 chars)
  
  - [x] 5.9 Add comprehensive error handling
    - Handle Bedrock throttling with exponential backoff
    - Handle Bedrock service unavailable (return 503)
    - Handle Bedrock timeout after 60 seconds (return 504)
    - Return user-friendly error messages without technical details
    - Log all errors to CloudWatch with context
    - _Requirements: 6.5, 10.3_
  
  - [ ]* 5.10 Write property test for AI error handling
    - **Property 16: AI Error Handling**
    - **Validates: Requirements 6.5**
    - Test that Bedrock errors return user-friendly messages without technical details
  
  - [ ]* 5.11 Write unit tests for question processor
    - Test successful question processing with valid session
    - Test 404 error for invalid session ID
    - Test CSV parsing integration
    - Test PDF parsing integration
    - Test Bedrock API call with constructed prompt
    - Test response formatting
    - Test Bedrock throttling error handling
    - _Requirements: 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.4, 6.5, 6.6_

- [ ] 6. Package and deploy Lambda functions
  - [ ] 6.1 Create deployment packages
    - Create upload-handler deployment package with dependencies
    - Create question-processor deployment package with dependencies (including pdfplumber)
    - Generate ZIP files for both functions
    - _Requirements: 9.4, 9.5_
  
  - [ ] 6.2 Deploy Lambda functions to AWS
    - Deploy aws-bill-analyzer-upload-handler function (Python 3.11, 512MB, 30s timeout)
    - Deploy aws-bill-analyzer-question-processor function (Python 3.11, 1024MB, 60s timeout)
    - Configure environment variables for both functions
    - Attach IAM roles to functions
    - _Requirements: 9.4, 9.5, 15.2, 15.3, 15.6_
  
  - [ ]* 6.3 Test deployed Lambda functions independently
    - Test upload handler with sample CSV file
    - Test upload handler with sample PDF file
    - Test question processor with valid session
    - Verify CloudWatch logs are created
    - _Requirements: 2.1, 2.2, 5.3, 5.4_

- [ ] 7. Checkpoint - Ensure Lambda functions work independently
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Configure API Gateway
  - [ ] 8.1 Create REST API and endpoints
    - Create REST API named `aws-bill-analyzer-api` in us-east-1
    - Create POST /upload endpoint with Lambda proxy integration to upload handler
    - Create POST /question endpoint with Lambda proxy integration to question processor
    - Configure binary media types for /upload: multipart/form-data, application/octet-stream
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 15.4, 15.7_
  
  - [ ] 8.2 Configure CORS for both endpoints
    - Set Access-Control-Allow-Origin to http://arieleshkolwebsite22feb2026.s3-website-us-east-1.amazonaws.com
    - Set Access-Control-Allow-Methods to POST, OPTIONS
    - Set Access-Control-Allow-Headers to Content-Type, X-Amz-Date, Authorization, X-Api-Key, X-Amz-Security-Token
    - Set Access-Control-Max-Age to 3600
    - _Requirements: 8.3_
  
  - [ ] 8.3 Configure throttling and deploy API
    - Set rate limit to 100 requests/second, burst limit to 200
    - Deploy API to prod stage
    - Note API Gateway endpoint URLs for frontend configuration
    - Grant Lambda invoke permissions to API Gateway
    - _Requirements: 8.6, 15.7_
  
  - [ ]* 8.4 Test API endpoints
    - Test POST /upload with curl or Postman (CSV file)
    - Test POST /upload with curl or Postman (PDF file)
    - Test POST /question with valid session ID
    - Test CORS preflight OPTIONS requests
    - Verify appropriate HTTP status codes (200, 400, 404, 413, 500)
    - _Requirements: 8.1, 8.2, 8.3, 8.6_

- [ ] 9. Implement frontend bill analyzer UI
  - [ ] 9.1 Create bill analyzer JavaScript module
    - Create `bill-analyzer.js` with BillAnalyzerUI class
    - Implement init() to attach event listeners
    - Implement showUploadInterface() to display file upload UI
    - Implement validateFile() for client-side validation (.csv, .pdf, max 10MB)
    - Store API Gateway endpoint URLs as constants
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 14.1_
  
  - [ ]* 9.2 Write property test for file type validation
    - **Property 1: File Type Validation**
    - **Validates: Requirements 1.3, 1.4**
    - Test that .csv and .pdf files pass validation, other extensions fail with descriptive error
  
  - [ ] 9.3 Implement file upload functionality
    - Implement uploadFile() to send multipart form data to POST /upload endpoint
    - Handle upload success: store sessionId in memory
    - Handle upload errors: display error messages for 400, 413, 500 responses
    - Implement showLoading() and hideLoading() for upload progress
    - Disable submit button during upload to prevent duplicates
    - _Requirements: 2.1, 10.1, 12.1, 12.4, 12.5_
  
  - [ ]* 9.4 Write property test for upload error handling
    - **Property 5: Upload Error Handling**
    - **Validates: Requirements 2.5**
    - Test that failed uploads return descriptive error messages
  
  - [ ] 9.5 Implement chat interface
    - Implement showChatInterface() to display chat UI after successful upload
    - Implement askQuestion() to send POST /question requests with sessionId and question
    - Implement renderMessage() to display user questions and AI responses
    - Visually distinguish user messages from AI messages with CSS classes
    - Display messages in chronological order with newest at bottom
    - Implement auto-scroll to newest message
    - _Requirements: 5.1, 5.2, 5.3, 7.2, 7.3, 7.4, 7.5_
  
  - [ ]* 9.6 Write property test for message display order
    - **Property 19: Message Display Order**
    - **Validates: Requirements 7.2, 7.3, 7.4**
    - Test that messages are displayed in chronological order
  
  - [ ] 9.7 Implement conversation history management
    - Store conversation history in memory (conversationHistory array)
    - Add each Q&A pair to history with timestamps
    - Maintain history for browser session duration
    - _Requirements: 7.1, 7.6_
  
  - [ ]* 9.8 Write property test for conversation history persistence
    - **Property 18: Conversation History Persistence**
    - **Validates: Requirements 7.1, 7.6**
    - Test that multiple Q&A exchanges are maintained in chronological order
  
  - [ ] 9.9 Implement comprehensive error handling and loading states
    - Display error messages for parsing failures (400 responses)
    - Display error messages for AI unavailability (503 responses)
    - Display error messages for network errors
    - Display error messages for session not found (404 responses)
    - Provide retry buttons for failed operations
    - Show loading indicator during question processing
    - Show typing indicator while AI generates response
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 12.2, 12.3_
  
  - [ ]* 9.10 Write property test for error message display
    - **Property 21: Error Message Display**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.6, 10.7**
    - Test that all error types display user-friendly messages without technical jargon
  
  - [ ]* 9.11 Write property test for loading state management
    - **Property 24: Loading State Management**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
    - Test that loading indicators appear during operations and buttons are disabled

- [ ] 10. Create CSS styles for bill analyzer UI
  - [ ] 10.1 Add bill analyzer styles to styles.css
    - Add .bill-analyzer-button class matching existing button styles
    - Add .upload-interface class for file upload container
    - Add .chat-interface class for chat conversation container
    - Add .message-user and .message-ai classes for message styling
    - Add .loading-indicator class for spinner/progress indicator
    - Add .error-message class for error display
    - Ensure styles match existing color scheme and design patterns
    - _Requirements: 1.5, 14.2, 14.3_
  
  - [ ] 10.2 Implement responsive design styles
    - Add media query for screens below 768px
    - Stack interface elements vertically on mobile
    - Ensure touch-friendly button sizes (min 44px height and width)
    - Make chat interface scrollable on mobile
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 14.5_
  
  - [ ]* 10.3 Write property test for touch-friendly button sizing
    - **Property 23: Touch-Friendly Button Sizing**
    - **Validates: Requirements 11.3**
    - Test that all interactive buttons are at least 44x44 pixels

- [ ] 11. Integrate bill analyzer into existing website
  - [ ] 11.1 Add bill analyzer to index.html
    - Add "Check your Bill" button in prominent location on home page
    - Add container divs for upload interface and chat interface (initially hidden)
    - Add script tag to load bill-analyzer.js
    - Initialize BillAnalyzerUI on page load
    - Maintain existing navigation and footer structure
    - _Requirements: 1.1, 14.1, 14.4, 14.5, 14.6_
  
  - [ ] 11.2 Update GitHub Actions workflow
    - Modify .github/workflows/deploy-to-s3.yml to deploy bill-analyzer.js
    - Add cache-control headers for JavaScript file (max-age=86400)
    - _Requirements: 14.1_
  
  - [ ]* 11.3 Test integration on multiple browsers
    - Test on Chrome, Firefox, Safari
    - Test on mobile browsers (iOS Safari, Chrome Android)
    - Verify responsive design at various screen sizes
    - _Requirements: 11.1, 11.2, 11.4_

- [ ] 12. End-to-end integration testing
  - [ ]* 12.1 Test complete upload and question flow with CSV
    - Upload sample AWS Cost and Usage Report CSV
    - Verify session ID returned
    - Ask question about total cost
    - Verify AI response displayed
    - Ask follow-up question
    - Verify conversation history maintained
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 5.1, 5.2, 6.1, 7.1_
  
  - [ ]* 12.2 Test complete upload and question flow with PDF
    - Upload sample AWS PDF bill
    - Verify session ID returned
    - Ask question about service costs
    - Verify AI response displayed
    - _Requirements: 1.1, 1.2, 2.1, 4.1, 5.1, 5.2, 6.1_
  
  - [ ]* 12.3 Test error scenarios
    - Test upload of invalid file type (.txt)
    - Test upload of oversized file (>10MB)
    - Test question with invalid session ID
    - Test question with expired session (after 24 hours)
    - Verify appropriate error messages displayed
    - Verify retry functionality works
    - _Requirements: 1.4, 2.5, 2.7, 10.1, 10.2, 10.4, 10.5, 13.5, 13.6_
  
  - [ ]* 12.4 Test session expiration
    - Verify S3 lifecycle policy deletes files after 24 hours
    - Verify expired session returns 410 error
    - _Requirements: 13.5, 13.6_

- [ ] 13. Final checkpoint - Verify deployment and monitoring
  - Ensure all tests pass, ask the user if questions arise.
  - Verify CloudWatch logs are being created for both Lambda functions
  - Verify API Gateway metrics are being collected
  - Test production deployment with real AWS bill files

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation follows a bottom-up approach: infrastructure → backend → API → frontend
- All Lambda functions use Python 3.11 as specified in the design
- Frontend uses vanilla JavaScript (no frameworks) to integrate with existing static website
- Checkpoints ensure incremental validation at key milestones
