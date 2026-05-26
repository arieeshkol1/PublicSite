"""Unit tests for the Terraform identifier converter module.

Tests cover various AWS resource ID formats, edge cases, and the
deterministic behavior of to_terraform_identifier().
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hcl_generator.identifiers import to_terraform_identifier, is_valid_terraform_identifier


class TestToTerraformIdentifier:
    """Tests for to_terraform_identifier() function."""

    # --- Standard AWS resource ID formats ---

    def test_ec2_instance_id(self):
        """EC2 instance IDs like i-0abc123def should pass through unchanged."""
        result = to_terraform_identifier('i-0abc123def')
        assert result == 'i-0abc123def'

    def test_ebs_volume_id(self):
        """EBS volume IDs like vol-0abc123 should pass through unchanged."""
        result = to_terraform_identifier('vol-0abc123')
        assert result == 'vol-0abc123'

    def test_eip_allocation_id(self):
        """EIP allocation IDs like eipalloc-0abc123 should pass through."""
        result = to_terraform_identifier('eipalloc-0abc123')
        assert result == 'eipalloc-0abc123'

    def test_security_group_id(self):
        """Security group IDs like sg-0abc123 should pass through."""
        result = to_terraform_identifier('sg-0abc123')
        assert result == 'sg-0abc123'

    def test_subnet_id(self):
        """Subnet IDs like subnet-0abc123 should pass through."""
        result = to_terraform_identifier('subnet-0abc123')
        assert result == 'subnet-0abc123'

    def test_vpc_id(self):
        """VPC IDs like vpc-0abc123 should pass through."""
        result = to_terraform_identifier('vpc-0abc123')
        assert result == 'vpc-0abc123'

    def test_nat_gateway_id(self):
        """NAT gateway IDs like nat-0abc123 should pass through."""
        result = to_terraform_identifier('nat-0abc123')
        assert result == 'nat-0abc123'

    def test_load_balancer_arn_style(self):
        """Load balancer ARN-style IDs get colons/slashes converted."""
        result = to_terraform_identifier(
            'arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-lb/abc123'
        )
        assert result == 'arn_aws_elasticloadbalancing_us-east-1_123456789012_loadbalancer_app_my-lb_abc123'

    def test_s3_bucket_name(self):
        """S3 bucket names with dots get dots converted to underscores."""
        result = to_terraform_identifier('my.bucket.name')
        assert result == 'my_bucket_name'

    def test_s3_bucket_name_simple(self):
        """Simple S3 bucket names with hyphens pass through."""
        result = to_terraform_identifier('my-bucket-name')
        assert result == 'my-bucket-name'

    # --- Case handling ---

    def test_uppercase_converted_to_lowercase(self):
        """Uppercase characters are converted to lowercase."""
        result = to_terraform_identifier('MyResource-ABC123')
        assert result == 'myresource-abc123'

    def test_mixed_case_instance_id(self):
        """Mixed case IDs are lowercased."""
        result = to_terraform_identifier('I-0ABC123DEF')
        assert result == 'i-0abc123def'

    # --- Special characters ---

    def test_colons_replaced_with_underscores(self):
        """Colons in ARNs are replaced with underscores."""
        result = to_terraform_identifier('arn:aws:ec2:us-east-1:123456789012:instance/i-0abc')
        assert result == 'arn_aws_ec2_us-east-1_123456789012_instance_i-0abc'

    def test_slashes_replaced_with_underscores(self):
        """Forward slashes are replaced with underscores."""
        result = to_terraform_identifier('path/to/resource')
        assert result == 'path_to_resource'

    def test_dots_replaced_with_underscores(self):
        """Dots are replaced with underscores."""
        result = to_terraform_identifier('my.resource.name')
        assert result == 'my_resource_name'

    def test_consecutive_special_chars_collapsed(self):
        """Multiple consecutive special characters collapse to single underscore."""
        result = to_terraform_identifier('a::b//c..d')
        assert result == 'a_b_c_d'

    # --- Leading character handling ---

    def test_leading_digit_gets_prefix(self):
        """IDs starting with a digit get an 'r' prefix."""
        result = to_terraform_identifier('123abc')
        assert result == 'r123abc'

    def test_leading_hyphen_stripped(self):
        """Leading hyphens are stripped, and prefix added if needed."""
        result = to_terraform_identifier('-abc123')
        assert result == 'abc123'

    def test_leading_underscore_stripped(self):
        """Leading underscores are stripped."""
        result = to_terraform_identifier('_abc123')
        assert result == 'abc123'

    def test_leading_special_char_handled(self):
        """Leading special characters are replaced and handled."""
        result = to_terraform_identifier('/resource/name')
        assert result == 'resource_name'

    # --- Trailing character handling ---

    def test_trailing_underscore_stripped(self):
        """Trailing underscores are stripped."""
        result = to_terraform_identifier('abc123_')
        assert result == 'abc123'

    def test_trailing_hyphen_stripped(self):
        """Trailing hyphens are stripped."""
        result = to_terraform_identifier('abc123-')
        assert result == 'abc123'

    # --- Determinism ---

    def test_deterministic_output(self):
        """Same input always produces same output."""
        input_id = 'i-0abc123def456'
        result1 = to_terraform_identifier(input_id)
        result2 = to_terraform_identifier(input_id)
        result3 = to_terraform_identifier(input_id)
        assert result1 == result2 == result3

    def test_deterministic_complex_input(self):
        """Complex inputs produce deterministic results."""
        input_id = 'arn:aws:ec2:us-east-1:123456789012:volume/vol-0abc'
        result1 = to_terraform_identifier(input_id)
        result2 = to_terraform_identifier(input_id)
        assert result1 == result2

    # --- Edge cases ---

    def test_empty_string_raises_error(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            to_terraform_identifier('')

    def test_none_raises_error(self):
        """None raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            to_terraform_identifier(None)

    def test_single_letter(self):
        """Single lowercase letter is valid."""
        result = to_terraform_identifier('a')
        assert result == 'a'

    def test_single_digit_gets_prefix(self):
        """Single digit gets 'r' prefix."""
        result = to_terraform_identifier('5')
        assert result == 'r5'

    def test_all_special_chars_fallback(self):
        """String of only special characters uses fallback."""
        result = to_terraform_identifier('::://')
        assert result == 'res'

    def test_long_aws_arn(self):
        """Long ARNs are converted correctly."""
        arn = 'arn:aws:elasticloadbalancing:eu-west-1:999888777666:targetgroup/my-targets/abc123def456'
        result = to_terraform_identifier(arn)
        assert is_valid_terraform_identifier(result)
        assert 'my-targets' in result

    # --- Output validity ---

    def test_output_always_valid_terraform_id_ec2(self):
        """Output for EC2 IDs is always a valid Terraform identifier."""
        ids = ['i-0abc123', 'i-1234567890abcdef0', 'i-0a1b2c3d4e5f6']
        for aws_id in ids:
            result = to_terraform_identifier(aws_id)
            assert is_valid_terraform_identifier(result), f"Invalid for input: {aws_id}"

    def test_output_always_valid_terraform_id_various(self):
        """Output for various AWS resource types is always valid."""
        ids = [
            'vol-0abc123',
            'eipalloc-0abc123',
            'sg-0abc123',
            'subnet-0abc123',
            'vpc-0abc123',
            'igw-0abc123',
            'rtb-0abc123',
            'acl-0abc123',
            'eni-0abc123',
        ]
        for aws_id in ids:
            result = to_terraform_identifier(aws_id)
            assert is_valid_terraform_identifier(result), f"Invalid for input: {aws_id}"


class TestIsValidTerraformIdentifier:
    """Tests for is_valid_terraform_identifier() helper."""

    def test_valid_simple(self):
        assert is_valid_terraform_identifier('abc') is True

    def test_valid_with_digits(self):
        assert is_valid_terraform_identifier('abc123') is True

    def test_valid_with_hyphens(self):
        assert is_valid_terraform_identifier('my-resource') is True

    def test_valid_with_underscores(self):
        assert is_valid_terraform_identifier('my_resource') is True

    def test_valid_complex(self):
        assert is_valid_terraform_identifier('i-0abc123def') is True

    def test_invalid_starts_with_digit(self):
        assert is_valid_terraform_identifier('123abc') is False

    def test_invalid_starts_with_hyphen(self):
        assert is_valid_terraform_identifier('-abc') is False

    def test_invalid_starts_with_underscore(self):
        assert is_valid_terraform_identifier('_abc') is False

    def test_invalid_uppercase(self):
        assert is_valid_terraform_identifier('Abc') is False

    def test_invalid_special_chars(self):
        assert is_valid_terraform_identifier('a:b') is False

    def test_invalid_empty(self):
        assert is_valid_terraform_identifier('') is False

    def test_invalid_spaces(self):
        assert is_valid_terraform_identifier('a b') is False
