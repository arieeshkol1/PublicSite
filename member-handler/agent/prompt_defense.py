"""Prompt injection defense - delimiter wrapping and pattern detection."""
from __future__ import annotations

import logging
import re

from .constants import DELIMITER_START, DELIMITER_END

logger = logging.getLogger(__name__)

# Known injection patterns to detect
_INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE)),
    ("ignore_above", re.compile(r"ignore\s+(everything|all)\s+(above|before)", re.IGNORECASE)),
    ("you_are_now", re.compile(r"you\s+are\s+now\s+", re.IGNORECASE)),
    ("new_instructions", re.compile(r"new\s+instructions?:", re.IGNORECASE)),
    ("system_prompt_override", re.compile(r"system\s*:\s*", re.IGNORECASE)),
    ("forget_everything", re.compile(r"forget\s+(everything|all|previous)", re.IGNORECASE)),
    ("act_as", re.compile(r"act\s+as\s+(if\s+you\s+are|a)\s+", re.IGNORECASE)),
    ("disregard", re.compile(r"disregard\s+(all\s+)?(previous|prior|above)", re.IGNORECASE)),
    ("pretend", re.compile(r"pretend\s+(you\s+are|to\s+be|that)", re.IGNORECASE)),
    ("override_role", re.compile(r"(override|change|modify)\s+(your|the)\s+(role|instructions|system)", re.IGNORECASE)),
    ("jailbreak", re.compile(r"(jailbreak|DAN|do\s+anything\s+now)", re.IGNORECASE)),
    ("reveal_prompt", re.compile(r"(reveal|show|display|print)\s+(your|the)\s+(system\s+)?(prompt|instructions)", re.IGNORECASE)),
]


def sanitize_user_input(raw_input: str) -> str:
    """Escape delimiter sequences in user text and wrap with boundaries.

    1. Escapes any occurrences of DELIMITER_START or DELIMITER_END in the input
    2. Wraps the sanitized text within delimiter boundaries
    """
    if not raw_input:
        return f"{DELIMITER_START}\n\n{DELIMITER_END}"

    # Escape any delimiter sequences in the user's text
    sanitized = raw_input.replace(DELIMITER_START, DELIMITER_START.replace(">>>", "\\>>>"))
    sanitized = sanitized.replace(DELIMITER_END, DELIMITER_END.replace(">>>", "\\>>>"))

    # Wrap with boundaries
    return f"{DELIMITER_START}\n{sanitized}\n{DELIMITER_END}"


def detect_injection_patterns(raw_input: str) -> list[str]:
    """Scan for known injection patterns in user input.

    Returns a list of detected pattern names.
    Logs each detection for security monitoring.
    """
    if not raw_input:
        return []

    detected: list[str] = []

    for pattern_name, pattern in _INJECTION_PATTERNS:
        if pattern.search(raw_input):
            detected.append(pattern_name)
            logger.warning(
                f"Prompt injection pattern detected: '{pattern_name}' "
                f"in input (length={len(raw_input)})"
            )

    return detected
