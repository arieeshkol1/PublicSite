"""Unit tests for the AWS client module (hcl_generator/aws_client.py).

Tests use unittest.mock.patch to mock boto3 calls and verify:
- assume_cross_account_role calls STS with correct parameters
- fetch_ebs_volume_attributes returns correct format
- fetch_eip_attributes returns correct format
- fetch_load_balancer_attributes returns correct format for ALB and Classic
- Error handling for API failures
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from hcl_generator.aws_client import (
    AccessDeniedError,
    AWSClientError,
    AssumeRoleError,
    ResourceNotFoundError,
    assume_cross_account_role,
    fetch_ebs_volume_attributes,
    fetch_eip_attributes,
    fetch_load_balancer_attributes,
)


class TestAssumeRole:
    """Tests for assume_cross_account_role."""

    @patch("hcl_generator.aws_client.boto3.client")
    def test_calls_sts_with_correct_parameters(self, mock_boto_client):
        """STS AssumeRole is called with the correct role ARN and ExternalId."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
                "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "SessionToken": "FwoGZXIvYXdzEBYaDH...",
            }
        }

        account_id = "123456789012"
        member_email = "user@example.com"
        expected_external_id = hashlib.sha256(member_email.encode("utf-8")).hexdigest()

        assume_cross_account_role(account_id, member_email)

        mock_boto_client.assert_called_once_with("sts")
        mock_sts.assume_role.assert_called_once_with(
            RoleArn=f"arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}",
            RoleSessionName="SlashMyBillTerraformGen",
            ExternalId=expected_external_id,
        )

    @patch("hcl_generator.aws_client.boto3.Session")
    @patch("hcl_generator.aws_client.boto3.client")
    def test_returns_session_with_assumed_credentials(self, mock_boto_client, mock_session_cls):
        """Returns a boto3 Session configured with the assumed role credentials."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKID_ASSUMED",
                "SecretAccessKey": "SECRET_ASSUMED",
                "SessionToken": "TOKEN_ASSUMED",
            }
        }

        assume_cross_account_role("123456789012", "user@example.com")

        mock_session_cls.assert_called_once_with(
            aws_access_key_id="AKID_ASSUMED",
            aws_secret_access_key="SECRET_ASSUMED",
            aws_session_token="TOKEN_ASSUMED",
        )

    @patch("hcl_generator.aws_client.boto3.client")
    def test_raises_assume_role_error_on_client_error(self, mock_boto_client):
        """Raises AssumeRoleError when STS returns a ClientError."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "AssumeRole",
        )

        with pytest.raises(AssumeRoleError, match="Cannot access account 123456789012"):
            assume_cross_account_role("123456789012", "user@example.com")

    @patch("hcl_generator.aws_client.boto3.client")
    def test_error_includes_account_id(self, mock_boto_client):
        """AssumeRoleError includes the account_id attribute."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "MalformedPolicyDocument", "Message": "Bad policy"}},
            "AssumeRole",
        )

        with pytest.raises(AssumeRoleError) as exc_info:
            assume_cross_account_role("987654321098", "test@test.com")

        assert exc_info.value.account_id == "987654321098"

    @patch("hcl_generator.aws_client.boto3.client")
    def test_external_id_is_sha256_of_email(self, mock_boto_client):
        """ExternalId is the SHA-256 hex digest of the member email."""
        mock_sts = MagicMock()
        mock_boto_client.return_value = mock_sts
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "ST",
            }
        }

        email = "admin@company.org"
        assume_cross_account_role("111222333444", email)

        call_kwargs = mock_sts.assume_role.call_args[1]
        expected_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        assert call_kwargs["ExternalId"] == expected_hash


class TestFetchEbsVolumeAttributes:
    """Tests for fetch_ebs_volume_attributes."""

    def _make_session(self, describe_volumes_response=None, side_effect=None):
        """Create a mock session with a mocked EC2 client."""
        session = MagicMock()
        ec2_client = MagicMock()
        session.client.return_value = ec2_client
        if side_effect:
            ec2_client.describe_volumes.side_effect = side_effect
        else:
            ec2_client.describe_volumes.return_value = describe_volumes_response
        return session, ec2_client

    def test_returns_correct_format(self):
        """Returns a dict with all expected keys in the correct format."""
        session, _ = self._make_session(
            describe_volumes_response={
                "Volumes": [
                    {
                        "VolumeId": "vol-0abc123def456789a",
                        "Size": 100,
                        "VolumeType": "gp3",
                        "AvailabilityZone": "us-east-1a",
                        "Tags": [
                            {"Key": "Name", "Value": "my-volume"},
                            {"Key": "Env", "Value": "prod"},
                        ],
                        "Iops": 3000,
                        "Throughput": 125,
                    }
                ]
            }
        )

        result = fetch_ebs_volume_attributes(session, "vol-0abc123def456789a", "us-east-1")

        assert result == {
            "volume_id": "vol-0abc123def456789a",
            "size": 100,
            "volume_type": "gp3",
            "availability_zone": "us-east-1a",
            "tags": {"Name": "my-volume", "Env": "prod"},
            "iops": 3000,
            "throughput": 125,
        }

    def test_omits_iops_and_throughput_when_not_present(self):
        """Omits iops and throughput keys when not in the API response."""
        session, _ = self._make_session(
            describe_volumes_response={
                "Volumes": [
                    {
                        "VolumeId": "vol-abc",
                        "Size": 50,
                        "VolumeType": "gp2",
                        "AvailabilityZone": "eu-west-1b",
                        "Tags": [],
                    }
                ]
            }
        )

        result = fetch_ebs_volume_attributes(session, "vol-abc", "eu-west-1")

        assert "iops" not in result
        assert "throughput" not in result
        assert result["volume_id"] == "vol-abc"
        assert result["size"] == 50
        assert result["tags"] == {}

    def test_handles_no_tags(self):
        """Returns empty tags dict when volume has no Tags key."""
        session, _ = self._make_session(
            describe_volumes_response={
                "Volumes": [
                    {
                        "VolumeId": "vol-notags",
                        "Size": 20,
                        "VolumeType": "standard",
                        "AvailabilityZone": "us-west-2a",
                    }
                ]
            }
        )

        result = fetch_ebs_volume_attributes(session, "vol-notags", "us-west-2")
        assert result["tags"] == {}

    def test_raises_resource_not_found_for_invalid_volume(self):
        """Raises ResourceNotFoundError when volume does not exist."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "InvalidVolume.NotFound", "Message": "Volume not found"}},
                "DescribeVolumes",
            )
        )

        with pytest.raises(ResourceNotFoundError, match="vol-nonexistent"):
            fetch_ebs_volume_attributes(session, "vol-nonexistent", "us-east-1")

    def test_raises_access_denied_error(self):
        """Raises AccessDeniedError when caller lacks permissions."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "UnauthorizedOperation", "Message": "Not authorized"}},
                "DescribeVolumes",
            )
        )

        with pytest.raises(AccessDeniedError, match="Access denied"):
            fetch_ebs_volume_attributes(session, "vol-denied", "us-east-1")

    def test_raises_aws_client_error_for_unknown_errors(self):
        """Raises AWSClientError for unexpected API errors."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "InternalError", "Message": "Something broke"}},
                "DescribeVolumes",
            )
        )

        with pytest.raises(AWSClientError, match="Failed to describe volume"):
            fetch_ebs_volume_attributes(session, "vol-error", "us-east-1")

    def test_raises_resource_not_found_for_empty_response(self):
        """Raises ResourceNotFoundError when API returns empty Volumes list."""
        session, _ = self._make_session(
            describe_volumes_response={"Volumes": []}
        )

        with pytest.raises(ResourceNotFoundError, match="not found"):
            fetch_ebs_volume_attributes(session, "vol-empty", "us-east-1")

    def test_calls_ec2_with_correct_region(self):
        """EC2 client is created with the specified region."""
        session, _ = self._make_session(
            describe_volumes_response={
                "Volumes": [
                    {
                        "VolumeId": "vol-region",
                        "Size": 10,
                        "VolumeType": "gp2",
                        "AvailabilityZone": "ap-southeast-1a",
                    }
                ]
            }
        )

        fetch_ebs_volume_attributes(session, "vol-region", "ap-southeast-1")
        session.client.assert_called_once_with("ec2", region_name="ap-southeast-1")


class TestFetchEipAttributes:
    """Tests for fetch_eip_attributes."""

    def _make_session(self, describe_addresses_response=None, side_effect=None):
        """Create a mock session with a mocked EC2 client."""
        session = MagicMock()
        ec2_client = MagicMock()
        session.client.return_value = ec2_client
        if side_effect:
            ec2_client.describe_addresses.side_effect = side_effect
        else:
            ec2_client.describe_addresses.return_value = describe_addresses_response
        return session, ec2_client

    def test_returns_correct_format(self):
        """Returns a dict with all expected keys in the correct format."""
        session, _ = self._make_session(
            describe_addresses_response={
                "Addresses": [
                    {
                        "AllocationId": "eipalloc-0abc123",
                        "PublicIp": "54.123.45.67",
                        "Domain": "vpc",
                        "Tags": [
                            {"Key": "Name", "Value": "my-eip"},
                        ],
                    }
                ]
            }
        )

        result = fetch_eip_attributes(session, "eipalloc-0abc123", "us-east-1")

        assert result == {
            "allocation_id": "eipalloc-0abc123",
            "public_ip": "54.123.45.67",
            "domain": "vpc",
            "tags": {"Name": "my-eip"},
        }

    def test_handles_no_tags(self):
        """Returns empty tags dict when EIP has no tags."""
        session, _ = self._make_session(
            describe_addresses_response={
                "Addresses": [
                    {
                        "AllocationId": "eipalloc-notags",
                        "PublicIp": "1.2.3.4",
                        "Domain": "vpc",
                    }
                ]
            }
        )

        result = fetch_eip_attributes(session, "eipalloc-notags", "us-east-1")
        assert result["tags"] == {}

    def test_raises_resource_not_found(self):
        """Raises ResourceNotFoundError when EIP does not exist."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "InvalidAllocationID.NotFound", "Message": "Not found"}},
                "DescribeAddresses",
            )
        )

        with pytest.raises(ResourceNotFoundError, match="eipalloc-gone"):
            fetch_eip_attributes(session, "eipalloc-gone", "us-east-1")

    def test_raises_access_denied_error(self):
        """Raises AccessDeniedError when caller lacks permissions."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
                "DescribeAddresses",
            )
        )

        with pytest.raises(AccessDeniedError, match="Access denied"):
            fetch_eip_attributes(session, "eipalloc-denied", "us-east-1")

    def test_raises_aws_client_error_for_unknown_errors(self):
        """Raises AWSClientError for unexpected API errors."""
        session, _ = self._make_session(
            side_effect=ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "Try later"}},
                "DescribeAddresses",
            )
        )

        with pytest.raises(AWSClientError, match="Failed to describe EIP"):
            fetch_eip_attributes(session, "eipalloc-err", "us-east-1")

    def test_raises_resource_not_found_for_empty_response(self):
        """Raises ResourceNotFoundError when API returns empty Addresses list."""
        session, _ = self._make_session(
            describe_addresses_response={"Addresses": []}
        )

        with pytest.raises(ResourceNotFoundError, match="not found"):
            fetch_eip_attributes(session, "eipalloc-empty", "us-east-1")

    def test_defaults_domain_to_vpc(self):
        """Defaults domain to 'vpc' when not present in response."""
        session, _ = self._make_session(
            describe_addresses_response={
                "Addresses": [
                    {
                        "AllocationId": "eipalloc-nodomain",
                        "PublicIp": "5.6.7.8",
                    }
                ]
            }
        )

        result = fetch_eip_attributes(session, "eipalloc-nodomain", "us-east-1")
        assert result["domain"] == "vpc"


class TestFetchLoadBalancerAttributes:
    """Tests for fetch_load_balancer_attributes."""

    def _make_elbv2_session(self, describe_response=None, tags_response=None, side_effect=None):
        """Create a mock session with a mocked ELBv2 client."""
        session = MagicMock()
        elbv2_client = MagicMock()
        session.client.return_value = elbv2_client
        if side_effect:
            elbv2_client.describe_load_balancers.side_effect = side_effect
        else:
            elbv2_client.describe_load_balancers.return_value = describe_response
        if tags_response:
            elbv2_client.describe_tags.return_value = tags_response
        else:
            elbv2_client.describe_tags.return_value = {"TagDescriptions": []}
        return session, elbv2_client

    def test_alb_by_arn_returns_correct_format(self):
        """ALB fetched by ARN returns correct attribute format."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123"
        session, _ = self._make_elbv2_session(
            describe_response={
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": arn,
                        "LoadBalancerName": "my-alb",
                        "Type": "application",
                        "AvailabilityZones": [
                            {"SubnetId": "subnet-abc123", "ZoneName": "us-east-1a"},
                            {"SubnetId": "subnet-def456", "ZoneName": "us-east-1b"},
                        ],
                        "SecurityGroups": ["sg-abc123"],
                    }
                ]
            },
            tags_response={
                "TagDescriptions": [
                    {
                        "ResourceArn": arn,
                        "Tags": [{"Key": "Name", "Value": "my-alb-tag"}],
                    }
                ]
            },
        )

        result = fetch_load_balancer_attributes(session, arn, "us-east-1")

        assert result == {
            "arn": arn,
            "name": "my-alb",
            "lb_type": "application",
            "subnets": ["subnet-abc123", "subnet-def456"],
            "security_groups": ["sg-abc123"],
            "tags": {"Name": "my-alb-tag"},
        }

    def test_nlb_by_arn_returns_network_type(self):
        """NLB fetched by ARN returns lb_type='network'."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/net/my-nlb/xyz789"
        session, _ = self._make_elbv2_session(
            describe_response={
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": arn,
                        "LoadBalancerName": "my-nlb",
                        "Type": "network",
                        "AvailabilityZones": [
                            {"SubnetId": "subnet-111", "ZoneName": "us-east-1a"},
                        ],
                        "SecurityGroups": [],
                    }
                ]
            },
        )

        result = fetch_load_balancer_attributes(session, arn, "us-east-1")

        assert result["lb_type"] == "network"
        assert result["name"] == "my-nlb"

    def test_classic_elb_by_name_returns_correct_format(self):
        """Classic ELB fetched by name returns correct attribute format."""
        session = MagicMock()
        elbv2_client = MagicMock()
        elb_client = MagicMock()

        # ELBv2 lookup by name fails (not found)
        elbv2_client.describe_load_balancers.side_effect = ClientError(
            {"Error": {"Code": "LoadBalancerNotFound", "Message": "Not found"}},
            "DescribeLoadBalancers",
        )

        # Classic ELB lookup succeeds
        elb_client.describe_load_balancers.return_value = {
            "LoadBalancerDescriptions": [
                {
                    "LoadBalancerName": "my-classic-elb",
                    "Subnets": ["subnet-aaa", "subnet-bbb"],
                    "SecurityGroups": ["sg-classic"],
                }
            ]
        }
        elb_client.describe_tags.return_value = {
            "TagDescriptions": [
                {
                    "LoadBalancerName": "my-classic-elb",
                    "Tags": [{"Key": "Team", "Value": "platform"}],
                }
            ]
        }

        def client_factory(service, **kwargs):
            if service == "elbv2":
                return elbv2_client
            elif service == "elb":
                return elb_client
            return MagicMock()

        session.client.side_effect = client_factory

        result = fetch_load_balancer_attributes(session, "my-classic-elb", "us-east-1")

        assert result == {
            "name": "my-classic-elb",
            "lb_type": "classic",
            "subnets": ["subnet-aaa", "subnet-bbb"],
            "security_groups": ["sg-classic"],
            "tags": {"Team": "platform"},
        }

    def test_raises_resource_not_found_for_arn(self):
        """Raises ResourceNotFoundError when ALB/NLB ARN is not found."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/gone/xyz"
        session, _ = self._make_elbv2_session(
            side_effect=ClientError(
                {"Error": {"Code": "LoadBalancerNotFound", "Message": "Not found"}},
                "DescribeLoadBalancers",
            )
        )

        with pytest.raises(ResourceNotFoundError, match="not found"):
            fetch_load_balancer_attributes(session, arn, "us-east-1")

    def test_raises_access_denied_for_arn(self):
        """Raises AccessDeniedError when access is denied for ALB/NLB."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/denied/xyz"
        session, _ = self._make_elbv2_session(
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
                "DescribeLoadBalancers",
            )
        )

        with pytest.raises(AccessDeniedError, match="Access denied"):
            fetch_load_balancer_attributes(session, arn, "us-east-1")

    def test_raises_resource_not_found_for_classic_name(self):
        """Raises ResourceNotFoundError when both ELBv2 and Classic fail."""
        session = MagicMock()
        elbv2_client = MagicMock()
        elb_client = MagicMock()

        # ELBv2 not found
        elbv2_client.describe_load_balancers.side_effect = ClientError(
            {"Error": {"Code": "LoadBalancerNotFound", "Message": "Not found"}},
            "DescribeLoadBalancers",
        )
        # Classic not found
        elb_client.describe_load_balancers.side_effect = ClientError(
            {"Error": {"Code": "LoadBalancerNotFound", "Message": "Not found"}},
            "DescribeLoadBalancers",
        )

        def client_factory(service, **kwargs):
            if service == "elbv2":
                return elbv2_client
            elif service == "elb":
                return elb_client
            return MagicMock()

        session.client.side_effect = client_factory

        with pytest.raises(ResourceNotFoundError, match="not found"):
            fetch_load_balancer_attributes(session, "nonexistent-lb", "us-east-1")

    def test_alb_with_empty_security_groups(self):
        """ALB with no security groups returns empty list."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/no-sg/abc"
        session, _ = self._make_elbv2_session(
            describe_response={
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": arn,
                        "LoadBalancerName": "no-sg",
                        "Type": "application",
                        "AvailabilityZones": [],
                        "SecurityGroups": [],
                    }
                ]
            },
        )

        result = fetch_load_balancer_attributes(session, arn, "us-east-1")
        assert result["security_groups"] == []
        assert result["subnets"] == []

    def test_tags_failure_does_not_raise(self):
        """If tag fetching fails, the function still returns with empty tags."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/tag-fail/abc"
        session = MagicMock()
        elbv2_client = MagicMock()
        session.client.return_value = elbv2_client

        elbv2_client.describe_load_balancers.return_value = {
            "LoadBalancers": [
                {
                    "LoadBalancerArn": arn,
                    "LoadBalancerName": "tag-fail",
                    "Type": "application",
                    "AvailabilityZones": [],
                    "SecurityGroups": [],
                }
            ]
        }
        elbv2_client.describe_tags.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "No tag access"}},
            "DescribeTags",
        )

        result = fetch_load_balancer_attributes(session, arn, "us-east-1")
        assert result["tags"] == {}
        assert result["name"] == "tag-fail"
