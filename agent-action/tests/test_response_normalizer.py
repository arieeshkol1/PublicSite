"""Unit tests for response_normalizer.py — validates normalized response schemas."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from response_normalizer import (
    normalize_compute_response,
    normalize_cost_response,
    normalize_database_response,
    normalize_storage_response,
    normalize_object_storage_response,
)


class TestNormalizeComputeResponse:
    """Validate compute response normalization across providers."""

    def test_aws_ec2_response_normalizes_correctly(self):
        raw = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-1234567890abcdef0",
                            "InstanceType": "t3.medium",
                            "State": {"Name": "running", "Code": 16},
                            "Tags": [{"Key": "Name", "Value": "web-server"}],
                            "Placement": {"AvailabilityZone": "us-east-1a"},
                            "LaunchTime": "2024-01-15T10:30:00Z",
                        }
                    ]
                }
            ]
        }
        result = normalize_compute_response(raw, "aws")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "i-1234567890abcdef0"
        assert inst["instanceType"] == "t3.medium"
        assert inst["state"] == "running"
        assert inst["name"] == "web-server"
        assert inst["region"] == "us-east-1a"
        assert inst["launchTime"] == "2024-01-15T10:30:00Z"
        assert inst["providerMetadata"]["provider"] == "aws"
        assert inst["providerMetadata"]["nativeId"] == "i-1234567890abcdef0"

    def test_azure_vm_response_normalizes_correctly(self):
        raw = {
            "value": [
                {
                    "id": "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
                    "name": "vm-1",
                    "location": "eastus",
                    "properties": {
                        "hardwareProfile": {"vmSize": "Standard_B2s"},
                        "provisioningState": "Succeeded",
                        "timeCreated": "2024-02-01T08:00:00Z",
                    },
                }
            ]
        }
        result = normalize_compute_response(raw, "azure")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
        assert inst["instanceType"] == "Standard_B2s"
        assert inst["state"] == "succeeded"
        assert inst["name"] == "vm-1"
        assert inst["region"] == "eastus"
        assert inst["launchTime"] == "2024-02-01T08:00:00Z"
        assert inst["providerMetadata"]["provider"] == "azure"

    def test_gcp_instance_response_normalizes_correctly(self):
        raw = {
            "items": [
                {
                    "id": "123456789",
                    "name": "gce-instance-1",
                    "machineType": "e2-medium",
                    "status": "RUNNING",
                    "zone": "us-central1-a",
                    "creationTimestamp": "2024-03-10T12:00:00Z",
                    "selfLink": "https://compute.googleapis.com/compute/v1/projects/my-project/zones/us-central1-a/instances/gce-instance-1",
                }
            ]
        }
        result = normalize_compute_response(raw, "gcp")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "123456789"
        assert inst["instanceType"] == "e2-medium"
        assert inst["state"] == "running"
        assert inst["name"] == "gce-instance-1"
        assert inst["region"] == "us-central1-a"
        assert inst["launchTime"] == "2024-03-10T12:00:00Z"
        assert inst["providerMetadata"]["provider"] == "gcp"

    def test_empty_raw_returns_empty_list(self):
        result = normalize_compute_response({}, "aws")
        assert result == {"instances": [], "count": 0}

    def test_non_dict_raw_returns_empty_list(self):
        result = normalize_compute_response(None, "aws")
        assert result == {"instances": [], "count": 0}

    def test_all_schema_fields_present_even_when_null(self):
        """Requirement 4.6: null for unsupported fields rather than omitting."""
        raw = {"instances": [{"id": "123"}]}
        result = normalize_compute_response(raw, "gcp")
        inst = result["instances"][0]
        # All required fields must be present (can be None)
        assert "instanceId" in inst
        assert "instanceType" in inst
        assert "state" in inst
        assert "name" in inst
        assert "region" in inst
        assert "launchTime" in inst
        assert "providerMetadata" in inst

    def test_provider_metadata_captures_unmapped_fields(self):
        """Requirement 4.5: providerMetadata captures unmapped source fields."""
        raw = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-abc",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                            "Tags": [],
                            "Placement": {"AvailabilityZone": "us-west-2b"},
                            "LaunchTime": "2024-01-01T00:00:00Z",
                            "EbsOptimized": True,
                            "Architecture": "x86_64",
                        }
                    ]
                }
            ]
        }
        result = normalize_compute_response(raw, "aws")
        additional = result["instances"][0]["providerMetadata"]["additionalFields"]
        assert "EbsOptimized" in additional
        assert "Architecture" in additional
        assert additional["EbsOptimized"] is True


class TestNormalizeCostResponse:
    """Validate cost response normalization across providers."""

    def test_basic_cost_response(self):
        raw = {
            "totalCost": 1234.56,
            "currency": "USD",
            "period": "2024-01-01 to 2024-01-31",
            "serviceBreakdown": [
                {"serviceName": "Compute", "cost": 800.00},
                {"serviceName": "Storage", "cost": 434.56},
            ],
            "dailyCosts": [
                {"date": "2024-01-01", "cost": 40.0},
                {"date": "2024-01-02", "cost": 38.5},
            ],
            "source": "live",
        }
        result = normalize_cost_response(raw, "aws")
        assert result["totalCost"] == 1234.56
        assert result["currency"] == "USD"
        assert result["period"] == "2024-01-01 to 2024-01-31"
        assert len(result["serviceBreakdown"]) == 2
        assert result["serviceBreakdown"][0] == {"serviceName": "Compute", "cost": 800.00}
        assert len(result["dailyCosts"]) == 2
        assert result["providerMetadata"]["provider"] == "aws"
        assert result["providerMetadata"]["source"] == "live"

    def test_aws_cost_explorer_format(self):
        raw = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-02"},
                    "Total": {"BlendedCost": {"Amount": "45.20", "Unit": "USD"}},
                    "Groups": [
                        {"Keys": ["Amazon EC2"], "Metrics": {"BlendedCost": {"Amount": "30.00"}}},
                        {"Keys": ["Amazon S3"], "Metrics": {"BlendedCost": {"Amount": "15.20"}}},
                    ],
                }
            ]
        }
        result = normalize_cost_response(raw, "aws")
        assert result["serviceBreakdown"] is not None
        services = {s["serviceName"]: s["cost"] for s in result["serviceBreakdown"]}
        assert "Amazon EC2" in services
        assert "Amazon S3" in services

    def test_all_required_fields_present(self):
        result = normalize_cost_response({}, "azure")
        assert "totalCost" in result
        assert "currency" in result
        assert "period" in result
        assert "serviceBreakdown" in result
        assert "dailyCosts" in result
        assert "providerMetadata" in result
        assert result["providerMetadata"]["provider"] == "azure"

    def test_non_dict_input(self):
        result = normalize_cost_response(None, "gcp")
        assert result["totalCost"] is None
        assert result["currency"] is None
        assert result["providerMetadata"]["provider"] == "gcp"

    def test_extra_fields_in_provider_metadata(self):
        """Requirement 4.5: unmapped fields go to providerMetadata."""
        raw = {
            "totalCost": 100.0,
            "currency": "EUR",
            "customField": "some_value",
            "anotherField": 42,
        }
        result = normalize_cost_response(raw, "azure")
        assert "additionalFields" in result["providerMetadata"]
        assert result["providerMetadata"]["additionalFields"]["customField"] == "some_value"
        assert result["providerMetadata"]["additionalFields"]["anotherField"] == 42

    def test_aws_time_period_dict_formatted(self):
        raw = {
            "totalCost": 50.0,
            "TimePeriod": {"Start": "2024-01-01", "End": "2024-01-31"},
        }
        result = normalize_cost_response(raw, "aws")
        assert result["period"] == "2024-01-01 to 2024-01-31"


class TestNormalizeDatabaseResponse:
    """Validate database response normalization across providers."""

    def test_aws_rds_response(self):
        raw = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "mydb-1",
                    "DBInstanceClass": "db.t3.medium",
                    "Engine": "mysql",
                    "DBInstanceStatus": "available",
                    "AllocatedStorage": 100,
                    "MultiAZ": True,
                    "DBInstanceArn": "arn:aws:rds:us-east-1:123456789:db:mydb-1",
                }
            ]
        }
        result = normalize_database_response(raw, "aws")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "mydb-1"
        assert inst["instanceType"] == "db.t3.medium"
        assert inst["engine"] == "mysql"
        assert inst["status"] == "available"
        assert inst["storageSizeGB"] == 100
        assert inst["multiAZ"] is True
        assert inst["providerMetadata"]["provider"] == "aws"
        assert inst["providerMetadata"]["nativeId"] == "arn:aws:rds:us-east-1:123456789:db:mydb-1"

    def test_azure_database_response(self):
        raw = {
            "value": [
                {
                    "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/servers/pg-1",
                    "sku": {"name": "GP_Gen5_2"},
                    "properties": {
                        "version": "14",
                        "state": "Ready",
                        "storageProfile": {"storageMB": 51200},
                        "highAvailability": {"mode": "ZoneRedundant"},
                    },
                }
            ]
        }
        result = normalize_database_response(raw, "azure")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/servers/pg-1"
        assert inst["instanceType"] == "GP_Gen5_2"
        assert inst["engine"] == "14"
        assert inst["status"] == "Ready"
        assert inst["storageSizeGB"] == 50  # 51200 MB converted to ~50 GB
        assert inst["multiAZ"] is True

    def test_gcp_cloud_sql_response(self):
        raw = {
            "items": [
                {
                    "name": "my-cloudsql",
                    "tier": "db-custom-2-8192",
                    "databaseVersion": "POSTGRES_14",
                    "state": "RUNNABLE",
                    "settings": {
                        "dataDiskSizeGb": "50",
                        "availabilityType": "REGIONAL",
                    },
                    "selfLink": "https://sqladmin.googleapis.com/sql/v1beta4/projects/my-proj/instances/my-cloudsql",
                }
            ]
        }
        result = normalize_database_response(raw, "gcp")
        assert result["count"] == 1
        inst = result["instances"][0]
        assert inst["instanceId"] == "my-cloudsql"
        assert inst["instanceType"] == "db-custom-2-8192"
        assert inst["engine"] == "POSTGRES_14"
        assert inst["status"] == "RUNNABLE"
        assert inst["storageSizeGB"] == 50
        assert inst["multiAZ"] is True

    def test_empty_response(self):
        result = normalize_database_response({}, "aws")
        assert result == {"instances": [], "count": 0}

    def test_null_fields_present(self):
        """Requirement 4.6: null for unsupported fields."""
        raw = {"instances": [{"name": "only-name"}]}
        result = normalize_database_response(raw, "gcp")
        inst = result["instances"][0]
        assert "instanceId" in inst
        assert "instanceType" in inst
        assert "engine" in inst
        assert "status" in inst
        assert "storageSizeGB" in inst
        assert "multiAZ" in inst


class TestNormalizeStorageResponse:
    """Validate storage volume response normalization across providers."""

    def test_aws_ebs_response(self):
        raw = {
            "Volumes": [
                {
                    "VolumeId": "vol-abc123",
                    "VolumeType": "gp3",
                    "Size": 100,
                    "State": "in-use",
                    "Attachments": [{"InstanceId": "i-123", "Device": "/dev/sda1"}],
                }
            ]
        }
        result = normalize_storage_response(raw, "aws")
        assert result["count"] == 1
        vol = result["volumes"][0]
        assert vol["volumeId"] == "vol-abc123"
        assert vol["volumeType"] == "gp3"
        assert vol["sizeGB"] == 100
        assert vol["state"] == "in-use"
        assert vol["attached"] is True
        assert vol["providerMetadata"]["provider"] == "aws"
        assert vol["providerMetadata"]["nativeId"] == "vol-abc123"

    def test_aws_ebs_unattached(self):
        raw = {
            "Volumes": [
                {
                    "VolumeId": "vol-xyz789",
                    "VolumeType": "gp2",
                    "Size": 50,
                    "State": "available",
                    "Attachments": [],
                }
            ]
        }
        result = normalize_storage_response(raw, "aws")
        vol = result["volumes"][0]
        assert vol["attached"] is False

    def test_azure_disk_response(self):
        raw = {
            "value": [
                {
                    "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1",
                    "sku": {"name": "Premium_LRS"},
                    "properties": {
                        "diskSizeGB": 256,
                        "diskState": "Attached",
                    },
                    "managedBy": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
                }
            ]
        }
        result = normalize_storage_response(raw, "azure")
        assert result["count"] == 1
        vol = result["volumes"][0]
        assert vol["volumeId"] == "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-1"
        assert vol["volumeType"] == "Premium_LRS"
        assert vol["sizeGB"] == 256
        assert vol["state"] == "Attached"
        assert vol["attached"] is True

    def test_gcp_disk_response(self):
        raw = {
            "items": [
                {
                    "id": "9876543210",
                    "type": "pd-ssd",
                    "sizeGb": "200",
                    "status": "READY",
                    "users": ["https://compute.googleapis.com/.../instances/vm-1"],
                    "selfLink": "https://compute.googleapis.com/.../disks/disk-1",
                }
            ]
        }
        result = normalize_storage_response(raw, "gcp")
        vol = result["volumes"][0]
        assert vol["volumeId"] == "9876543210"
        assert vol["volumeType"] == "pd-ssd"
        assert vol["sizeGB"] == 200
        assert vol["state"] == "READY"
        assert vol["attached"] is True

    def test_empty_response(self):
        result = normalize_storage_response({}, "gcp")
        assert result == {"volumes": [], "count": 0}

    def test_all_fields_present(self):
        """Requirement 4.6: null for unsupported fields."""
        raw = {"volumes": [{"id": "123"}]}
        result = normalize_storage_response(raw, "gcp")
        vol = result["volumes"][0]
        assert "volumeId" in vol
        assert "volumeType" in vol
        assert "sizeGB" in vol
        assert "state" in vol
        assert "attached" in vol
        assert "providerMetadata" in vol


class TestNormalizeObjectStorageResponse:
    """Validate object storage response normalization across providers."""

    def test_aws_s3_response(self):
        raw = {
            "Buckets": [
                {"Name": "my-bucket", "CreationDate": "2024-01-01T00:00:00Z"},
                {"Name": "logs-bucket", "CreationDate": "2024-02-15T10:30:00Z"},
            ],
            "Owner": {"ID": "owner-123"},
        }
        result = normalize_object_storage_response(raw, "aws")
        assert result["count"] == 2
        assert result["buckets"][0]["name"] == "my-bucket"
        assert result["buckets"][0]["creationDate"] == "2024-01-01T00:00:00Z"
        assert result["buckets"][0]["providerMetadata"]["provider"] == "aws"
        assert result["providerMetadata"]["provider"] == "aws"

    def test_azure_blob_containers(self):
        raw = {
            "containers": [
                {
                    "name": "container-1",
                    "id": "/subscriptions/sub/...",
                    "properties": {"creationTime": "2024-03-01T00:00:00Z"},
                }
            ]
        }
        result = normalize_object_storage_response(raw, "azure")
        assert result["count"] == 1
        assert result["buckets"][0]["name"] == "container-1"
        assert result["buckets"][0]["creationDate"] == "2024-03-01T00:00:00Z"
        assert result["providerMetadata"]["provider"] == "azure"

    def test_gcp_gcs_response(self):
        raw = {
            "items": [
                {
                    "name": "gcs-bucket-1",
                    "timeCreated": "2024-04-01T12:00:00Z",
                    "selfLink": "https://storage.googleapis.com/storage/v1/b/gcs-bucket-1",
                    "id": "gcs-bucket-1",
                    "storageClass": "STANDARD",
                }
            ]
        }
        result = normalize_object_storage_response(raw, "gcp")
        assert result["count"] == 1
        bucket = result["buckets"][0]
        assert bucket["name"] == "gcs-bucket-1"
        assert bucket["creationDate"] == "2024-04-01T12:00:00Z"
        assert bucket["providerMetadata"]["provider"] == "gcp"
        # storageClass is an unmapped field, should be in additionalFields
        assert "storageClass" in bucket["providerMetadata"]["additionalFields"]

    def test_empty_response(self):
        result = normalize_object_storage_response({}, "aws")
        assert result["buckets"] == []
        assert result["count"] == 0
        assert result["providerMetadata"]["provider"] == "aws"

    def test_non_dict_returns_empty(self):
        result = normalize_object_storage_response(None, "gcp")
        assert result == {"buckets": [], "count": 0, "providerMetadata": {"provider": "gcp"}}

    def test_unmapped_top_level_fields_in_provider_metadata(self):
        """Requirement 4.5: providerMetadata captures unmapped fields."""
        raw = {
            "Buckets": [{"Name": "b1", "CreationDate": "2024-01-01"}],
            "customTopLevel": "extra_data",
        }
        result = normalize_object_storage_response(raw, "aws")
        assert "additionalFields" in result["providerMetadata"]
        assert result["providerMetadata"]["additionalFields"]["customTopLevel"] == "extra_data"
