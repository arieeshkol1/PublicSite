# Implementation Plan: Mobile-to-Cloud Personal Knowledge Assistant

## Overview

This implementation plan breaks down the Mobile-to-Cloud Personal Knowledge Assistant into discrete coding tasks. The system consists of AWS serverless infrastructure (CloudFormation), Python Lambda functions for backend processing, and iOS Shortcuts for the mobile client. Tasks are organized to build incrementally, with testing integrated throughout.

## Technology Stack

- **Infrastructure**: AWS CloudFormation
- **Backend**: Python 3.11 on AWS Lambda (arm64)
- **API**: AWS API Gateway (REST API)
- **Storage**: Amazon S3, DynamoDB (on-demand)
- **Mobile**: iOS Shortcuts (no App Store publishing)
- **CI/CD**: GitHub Actions
- **Testing**: pytest + Hypothesis (Python), manual testing (iOS Shortcuts)

## Tasks

- [x] 1. Set up project structure and CloudFormation infrastructure
  - Create directory structure for Lambda functions, CloudFormation templates, and tests
  - Create CloudFormation template for DynamoDB tables (KnowledgeBase, Transcripts)
  - Create CloudFormation template for S3 bucket with lifecycle policies
  - Create CloudFormation template for IAM roles and policies
  - Set up Python project with requirements.txt (boto3, hypothesis, pytest, langdetect, PyPDF2, python-docx)
  - _Requirements: 13.1, 13.2, 18.1, 18.2, 18.3_

- [x] 2. Implement API Gateway and authentication infrastructure
  - [x] 2.1 Create CloudFormation template for API Gateway REST API
    - Define /query POST endpoint with request validation
    - Define /health GET endpoint
    - Configure API key authentication with usage plans (100 req/hour)
    - Enable CORS for web app support
    - Configure CloudWatch logging
    - _Requirements: 3.1, 3.2, 12.1, 12.2, 12.3_
  
  - [ ]* 2.2 Write property test for API key validation
    - **Property 8: API Key Validation**
    - **Validates: Requirements 3.2**
  
  - [ ]* 2.3 Write property test for rate limiting
    - **Property 46: Hourly Rate Limiting**
    - **Property 47: Rate Limit Response Code**
    - **Validates: Requirements 12.1, 12.2**

- [x] 3. Implement Document Ingestion Lambda function
  - [x] 3.1 Create Lambda function handler for S3 event processing
    - Implement S3 event parsing and document download
    - Implement text extraction for PDF, TXT, DOCX formats
    - Implement language detection (Hebrew/English)
    - _Requirements: 5.1, 5.2, 6.1, 16.1_
  
  - [x] 3.2 Implement multiple choice document parser
    - Parse question text, answer options (A-D), correct answer, explanation
    - Extract topics and metadata from document
    - Create structured records with all required fields
    - _Requirements: 6.4, 19.1, 19.2_
  
  - [x] 3.3 Implement DynamoDB batch write for knowledge base records
    - Write parsed records to KnowledgeBase table
    - Assign unique recordId and documentId
    - Update S3 object metadata (indexed=true)
    - _Requirements: 5.3, 6.2, 6.3, 6.5_
  
  - [ ]* 3.4 Write property test for document format support
    - **Property 16: Document Format Support**
    - **Validates: Requirements 5.4**
  
  - [ ]* 3.5 Write property test for metadata preservation
    - **Property 17: Document Metadata Preservation**
    - **Property 20: Metadata Preservation in Records**
    - **Validates: Requirements 5.5, 6.3**
  
  - [ ]* 3.6 Write property test for multiple choice parsing
    - **Property 21: Multiple Choice Format Parsing**
    - **Property 63: Option Letter Association**
    - **Validates: Requirements 6.4, 19.1, 19.2**
  
  - [ ]* 3.7 Write property test for round-trip document processing
    - **Property 67: Round-Trip Document Processing**
    - **Validates: Requirements 20.3, 20.5**
  
  - [ ]* 3.8 Write unit tests for text extraction edge cases
    - Test empty documents, malformed formats, mixed languages
    - Test documents with special characters and encodings
    - _Requirements: 6.1, 16.1_

- [x] 4. Checkpoint - Test document ingestion end-to-end
  - Upload test documents to S3 and verify records in DynamoDB
  - Ensure all tests pass, ask the user if questions arise

- [x] 5. Implement Answer Retrieval Lambda function
  - [x] 5.1 Create Lambda function handler for answer retrieval
    - Implement DynamoDB query with language filter
    - Implement keyword extraction from questions
    - Implement relevance scoring and ranking
    - Handle "no answer found" case
    - _Requirements: 7.1, 7.3, 7.4, 7.5, 9.5_
  
  - [x] 5.2 Implement response formatting logic
    - Multiple choice short format (letter only)
    - Multiple choice long format (letter + option + explanation)
    - Conversation short format (brief answer, max 2 sentences)
    - Conversation long format (detailed explanation)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 19.4_
  
  - [x] 5.3 Implement transcript storage in DynamoDB
    - Store question, answer, timestamp, language, mode, format
    - Associate with source document ID and record ID
    - Store within 1 second of generating response
    - _Requirements: 11.1, 11.2, 11.3, 11.4_
  
  - [ ]* 5.4 Write property test for language-filtered search
    - **Property 25: Language-Filtered Search**
    - **Validates: Requirements 7.4, 9.5**
  
  - [ ]* 5.5 Write property test for relevance-based ranking
    - **Property 24: Relevance-Based Ranking**
    - **Validates: Requirements 7.3**
  
  - [ ]* 5.6 Write property test for response format correctness
    - **Property 27: Multiple Choice Short Format**
    - **Property 28: Multiple Choice Long Format**
    - **Property 29: Conversation Short Format**
    - **Property 30: Conversation Long Format**
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
  
  - [ ]* 5.7 Write property test for transcript storage
    - **Property 42: Transcript Storage**
    - **Property 43: Transcript Metadata Completeness**
    - **Property 44: Transcript Source Association**
    - **Validates: Requirements 11.1, 11.2, 11.3**
  
  - [ ]* 5.8 Write unit tests for edge cases
    - Test empty query results, malformed questions, timeout scenarios
    - Test DynamoDB throttling and retry logic
    - _Requirements: 7.5, 14.1_

- [x] 6. Implement Query Handler Lambda function
  - [x] 6.1 Create Lambda function handler for API Gateway integration
    - Parse API Gateway proxy event
    - Validate request body (question, mode, format)
    - Implement language detection (Hebrew/English with fallback to English)
    - Invoke Answer Retrieval Lambda
    - Format response for API Gateway
    - _Requirements: 4.2, 4.3, 9.3, 9.4_
  
  - [x] 6.2 Implement error handling and logging
    - Handle Lambda invocation failures
    - Handle timeout scenarios
    - Log request metadata (no full question content)
    - Return appropriate error responses (400, 500, 504)
    - _Requirements: 14.1, 15.1, 15.3, 15.4_
  
  - [ ]* 6.3 Write property test for language detection
    - **Property 33: Automatic Language Detection**
    - **Property 34: Default Language Fallback**
    - **Validates: Requirements 9.3, 9.4**
  
  - [ ]* 6.4 Write property test for language-matched responses
    - **Property 31: Hebrew Question Hebrew Answer**
    - **Property 32: English Question English Answer**
    - **Validates: Requirements 9.1, 9.2**
  
  - [ ]* 6.5 Write unit tests for error handling
    - Test invalid request formats, missing fields, authentication failures
    - Test Lambda timeout and retry scenarios
    - _Requirements: 14.1, 14.5_

- [x] 7. Checkpoint - Test query processing end-to-end
  - Test API Gateway → Query Handler → Answer Retrieval → DynamoDB flow
  - Verify transcript storage and response formatting
  - Ensure all tests pass, ask the user if questions arise

- [x] 8. Create CloudFormation deployment template
  - [x] 8.1 Create master CloudFormation template
    - Integrate all resource templates (DynamoDB, S3, Lambda, API Gateway)
    - Define Lambda function resources with Python 3.11 runtime
    - Configure Lambda environment variables
    - Set up Lambda triggers (S3 event for Document Ingestion)
    - Configure API Gateway integration with Query Handler Lambda
    - _Requirements: 13.1, 13.2, 13.4_
  
  - [x] 8.2 Add CloudWatch monitoring and alarms
    - Lambda error rate alarm (> 5% over 5 minutes)
    - API Gateway 5xx error rate alarm (> 1% over 5 minutes)
    - DynamoDB throttling alarm (> 10 per minute)
    - Lambda duration alarm (> 80% of timeout)
    - _Requirements: 13.3_
  
  - [ ]* 8.3 Write unit tests for CloudFormation template validation
    - Test template syntax and resource dependencies
    - Test IAM policy least privilege
    - _Requirements: 13.1_

- [x] 9. Implement GitHub Actions CI/CD pipeline
  - [x] 9.1 Create GitHub Actions workflow for deployment
    - Configure AWS credentials (account 991105135552, region us-east-1)
    - Add step to run pytest with Hypothesis tests
    - Add step to package Lambda functions
    - Add step to deploy CloudFormation stack
    - Add step to run integration tests post-deployment
    - _Requirements: 13.1_
  
  - [ ]* 9.2 Write integration tests for deployed infrastructure
    - Test API Gateway endpoints with real API keys
    - Test document upload and ingestion flow
    - Test query processing with real DynamoDB data
    - _Requirements: 3.1, 4.2, 7.1_

- [x] 10. Create iOS Shortcuts workflow
  - [x] 10.1 Create camera capture shortcut
    - Take photo action
    - Extract text from image using iOS OCR
    - Display extracted text for confirmation
    - Store extracted text in variable
    - _Requirements: 1.1, 1.2, 1.3_
  
  - [x] 10.2 Create voice capture shortcut
    - Dictate text action with language auto-detection
    - Display transcribed text for confirmation
    - Store transcribed text in variable
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_
  
  - [x] 10.3 Create API request shortcut
    - Get API key from user input (first run) or stored variable
    - Prompt user to select mode (Multiple Choice / Conversation)
    - Prompt user to select format (Short / Long)
    - Build JSON request body
    - Send HTTPS POST to API Gateway /query endpoint with API key header
    - Parse JSON response
    - _Requirements: 3.5, 4.1, 4.4, 8.5, 8.6_
  
  - [x] 10.4 Create text-to-speech playback shortcut
    - Detect response language (Hebrew/English)
    - Configure voice based on language
    - Speak text action with appropriate voice
    - Handle earphone routing automatically
    - _Requirements: 10.1, 10.2, 10.5, 10.6, 10.7_
  
  - [x] 10.5 Create error handling in shortcuts
    - Display error messages for OCR failures
    - Display error messages for speech recognition failures
    - Display error messages for network failures
    - Offer retry option for all error types
    - Speak error messages using TTS
    - _Requirements: 1.4, 2.4, 4.5, 14.1, 14.2, 14.3, 14.4_
  
  - [x] 10.6 Create main workflow shortcut
    - Prompt user to select capture mode (Camera / Voice)
    - Call appropriate capture shortcut
    - Call API request shortcut with captured text
    - Call TTS playback shortcut with response
    - Implement loading indicators during processing
    - Store user preferences (last mode, format)
    - _Requirements: 17.1, 17.2, 17.4, 17.5_
  
  - [ ]* 10.7 Create manual test checklist for iOS Shortcuts
    - Test camera capture with Hebrew and English text
    - Test voice capture with Hebrew and English speech
    - Test all mode and format combinations
    - Test error scenarios (no network, invalid API key)
    - Test preference persistence across runs
    - _Requirements: 1.1-1.5, 2.1-2.6, 8.1-8.6, 10.1-10.9_

- [x] 11. Checkpoint - Test complete end-to-end flow
  - Test iOS Shortcuts → API Gateway → Lambda → DynamoDB → Response → TTS
  - Verify all error handling paths work correctly
  - Ensure all tests pass, ask the user if questions arise

- [x] 12. Create deployment documentation
  - [x] 12.1 Write README with setup instructions
    - AWS account setup and credentials configuration
    - CloudFormation stack deployment steps
    - API key creation and configuration
    - iOS Shortcuts installation instructions
    - Testing and validation steps
    - _Requirements: 16.4_
  
  - [x] 12.2 Create sample documents for testing
    - Create sample multiple choice documents in Hebrew
    - Create sample multiple choice documents in English
    - Create sample conversation documents in both languages
    - Upload to S3 for initial testing
    - _Requirements: 5.4, 6.4, 19.1_
  
  - [x] 12.3 Document cost optimization settings
    - Document usage plan limits and cost caps
    - Document CloudWatch log retention settings
    - Document S3 lifecycle policies
    - Document DynamoDB on-demand pricing expectations
    - _Requirements: 13.2, 13.3_

- [-] 13. Final validation and cleanup
  - [-] 13.1 Run full test suite
    - Run all pytest unit tests
    - Run all Hypothesis property tests (100+ iterations each)
    - Run integration tests against deployed infrastructure
    - Verify all 68 correctness properties are tested
    - _Requirements: All_
  
  - [x] 13.2 Validate privacy and security requirements
    - Verify no PII in CloudWatch logs
    - Verify API keys are not logged
    - Verify HTTPS-only communication
    - Verify IAM roles follow least privilege
    - Test log retention and TTL policies
    - _Requirements: 3.1, 15.1, 15.3, 15.4, 15.5_
  
  - [x] 13.3 Performance validation
    - Measure OCR processing time (target < 3s for 95%)
    - Measure speech recognition time (target < 2s for 95%)
    - Measure answer retrieval time (target < 2s for 95%)
    - Measure end-to-end response time (target < 10s for 95%)
    - _Requirements: 1.2, 2.2, 7.2_
  
  - [ ]* 13.4 Load testing
    - Simulate 100 concurrent users
    - Test rate limiting under load
    - Test Lambda cold start impact
    - Test DynamoDB throttling behavior
    - _Requirements: 12.1, 12.2, 13.1_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property-based tests validate universal correctness properties using Hypothesis (Python)
- iOS Shortcuts testing is manual due to platform limitations
- CloudFormation templates enable infrastructure-as-code deployment
- GitHub Actions automates testing and deployment
- All Lambda functions use Python 3.11 on arm64 for cost optimization
- DynamoDB uses on-demand billing to avoid fixed costs
- API Gateway usage plans enforce rate limiting (100 req/hour per user)

## Implementation Order Rationale

1. Infrastructure first (CloudFormation) to establish foundation
2. Backend services (Lambda functions) before frontend
3. Document ingestion before query processing (need data to query)
4. Testing integrated throughout (not deferred to end)
5. iOS Shortcuts last (depends on working backend)
6. Documentation and validation at the end

## Testing Strategy

- **Property-Based Tests**: 68 correctness properties from design document
- **Unit Tests**: Specific examples and edge cases
- **Integration Tests**: End-to-end flows with real AWS services
- **Manual Tests**: iOS Shortcuts functionality (platform limitation)
- **Performance Tests**: Response time and throughput validation
- **Load Tests**: Concurrent user simulation and rate limiting

## Deployment Process

1. Deploy CloudFormation stack to AWS account 991105135552 (us-east-1)
2. Create API keys in API Gateway console
3. Upload sample documents to S3 bucket
4. Wait for Document Ingestion Lambda to process documents
5. Install iOS Shortcuts on iPhone
6. Configure API key in shortcuts
7. Test end-to-end flow

## Cost Expectations

Based on 1000 queries/month:
- API Gateway: ~$3.50
- Lambda: ~$0.20
- DynamoDB: ~$1.25
- S3: ~$0.50
- **Total: ~$5.50/month**

Rate limiting (100 req/hour) caps maximum monthly cost at ~$16.50 (assuming 24/7 usage at limit).
