"""Unit tests for tip_citation module."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tip_citation import build_tip_citation_prompt


class TestBuildTipCitationPrompt:
    """Tests for build_tip_citation_prompt function."""

    def test_empty_tips_returns_empty_string(self):
        """Should return empty string when tips list is empty."""
        result = build_tip_citation_prompt([])
        assert result == ""

    def test_none_tips_returns_empty_string(self):
        """Should return empty string when tips is None (falsy)."""
        result = build_tip_citation_prompt(None)
        assert result == ""

    def test_non_empty_tips_includes_citation_instruction(self):
        """Should include tip citation instruction when tips are present."""
        tips = [{"title": "Right-size EC2", "description": "Use smaller instances", "confidenceTag": "high-confidence"}]
        result = build_tip_citation_prompt(tips)
        assert "💡 Tip:" in result
        assert "You MUST cite at least one relevant tip" in result

    def test_includes_tip_title(self):
        """Should include tip titles in prompt context."""
        tips = [{"title": "Use Savings Plans", "description": "Commit for savings", "confidenceTag": "standard"}]
        result = build_tip_citation_prompt(tips)
        assert "Use Savings Plans" in result

    def test_includes_tip_description(self):
        """Should include tip descriptions in prompt context."""
        tips = [{"title": "Right-size RDS", "description": "Downsize underutilized databases", "confidenceTag": "standard"}]
        result = build_tip_citation_prompt(tips)
        assert "Downsize underutilized databases" in result

    def test_includes_confidence_level(self):
        """Should include confidence levels in prompt context."""
        tips = [{"title": "Delete idle EBS", "description": "Remove unattached volumes", "confidenceTag": "high-confidence"}]
        result = build_tip_citation_prompt(tips)
        assert "high-confidence" in result

    def test_default_confidence_when_missing(self):
        """Should use 'standard' as default confidence when confidenceTag is missing."""
        tips = [{"title": "Some tip", "description": "Some desc"}]
        result = build_tip_citation_prompt(tips)
        assert "standard" in result

    def test_multiple_tips_all_included(self):
        """Should include all tips (up to 5) in the prompt context."""
        tips = [
            {"title": "Tip A", "description": "Desc A", "confidenceTag": "high-confidence"},
            {"title": "Tip B", "description": "Desc B", "confidenceTag": "standard"},
            {"title": "Tip C", "description": "Desc C", "confidenceTag": "standard"},
        ]
        result = build_tip_citation_prompt(tips)
        assert "Tip A" in result
        assert "Tip B" in result
        assert "Tip C" in result

    def test_limits_to_five_tips(self):
        """Should only include up to 5 tips even if more are provided."""
        tips = [{"title": f"Tip {i}", "description": f"Desc {i}", "confidenceTag": "standard"} for i in range(8)]
        result = build_tip_citation_prompt(tips)
        assert "Tip 0" in result
        assert "Tip 4" in result
        assert "Tip 5" not in result

    def test_format_includes_tip_prefix_instruction(self):
        """Should instruct model to use 💡 Tip: prefix format."""
        tips = [{"title": "Test tip", "description": "Test desc", "confidenceTag": "standard"}]
        result = build_tip_citation_prompt(tips)
        assert "💡 Tip:" in result
        assert "tip title" in result.lower() or "[tip title]" in result

    def test_handles_missing_fields_gracefully(self):
        """Should handle tips with missing title or description gracefully."""
        tips = [{"tipId": "t1"}]
        result = build_tip_citation_prompt(tips)
        # Should not raise, should still produce citation instruction
        assert "💡 Tip:" in result
        assert "You MUST cite at least one relevant tip" in result
