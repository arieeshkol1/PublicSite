"""
AWS Bill Analyzer - Response Formatter Module

This module formats AI responses for display in the chat interface.
"""

import re
from datetime import datetime
from typing import Dict, Any


class ResponseFormatter:
    """Format AI responses for display"""
    
    MAX_RESPONSE_LENGTH = 2000
    
    def format_response(self, bedrock_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract and format response from Bedrock output.
        
        Args:
            bedrock_response: Raw response from Bedrock API
            
        Returns:
            Formatted response dictionary with answer and metadata
        """
        # Extract text from Bedrock response structure
        answer_text = self._extract_text(bedrock_response)
        
        # Sanitize output
        answer_text = self.sanitize_output(answer_text)
        
        # Truncate if too long
        if len(answer_text) > self.MAX_RESPONSE_LENGTH:
            answer_text = answer_text[:self.MAX_RESPONSE_LENGTH - 3] + '...'
        
        # Add metadata
        return self.add_metadata(answer_text, {})
    
    def _extract_text(self, bedrock_response: Dict[str, Any]) -> str:
        """
        Extract text from Bedrock response structure.
        
        Args:
            bedrock_response: Raw Bedrock response
            
        Returns:
            Extracted text string
        """
        try:
            # Nova Lite response structure
            if 'output' in bedrock_response:
                output = bedrock_response['output']
                if 'message' in output:
                    message = output['message']
                    if 'content' in message:
                        content = message['content']
                        if isinstance(content, list) and len(content) > 0:
                            if 'text' in content[0]:
                                return content[0]['text']
            
            # Fallback: try to find text in any nested structure
            return self._find_text_recursive(bedrock_response)
            
        except Exception as e:
            print(f"Error extracting text from Bedrock response: {e}")
            return "I apologize, but I encountered an error processing the response. Please try again."
    
    def _find_text_recursive(self, obj: Any, depth: int = 0) -> str:
        """
        Recursively search for text in nested structure.
        
        Args:
            obj: Object to search
            depth: Current recursion depth
            
        Returns:
            Found text or empty string
        """
        if depth > 10:  # Prevent infinite recursion
            return ""
        
        if isinstance(obj, str):
            return obj
        elif isinstance(obj, dict):
            # Check for common text keys
            for key in ['text', 'content', 'answer', 'response', 'message']:
                if key in obj:
                    result = self._find_text_recursive(obj[key], depth + 1)
                    if result:
                        return result
            # Search all values
            for value in obj.values():
                result = self._find_text_recursive(value, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_text_recursive(item, depth + 1)
                if result:
                    return result
        
        return ""
    
    def sanitize_output(self, text: str) -> str:
        """
        Remove any sensitive data or formatting issues.
        
        Args:
            text: Raw text to sanitize
            
        Returns:
            Sanitized text
        """
        if not text:
            return "I apologize, but I couldn't generate a response. Please try rephrasing your question."
        
        # Remove any potential PII patterns (overly cautious)
        # Email addresses
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[email]', text)
        
        # Phone numbers (various formats)
        text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[phone]', text)
        text = re.sub(r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b', '[phone]', text)
        
        # Credit card numbers (basic pattern)
        text = re.sub(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[card]', text)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Remove problematic markdown that doesn't render well
        # Keep basic formatting but remove complex structures
        text = re.sub(r'```[\s\S]*?```', '', text)  # Remove code blocks
        
        # Ensure text is not empty after sanitization
        if not text or len(text.strip()) < 3:
            return "I apologize, but I couldn't generate a meaningful response. Please try rephrasing your question."
        
        return text
    
    def add_metadata(self, response: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add timestamp and other metadata to response.
        
        Args:
            response: Formatted response text
            metadata: Additional metadata dictionary
            
        Returns:
            Response dictionary with metadata
        """
        return {
            'answer': response,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'length': len(response),
            **metadata
        }
    
    def format_error_response(self, error_message: str) -> Dict[str, Any]:
        """
        Format an error message as a response.
        
        Args:
            error_message: Error message to format
            
        Returns:
            Formatted error response
        """
        return self.add_metadata(
            f"I apologize, but I encountered an error: {error_message}",
            {'is_error': True}
        )
