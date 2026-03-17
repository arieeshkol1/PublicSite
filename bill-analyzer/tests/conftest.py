"""Shared fixtures for bill-analyzer tests."""
import os
import sys

import pytest

# Add bill-analyzer to path so modules can be imported directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


SAMPLE_PDF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "EUINIL26-139120 (1).pdf"
)


@pytest.fixture
def sample_pdf_bytes():
    """Load the sample AWS invoice PDF bytes."""
    if not os.path.exists(SAMPLE_PDF_PATH):
        pytest.skip("Sample PDF not found")
    with open(SAMPLE_PDF_PATH, "rb") as f:
        return f.read()
