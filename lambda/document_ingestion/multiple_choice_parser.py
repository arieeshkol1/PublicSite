# Multiple Choice Document Parser
# Parses multiple choice questions from text documents

import re
from typing import Dict, List, Optional, Any


def parse_multiple_choice(text: str) -> List[Dict[str, Any]]:
    """
    Parse multiple choice questions from text.
    
    Expected format:
    Question: <question text>
    A. <option A>
    B. <option B>
    C. <option C>
    D. <option D>
    Answer: <correct letter>
    Explanation: <explanation text>
    
    Returns list of parsed questions with structure:
    {
        'question': str,
        'options': {'A': str, 'B': str, 'C': str, 'D': str},
        'correctAnswer': str,
        'explanation': str,
        'topic': str (optional)
    }
    """
    questions = []
    
    # Split text into potential question blocks
    # Look for "Question:" or numbered questions
    question_pattern = r'(?:Question\s*\d*:|^\d+\.)\s*(.+?)(?=(?:Question\s*\d*:|\d+\.|$))'
    blocks = re.split(question_pattern, text, flags=re.MULTILINE | re.DOTALL)
    
    for block in blocks:
        if not block or len(block.strip()) < 10:
            continue
        
        question_data = parse_question_block(block)
        if question_data:
            questions.append(question_data)
    
    return questions


def parse_question_block(block: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single question block.
    """
    lines = block.strip().split('\n')
    
    question_text = None
    options = {}
    correct_answer = None
    explanation = None
    topic = None
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Extract question text (first non-empty line or line after "Question:")
        if question_text is None:
            if line.lower().startswith('question:'):
                question_text = line.split(':', 1)[1].strip()
            elif not re.match(r'^[A-D]\.', line) and not line.lower().startswith(('answer:', 'explanation:', 'topic:')):
                question_text = line
            i += 1
            continue
        
        # Extract options (A. B. C. D.)
        option_match = re.match(r'^([A-D])\.?\s*(.+)', line, re.IGNORECASE)
        if option_match:
            letter = option_match.group(1).upper()
            option_text = option_match.group(2).strip()
            options[letter] = option_text
            i += 1
            continue
        
        # Extract correct answer
        if line.lower().startswith('answer:'):
            answer_text = line.split(':', 1)[1].strip()
            # Extract just the letter (A, B, C, or D)
            answer_match = re.search(r'([A-D])', answer_text, re.IGNORECASE)
            if answer_match:
                correct_answer = answer_match.group(1).upper()
            i += 1
            continue
        
        # Extract explanation
        if line.lower().startswith('explanation:'):
            explanation = line.split(':', 1)[1].strip()
            # Continue reading explanation if it spans multiple lines
            i += 1
            while i < len(lines) and not lines[i].strip().lower().startswith(('question:', 'topic:', 'answer:')):
                explanation += ' ' + lines[i].strip()
                i += 1
            continue
        
        # Extract topic
        if line.lower().startswith('topic:'):
            topic = line.split(':', 1)[1].strip()
            i += 1
            continue
        
        i += 1
    
    # Validate that we have all required fields
    if question_text and len(options) >= 2 and correct_answer:
        return {
            'question': question_text,
            'options': options,
            'correctAnswer': correct_answer,
            'explanation': explanation or '',
            'topic': topic or 'General'
        }
    
    return None


def format_multiple_choice_short(question_data: Dict[str, Any]) -> str:
    """
    Format multiple choice answer in short form (letter only).
    """
    return question_data['correctAnswer']


def format_multiple_choice_long(question_data: Dict[str, Any]) -> str:
    """
    Format multiple choice answer in long form (letter + option + explanation).
    """
    letter = question_data['correctAnswer']
    option_text = question_data['options'].get(letter, '')
    explanation = question_data.get('explanation', '')
    
    result = f"{letter}. {option_text}"
    if explanation:
        result += f"\n\nExplanation: {explanation}"
    
    return result


def extract_topics(questions: List[Dict[str, Any]]) -> List[str]:
    """
    Extract unique topics from parsed questions.
    """
    topics = set()
    for q in questions:
        if q.get('topic'):
            topics.add(q['topic'])
    return list(topics)
