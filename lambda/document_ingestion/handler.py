# Document Ingestion Lambda Handler
# Processes documents uploaded to S3 and creates structured records in DynamoDB

import json
import boto3
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
import PyPDF2
import docx
from langdetect import detect, LangDetectException
import io
from multiple_choice_parser import parse_multiple_choice

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Environment variables
KB_TABLE_NAME = os.environ.get('KB_TABLE_NAME', 'mobile-knowledge-assistant-kb')
kb_table = dynamodb.Table(KB_TABLE_NAME)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for S3 event processing.
    Triggered when documents are uploaded to the knowledge base S3 bucket.
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Parse S3 event
        for record in event.get('Records', []):
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            print(f"Processing document: s3://{bucket}/{key}")
            
            # Download document from S3
            response = s3_client.get_object(Bucket=bucket, Key=key)
            file_content = response['Body'].read()
            
            # Extract text based on file extension
            file_extension = key.lower().split('.')[-1]
            text = extract_text(file_content, file_extension)
            
            if not text:
                print(f"No text extracted from {key}")
                continue
            
            # Detect language
            language = detect_language(text)
            print(f"Detected language: {language}")
            
            # Generate document ID
            document_id = str(uuid.uuid4())
            
            # Try to parse as multiple choice document
            questions = parse_multiple_choice(text)
            
            if questions:
                print(f"Parsed {len(questions)} multiple choice questions")
                # Store each question as a separate record
                records = []
                for q in questions:
                    record_data = {
                        'recordId': str(uuid.uuid4()),
                        'documentId': document_id,
                        'sourceFile': key,
                        'language': language,
                        'timestamp': int(datetime.utcnow().timestamp()),
                        'indexed': True,
                        'type': 'multiple_choice',
                        'question': q['question'],
                        'options': q['options'],
                        'correctAnswer': q['correctAnswer'],
                        'explanation': q.get('explanation', ''),
                        'topic': q.get('topic', 'General')
                    }
                    records.append(record_data)
                
                # Batch write to DynamoDB
                batch_write_records(records)
            else:
                # Store as conversation-style document
                print("Storing as conversation document")
                record_data = {
                    'recordId': str(uuid.uuid4()),
                    'documentId': document_id,
                    'sourceFile': key,
                    'content': text,
                    'language': language,
                    'timestamp': int(datetime.utcnow().timestamp()),
                    'indexed': True,
                    'type': 'conversation'
                }
                kb_table.put_item(Item=record_data)
            
            # Update S3 object metadata
            s3_client.copy_object(
                Bucket=bucket,
                Key=key,
                CopySource={'Bucket': bucket, 'Key': key},
                Metadata={
                    'indexed': 'true',
                    'documentId': document_id,
                    'language': language,
                    'questionCount': str(len(questions)) if questions else '0'
                },
                MetadataDirective='REPLACE'
            )
            
            print(f"Successfully processed document: {key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Document ingestion completed successfully'})
        }
    
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def batch_write_records(records: List[Dict[str, Any]]) -> None:
    """
    Batch write records to DynamoDB.
    Handles batches of up to 25 items (DynamoDB limit).
    """
    batch_size = 25
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        
        with kb_table.batch_writer() as writer:
            for record in batch:
                writer.put_item(Item=record)
        
        print(f"Wrote batch of {len(batch)} records to DynamoDB")


def extract_text(file_content: bytes, file_extension: str) -> Optional[str]:
    """
    Extract text from document based on file type.
    Supports PDF, TXT, and DOCX formats.
    """
    try:
        if file_extension == 'pdf':
            return extract_text_from_pdf(file_content)
        elif file_extension == 'txt':
            return file_content.decode('utf-8')
        elif file_extension in ['docx', 'doc']:
            return extract_text_from_docx(file_content)
        else:
            print(f"Unsupported file extension: {file_extension}")
            return None
    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        return None


def extract_text_from_pdf(file_content: bytes) -> str:
    """Extract text from PDF file."""
    pdf_file = io.BytesIO(file_content)
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    
    text = []
    for page in pdf_reader.pages:
        text.append(page.extract_text())
    
    return '\n'.join(text)


def extract_text_from_docx(file_content: bytes) -> str:
    """Extract text from DOCX file."""
    docx_file = io.BytesIO(file_content)
    doc = docx.Document(docx_file)
    
    text = []
    for paragraph in doc.paragraphs:
        text.append(paragraph.text)
    
    return '\n'.join(text)


def detect_language(text: str) -> str:
    """
    Detect language of text.
    Returns 'he' for Hebrew, 'en' for English, or 'unknown'.
    """
    try:
        lang = detect(text)
        # Map langdetect codes to our language codes
        if lang == 'he':
            return 'he'
        elif lang == 'en':
            return 'en'
        else:
            # Default to English for other languages
            return 'en'
    except LangDetectException:
        print("Could not detect language, defaulting to English")
        return 'en'
