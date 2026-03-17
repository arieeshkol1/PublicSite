"""
Shared validation utilities for the ViewMyBill feature.

Provides reusable validation for email format, file extensions,
file sizes, and session ID generation. Validation rules match
the frontend (viewMyBill.js) to ensure consistent behavior.
"""

import os
import re
import uuid

MAX_FILE_SIZE = 10_485_760  # 10 MB in bytes
ALLOWED_EXTENSIONS = {'.pdf'}
EMAIL_REGEX = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def validate_email(email: str) -> tuple[bool, str]:
    """
    Validate email format.

    The email must contain exactly one @, a non-empty local part,
    and a domain with at least one dot. Matches the frontend regex:
    ``/^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/``

    Args:
        email: The email address string to validate.

    Returns:
        A tuple of (is_valid, error_message). error_message is empty
        when the email is valid.
    """
    if not isinstance(email, str) or not email.strip():
        return False, "Email is required"

    if not EMAIL_REGEX.match(email):
        return False, "Please enter a valid email address"

    return True, ""


def validate_file_extension(filename: str) -> tuple[bool, str]:
    """
    Validate that the file has a .pdf extension (case-insensitive).

    Args:
        filename: The original filename to check.

    Returns:
        A tuple of (is_valid, error_message). error_message is empty
        when the extension is valid.
    """
    if not isinstance(filename, str) or not filename.strip():
        return False, "Filename is required"

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Only PDF files are supported"

    return True, ""


def validate_file_size(size_bytes: int) -> tuple[bool, str]:
    """
    Validate that the file size is within the allowed limit.

    The file must be between 1 byte and 10 MB (10,485,760 bytes) inclusive.

    Args:
        size_bytes: File size in bytes.

    Returns:
        A tuple of (is_valid, error_message). error_message is empty
        when the size is valid.
    """
    if not isinstance(size_bytes, int) or size_bytes <= 0:
        return False, "The selected file is empty"

    if size_bytes > MAX_FILE_SIZE:
        return False, "File exceeds 10 MB limit. Please upload a smaller file"

    return True, ""


def generate_session_id() -> str:
    """
    Generate a UUID v4 session identifier.

    Returns:
        A lowercase UUID v4 string (e.g. '550e8400-e29b-41d4-a716-446655440000').
    """
    return str(uuid.uuid4())
