"""Unit tests for the RI/SP commitment snippet generator.

Tests cover:
- Generated HCL contains aws_budgets_budget resource
- Budget has correct monthly amount from first option
- Notification rules at 80% and 100%
- Member email in subscriber list
- Comment about RI/SP purchase via Console/CLI
- Multiple options generate separate commented sections
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hcl_generator.commitments import generate_commitment_snippet


def _make_options(count=1):
    """Helper to create test commitment options."""
    base_options = [
        {
            "term": "1-year",
            "paymentOption": "no-upfront",
            "estimatedSavings": 150,
            "instanceFamily": "m5",
            "computeType": "",
            "monthlyCommitment": 500,
        },
        {
            "term": "3-year",
            "paymentOption": "all-upfront",
            "estimatedSavings": 300,
            "instanceFamily": "m5",
            "computeType": "",
            "monthlyCommitment": 350,
        },
        {
            "term": "1-year",
            "paymentOption": "partial-upfront",
            "estimatedSavings": 200,
            "instanceFamily": "c5",
            "computeType": "",
            "monthlyCommitment": 450,
        },
    ]
    return base_options[:count]


class TestCommitmentSnippetContainsBudgetResource:
    """Test that generated HCL contains aws_budgets_budget resource."""

    def test_ri_commitment_contains_budget_resource(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert 'resource "aws_budgets_budget"' in rendered

    def test_sp_commitment_contains_budget_resource(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("sp", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert 'resource "aws_budgets_budget"' in rendered


class TestBudgetHasCorrectMonthlyAmount:
    """Test that budget uses the first option's monthlyCommitment as limit."""

    def test_budget_limit_matches_first_option(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        # First option has monthlyCommitment = 500
        assert 'limit_amount = "500"' in rendered

    def test_budget_limit_ignores_second_option(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        # Second option has monthlyCommitment = 350, should NOT be the limit_amount
        # The limit_amount should be 500 (first option)
        assert 'limit_amount = "500"' in rendered

    def test_budget_has_cost_type(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert 'budget_type = "COST"' in rendered

    def test_budget_has_usd_unit(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert 'limit_unit = "USD"' in rendered

    def test_budget_has_monthly_time_unit(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert 'time_unit = "MONTHLY"' in rendered


class TestNotificationRulesAt80And100:
    """Test that notification rules exist at 80% and 100% thresholds."""

    def test_notification_at_80_percent(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "threshold = 80" in rendered

    def test_notification_at_100_percent(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "threshold = 100" in rendered

    def test_both_notifications_are_actual_type(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert rendered.count('notification_type = "ACTUAL"') == 2

    def test_both_notifications_use_percentage(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert rendered.count('threshold_type = "PERCENTAGE"') == 2

    def test_both_notifications_use_greater_than(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert rendered.count('comparison_operator = "GREATER_THAN"') == 2


class TestMemberEmailInSubscriberList:
    """Test that member email appears in notification subscriber list."""

    def test_email_in_subscriber_addresses(self):
        email = "finance@company.com"
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, email, "123456789012")
        rendered = doc.render()
        assert email in rendered

    def test_email_appears_in_both_notifications(self):
        email = "alerts@myorg.io"
        options = _make_options(1)
        doc = generate_commitment_snippet("sp", options, email, "123456789012")
        rendered = doc.render()
        # Email should appear twice (once per notification block)
        assert rendered.count(email) == 2


class TestConsoleCliPurchaseComment:
    """Test that comment about RI/SP purchase via Console/CLI is present."""

    def test_contains_console_cli_comment(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "AWS Console" in rendered or "Console" in rendered
        assert "CLI" in rendered

    def test_contains_cannot_purchase_via_terraform_note(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "cannot be purchased via Terraform" in rendered

    def test_contains_tracking_explanation(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("sp", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "tracking" in rendered


class TestMultipleOptionsGenerateSeparateSections:
    """Test that multiple options generate separate commented sections."""

    def test_two_options_generate_two_sections(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "Option 1" in rendered
        assert "Option 2" in rendered

    def test_three_options_generate_three_sections(self):
        options = _make_options(3)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "Option 1" in rendered
        assert "Option 2" in rendered
        assert "Option 3" in rendered

    def test_each_option_shows_term(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "1-year" in rendered
        assert "3-year" in rendered

    def test_each_option_shows_payment_option(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "no-upfront" in rendered
        assert "all-upfront" in rendered

    def test_each_option_shows_estimated_savings(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "$150" in rendered
        assert "$300" in rendered

    def test_each_option_shows_instance_family(self):
        options = _make_options(3)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "m5" in rendered
        assert "c5" in rendered

    def test_each_option_shows_monthly_commitment(self):
        options = _make_options(2)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "$500" in rendered
        assert "$350" in rendered

    def test_sp_commitment_shows_type_label(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("sp", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "Savings Plan" in rendered

    def test_ri_commitment_shows_type_label(self):
        options = _make_options(1)
        doc = generate_commitment_snippet("ri", options, "user@example.com", "123456789012")
        rendered = doc.render()
        assert "Reserved Instance" in rendered
