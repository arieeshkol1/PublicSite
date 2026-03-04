# Answer Retrieval Lambda Handler
# Searches knowledge base and formats responses

import json
import boto3
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

# Environment variables
KB_TABLE_NAME = os.environ.get('KB_TABLE_NAME', 'mobile-knowledge-assistant-kb')
TRANSCRIPTS_TABLE_NAME = os.environ.get('TRANSCRIPTS_TABLE_NAME', 'mobile-knowledge-assistant-transcripts')

kb_table = dynamodb.Table(KB_TABLE_NAME)
transcripts_table = dynamodb.Table(TRANSCRIPTS_TABLE_NAME)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for answer retrieval.
    Searches DynamoDB knowledge base and formats responses.
    
    Expected event structure:
    {
        'question': str,
        'language': str ('he' or 'en'),
        'mode': str ('multiple_choice' or 'conversation'),
        'format': str ('short' or 'long')
    }
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Extract parameters
        question = event.get('question', '').strip()
        language = event.get('language', 'en')
        mode = event.get('mode', 'conversation')
        response_format = event.get('format', 'short')
        
        if not question:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Question is required'})
            }
        
        # Search knowledge base
        results = search_knowledge_base(question, language, mode)
        
        if not results:
            answer = "No answer found in knowledge base." if language == 'en' else "לא נמצאה תשובה במאגר הידע."
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'answer': answer,
                    'language': language,
                    'found': False
                })
            }
        
        # Get best match
        best_match = results[0]
        
        # Format response based on mode and format
        answer = format_response(best_match, mode, response_format)
        
        # Store transcript
        transcript_id = store_transcript(
            question=question,
            answer=answer,
            language=language,
            mode=mode,
            response_format=response_format,
            source_document_id=best_match.get('documentId'),
            record_id=best_match.get('recordId')
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'answer': answer,
                'language': language,
                'sourceDocumentId': best_match.get('documentId'),
                'transcriptId': transcript_id,
                'found': True
            })
        }
    
    except Exception as e:
        print(f"Error retrieving answer: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def search_knowledge_base(question: str, language: str, mode: str) -> List[Dict[str, Any]]:
    """
    Search knowledge base for relevant records.
    Returns list of matching records sorted by relevance.
    """
    try:
        # Query by language using GSI
        response = kb_table.query(
            IndexName='language-index',
            KeyConditionExpression=Key('language').eq(language)
        )
        
        records = response.get('Items', [])
        
        # Filter by type if mode is specified
        if mode == 'multiple_choice':
            records = [r for r in records if r.get('type') == 'multiple_choice']
        elif mode == 'conversation':
            records = [r for r in records if r.get('type') == 'conversation']
        
        # Score and rank results
        scored_results = []
        question_lower = question.lower()
        
        for record in records:
            score = calculate_relevance_score(question_lower, record)
            if score > 0:
                record['relevance_score'] = score
                scored_results.append(record)
        
        # Sort by relevance score (descending)
        scored_results.sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return scored_results
    
    except Exception as e:
        print(f"Error searching knowledge base: {str(e)}")
        return []


def calculate_relevance_score(question: str, record: Dict[str, Any]) -> float:
    """
    Calculate relevance score for a record based on keyword matching.
    Simple scoring: count of matching words.
    """
    score = 0.0
    question_words = set(question.split())
    
    # Check question field (for multiple choice)
    if 'question' in record:
        record_question = record['question'].lower()
        record_words = set(record_question.split())
        common_words = question_words.intersection(record_words)
        score += len(common_words) * 2  # Weight question matches higher
    
    # Check content field (for conversation)
    if 'content' in record:
        content = record['content'].lower()
        content_words = set(content.split())
        common_words = question_words.intersection(content_words)
        score += len(common_words)
    
    # Check topic field
    if 'topic' in record:
        topic = record['topic'].lower()
        if any(word in topic for word in question_words):
            score += 5  # Bonus for topic match
    
    return score


def format_response(record: Dict[str, Any], mode: str, response_format: str) -> str:
    """
    Format response based on mode and format.
    """
    if mode == 'multiple_choice':
        return format_multiple_choice_response(record, response_format)
    else:
        return format_conversation_response(record, response_format)


def format_multiple_choice_response(record: Dict[str, Any], response_format: str) -> str:
    """
    Format multiple choice response.
    Short: letter only
    Long: letter + option text + explanation
    """
    correct_answer = record.get('correctAnswer', '')
    options = record.get('options', {})
    explanation = record.get('explanation', '')
    
    if response_format == 'short':
        # Return just the letter
        return correct_answer
    else:
        # Return letter + option + explanation
        option_text = options.get(correct_answer, '')
        result = f"{correct_answer}. {option_text}"
        if explanation:
            result += f"\n\nExplanation: {explanation}"
        return result


def format_conversation_response(record: Dict[str, Any], response_format: str) -> str:
    """
    Format conversation response.
    Short: first 2 sentences
    Long: full content
    """
    content = record.get('content', '')
    
    if response_format == 'short':
        # Return first 2 sentences
        sentences = content.split('.')
        return '. '.join(sentences[:2]) + '.' if len(sentences) > 1 else content
    else:
        # Return full content
        return content


def store_transcript(
    question: str,
    answer: str,
    language: str,
    mode: str,
    response_format: str,
    source_document_id: Optional[str],
    record_id: Optional[str]
) -> str:
    """
    Store question/answer transcript in DynamoDB.
    Returns transcript ID.
    """
    try:
        transcript_id = str(uuid.uuid4())
        timestamp = int(datetime.utcnow().timestamp())
        
        item = {
            'transcriptId': transcript_id,
            'timestamp': timestamp,
            'question': question,
            'answer': answer,
            'language': language,
            'mode': mode,
            'format': response_format,
            'ttl': timestamp + (90 * 24 * 60 * 60)  # 90 days TTL
        }
        
        if source_document_id:
            item['sourceDocumentId'] = source_document_id
        if record_id:
            item['recordId'] = record_id
        
        transcripts_table.put_item(Item=item)
        print(f"Stored transcript: {transcript_id}")
        
        return transcript_id
    
    except Exception as e:
        print(f"Error storing transcript: {str(e)}")
        return ''
