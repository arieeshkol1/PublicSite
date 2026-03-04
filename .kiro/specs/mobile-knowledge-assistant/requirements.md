# Requirements Document

## Introduction

The Mobile-to-Cloud Personal Knowledge Assistant is a system that enables users to capture questions via iPhone (through camera OCR or voice input), send them to a cloud backend that retrieves answers from a user-owned knowledge base, and receive spoken responses through the device. The system prioritizes cost efficiency through serverless architecture, supports Hebrew and English languages, and operates without requiring App Store publishing or laptop involvement.

## Glossary

- **Mobile_Client**: The iPhone application that captures user input, sends requests, and delivers audio responses
- **Cloud_Backend**: The serverless cloud infrastructure that processes requests and retrieves answers
- **Knowledge_Base**: The collection of user-owned documents stored in cloud storage
- **Document_Ingestion_Service**: The component that converts documents into structured database records
- **OCR_Service**: The service that extracts text from camera-captured images
- **Speech_Recognition_Service**: The service that converts spoken audio to text
- **TTS_Service**: The text-to-speech service that converts text responses to audio
- **Answer_Retrieval_Engine**: The component that searches the structured database for relevant information
- **API_Gateway**: The HTTPS endpoint that receives and authenticates client requests
- **Transcript_Store**: The DynamoDB database storing question/answer history
- **Structured_Database**: The database containing indexed knowledge base records for fast lookup
- **Authentication_Service**: The component that validates API keys or tokens

## Requirements

### Requirement 1: Text Capture via Camera

**User Story:** As a user, I want to capture text from my laptop screen using my iPhone camera, so that I can ask questions about what I'm viewing without typing.

#### Acceptance Criteria

1. WHEN the user activates camera capture mode, THE Mobile_Client SHALL capture an image of the target surface
2. WHEN an image is captured, THE OCR_Service SHALL extract text from the image within 3 seconds
3. WHEN text extraction succeeds, THE Mobile_Client SHALL display the extracted text for user confirmation
4. IF text extraction fails, THEN THE Mobile_Client SHALL display an error message and offer to retry
5. THE OCR_Service SHALL support both Hebrew and English text recognition

### Requirement 2: Voice Capture via Microphone

**User Story:** As a user, I want to speak my questions into my iPhone, so that I can interact hands-free while multitasking.

#### Acceptance Criteria

1. WHEN the user activates voice capture mode, THE Mobile_Client SHALL begin recording audio
2. WHEN the user completes speaking, THE Speech_Recognition_Service SHALL convert the audio to text within 2 seconds
3. WHEN speech recognition succeeds, THE Mobile_Client SHALL display the transcribed text for user confirmation
4. IF speech recognition fails, THEN THE Mobile_Client SHALL display an error message and offer to retry
5. THE Speech_Recognition_Service SHALL support both Hebrew and English speech recognition
6. THE Speech_Recognition_Service SHALL automatically detect the language being spoken

### Requirement 3: Secure API Communication

**User Story:** As a system administrator, I want all client-server communication to be authenticated, so that unauthorized access is prevented.

#### Acceptance Criteria

1. THE API_Gateway SHALL accept requests via HTTPS
2. WHEN a request is received, THE Authentication_Service SHALL validate the API key or token
3. IF authentication fails, THEN THE API_Gateway SHALL return a 401 Unauthorized response
4. THE API_Gateway SHALL reject requests with invalid or expired credentials
5. THE Mobile_Client SHALL include authentication credentials in every API request

### Requirement 4: Question Processing and Routing

**User Story:** As a user, I want my captured questions to be sent to the cloud backend efficiently, so that I receive answers quickly.

#### Acceptance Criteria

1. WHEN the user confirms a question, THE Mobile_Client SHALL send the text to the API_Gateway
2. THE API_Gateway SHALL forward authenticated requests to the Answer_Retrieval_Engine
3. WHEN a request is received, THE Cloud_Backend SHALL log the question with timestamp and language metadata
4. THE Mobile_Client SHALL display a loading indicator while waiting for a response
5. IF network connectivity fails, THEN THE Mobile_Client SHALL display an error message and offer to retry

### Requirement 5: Knowledge Base Storage

**User Story:** As a user, I want my documents stored in cloud storage, so that my knowledge base is accessible to the system.

#### Acceptance Criteria

1. THE Knowledge_Base SHALL store documents in S3
2. THE Cloud_Backend SHALL have read-only access to the Knowledge_Base
3. WHEN a document is uploaded, THE Document_Ingestion_Service SHALL assign it a unique document ID
4. THE Knowledge_Base SHALL support common document formats including PDF, TXT, and DOCX
5. THE Knowledge_Base SHALL organize documents with metadata including source, topic labels, and language

### Requirement 6: Document Ingestion and Indexing

**User Story:** As a user, I want my documents automatically processed into searchable records, so that the system can quickly find relevant answers.

#### Acceptance Criteria

1. WHEN a document is added to the Knowledge_Base, THE Document_Ingestion_Service SHALL extract text content
2. WHEN text is extracted, THE Document_Ingestion_Service SHALL create structured records in the Structured_Database
3. THE Document_Ingestion_Service SHALL preserve source document ID, section labels, topic labels, and language in each record
4. THE Document_Ingestion_Service SHALL support multiple choice format documents
5. WHEN ingestion completes, THE Document_Ingestion_Service SHALL mark the document as indexed

### Requirement 7: Answer Retrieval from Knowledge Base

**User Story:** As a user, I want the system to find relevant answers from my knowledge base, so that I receive accurate information based on my own documents.

#### Acceptance Criteria

1. WHEN a question is received, THE Answer_Retrieval_Engine SHALL search the Structured_Database for relevant records
2. THE Answer_Retrieval_Engine SHALL return results within 2 seconds for 95% of queries
3. WHEN multiple relevant records are found, THE Answer_Retrieval_Engine SHALL prioritize by relevance score
4. THE Answer_Retrieval_Engine SHALL search only records matching the question language
5. IF no relevant records are found, THEN THE Answer_Retrieval_Engine SHALL return a "no answer found" response

### Requirement 8: Response Format Selection

**User Story:** As a user, I want to receive answers in either multiple choice mode or conversation mode depending on my needs, so that I can get quick confirmations or natural conversational responses.

#### Acceptance Criteria

1. WHERE the user selects multiple choice mode with short response, THE Answer_Retrieval_Engine SHALL return the answer letter only
2. WHERE the user selects multiple choice mode with long response, THE Answer_Retrieval_Engine SHALL return the letter, option text, and explanation
3. WHERE the user selects conversation mode with short response, THE Answer_Retrieval_Engine SHALL return a brief conversational answer
4. WHERE the user selects conversation mode with long response, THE Answer_Retrieval_Engine SHALL return a complete conversational explanation
5. THE Mobile_Client SHALL allow users to toggle between multiple choice mode and conversation mode
6. THE Mobile_Client SHALL allow users to toggle between short and long response formats within each mode

### Requirement 9: Language-Matched Responses

**User Story:** As a bilingual user, I want answers in the same language as my question, so that I can seamlessly work in either Hebrew or English.

#### Acceptance Criteria

1. WHEN a question is in Hebrew, THE Answer_Retrieval_Engine SHALL return answers in Hebrew
2. WHEN a question is in English, THE Answer_Retrieval_Engine SHALL return answers in English
3. THE Cloud_Backend SHALL detect question language automatically
4. IF the question language cannot be determined, THEN THE Cloud_Backend SHALL default to English
5. THE Answer_Retrieval_Engine SHALL only search records matching the detected language

### Requirement 10: Text-to-Speech Audio Response

**User Story:** As a user, I want to hear answers read aloud through my earphones in either multiple choice or conversation mode, so that I can receive information hands-free while working.

#### Acceptance Criteria

1. WHEN a text response is received, THE TTS_Service SHALL convert it to audio
2. THE Mobile_Client SHALL play the audio through the device's audio output
3. WHERE the system is in multiple choice mode, THE TTS_Service SHALL read the answer letter and option text
4. WHERE the system is in conversation mode, THE TTS_Service SHALL read the full conversational response
5. THE TTS_Service SHALL use Hebrew voice synthesis for Hebrew responses
6. THE TTS_Service SHALL use English voice synthesis for English responses
7. WHERE the user has earphones connected, THE Mobile_Client SHALL route audio to the earphones
8. THE Mobile_Client SHALL allow users to adjust TTS speed and voice settings
9. THE Mobile_Client SHALL allow users to toggle between multiple choice mode and conversation mode

### Requirement 11: Transcript Storage

**User Story:** As a user, I want my question and answer history saved, so that I can review past interactions and track my learning.

#### Acceptance Criteria

1. WHEN an answer is returned, THE Cloud_Backend SHALL store the question and answer in the Transcript_Store
2. THE Transcript_Store SHALL record the timestamp, question text, answer text, language, and response mode
3. THE Transcript_Store SHALL associate each transcript with the source document ID
4. THE Cloud_Backend SHALL store transcripts within 1 second of generating the response
5. THE Transcript_Store SHALL support querying transcripts by date range and language

### Requirement 12: Rate Limiting and Abuse Prevention

**User Story:** As a system administrator, I want to prevent API abuse and control costs, so that the system remains available and affordable.

#### Acceptance Criteria

1. THE API_Gateway SHALL enforce a maximum of 100 requests per user per hour
2. WHEN rate limits are exceeded, THE API_Gateway SHALL return a 429 Too Many Requests response
3. THE API_Gateway SHALL implement daily request quotas per user
4. THE Authentication_Service SHALL track request counts per API key
5. WHERE suspicious patterns are detected, THE API_Gateway SHALL temporarily block the API key

### Requirement 13: Cost Control and Serverless Architecture

**User Story:** As a system owner, I want to minimize operational costs through serverless services, so that the system is economically sustainable.

#### Acceptance Criteria

1. THE Cloud_Backend SHALL use only serverless compute services with pay-per-use pricing
2. THE Cloud_Backend SHALL avoid services with fixed monthly fees
3. THE Cloud_Backend SHALL implement request quotas to cap maximum monthly costs
4. THE Structured_Database SHALL use a serverless database service
5. THE Cloud_Backend SHALL automatically scale down during periods of no usage

### Requirement 14: Error Handling and User Feedback

**User Story:** As a user, I want clear error messages when something goes wrong, so that I understand what happened and how to proceed.

#### Acceptance Criteria

1. WHEN an error occurs, THE Mobile_Client SHALL display a descriptive error message
2. WHEN an error occurs, THE TTS_Service SHALL read the error message aloud
3. IF a network error occurs, THEN THE Mobile_Client SHALL offer to retry the request
4. IF authentication fails, THEN THE Mobile_Client SHALL prompt the user to check credentials
5. THE Mobile_Client SHALL never crash due to backend errors

### Requirement 15: Privacy-Preserving Logging

**User Story:** As a privacy-conscious user, I want logging to be configurable and privacy-preserving, so that my sensitive information is protected.

#### Acceptance Criteria

1. WHERE logging is enabled, THE Cloud_Backend SHALL log request metadata without full question content
2. THE Cloud_Backend SHALL allow users to disable detailed logging
3. THE Cloud_Backend SHALL never log authentication credentials
4. WHERE logging is disabled, THE Cloud_Backend SHALL log only error events
5. THE Cloud_Backend SHALL automatically delete logs older than 90 days

### Requirement 16: Deployment Without App Store

**User Story:** As a developer, I want to deploy the iPhone application without App Store publishing, so that I can iterate quickly and avoid review delays.

#### Acceptance Criteria

1. THE Mobile_Client SHALL support deployment via TestFlight, web app, or iOS Shortcuts
2. THE Mobile_Client SHALL function without requiring App Store distribution
3. WHERE deployed as a web app, THE Mobile_Client SHALL request necessary device permissions
4. THE Mobile_Client SHALL provide installation instructions for the chosen deployment method
5. THE Mobile_Client SHALL update without requiring App Store review

### Requirement 17: Minimal User Interaction Flow

**User Story:** As a user, I want to complete the capture-to-response flow in minimal steps, so that I can get answers quickly without friction.

#### Acceptance Criteria

1. THE Mobile_Client SHALL complete the full flow in 3 steps: capture, confirm, receive
2. THE Mobile_Client SHALL provide a single-tap shortcut to activate the most recent capture mode
3. WHERE hands-free mode is enabled, THE Mobile_Client SHALL skip confirmation steps
4. THE Mobile_Client SHALL remember the user's preferred capture mode and response format
5. THE Mobile_Client SHALL display progress indicators during processing

### Requirement 18: Data Storage

**User Story:** As a user, I want all my data stored reliably in the cloud, so that my knowledge base and transcripts are available when I need them.

#### Acceptance Criteria

1. THE Knowledge_Base SHALL store all documents in S3 with standard durability
2. THE Structured_Database SHALL store all indexed records with automatic backups
3. THE Transcript_Store SHALL store all transcripts in DynamoDB with point-in-time recovery enabled
4. THE Cloud_Backend SHALL provide data retention policies configurable by the user
5. THE Cloud_Backend SHALL support data export for backup purposes

### Requirement 19: Multiple Choice Document Support

**User Story:** As a student, I want the system to handle multiple choice format documents, so that I can study exam materials effectively.

#### Acceptance Criteria

1. WHEN ingesting multiple choice documents, THE Document_Ingestion_Service SHALL parse question text and answer options
2. THE Document_Ingestion_Service SHALL associate each option letter with its corresponding text
3. WHEN answering multiple choice questions, THE Answer_Retrieval_Engine SHALL return the correct option letter
4. WHERE long response mode is selected, THE Answer_Retrieval_Engine SHALL include the explanation for the correct answer
5. THE Structured_Database SHALL store multiple choice questions with all options and explanations

### Requirement 20: Round-Trip Document Processing

**User Story:** As a system administrator, I want to verify that document ingestion preserves content accurately, so that answers remain faithful to source documents.

#### Acceptance Criteria

1. THE Document_Ingestion_Service SHALL parse documents into structured records
2. THE Document_Ingestion_Service SHALL provide a formatting function that converts structured records back to document format
3. FOR ALL successfully ingested documents, parsing then formatting then parsing SHALL produce equivalent structured records
4. WHEN formatting errors occur, THE Document_Ingestion_Service SHALL log the discrepancy with document ID
5. THE Document_Ingestion_Service SHALL validate round-trip accuracy for each document type

---

This requirements document provides a comprehensive foundation for the Mobile-to-Cloud Personal Knowledge Assistant. Please review the requirements and let me know if you'd like any modifications, additions, or clarifications before proceeding to the design phase.
