from aws_cdk import (
    Stack, Duration, CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_int,
    aws_iam as iam,
)
from constructs import Construct
import os


class ServerlessJp2Stack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs):
        super().__init__(scope, cid, **kwargs)

        account = Stack.of(self).account
        region = Stack.of(self).region

        # ---------------- Buckets ----------------
        input_bucket = s3.Bucket.from_bucket_name(
            self, "InputBucket",
            bucket_name=f"jp2-input-{account}-{region}"
        )
        output_bucket = s3.Bucket.from_bucket_name(
            self, "OutputBucket",
            bucket_name=f"jp2-output-{account}-{region}"
        )
        ui_bucket = s3.Bucket.from_bucket_name(
            self, "UiBucket",
            bucket_name="jp2-ui-991105135552-us-east-1"
        )

        # ---------------- UI Deployment ----------------
        ui_dir = os.path.join(os.path.dirname(__file__), "..", "ui")
        s3deploy.BucketDeployment(
            self, "DeployStaticUI",
            sources=[s3deploy.Source.asset(ui_dir)],
            destination_bucket=ui_bucket,
            destination_key_prefix="",
            prune=True,
            retain_on_delete=False,
        )

        lambda_code_dir = os.path.join(os.path.dirname(__file__), "lambda")

        # ---------------- List Input Lambda ----------------
        list_input_fn = _lambda.Function(
            self, "ListInputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={"BUCKET": input_bucket.bucket_name},
        )
        list_input_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetObject"],
            resources=[
                input_bucket.bucket_arn,
                input_bucket.arn_for_objects("*")
            ]
        ))

        # ---------------- List Output Lambda ----------------
        list_output_fn = _lambda.Function(
            self, "ListOutputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={"BUCKET": output_bucket.bucket_name},
        )
        list_output_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetObject"],
            resources=[
                output_bucket.bucket_arn,
                output_bucket.arn_for_objects("*")
            ]
        ))

        # ---------------- Convert Lambda ----------------
        convert_fn = _lambda.Function(
            self, "ConvertFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="convert.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=2048,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
            },
        )

        # Permissions for ConvertFn
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[
                input_bucket.bucket_arn,
                input_bucket.arn_for_objects("*"),
                output_bucket.bucket_arn,
                output_bucket.arn_for_objects("*"),
            ]
        ))

        # ---------------- HTTP API ----------------
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["Content-Type"],
                allow_methods=[apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.OPTIONS],
                allow_origins=["*"],
                max_age=Duration.days(10),
            ),
        )

        list_input_integ = apigw_int.HttpLambdaIntegration("ListInputIntegration", handler=list_input_fn)
        list_output_integ = apigw_int.HttpLambdaIntegration("ListOutputIntegration", handler=list_output_fn)
        convert_integ = apigw_int.HttpLambdaIntegration("ConvertIntegration", handler=convert_fn)

        http_api.add_routes(path="/list-input", methods=[apigw.HttpMethod.GET], integration=list_input_integ)
        http_api.add_routes(path="/list-output", methods=[apigw.HttpMethod.GET], integration=list_output_integ)
        http_api.add_routes(path="/convert", methods=[apigw.HttpMethod.POST], integration=convert_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName", value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        


        # ---------------- File Manager Lambdas (NEW) ----------------
        fm_env = {
            "INPUT_BUCKET": input_bucket.bucket_name,
            "OUTPUT_BUCKET": output_bucket.bucket_name,
        }

        copy_files_fn = _lambda.Function(
            self, "CopyFilesFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_copy_files.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment=fm_env,
        )
        delete_files_fn = _lambda.Function(
            self, "DeleteFilesFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_delete_files.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=fm_env,
        )
        download_file_fn = _lambda.Function(
            self, "DownloadFileFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_download_file.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment=fm_env,
        )

        # IAM (scoped to input/output buckets only)
        for fn in [copy_files_fn, delete_files_fn, download_file_fn]:
            fn.add_to_role_policy(iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[input_bucket.bucket_arn, output_bucket.bucket_arn]
            ))
            fn.add_to_role_policy(iam.PolicyStatement(
                actions=[
                    "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                    "s3:AbortMultipartUpload", "s3:CreateMultipartUpload",
                    "s3:UploadPart", "s3:CompleteMultipartUpload"
                ],
                resources=[
                    input_bucket.arn_for_objects("*"),
                    output_bucket.arn_for_objects("*")
                ]
            ))

        # ---------------- Integrations & Routes (same HttpApi) ----------------
        copy_files_integ = apigw_int.HttpLambdaIntegration("CopyFilesIntegration", handler=copy_files_fn)
        delete_files_integ = apigw_int.HttpLambdaIntegration("DeleteFilesIntegration", handler=delete_files_fn)
        download_file_integ = apigw_int.HttpLambdaIntegration("DownloadFileIntegration", handler=download_file_fn)

        http_api.add_routes(path="/copy-files", methods=[apigw.HttpMethod.POST], integration=copy_files_integ)
        http_api.add_routes(path="/delete-files", methods=[apigw.HttpMethod.POST], integration=delete_files_integ)
        http_api.add_routes(path="/download-file", methods=[apigw.HttpMethod.POST], integration=download_file_integ)

