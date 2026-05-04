import json
import boto3
import os
from datetime import datetime

ses_client = boto3.client('ses', region_name='us-east-1')

def lambda_handler(event, context):
    """
    Lambda function to handle contact form submissions and send emails via SES
    """
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Extract form data
        name = body.get('name', 'Unknown')
        email = body.get('email', 'no-email@provided.com')
        phone = body.get('phone', 'Not provided')
        company = body.get('company', 'Not provided')
        message = body.get('message', 'No message provided')
        
        # Validate required fields
        if not name or not email or not message:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'Missing required fields: name, email, and message are required'
                })
            }
        
        # Get recipient email from environment variable
        recipient_email = os.environ.get('RECIPIENT_EMAIL', 'ariel@slashmycloudbill.com')
        sender_email = os.environ.get('SENDER_EMAIL', 'noreply@slashmycloudbill.com')
        
        # Prepare email content
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        email_subject = f"New Contact Form Submission from {name}"
        
        email_body_text = f"""
New Contact Form Submission
============================

Submitted: {timestamp}

Contact Information:
-------------------
Name: {name}
Email: {email}
Phone: {phone}
Company: {company}

Message:
--------
{message}

---
This email was sent from the contact form at slashmycloudbill.com
"""
        
        email_body_html = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #0066ff 0%, #00d4ff 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #f9fafb; padding: 20px; border: 1px solid #e5e7eb; border-radius: 0 0 8px 8px; }}
        .field {{ margin-bottom: 15px; }}
        .label {{ font-weight: bold; color: #0066ff; }}
        .value {{ margin-top: 5px; }}
        .message-box {{ background: white; padding: 15px; border-left: 4px solid #0066ff; margin-top: 10px; }}
        .footer {{ margin-top: 20px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>New Contact Form Submission</h2>
            <p style="margin: 0; opacity: 0.9;">Submitted: {timestamp}</p>
        </div>
        <div class="content">
            <div class="field">
                <div class="label">Name:</div>
                <div class="value">{name}</div>
            </div>
            <div class="field">
                <div class="label">Email:</div>
                <div class="value"><a href="mailto:{email}">{email}</a></div>
            </div>
            <div class="field">
                <div class="label">Phone:</div>
                <div class="value">{phone}</div>
            </div>
            <div class="field">
                <div class="label">Company:</div>
                <div class="value">{company}</div>
            </div>
            <div class="field">
                <div class="label">Message:</div>
                <div class="message-box">{message}</div>
            </div>
            <div class="footer">
                This email was sent from the contact form at <a href="https://slashmycloudbill.com">slashmycloudbill.com</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
        
        # Send email via SES
        response = ses_client.send_email(
            Source=sender_email,
            Destination={
                'ToAddresses': [recipient_email]
            },
            Message={
                'Subject': {
                    'Data': email_subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': email_body_text,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': email_body_html,
                        'Charset': 'UTF-8'
                    }
                }
            },
            ReplyToAddresses=[email]
        )
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'message': 'Email sent successfully',
                'messageId': response['MessageId']
            })
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Failed to send email',
                'details': str(e)
            })
        }
