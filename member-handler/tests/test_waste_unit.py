"""Unit tests for the waste action HCL generator module.

Tests all three waste types: EBS volume, Elastic IP, and load balancer.
Validates resource blocks, import blocks, workflow comments, and attribute handling.
"""

import pytest

from hcl_generator.waste import (
    SUPPORTED_WASTE_TYPES,
    generate_waste_action_hcl,
)


class TestGenerateWasteActionHcl:
    """Tests for the generate_waste_action_hcl dispatch function."""

    def test_unsupported_waste_type_raises_value_error(self):
        """Unsupported waste types raise ValueError with descriptive message."""
        with pytest.raises(ValueError, match="Unsupported waste type"):
            generate_waste_action_hcl(
                waste_type="unknown-type",
                resource_attributes={},
                account_id="123456789012",
                region="us-east-1",
            )

    def test_supported_waste_types_set(self):
        """All expected waste types are in the supported set."""
        assert "ebs-volume" in SUPPORTED_WASTE_TYPES
        assert "elastic-ip" in SUPPORTED_WASTE_TYPES
        assert "load-balancer" in SUPPORTED_WASTE_TYPES
        assert len(SUPPORTED_WASTE_TYPES) == 3


class TestEbsVolumeWaste:
    """Tests for EBS volume waste action generation."""

    def setup_method(self):
        """Set up common test attributes for EBS volume tests."""
        self.resource_attributes = {
            "volume_id": "vol-0abc123def456789a",
            "size": 100,
            "volume_type": "gp3",
            "availability_zone": "us-east-1a",
            "tags": {"Name": "unused-volume", "Environment": "dev"},
        }
        self.account_id = "123456789012"
        self.region = "us-east-1"

    def test_generates_valid_hcl_document(self):
        """EBS volume waste action produces a non-empty HCL document."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert len(rendered) > 0

    def test_contains_aws_ebs_volume_resource(self):
        """Generated HCL contains an aws_ebs_volume resource block."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert 'resource "aws_ebs_volume"' in rendered

    def test_contains_import_block_with_volume_id(self):
        """Generated HCL contains an import block with the volume ID."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "import {" in rendered
        assert "vol-0abc123def456789a" in rendered

    def test_contains_resource_attributes(self):
        """Generated HCL includes size, type, and availability_zone attributes."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "size = 100" in rendered
        assert 'type = "gp3"' in rendered
        assert 'availability_zone = "us-east-1a"' in rendered

    def test_contains_tags(self):
        """Generated HCL includes tags when provided."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "unused-volume" in rendered
        assert "Environment" in rendered

    def test_contains_optional_iops(self):
        """Generated HCL includes iops when provided."""
        attrs = {**self.resource_attributes, "iops": 3000}
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=attrs,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "iops = 3000" in rendered

    def test_contains_optional_throughput(self):
        """Generated HCL includes throughput when provided."""
        attrs = {**self.resource_attributes, "throughput": 125}
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=attrs,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "throughput = 125" in rendered

    def test_omits_iops_when_not_provided(self):
        """Generated HCL omits iops when not in resource_attributes."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "iops" not in rendered

    def test_contains_workflow_comment(self):
        """Generated HCL contains the import-then-destroy workflow comment."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "Import-then-Destroy Workflow" in rendered
        assert "terraform init" in rendered
        assert "terraform plan" in rendered
        assert "terraform apply" in rendered
        assert "Remove the resource block" in rendered

    def test_contains_provider_block(self):
        """Generated HCL contains a provider block with assume_role."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert 'provider "aws"' in rendered
        assert "assume_role" in rendered
        assert self.account_id in rendered

    def test_contains_header_comment(self):
        """Generated HCL contains the standard header comment elements."""
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "Generated by SlashMyBill" in rendered
        assert "Action:" in rendered
        assert "Account: 123456789012" in rendered
        assert "WARNING:" in rendered


class TestElasticIpWaste:
    """Tests for Elastic IP waste action generation."""

    def setup_method(self):
        """Set up common test attributes for EIP tests."""
        self.resource_attributes = {
            "allocation_id": "eipalloc-0abc123def456789a",
            "public_ip": "54.123.45.67",
            "domain": "vpc",
            "tags": {"Name": "unused-eip"},
        }
        self.account_id = "987654321098"
        self.region = "eu-west-1"

    def test_generates_valid_hcl_document(self):
        """EIP waste action produces a non-empty HCL document."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert len(rendered) > 0

    def test_contains_aws_eip_resource(self):
        """Generated HCL contains an aws_eip resource block."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert 'resource "aws_eip"' in rendered

    def test_contains_import_block_with_allocation_id(self):
        """Generated HCL contains an import block with the allocation ID."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "import {" in rendered
        assert "eipalloc-0abc123def456789a" in rendered

    def test_contains_domain_attribute(self):
        """Generated HCL includes the domain attribute."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert 'domain = "vpc"' in rendered

    def test_contains_tags(self):
        """Generated HCL includes tags when provided."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "unused-eip" in rendered

    def test_no_tags_when_empty(self):
        """Generated HCL omits tags block when tags dict is empty."""
        attrs = {**self.resource_attributes, "tags": {}}
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=attrs,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "tags" not in rendered

    def test_contains_workflow_comment(self):
        """Generated HCL contains the import-then-destroy workflow comment."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert "Import-then-Destroy Workflow" in rendered
        assert "terraform init" in rendered

    def test_contains_provider_with_correct_region(self):
        """Generated HCL contains provider block with the specified region."""
        doc = generate_waste_action_hcl(
            waste_type="elastic-ip",
            resource_attributes=self.resource_attributes,
            account_id=self.account_id,
            region=self.region,
        )
        rendered = doc.render()
        assert 'region = "eu-west-1"' in rendered


class TestLoadBalancerWaste:
    """Tests for load balancer waste action generation."""

    def test_alb_generates_aws_lb_resource(self):
        """ALB waste action generates an aws_lb resource block."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123",
            "name": "my-alb",
            "lb_type": "application",
            "subnets": ["subnet-abc123", "subnet-def456"],
            "security_groups": ["sg-abc123"],
            "tags": {"Name": "idle-alb"},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert 'resource "aws_lb"' in rendered
        assert 'load_balancer_type = "application"' in rendered

    def test_alb_import_uses_arn(self):
        """ALB import block uses the ARN as the import ID."""
        arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123"
        attrs = {
            "arn": arn,
            "name": "my-alb",
            "lb_type": "application",
            "subnets": ["subnet-abc123"],
            "security_groups": [],
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "import {" in rendered
        assert arn in rendered

    def test_nlb_generates_aws_lb_resource(self):
        """NLB waste action generates an aws_lb resource with network type."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/net/my-nlb/abc123",
            "name": "my-nlb",
            "lb_type": "network",
            "subnets": ["subnet-abc123"],
            "security_groups": [],
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert 'resource "aws_lb"' in rendered
        assert 'load_balancer_type = "network"' in rendered

    def test_classic_elb_generates_aws_elb_resource(self):
        """Classic ELB waste action generates an aws_elb resource block."""
        attrs = {
            "name": "my-classic-elb",
            "lb_type": "classic",
            "tags": {"Name": "old-elb"},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert 'resource "aws_elb"' in rendered
        assert 'name = "my-classic-elb"' in rendered

    def test_classic_elb_import_uses_name(self):
        """Classic ELB import block uses the name as the import ID."""
        attrs = {
            "name": "my-classic-elb",
            "lb_type": "classic",
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "import {" in rendered
        assert "my-classic-elb" in rendered

    def test_alb_includes_subnets(self):
        """ALB resource includes subnets when provided."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123",
            "name": "my-alb",
            "lb_type": "application",
            "subnets": ["subnet-abc123", "subnet-def456"],
            "security_groups": [],
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "subnet-abc123" in rendered
        assert "subnet-def456" in rendered

    def test_alb_includes_security_groups(self):
        """ALB resource includes security_groups when provided."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123",
            "name": "my-alb",
            "lb_type": "application",
            "subnets": ["subnet-abc123"],
            "security_groups": ["sg-abc123", "sg-def456"],
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "sg-abc123" in rendered
        assert "sg-def456" in rendered

    def test_contains_workflow_comment(self):
        """Load balancer waste action contains the workflow comment."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123",
            "name": "my-alb",
            "lb_type": "application",
            "subnets": [],
            "security_groups": [],
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "Import-then-Destroy Workflow" in rendered
        assert "terraform init" in rendered
        assert "terraform plan" in rendered
        assert "terraform apply" in rendered
        assert "Remove the resource block" in rendered

    def test_contains_tags_for_alb(self):
        """ALB resource includes tags when provided."""
        attrs = {
            "arn": "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/abc123",
            "name": "my-alb",
            "lb_type": "application",
            "subnets": [],
            "security_groups": [],
            "tags": {"Name": "idle-alb", "Team": "platform"},
        }
        doc = generate_waste_action_hcl(
            waste_type="load-balancer",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        assert "idle-alb" in rendered
        assert "platform" in rendered


class TestWorkflowComment:
    """Tests specifically for the workflow comment content."""

    def test_workflow_has_all_five_steps(self):
        """The workflow comment includes all 5 steps of the import-then-destroy process."""
        attrs = {
            "volume_id": "vol-abc123",
            "size": 50,
            "volume_type": "gp2",
            "availability_zone": "us-east-1a",
            "tags": {},
        }
        doc = generate_waste_action_hcl(
            waste_type="ebs-volume",
            resource_attributes=attrs,
            account_id="123456789012",
            region="us-east-1",
        )
        rendered = doc.render()
        # Verify all 5 steps are present
        assert "1. terraform init" in rendered
        assert "2. terraform plan" in rendered
        assert "3. terraform apply" in rendered
        assert "4. Remove the resource block" in rendered
        assert "5. terraform apply" in rendered

    def test_workflow_comment_present_for_all_waste_types(self):
        """All waste types include the workflow comment."""
        test_cases = [
            ("ebs-volume", {"volume_id": "vol-abc", "size": 10, "volume_type": "gp2", "availability_zone": "us-east-1a"}),
            ("elastic-ip", {"allocation_id": "eipalloc-abc", "domain": "vpc"}),
            ("load-balancer", {"name": "my-lb", "lb_type": "application", "arn": "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/x/y"}),
        ]
        for waste_type, attrs in test_cases:
            doc = generate_waste_action_hcl(
                waste_type=waste_type,
                resource_attributes=attrs,
                account_id="123456789012",
                region="us-east-1",
            )
            rendered = doc.render()
            assert "Import-then-Destroy Workflow" in rendered, (
                f"Workflow comment missing for waste_type={waste_type}"
            )
