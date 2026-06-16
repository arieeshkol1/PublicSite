#!/usr/bin/env python3
"""Quick test runner for filter property tests."""
import sys
import os
import pytest

# Add the dashboard-handler to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Change to tests directory
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))

# Run tests - include all TestFilterUnitCases to start
exit_code = pytest.main([
    '-v',
    'test_datasource_filters_props.py::TestFilterUnitCases',
    '--tb=short',
])

sys.exit(exit_code)
