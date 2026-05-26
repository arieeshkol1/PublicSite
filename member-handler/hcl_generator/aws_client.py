"""AWS API integration for fetching current resource attributes.

Provides functions to assume a cross-account role into a customer account
and query EC2/EBS/ELB APIs to populate resource definitions for waste action
Terraform generation.

Usage:
    session = assume_cross_account_role(account_id, member_email)
    attrs = fetch_ebs_volume_attributes(session, volume_id, region)
"""

from __future__ import annotations

import hashlib
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSClientError(Exception):
    """Base exception for AWS client errors."""

    def __init__(self, message: str, account_id: str = "", resource_id: str = ""):
        self.account_id = account_id
        self.resource_id = resource_id
        super().__init__(message)


class AccessDeniedError(AWSClientError):
    """Raised when access to the customer account or resource is denied."""
    pass


class ResourceNotFoundError(AWSClientError):
    """Raised when the requested AWS resource does not exist."""
    pass


class AssumeRoleError(AWSClientError):
    """Raised when STS AssumeRole fails."""
    pass


def assume_cross_account_role(
    account_id: str,
    member_email: str,
) -> boto3.Session:
    """Assume the cross-account role in a customer account via STS.

    Uses the SlashMyBill-{accountId} role with ExternalId = SHA-256(memberEmail).

    Args:
        account_id: The 12-digit AWS account ID of the customer account.
        member_email: The member's email address used to compute the ExternalId.

    Returns:
        A boto3 Session configured with temporary credentials for the customer account.

    Raises:
        AssumeRoleError: If STS AssumeRole fails (role not found, access denied, etc.).
    """
    role_arn = f"arn:aws:iam::{account_id}:role/SlashMyBill-{account_id}"
    external_id = hashlib.sha256(member_email.encode("utf-8")).hexdigest()

    sts_client = boto3.client("sts")
    try:
        assume_response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="SlashMyBillTerraformGen",
            ExternalId=external_id,
        )
        credentials = assume_response["Credentials"]
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        logger.error(
            "STS AssumeRole failed for account %s (role %s): %s - %s",
            account_id, role_arn, error_code, error_msg,
        )
        raise AssumeRoleError(
            f"Cannot access account {account_id}: {error_code} - {error_msg}",
            account_id=account_id,
        ) from e

    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )


def fetch_ebs_volume_attributes(
    session: boto3.Session,
    volume_id: str,
    region: str,
) -> dict:
    """Fetch EBS volume attributes from the customer account.

    Calls EC2 DescribeVolumes to get volume attributes needed for
    Terraform resource generation.

    Args:
        session: A boto3 Session with credentials for the customer account.
        volume_id: The EBS volume ID (e.g., "vol-0abc123def456789a").
        region: The AWS region where the volume resides.

    Returns:
        A dict with keys: volume_id, size, volume_type, availability_zone,
        tags (dict), iops (optional), throughput (optional).

    Raises:
        ResourceNotFoundError: If the volume does not exist.
        AccessDeniedError: If the caller lacks permission to describe the volume.
        AWSClientError: For other API failures.
    """
    ec2_client = session.client("ec2", region_name=region)

    try:
        response = ec2_client.describe_volumes(VolumeIds=[volume_id])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "InvalidVolume.NotFound":
            raise ResourceNotFoundError(
                f"EBS volume {volume_id} not found in region {region}",
                resource_id=volume_id,
            ) from e
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            raise AccessDeniedError(
                f"Access denied when describing volume {volume_id}: {error_msg}",
                resource_id=volume_id,
            ) from e
        raise AWSClientError(
            f"Failed to describe volume {volume_id}: {error_code} - {error_msg}",
            resource_id=volume_id,
        ) from e

    volumes = response.get("Volumes", [])
    if not volumes:
        raise ResourceNotFoundError(
            f"EBS volume {volume_id} not found in region {region}",
            resource_id=volume_id,
        )

    volume = volumes[0]

    # Convert AWS Tags list to dict
    tags = {}
    for tag in volume.get("Tags", []):
        tags[tag["Key"]] = tag["Value"]

    attrs: dict = {
        "volume_id": volume["VolumeId"],
        "size": volume["Size"],
        "volume_type": volume["VolumeType"],
        "availability_zone": volume["AvailabilityZone"],
        "tags": tags,
    }

    # Add optional attributes if present and meaningful
    if volume.get("Iops") is not None:
        attrs["iops"] = volume["Iops"]
    if volume.get("Throughput") is not None:
        attrs["throughput"] = volume["Throughput"]

    return attrs


def fetch_eip_attributes(
    session: boto3.Session,
    allocation_id: str,
    region: str,
) -> dict:
    """Fetch Elastic IP attributes from the customer account.

    Calls EC2 DescribeAddresses to get EIP attributes needed for
    Terraform resource generation.

    Args:
        session: A boto3 Session with credentials for the customer account.
        allocation_id: The EIP allocation ID (e.g., "eipalloc-0abc123def456789a").
        region: The AWS region where the EIP resides.

    Returns:
        A dict with keys: allocation_id, public_ip, domain, tags (dict).

    Raises:
        ResourceNotFoundError: If the EIP does not exist.
        AccessDeniedError: If the caller lacks permission to describe the address.
        AWSClientError: For other API failures.
    """
    ec2_client = session.client("ec2", region_name=region)

    try:
        response = ec2_client.describe_addresses(AllocationIds=[allocation_id])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "InvalidAllocationID.NotFound":
            raise ResourceNotFoundError(
                f"Elastic IP {allocation_id} not found in region {region}",
                resource_id=allocation_id,
            ) from e
        if error_code in ("UnauthorizedOperation", "AccessDenied"):
            raise AccessDeniedError(
                f"Access denied when describing EIP {allocation_id}: {error_msg}",
                resource_id=allocation_id,
            ) from e
        raise AWSClientError(
            f"Failed to describe EIP {allocation_id}: {error_code} - {error_msg}",
            resource_id=allocation_id,
        ) from e

    addresses = response.get("Addresses", [])
    if not addresses:
        raise ResourceNotFoundError(
            f"Elastic IP {allocation_id} not found in region {region}",
            resource_id=allocation_id,
        )

    address = addresses[0]

    # Convert AWS Tags list to dict
    tags = {}
    for tag in address.get("Tags", []):
        tags[tag["Key"]] = tag["Value"]

    return {
        "allocation_id": address["AllocationId"],
        "public_ip": address.get("PublicIp", ""),
        "domain": address.get("Domain", "vpc"),
        "tags": tags,
    }


def fetch_load_balancer_attributes(
    session: boto3.Session,
    resource_id: str,
    region: str,
) -> dict:
    """Fetch load balancer attributes from the customer account.

    Attempts ELBv2 DescribeLoadBalancers first (for ALB/NLB). If the resource_id
    is not an ARN (i.e., it's a plain name), falls back to Classic ELB
    DescribeLoadBalancers.

    Args:
        session: A boto3 Session with credentials for the customer account.
        resource_id: The load balancer ARN (for ALB/NLB) or name (for Classic).
        region: The AWS region where the load balancer resides.

    Returns:
        A dict with keys: arn (for ALB/NLB), name, lb_type, subnets (list),
        security_groups (list), tags (dict).

    Raises:
        ResourceNotFoundError: If the load balancer does not exist.
        AccessDeniedError: If the caller lacks permission.
        AWSClientError: For other API failures.
    """
    # Determine if this is an ARN (ALB/NLB) or a name (Classic)
    is_arn = resource_id.startswith("arn:")

    if is_arn:
        return _fetch_elbv2_attributes(session, resource_id, region)
    else:
        # Try ELBv2 by name first, fall back to Classic
        try:
            return _fetch_elbv2_by_name(session, resource_id, region)
        except ResourceNotFoundError:
            return _fetch_classic_elb_attributes(session, resource_id, region)


def _fetch_elbv2_attributes(
    session: boto3.Session,
    lb_arn: str,
    region: str,
) -> dict:
    """Fetch ALB/NLB attributes using ELBv2 API by ARN."""
    elbv2_client = session.client("elbv2", region_name=region)

    try:
        response = elbv2_client.describe_load_balancers(LoadBalancerArns=[lb_arn])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "LoadBalancerNotFound":
            raise ResourceNotFoundError(
                f"Load balancer {lb_arn} not found in region {region}",
                resource_id=lb_arn,
            ) from e
        if error_code in ("AccessDenied", "UnauthorizedOperation"):
            raise AccessDeniedError(
                f"Access denied when describing load balancer {lb_arn}: {error_msg}",
                resource_id=lb_arn,
            ) from e
        raise AWSClientError(
            f"Failed to describe load balancer {lb_arn}: {error_code} - {error_msg}",
            resource_id=lb_arn,
        ) from e

    lbs = response.get("LoadBalancers", [])
    if not lbs:
        raise ResourceNotFoundError(
            f"Load balancer {lb_arn} not found in region {region}",
            resource_id=lb_arn,
        )

    lb = lbs[0]

    # Fetch tags separately
    tags = _fetch_elbv2_tags(elbv2_client, lb_arn)

    return {
        "arn": lb["LoadBalancerArn"],
        "name": lb["LoadBalancerName"],
        "lb_type": lb.get("Type", "application"),
        "subnets": [az["SubnetId"] for az in lb.get("AvailabilityZones", []) if "SubnetId" in az],
        "security_groups": lb.get("SecurityGroups", []),
        "tags": tags,
    }


def _fetch_elbv2_by_name(
    session: boto3.Session,
    lb_name: str,
    region: str,
) -> dict:
    """Fetch ALB/NLB attributes using ELBv2 API by name."""
    elbv2_client = session.client("elbv2", region_name=region)

    try:
        response = elbv2_client.describe_load_balancers(Names=[lb_name])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "LoadBalancerNotFound":
            raise ResourceNotFoundError(
                f"Load balancer '{lb_name}' not found in region {region}",
                resource_id=lb_name,
            ) from e
        if error_code in ("AccessDenied", "UnauthorizedOperation"):
            raise AccessDeniedError(
                f"Access denied when describing load balancer '{lb_name}': {error_msg}",
                resource_id=lb_name,
            ) from e
        raise AWSClientError(
            f"Failed to describe load balancer '{lb_name}': {error_code} - {error_msg}",
            resource_id=lb_name,
        ) from e

    lbs = response.get("LoadBalancers", [])
    if not lbs:
        raise ResourceNotFoundError(
            f"Load balancer '{lb_name}' not found in region {region}",
            resource_id=lb_name,
        )

    lb = lbs[0]
    lb_arn = lb["LoadBalancerArn"]

    # Fetch tags separately
    tags = _fetch_elbv2_tags(elbv2_client, lb_arn)

    return {
        "arn": lb_arn,
        "name": lb["LoadBalancerName"],
        "lb_type": lb.get("Type", "application"),
        "subnets": [az["SubnetId"] for az in lb.get("AvailabilityZones", []) if "SubnetId" in az],
        "security_groups": lb.get("SecurityGroups", []),
        "tags": tags,
    }


def _fetch_elbv2_tags(elbv2_client, resource_arn: str) -> dict:
    """Fetch tags for an ELBv2 resource."""
    tags = {}
    try:
        tag_response = elbv2_client.describe_tags(ResourceArns=[resource_arn])
        for tag_desc in tag_response.get("TagDescriptions", []):
            for tag in tag_desc.get("Tags", []):
                tags[tag["Key"]] = tag["Value"]
    except ClientError:
        # Tags are optional; if we can't fetch them, continue without
        logger.warning("Failed to fetch tags for %s, continuing without tags", resource_arn)
    return tags


def _fetch_classic_elb_attributes(
    session: boto3.Session,
    lb_name: str,
    region: str,
) -> dict:
    """Fetch Classic ELB attributes using the ELB API."""
    elb_client = session.client("elb", region_name=region)

    try:
        response = elb_client.describe_load_balancers(LoadBalancerNames=[lb_name])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "LoadBalancerNotFound":
            raise ResourceNotFoundError(
                f"Classic load balancer '{lb_name}' not found in region {region}",
                resource_id=lb_name,
            ) from e
        if error_code in ("AccessDenied", "UnauthorizedOperation"):
            raise AccessDeniedError(
                f"Access denied when describing Classic ELB '{lb_name}': {error_msg}",
                resource_id=lb_name,
            ) from e
        raise AWSClientError(
            f"Failed to describe Classic ELB '{lb_name}': {error_code} - {error_msg}",
            resource_id=lb_name,
        ) from e

    lbs = response.get("LoadBalancerDescriptions", [])
    if not lbs:
        raise ResourceNotFoundError(
            f"Classic load balancer '{lb_name}' not found in region {region}",
            resource_id=lb_name,
        )

    lb = lbs[0]

    # Fetch tags for Classic ELB
    tags = {}
    try:
        tag_response = elb_client.describe_tags(LoadBalancerNames=[lb_name])
        for tag_desc in tag_response.get("TagDescriptions", []):
            for tag in tag_desc.get("Tags", []):
                tags[tag["Key"]] = tag["Value"]
    except ClientError:
        logger.warning("Failed to fetch tags for Classic ELB %s, continuing without tags", lb_name)

    return {
        "name": lb["LoadBalancerName"],
        "lb_type": "classic",
        "subnets": lb.get("Subnets", []),
        "security_groups": lb.get("SecurityGroups", []),
        "tags": tags,
    }
