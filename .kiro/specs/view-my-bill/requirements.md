# Requirements Document

## Introduction

The ViewMyBill feature is a self-service AWS bill analysis tool that allows users to upload their AWS billing documents, receive AI-powered analysis using Amazon Bedrock, and download a comprehensive PDF report containing bill summaries, explanations of charges, and cost-saving recommendations. This feature will be hosted on the existing eshkolai.com domain under the `/viewMyBill` path.

## Glossary

- **ViewMyBill_System**: The complete web application including frontend, backend APIs, and processing components that handles bill analysis
- **Registration_Form**: The web form component that captures user email and accepts bill file uploads
- **Bill_Processor**: The Lambda function that parses uploaded AWS bills (CSV/PDF) and extracts billing data
- **AI_Analyzer**: The component that uses Amazon Bedrock (Nova Lite model) to analyze bill data and generate insights
- **PDF_Generator**: The component that creates downloadable PDF reports from the analysis results
- **Storage_Service**: The S3-based storage for uploaded bills and generated PDF reports
- **User**: A visitor to the ViewMyBill page who wants to analyze their AWS bill

## Requirements

### Requirement 1: User Registration and Email Capture

**User Story:** As a user, I want to provide my email address before uploading my bill, so that I can be identified and potentially receive follow-up communications.

#### Acceptance Criteria

1. THE Registration_Form SHALL display an email input field with validation for proper email format
2. WHEN a user submits an invalid email format, THE Registration_Form SHALL display an error message indicating the email format is incorrect
3. THE Registration_Form SHALL require the email field to be completed before allowing bill upload
4. THE ViewMyBill_System SHALL store the user email associated with the session for tracking purposes

### Requirement 2: Bill File Upload

**User Story:** As a user, I want to upload my AWS bill PDF, so that the system can analyze my cloud spending.

#### Acceptance Criteria

1. THE Registration_Form SHALL provide a file upload control that accepts PDF file format only
2. WHEN a user selects a file with an unsupported format (not PDF), THE Registration_Form SHALL display an error message indicating only PDF files are supported
3. WHEN a user uploads a file exceeding 10 MB, THE ViewMyBill_System SHALL reject the upload and display a file size limit error
4. WHEN a user uploads an empty file, THE ViewMyBill_System SHALL reject the upload and display an error indicating the file is empty
5. THE Registration_Form SHALL display the selected filename to confirm the upload selection
6. THE ViewMyBill_System SHALL store uploaded files in S3 with a unique session identifier

### Requirement 3: Bill Processing Initiation

**User Story:** As a user, I want to click a "Revise" button to start the analysis, so that I have control over when processing begins.

#### Acceptance Criteria

1. THE Registration_Form SHALL display a "Revise" button that initiates bill processing
2. WHILE the email field is empty or invalid, THE Registration_Form SHALL disable the Revise button
3. WHILE no file is selected, THE Registration_Form SHALL disable the Revise button
4. WHEN the user clicks the Revise button, THE ViewMyBill_System SHALL display a loading indicator
5. WHEN the user clicks the Revise button, THE ViewMyBill_System SHALL disable the button to prevent duplicate submissions

### Requirement 4: Bill Parsing

**User Story:** As a user, I want my PDF bill to be parsed correctly, so that the analysis is accurate.

#### Acceptance Criteria

1. WHEN a PDF bill file is uploaded, THE Bill_Processor SHALL extract text content and identify billing information including service names, costs, and billing dates
2. IF the Bill_Processor cannot parse the uploaded PDF, THEN THE ViewMyBill_System SHALL return a descriptive error message to the user
3. THE Bill_Processor SHALL calculate total cost and aggregate costs by AWS service
4. THE Bill_Processor SHALL identify the billing period start and end dates from the bill data

### Requirement 5: AI-Powered Bill Analysis

**User Story:** As a user, I want AI to analyze my bill and provide insights, so that I understand my AWS spending better.

#### Acceptance Criteria

1. WHEN a bill is successfully parsed, THE AI_Analyzer SHALL invoke Amazon Bedrock Nova Lite model with the bill data
2. THE AI_Analyzer SHALL generate a summary of the total bill amount and top spending services
3. THE AI_Analyzer SHALL generate explanations for each significant charge describing what the user is paying for
4. THE AI_Analyzer SHALL generate cost-saving recommendations based on the usage patterns identified
5. IF the Bedrock service is unavailable, THEN THE ViewMyBill_System SHALL return an error message indicating temporary service unavailability
6. IF the Bedrock service is throttled, THEN THE ViewMyBill_System SHALL return an error message asking the user to retry in a moment

### Requirement 6: PDF Report Generation

**User Story:** As a user, I want to receive a downloadable PDF report, so that I can save and share the analysis results.

#### Acceptance Criteria

1. WHEN the AI analysis completes successfully, THE PDF_Generator SHALL create a PDF document
2. THE PDF_Generator SHALL include a bill summary section with total cost, billing period, and currency
3. THE PDF_Generator SHALL include a service breakdown section listing costs per AWS service
4. THE PDF_Generator SHALL include an explanations section describing what each charge represents
5. THE PDF_Generator SHALL include a recommendations section with actionable cost-saving suggestions
6. THE PDF_Generator SHALL include a header with the eshkolai.com branding and generation timestamp
7. THE Storage_Service SHALL store the generated PDF in S3 with a unique identifier
8. THE Storage_Service SHALL generate a pre-signed URL for the PDF with a 24-hour expiration

### Requirement 7: Report Delivery

**User Story:** As a user, I want to see a download link for my report, so that I can access the analysis results.

#### Acceptance Criteria

1. WHEN the PDF is generated successfully, THE ViewMyBill_System SHALL display a download link to the user
2. THE ViewMyBill_System SHALL display a success message indicating the report is ready
3. WHEN the user clicks the download link, THE ViewMyBill_System SHALL initiate the PDF file download
4. THE ViewMyBill_System SHALL hide the loading indicator when the download link is displayed
5. IF the PDF generation fails, THEN THE ViewMyBill_System SHALL display an error message and allow the user to retry

### Requirement 8: Frontend Page Structure

**User Story:** As a user, I want a clean and intuitive interface, so that I can easily use the bill analysis feature.

#### Acceptance Criteria

1. THE ViewMyBill_System SHALL serve the feature from the path /viewMyBill on the eshkolai.com domain
2. THE ViewMyBill_System SHALL display consistent branding with the main eshkolai.com website
3. THE ViewMyBill_System SHALL be responsive and functional on desktop and mobile devices
4. THE ViewMyBill_System SHALL display clear instructions explaining the bill analysis process
5. THE ViewMyBill_System SHALL include a privacy notice explaining how uploaded data is handled

### Requirement 9: Error Handling

**User Story:** As a user, I want clear error messages when something goes wrong, so that I know how to proceed.

#### Acceptance Criteria

1. IF an upload fails due to network issues, THEN THE ViewMyBill_System SHALL display a retry option with an appropriate error message
2. IF the bill parsing fails, THEN THE ViewMyBill_System SHALL display a message indicating the file format may be unsupported or corrupted
3. IF the AI analysis times out, THEN THE ViewMyBill_System SHALL display a timeout message with a retry option
4. THE ViewMyBill_System SHALL log all errors for debugging purposes without exposing technical details to users

### Requirement 10: Data Security and Privacy

**User Story:** As a user, I want my billing data to be handled securely, so that my sensitive information is protected.

#### Acceptance Criteria

1. THE Storage_Service SHALL encrypt uploaded bills and generated PDFs at rest using S3 server-side encryption
2. THE ViewMyBill_System SHALL transmit all data over HTTPS
3. THE Storage_Service SHALL automatically delete uploaded bills and generated PDFs after 24 hours
4. THE ViewMyBill_System SHALL not store or log the actual bill content beyond the processing session
5. THE ViewMyBill_System SHALL use unique session identifiers that are not guessable
