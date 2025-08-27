from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_kms as kms,
    aws_s3 as s3,
    aws_ec2 as ec2,
)
from constructs import Construct

class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, vpc: ec2.IVpc, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account_suffix = "991105135552"
        key = kms.Key(self, "BucketsKey", enable_key_rotation=True)

        def bucket(logical_id: str, base_name: str) -> s3.Bucket:
            return s3.Bucket(
                self, logical_id,
                bucket_name=f"{base_name}-{account_suffix}".format(base_name=base_name, account_suffix=account_suffix),
                encryption=s3.BucketEncryption.KMS,
                encryption_key=key,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
                versioned=True,
                lifecycle_rules=[
                    s3.LifecycleRule(
                        noncurrent_version_expiration=Duration.days(30),
                        abort_incomplete_multipart_upload_after=Duration.days(7),
                    )
                ],
                removal_policy=RemovalPolicy.RETAIN,
            )

        b_dirty = bucket("DirtyIn", "tsg-demo-dirty-in")
        b_white = bucket("WhiteLibrary", "tsg-demo-white-library")
        b_ui = bucket("UiDashboard", "tsg-demo-ui-dashboard")

        self.buckets = {
            "dirty": b_dirty,
            "white": b_white,
            "ui": b_ui,
        }