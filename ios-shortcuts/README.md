# iOS Shortcuts for Mobile Knowledge Assistant

This directory contains instructions for creating iOS Shortcuts to interact with the Mobile Knowledge Assistant API.

## Prerequisites

1. iPhone with iOS 14 or later
2. Shortcuts app installed (pre-installed on iOS)
3. API endpoint URL from CloudFormation outputs
4. API key from AWS Console (API Gateway > API Keys)

## Setup Instructions

### Step 1: Get API Configuration

After deploying the CloudFormation stacks, retrieve:

1. **API Endpoint**: From CloudFormation stack `mobile-ka-api` outputs
   - Example: `https://abc123xyz.execute-api.us-east-1.amazonaws.com/prod`

2. **API Key**: From AWS Console
   - Navigate to: API Gateway > API Keys > mobile-ka-api-key
   - Click "Show" to reveal the key value
   - Copy the key (format: `aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890`)

### Step 2: Create Main Shortcut

1. Open Shortcuts app on iPhone
2. Tap "+" to create new shortcut
3. Name it "Knowledge Assistant"
4. Follow the configuration below

## Shortcut Configurations

### 1. Camera Capture Shortcut

**Name**: "Capture Question from Camera"

**Actions**:
1. **Take Photo** (or **Select Photos** for existing images)
2. **Extract Text from Image**
   - Input: Photo from previous action
3. **Show Result**
   - Input: Extracted Text
   - This allows user to confirm the text
4. **Set Variable**
   - Name: "CapturedQuestion"
   - Value: Extracted Text

**Usage**: Takes a photo of text (e.g., exam question) and extracts it using iOS OCR.

---

### 2. Voice Capture Shortcut

**Name**: "Capture Question from Voice"

**Actions**:
1. **Dictate Text**
   - Language: Auto-detect
   - Stop listening: After Pause
2. **Show Result**
   - Input: Dictated Text
   - This allows user to confirm the text
3. **Set Variable**
   - Name: "CapturedQuestion"
   - Value: Dictated Text

**Usage**: Records voice input and transcribes it to text.

---

### 3. API Request Shortcut

**Name**: "Send Question to API"

**Actions**:
1. **Ask for Input**
   - Prompt: "Enter API Key (first time only)"
   - Input Type: Text
   - Default Answer: (leave empty)
   - Store in: Variable "APIKey"
   
2. **Choose from Menu**
   - Prompt: "Select Mode"
   - Options:
     - **Multiple Choice**
       - Set Variable "Mode" = "multiple_choice"
     - **Conversation**
       - Set Variable "Mode" = "conversation"

3. **Choose from Menu**
   - Prompt: "Select Format"
   - Options:
     - **Short Answer**
       - Set Variable "Format" = "short"
     - **Long Answer**
       - Set Variable "Format" = "long"

4. **Text**
   - Content:
     ```json
     {
       "question": "[CapturedQuestion]",
       "mode": "[Mode]",
       "format": "[Format]"
     }
     ```
   - Replace [CapturedQuestion], [Mode], [Format] with variables

5. **Get Contents of URL**
   - URL: `https://YOUR-API-ENDPOINT.execute-api.us-east-1.amazonaws.com/prod/query`
   - Method: POST
   - Headers:
     - `Content-Type`: `application/json`
     - `x-api-key`: `[APIKey]`
   - Request Body: JSON from previous action

6. **Get Dictionary from Input**
   - Input: Contents of URL

7. **Get Dictionary Value**
   - Key: "answer"
   - Dictionary: Dictionary from previous action

8. **Set Variable**
   - Name: "Answer"
   - Value: Dictionary Value

**Usage**: Sends question to API and retrieves answer.

---

### 4. Text-to-Speech Playback Shortcut

**Name**: "Speak Answer"

**Actions**:
1. **Detect Language**
   - Input: Variable "Answer"
   - Store in: Variable "DetectedLanguage"

2. **If** DetectedLanguage is "Hebrew"
   - **Speak Text**
     - Text: Variable "Answer"
     - Language: Hebrew
     - Voice: Carmit (or other Hebrew voice)
     - Rate: Normal
     - Pitch: Normal
     - Wait Until Finished: Yes

3. **Otherwise**
   - **Speak Text**
     - Text: Variable "Answer"
     - Language: English
     - Voice: Samantha (or other English voice)
     - Rate: Normal
     - Pitch: Normal
     - Wait Until Finished: Yes

**Usage**: Speaks the answer using appropriate language voice.

---

### 5. Error Handling Shortcut

**Name**: "Handle API Error"

**Actions**:
1. **If** Variable "Answer" is empty
   - **Show Alert**
     - Title: "Error"
     - Message: "Failed to get answer. Please check your connection and API key."
   - **Speak Text**
     - Text: "Error: Failed to get answer"
   - **Choose from Menu**
     - Prompt: "What would you like to do?"
     - Options:
       - **Retry**: Run "Knowledge Assistant" shortcut again
       - **Cancel**: Stop shortcut

**Usage**: Handles errors and offers retry option.

---

### 6. Main Workflow Shortcut

**Name**: "Knowledge Assistant" (Main Entry Point)

**Actions**:
1. **Choose from Menu**
   - Prompt: "How do you want to ask your question?"
   - Options:
     - **Camera**
       - Run Shortcut: "Capture Question from Camera"
     - **Voice**
       - Run Shortcut: "Capture Question from Voice"

2. **Show Notification**
   - Title: "Processing..."
   - Body: "Sending your question to the knowledge assistant"

3. **Run Shortcut**
   - Shortcut: "Send Question to API"
   - Input: Variable "CapturedQuestion"

4. **If** Variable "Answer" is not empty
   - **Show Result**
     - Input: Variable "Answer"
   - **Run Shortcut**
     - Shortcut: "Speak Answer"
     - Input: Variable "Answer"

5. **Otherwise**
   - **Run Shortcut**
     - Shortcut: "Handle API Error"

**Usage**: Main entry point that orchestrates the entire workflow.

---

## Configuration Steps

### Setting Up API Credentials

1. Open "Send Question to API" shortcut
2. Edit the "Get Contents of URL" action
3. Replace `YOUR-API-ENDPOINT` with your actual API endpoint
4. On first run, enter your API key when prompted
5. The key will be stored for future use

### Testing the Shortcuts

1. **Test Camera Capture**:
   - Run "Capture Question from Camera"
   - Take a photo of printed text
   - Verify the extracted text is correct

2. **Test Voice Capture**:
   - Run "Capture Question from Voice"
   - Speak a question in Hebrew or English
   - Verify the transcription is correct

3. **Test API Request**:
   - Run "Send Question to API" with a test question
   - Select mode (Multiple Choice or Conversation)
   - Select format (Short or Long)
   - Verify you receive an answer

4. **Test Full Workflow**:
   - Run "Knowledge Assistant" (main shortcut)
   - Choose Camera or Voice
   - Verify the answer is displayed and spoken

## Troubleshooting

### OCR Not Working
- Ensure the text in the photo is clear and well-lit
- Try taking the photo from a different angle
- Make sure the text is in focus

### Voice Recognition Not Working
- Check microphone permissions for Shortcuts app
- Speak clearly and at a moderate pace
- Reduce background noise

### API Errors

**401 Unauthorized**:
- Check that your API key is correct
- Verify the key is enabled in AWS Console

**429 Too Many Requests**:
- You've exceeded the rate limit (100 requests/hour)
- Wait before trying again

**500 Internal Server Error**:
- Check CloudWatch logs for Lambda errors
- Verify all CloudFormation stacks are deployed successfully

**No Answer Found**:
- Upload more documents to the S3 bucket
- Verify documents are being indexed (check DynamoDB table)
- Try rephrasing your question

## Advanced Configuration

### Customizing Voices

1. Go to Settings > Accessibility > Spoken Content > Voices
2. Download additional Hebrew or English voices
3. Update the "Speak Answer" shortcut to use your preferred voice

### Adding Shortcuts to Home Screen

1. Open Shortcuts app
2. Long-press on "Knowledge Assistant" shortcut
3. Select "Add to Home Screen"
4. Choose an icon and name
5. Tap "Add"

### Siri Integration

1. Open Shortcuts app
2. Tap on "Knowledge Assistant" shortcut
3. Tap the (i) info button
4. Enable "Add to Siri"
5. Record a phrase like "Ask my knowledge assistant"
6. Now you can trigger it with Siri

## Privacy Notes

- Questions are sent to your AWS account only
- No data is shared with third parties
- Transcripts are stored in DynamoDB with 90-day TTL
- API keys should be kept secure and not shared

## Cost Monitoring

Each shortcut run costs approximately:
- API Gateway: $0.0000035 per request
- Lambda: $0.0000002 per request
- DynamoDB: $0.00000125 per write

With 100 requests/hour limit, maximum monthly cost is ~$16.50.

## Next Steps

1. Upload knowledge documents to S3 bucket (documents/ prefix)
2. Wait for documents to be indexed (check DynamoDB)
3. Test with real questions
4. Share shortcuts with other users (export as .shortcut file)

## Support

For issues or questions:
1. Check CloudWatch logs for Lambda errors
2. Verify all CloudFormation stacks are healthy
3. Test API endpoint with curl or Postman
4. Review DynamoDB tables for indexed documents
