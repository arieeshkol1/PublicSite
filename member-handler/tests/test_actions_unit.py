"""Unit tests for hcl_generator.actions module.

Tests cover:
- SUPPORTED_ACTION_TYPES contains all 10 expected types
- Unsupported action type raises ValueError
- Header comment contains action description, timestamp, account ID, warning
- Dispatch calls correct generator function for each type
"""

import sys
import os
import re
from unittest.mock import patch
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from hcl_generator.actions import (
    SUPPORTED_ACTION_TYPES,
    generate_action_hcl,
    _build_header_comment,
    _action_description,
)


class TestSupportedActionTypes:
    """Tests for SUPPORTED_ACTION_TYPES constant."""

    def test_contains_all_ten_types(self):
        """SUPPORTED_ACTION_TYPES must contain exactly 10 action types."""
        assert len(SUPPORTED_ACTION_TYPES) == 10

    def test_contains_resize_ec2(self):
        assert "resize-ec2" in SUPPORTED_ACTION_TYPES

    def test_contains_delete_ebs(self):
        assert "delete-ebs" in SUPPORTED_ACTION_TYPES

    def test_contains_release_eip(self):
        assert "release-eip" in SUPPORTED_ACTION_TYPES

    def test_contains_s3_lifecycle(self):
        assert "s3-lifecycle" in SUPPORTED_ACTION_TYPES

    def test_contains_create_schedule(self):
        assert "create-schedule" in SUPPORTED_ACTION_TYPES

    def test_contains_apply_tags(self):
        assert "apply-tags" in SUPPORTED_ACTION_TYPES

    def test_contains_create_budget(self):
        assert "create-budget" in SUPPORTED_ACTION_TYPES

    def test_contains_ec2_idle(self):
        assert "ec2-idle" in SUPPORTED_ACTION_TYPES

    def test_contains_rds_idle(self):
        assert "rds-idle" in SUPPORTED_ACTION_TYPES

    def test_contains_ebs_snapshot(self):
        assert "ebs-snapshot" in SUPPORTED_ACTION_TYPES

    def test_is_a_set(self):
        """SUPPORTED_ACTION_TYPES should be a set for O(1) lookup."""
        assert isinstance(SUPPORTED_ACTION_TYPES, set)


class TestUnsupportedActionType:
    """Tests for ValueError on unsupported action types."""

    def test_raises_value_error_for_unknown_type(self):
        with pytest.raises(ValueError, match="Unsupported action type"):
            generate_action_hcl("unknown-action", {}, "123456789012")

    def test_raises_value_error_for_empty_string(self):
        with pytest.raises(ValueError, match="Unsupported action type"):
            generate_action_hcl("", {}, "123456789012")

    def test_raises_value_error_for_similar_but_wrong_type(self):
        """Typos or close matches should still raise."""
        with pytest.raises(ValueError, match="Unsupported action type"):
            generate_action_hcl("resize_ec2", {}, "123456789012")

    def test_error_message_includes_action_type(self):
        with pytest.raises(ValueError, match="custom-action"):
            generate_action_hcl("custom-action", {}, "123456789012")

    def test_error_message_lists_supported_types(self):
        with pytest.raises(ValueError, match="Supported types are"):
            generate_action_hcl("invalid", {}, "123456789012")


class TestHeaderComment:
    """Tests for header comment generation."""

    def test_contains_action_description(self):
        fixed_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        header = _build_header_comment(
            "Resize EC2 instance i-0abc to t3.medium",
            "123456789012",
            timestamp=fixed_time,
        )
        assert "Resize EC2 instance i-0abc to t3.medium" in header

    def test_contains_iso_8601_timestamp(self):
        fixed_time = datetime(2024, 6, 20, 14, 45, 30, tzinfo=timezone.utc)
        header = _build_header_comment("Test action", "123456789012", timestamp=fixed_time)
        assert "2024-06-20T14:45:30Z" in header

    def test_contains_account_id(self):
        header = _build_header_comment("Test action", "987654321098")
        assert "987654321098" in header

    def test_contains_review_warning(self):
        header = _build_header_comment("Test action", "123456789012")
        assert "WARNING" in header
        assert "review" in header.lower() or "Review" in header

    def test_timestamp_defaults_to_current_utc(self):
        """When no timestamp is provided, uses current UTC time."""
        before = datetime.now(timezone.utc).replace(microsecond=0)
        header = _build_header_comment("Test action", "123456789012")
        after = datetime.now(timezone.utc).replace(microsecond=0)

        # Extract the timestamp from the header
        match = re.search(r"Generated: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", header)
        assert match is not None
        generated_time = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        assert before <= generated_time <= after

    def test_header_has_all_four_elements(self):
        """Header must contain: description, timestamp, account ID, warning."""
        fixed_time = datetime(2024, 3, 10, 8, 0, 0, tzinfo=timezone.utc)
        header = _build_header_comment(
            "Delete EBS volume vol-abc123",
            "111222333444",
            timestamp=fixed_time,
        )
        # 1. Action description
        assert "Delete EBS volume vol-abc123" in header
        # 2. ISO 8601 timestamp
        assert "2024-03-10T08:00:00Z" in header
        # 3. Account ID
        assert "111222333444" in header
        # 4. Review warning
        assert "WARNING" in header


class TestActionDescription:
    """Tests for _action_description helper."""

    def test_resize_ec2_description(self):
        desc = _action_description(
            "resize-ec2",
            {"instanceId": "i-0abc123", "targetInstanceType": "t3.large"},
        )
        assert "i-0abc123" in desc
        assert "t3.large" in desc

    def test_delete_ebs_description(self):
        desc = _action_description("delete-ebs", {"volumeId": "vol-xyz789"})
        assert "vol-xyz789" in desc

    def test_release_eip_description(self):
        desc = _action_description("release-eip", {"allocationId": "eipalloc-abc"})
        assert "eipalloc-abc" in desc

    def test_s3_lifecycle_description(self):
        desc = _action_description("s3-lifecycle", {"bucketName": "my-bucket"})
        assert "my-bucket" in desc

    def test_create_schedule_description(self):
        desc = _action_description(
            "create-schedule",
            {"resourceId": "i-0abc", "resourceType": "ec2"},
        )
        assert "i-0abc" in desc

    def test_apply_tags_description(self):
        desc = _action_description(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2"},
        )
        assert "i-0abc" in desc

    def test_create_budget_description(self):
        desc = _action_description("create-budget", {"budgetName": "monthly-limit"})
        assert "monthly-limit" in desc


class TestDispatch:
    """Tests for dispatch to correct generator function for each type."""

    def test_resize_ec2_dispatches_correctly(self):
        """resize-ec2 should dispatch to _generate_resize_ec2 and return HclDocument."""
        from hcl_generator.core import HclDocument
        result = generate_action_hcl(
            "resize-ec2",
            {"instanceId": "i-0abc", "targetInstanceType": "t3.medium"},
            "123456789012",
        )
        assert isinstance(result, HclDocument)

    def test_delete_ebs_dispatches_correctly(self):
        """delete-ebs should dispatch to _generate_delete_ebs and return HclDocument."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-abc123"},
            "123456789012",
        )
        # Should return an HclDocument (no longer raises NotImplementedError)
        from hcl_generator.core import HclDocument
        assert isinstance(result, HclDocument)

    def test_release_eip_dispatches_correctly(self):
        """release-eip should dispatch to _generate_release_eip and return HclDocument."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-abc"},
            "123456789012",
        )
        from hcl_generator.core import HclDocument
        assert isinstance(result, HclDocument)

    def test_s3_lifecycle_dispatches_correctly(self):
        """s3-lifecycle should dispatch to _generate_s3_lifecycle and return HclDocument."""
        from hcl_generator.core import HclDocument
        result = generate_action_hcl(
            "s3-lifecycle",
            {"bucketName": "my-bucket", "transitionDays": 30,
             "storageClass": "GLACIER", "expirationDays": 365},
            "123456789012",
        )
        assert isinstance(result, HclDocument)

    def test_create_schedule_dispatches_correctly(self):
        """create-schedule should dispatch to _generate_create_schedule and return HclDocument."""
        result = generate_action_hcl(
            "create-schedule",
            {
                "resourceId": "i-0abc",
                "resourceType": "ec2",
                "startCron": "0 8 * * *",
                "stopCron": "0 18 * * *",
                "timezone": "UTC",
            },
            "123456789012",
        )
        from hcl_generator.core import HclDocument
        assert isinstance(result, HclDocument)

    def test_apply_tags_dispatches_correctly(self):
        """apply-tags should dispatch to _generate_apply_tags and return HclDocument."""
        from hcl_generator.core import HclDocument
        result = generate_action_hcl(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2", "tags": {"Env": "prod"}},
            "123456789012",
        )
        assert isinstance(result, HclDocument)

    def test_create_budget_dispatches_correctly(self):
        """create-budget should dispatch to _generate_create_budget and return HclDocument."""
        from hcl_generator.core import HclDocument
        result = generate_action_hcl(
            "create-budget",
            {"budgetName": "monthly", "amount": 100},
            "123456789012",
        )
        assert isinstance(result, HclDocument)

    def test_each_type_dispatches_to_unique_function(self):
        """Each supported type should dispatch to its own generator and return HclDocument."""
        from hcl_generator.core import HclDocument

        # All types are now implemented and return HclDocument
        test_params = {
            "resize-ec2": {"instanceId": "i-test", "targetInstanceType": "t3.medium"},
            "delete-ebs": {"volumeId": "vol-test"},
            "release-eip": {"allocationId": "eipalloc-test"},
            "s3-lifecycle": {"bucketName": "test-bucket", "transitionDays": 30,
                            "storageClass": "GLACIER", "expirationDays": 365},
            "create-schedule": {"resourceId": "i-test", "resourceType": "ec2",
                                "startCron": "0 8 * * *", "stopCron": "0 18 * * *", "timezone": "UTC"},
            "apply-tags": {"resourceId": "i-test", "resourceType": "ec2", "tags": {"Env": "prod"}},
            "create-budget": {"budgetName": "test", "amount": 100, "timeUnit": "MONTHLY",
                              "notificationThresholds": [80, 100], "subscriberEmail": "test@example.com"},
        }
        for action_type in SUPPORTED_ACTION_TYPES:
            params = test_params.get(action_type, {})
            result = generate_action_hcl(action_type, params, "123456789012")
            assert isinstance(result, HclDocument), f"{action_type} did not return HclDocument"


class TestResizeEc2Generator:
    """Tests for the resize-ec2 action generator."""

    def _generate(self, instance_id="i-0abc123def", target_type="t3.medium",
                  account_id="123456789012", region="us-east-1"):
        """Helper to generate resize-ec2 HCL and return rendered string."""
        doc = generate_action_hcl(
            "resize-ec2",
            {"instanceId": instance_id, "targetInstanceType": target_type},
            account_id,
            region,
        )
        return doc.render()

    def test_contains_aws_instance_resource(self):
        """Generated HCL must contain an aws_instance resource block."""
        hcl = self._generate()
        assert 'resource "aws_instance"' in hcl

    def test_contains_target_instance_type(self):
        """Generated HCL must contain the target instance type."""
        hcl = self._generate(target_type="m5.xlarge")
        assert "m5.xlarge" in hcl

    def test_contains_import_block_with_instance_id(self):
        """Generated HCL must contain an import block with the instance ID."""
        hcl = self._generate(instance_id="i-0abc123def456")
        assert "import {" in hcl
        assert "i-0abc123def456" in hcl

    def test_contains_provider_block(self):
        """Generated HCL must contain a provider aws block."""
        hcl = self._generate()
        assert 'provider "aws"' in hcl

    def test_contains_header_comment(self):
        """Generated HCL must contain the header comment with action info."""
        hcl = self._generate()
        assert "Generated by SlashMyBill" in hcl
        assert "WARNING" in hcl

    def test_import_block_references_correct_resource(self):
        """Import block 'to' must reference the aws_instance resource name."""
        hcl = self._generate(instance_id="i-0abc123def")
        assert "aws_instance.i-0abc123def" in hcl

    def test_provider_block_contains_region(self):
        """Provider block must contain the specified region."""
        hcl = self._generate(region="eu-west-1")
        assert "eu-west-1" in hcl

    def test_provider_block_contains_assume_role(self):
        """Provider block must contain assume_role with the account role ARN."""
        hcl = self._generate(account_id="987654321098")
        assert "arn:aws:iam::987654321098:role/SlashMyBill-987654321098" in hcl

    def test_contains_required_providers(self):
        """Generated HCL must contain terraform required_providers block."""
        hcl = self._generate()
        assert "required_providers" in hcl
        assert "hashicorp/aws" in hcl

    def test_header_contains_account_id(self):
        """Header comment must include the target account ID."""
        hcl = self._generate(account_id="111222333444")
        assert "111222333444" in hcl


class TestDeleteEbsGenerator:
    """Tests for _generate_delete_ebs action generator."""

    def test_generates_removed_block_with_correct_from_reference(self):
        """delete-ebs should generate a removed block with from = aws_ebs_volume.<name>."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-0abc123def456"},
            "123456789012",
            region="us-east-1",
        )
        rendered = result.render()
        assert "removed {" in rendered
        assert "aws_ebs_volume.vol-0abc123def456" in rendered

    def test_generates_lifecycle_destroy_true(self):
        """delete-ebs should include lifecycle { destroy = true } in removed block."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "lifecycle {" in rendered
        assert "destroy = true" in rendered

    def test_contains_provider_block(self):
        """delete-ebs should include a provider aws block with assume_role."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-abc123"},
            "123456789012",
            region="eu-west-1",
        )
        rendered = result.render()
        assert 'provider "aws"' in rendered
        assert "eu-west-1" in rendered
        assert "assume_role" in rendered
        assert "arn:aws:iam::123456789012:role/SlashMyBill-123456789012" in rendered

    def test_contains_header_comment(self):
        """delete-ebs should include the standard header comment."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "Generated by SlashMyBill" in rendered
        assert "Delete EBS volume vol-abc123" in rendered
        assert "123456789012" in rendered
        assert "WARNING" in rendered

    def test_contains_terraform_required_providers(self):
        """delete-ebs should include terraform { required_providers {} } block."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "terraform {" in rendered
        assert "required_providers {" in rendered
        assert "hashicorp/aws" in rendered

    def test_uses_terraform_identifier_for_resource_name(self):
        """Volume ID should be converted to a valid Terraform identifier."""
        result = generate_action_hcl(
            "delete-ebs",
            {"volumeId": "vol-0abc123"},
            "123456789012",
        )
        rendered = result.render()
        # vol-0abc123 is already a valid terraform identifier
        assert "aws_ebs_volume.vol-0abc123" in rendered


class TestReleaseEipGenerator:
    """Tests for _generate_release_eip action generator."""

    def test_generates_removed_block_with_correct_from_reference(self):
        """release-eip should generate a removed block with from = aws_eip.<name>."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-0abc123def456"},
            "123456789012",
            region="us-east-1",
        )
        rendered = result.render()
        assert "removed {" in rendered
        assert "aws_eip.eipalloc-0abc123def456" in rendered

    def test_generates_lifecycle_destroy_true(self):
        """release-eip should include lifecycle { destroy = true } in removed block."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "lifecycle {" in rendered
        assert "destroy = true" in rendered

    def test_contains_provider_block(self):
        """release-eip should include a provider aws block with assume_role."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-abc123"},
            "999888777666",
            region="ap-southeast-1",
        )
        rendered = result.render()
        assert 'provider "aws"' in rendered
        assert "ap-southeast-1" in rendered
        assert "assume_role" in rendered
        assert "arn:aws:iam::999888777666:role/SlashMyBill-999888777666" in rendered

    def test_contains_header_comment(self):
        """release-eip should include the standard header comment."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "Generated by SlashMyBill" in rendered
        assert "Release Elastic IP eipalloc-abc123" in rendered
        assert "123456789012" in rendered
        assert "WARNING" in rendered

    def test_contains_terraform_required_providers(self):
        """release-eip should include terraform { required_providers {} } block."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "terraform {" in rendered
        assert "required_providers {" in rendered
        assert "hashicorp/aws" in rendered

    def test_uses_terraform_identifier_for_resource_name(self):
        """Allocation ID should be converted to a valid Terraform identifier."""
        result = generate_action_hcl(
            "release-eip",
            {"allocationId": "eipalloc-0abc123"},
            "123456789012",
        )
        rendered = result.render()
        assert "aws_eip.eipalloc-0abc123" in rendered


class TestApplyTagsGenerator:
    """Tests for _generate_apply_tags action generator."""

    def test_generates_resource_with_tags(self):
        """apply-tags should generate a resource block with the provided tags."""
        doc = generate_action_hcl(
            "apply-tags",
            {
                "resourceId": "i-0abc123def",
                "resourceType": "ec2",
                "tags": {"Environment": "production", "Team": "platform"},
            },
            "123456789012",
            "us-east-1",
        )
        rendered = doc.render()
        assert "aws_instance" in rendered
        assert "Environment" in rendered
        assert "production" in rendered
        assert "Team" in rendered
        assert "platform" in rendered

    def test_generates_import_block(self):
        """apply-tags should generate an import block referencing the resource."""
        doc = generate_action_hcl(
            "apply-tags",
            {
                "resourceId": "i-0abc123def",
                "resourceType": "ec2",
                "tags": {"Env": "prod"},
            },
            "123456789012",
            "us-east-1",
        )
        rendered = doc.render()
        assert "import" in rendered
        assert "i-0abc123def" in rendered
        assert "aws_instance" in rendered

    def test_maps_ec2_resource_type(self):
        """resourceType 'ec2' should map to aws_instance."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2", "tags": {"k": "v"}},
            "123456789012",
        )
        rendered = doc.render()
        assert "aws_instance" in rendered

    def test_maps_ebs_resource_type(self):
        """resourceType 'ebs' should map to aws_ebs_volume."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "vol-abc", "resourceType": "ebs", "tags": {"k": "v"}},
            "123456789012",
        )
        rendered = doc.render()
        assert "aws_ebs_volume" in rendered

    def test_maps_s3_resource_type(self):
        """resourceType 's3' should map to aws_s3_bucket."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "my-bucket", "resourceType": "s3", "tags": {"k": "v"}},
            "123456789012",
        )
        rendered = doc.render()
        assert "aws_s3_bucket" in rendered

    def test_contains_provider_block(self):
        """apply-tags should include a provider 'aws' block."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2", "tags": {"k": "v"}},
            "123456789012",
            "us-west-2",
        )
        rendered = doc.render()
        assert 'provider "aws"' in rendered
        assert "us-west-2" in rendered

    def test_contains_header_comment(self):
        """apply-tags should include the standard header comment."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2", "tags": {"k": "v"}},
            "123456789012",
        )
        rendered = doc.render()
        assert "Generated by SlashMyBill" in rendered
        assert "123456789012" in rendered
        assert "WARNING" in rendered

    def test_contains_terraform_required_providers(self):
        """apply-tags should include terraform { required_providers {} } block."""
        doc = generate_action_hcl(
            "apply-tags",
            {"resourceId": "i-0abc", "resourceType": "ec2", "tags": {"k": "v"}},
            "123456789012",
        )
        rendered = doc.render()
        assert "terraform" in rendered
        assert "required_providers" in rendered
        assert "hashicorp/aws" in rendered


class TestCreateBudgetGenerator:
    """Tests for _generate_create_budget action generator."""

    def test_generates_aws_budgets_budget_resource(self):
        """create-budget should generate an aws_budgets_budget resource."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "monthly-limit",
                "amount": 500,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80, 100],
                "subscriberEmail": "user@example.com",
            },
            "123456789012",
            "us-east-1",
        )
        rendered = doc.render()
        assert "aws_budgets_budget" in rendered

    def test_contains_amount_and_time_unit(self):
        """create-budget should contain the budget amount and time unit."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "quarterly-budget",
                "amount": 1500,
                "timeUnit": "QUARTERLY",
                "notificationThresholds": [90],
                "subscriberEmail": "admin@example.com",
            },
            "123456789012",
            "us-east-1",
        )
        rendered = doc.render()
        assert "1500" in rendered
        assert "QUARTERLY" in rendered
        assert "USD" in rendered
        assert "COST" in rendered

    def test_contains_notification_thresholds(self):
        """create-budget should contain notification blocks for each threshold."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "my-budget",
                "amount": 200,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [50, 80, 100],
                "subscriberEmail": "alerts@example.com",
            },
            "123456789012",
            "us-east-1",
        )
        rendered = doc.render()
        # Should have notification blocks with thresholds
        assert "notification" in rendered
        assert "GREATER_THAN" in rendered
        assert "PERCENTAGE" in rendered
        assert "ACTUAL" in rendered
        assert "alerts@example.com" in rendered
        # Check all three thresholds are present
        assert "50" in rendered
        assert "80" in rendered
        assert "100" in rendered

    def test_contains_budget_name(self):
        """create-budget should include the budget name."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "dev-team-budget",
                "amount": 300,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80],
                "subscriberEmail": "dev@example.com",
            },
            "123456789012",
        )
        rendered = doc.render()
        assert "dev-team-budget" in rendered

    def test_contains_provider_block(self):
        """create-budget should include a provider 'aws' block."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "budget",
                "amount": 100,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80],
                "subscriberEmail": "user@example.com",
            },
            "123456789012",
            "eu-west-1",
        )
        rendered = doc.render()
        assert 'provider "aws"' in rendered
        assert "eu-west-1" in rendered

    def test_contains_header_comment(self):
        """create-budget should include the standard header comment."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "budget",
                "amount": 100,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80],
                "subscriberEmail": "user@example.com",
            },
            "123456789012",
        )
        rendered = doc.render()
        assert "Generated by SlashMyBill" in rendered
        assert "123456789012" in rendered
        assert "WARNING" in rendered

    def test_contains_terraform_required_providers(self):
        """create-budget should include terraform { required_providers {} } block."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "budget",
                "amount": 100,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80],
                "subscriberEmail": "user@example.com",
            },
            "123456789012",
        )
        rendered = doc.render()
        assert "terraform" in rendered
        assert "required_providers" in rendered
        assert "hashicorp/aws" in rendered

    def test_subscriber_email_in_notification(self):
        """Each notification block should contain the subscriber email."""
        doc = generate_action_hcl(
            "create-budget",
            {
                "budgetName": "budget",
                "amount": 100,
                "timeUnit": "MONTHLY",
                "notificationThresholds": [80, 100],
                "subscriberEmail": "finance@company.com",
            },
            "123456789012",
        )
        rendered = doc.render()
        assert "finance@company.com" in rendered


class TestCreateScheduleGenerator:
    """Tests for the create-schedule action generator."""

    @pytest.fixture
    def schedule_params(self):
        return {
            "resourceId": "i-0abc123def",
            "resourceType": "ec2",
            "startCron": "0 8 * * MON-FRI",
            "stopCron": "0 18 * * MON-FRI",
            "timezone": "America/New_York",
        }

    @pytest.fixture
    def rendered_hcl(self, schedule_params):
        doc = generate_action_hcl(
            "create-schedule",
            schedule_params,
            "123456789012",
            region="us-east-1",
        )
        return doc.render()

    def test_contains_two_scheduler_schedule_resources(self, rendered_hcl):
        """Generated HCL must contain two aws_scheduler_schedule resources (start and stop)."""
        assert rendered_hcl.count('resource "aws_scheduler_schedule"') == 2

    def test_contains_start_schedule_resource(self, rendered_hcl):
        """Generated HCL must contain a start schedule resource."""
        assert "slashmybill-start-i-0abc123def" in rendered_hcl

    def test_contains_stop_schedule_resource(self, rendered_hcl):
        """Generated HCL must contain a stop schedule resource."""
        assert "slashmybill-stop-i-0abc123def" in rendered_hcl

    def test_contains_start_cron_expression(self, rendered_hcl):
        """Generated HCL must contain the start cron expression."""
        assert "cron(0 8 * * MON-FRI)" in rendered_hcl

    def test_contains_stop_cron_expression(self, rendered_hcl):
        """Generated HCL must contain the stop cron expression."""
        assert "cron(0 18 * * MON-FRI)" in rendered_hcl

    def test_contains_timezone(self, rendered_hcl):
        """Generated HCL must contain the timezone."""
        assert "America/New_York" in rendered_hcl

    def test_contains_provider_block(self, rendered_hcl):
        """Generated HCL must contain a provider aws block."""
        assert 'provider "aws"' in rendered_hcl
        assert "us-east-1" in rendered_hcl

    def test_contains_header_comment(self, rendered_hcl):
        """Generated HCL must contain the header comment with action info."""
        assert "Generated by SlashMyBill" in rendered_hcl
        assert "WARNING" in rendered_hcl
        assert "123456789012" in rendered_hcl

    def test_contains_terraform_required_providers(self, rendered_hcl):
        """Generated HCL must contain terraform { required_providers {} } block."""
        assert "terraform {" in rendered_hcl
        assert "required_providers {" in rendered_hcl
        assert "hashicorp/aws" in rendered_hcl

    def test_contains_flexible_time_window(self, rendered_hcl):
        """Generated HCL must contain flexible_time_window with mode OFF."""
        assert "flexible_time_window {" in rendered_hcl
        assert '"OFF"' in rendered_hcl

    def test_contains_target_block(self, rendered_hcl):
        """Generated HCL must contain target blocks."""
        assert "target {" in rendered_hcl


class TestS3LifecycleGenerator:
    """Tests for the S3 lifecycle rule action generator."""

    @pytest.fixture
    def s3_params(self):
        """Standard S3 lifecycle action parameters."""
        return {
            "bucketName": "my-data-bucket",
            "transitionDays": 90,
            "storageClass": "GLACIER",
            "expirationDays": 365,
        }

    @pytest.fixture
    def rendered_hcl(self, s3_params):
        """Rendered HCL output for standard S3 lifecycle params."""
        doc = generate_action_hcl("s3-lifecycle", s3_params, "123456789012", "us-east-1")
        return doc.render()

    def test_contains_lifecycle_configuration_resource(self, rendered_hcl):
        """Generated HCL must contain aws_s3_bucket_lifecycle_configuration resource."""
        assert "aws_s3_bucket_lifecycle_configuration" in rendered_hcl

    def test_contains_transition_with_correct_days(self, rendered_hcl):
        """Generated HCL must contain transition block with correct days."""
        assert "transition" in rendered_hcl
        assert "days = 90" in rendered_hcl

    def test_contains_transition_with_correct_storage_class(self, rendered_hcl):
        """Generated HCL must contain transition block with correct storage class."""
        assert 'storage_class = "GLACIER"' in rendered_hcl

    def test_contains_expiration_with_correct_days(self, rendered_hcl):
        """Generated HCL must contain expiration block with correct days."""
        assert "expiration" in rendered_hcl
        # Expiration days is 365
        assert "days = 365" in rendered_hcl

    def test_contains_import_block_with_bucket_name(self, rendered_hcl):
        """Generated HCL must contain import block with bucket name."""
        assert "import {" in rendered_hcl
        assert 'id = "my-data-bucket"' in rendered_hcl

    def test_import_block_references_lifecycle_resource(self, rendered_hcl):
        """Import block 'to' must reference the lifecycle configuration resource."""
        assert "aws_s3_bucket_lifecycle_configuration." in rendered_hcl

    def test_contains_provider_block(self, rendered_hcl):
        """Generated HCL must contain provider aws block."""
        assert 'provider "aws"' in rendered_hcl
        assert 'region = "us-east-1"' in rendered_hcl

    def test_contains_header_comment(self, rendered_hcl):
        """Generated HCL must contain the standard header comment."""
        assert "Generated by SlashMyBill" in rendered_hcl
        assert "WARNING" in rendered_hcl
        assert "123456789012" in rendered_hcl

    def test_contains_terraform_required_providers(self, rendered_hcl):
        """Generated HCL must contain terraform required_providers block."""
        assert "terraform {" in rendered_hcl
        assert "required_providers" in rendered_hcl
        assert "hashicorp/aws" in rendered_hcl

    def test_contains_bucket_attribute(self, rendered_hcl):
        """Resource must have bucket attribute set to the bucket name."""
        assert 'bucket = "my-data-bucket"' in rendered_hcl

    def test_contains_rule_block_with_id(self, rendered_hcl):
        """Resource must have a rule block with the standard rule ID."""
        assert 'id = "slashmybill-lifecycle-rule"' in rendered_hcl

    def test_contains_rule_status_enabled(self, rendered_hcl):
        """Rule block must have status = Enabled."""
        assert 'status = "Enabled"' in rendered_hcl

    def test_different_storage_class(self):
        """Generator should use the provided storage class."""
        params = {
            "bucketName": "archive-bucket",
            "transitionDays": 60,
            "storageClass": "DEEP_ARCHIVE",
            "expirationDays": 730,
        }
        doc = generate_action_hcl("s3-lifecycle", params, "999888777666", "eu-west-1")
        rendered = doc.render()
        assert 'storage_class = "DEEP_ARCHIVE"' in rendered
        assert "days = 60" in rendered
        assert "days = 730" in rendered

    def test_assume_role_in_provider(self, rendered_hcl):
        """Provider block must include assume_role with correct role ARN."""
        assert "assume_role" in rendered_hcl
        assert "arn:aws:iam::123456789012:role/SlashMyBill-123456789012" in rendered_hcl
