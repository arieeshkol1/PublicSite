from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_int,
)
from constructs import Construct
import os


class ServerlessJp2Stack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs):
        super().__init__(scope, cid, **kwargs)

        account = Stack.of(self).account
        region = Stack.of(self).region

        # Input bucket (private)
        input_bucket = s3.Bucket(
            self, "InputBucket",
            bucket_name=f"jp2-input-{account}-{region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Output bucket (private)
        output_bucket = s3.Bucket(
            self, "OutputBucket",
            bucket_name=f"jp2-output-{account}-{region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # UI bucket (S3 static website) - public via bucket policy (ACLs blocked)
        ui_bucket = s3.Bucket(
            self, "UiBucket",
            bucket_name=f"jp2-ui-{account}-{region}",
            website_index_document="index.html",
            public_read_access=True,  # demo simplicity; prefer CloudFront+OAC for prod
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS,  # allow public bucket policy, block ACLs
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Lambda stub controller for /split, /unite, /status
        controller_fn = _lambda.Function(
            self, "ControllerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="controller.handler",
            code=_lambda.Code.from_asset(os.path.join(os.path.dirname(__file__), "lambda")),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
            },
        )

        # API Gateway HTTP API
        http_api = apigw.HttpApi(self, "HttpApi")
        integ = apigw_int.HttpLambdaIntegration("ControllerIntegration", handler=controller_fn)

        http_api.add_routes(
            path="/split",
            methods=[apigw.HttpMethod.POST],
            integration=integ,
        )
        http_api.add_routes(
            path="/unite",
            methods=[apigw.HttpMethod.POST],
            integration=integ,
        )
        http_api.add_routes(
            path="/status/{jobId}",
            methods=[apigw.HttpMethod.GET],
            integration=integ,
        )

        # Useful outputs
        CfnOutput(self, "UiBucketWebsiteUrl", value=ui_bucket.bucket_website_url)
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
