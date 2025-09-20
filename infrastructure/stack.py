from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
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

        # ---------------- Reuse EXISTING Buckets ----------------
        input_bucket = s3.Bucket.from_bucket_name(
            self, "InputBucket",
            bucket_name=f"jp2-input-{account}-{region}"
        )
        output_bucket = s3.Bucket.from_bucket_name(
            self, "OutputBucket",
            bucket_name=f"jp2-output-{account}-{region}"
        )

        # ---------------- UI bucket is PRE-EXISTING ----------------
        ui_bucket = s3.Bucket.from_bucket_name(
            self, "UiBucket",
            bucket_name="jp2-ui-991105135552-us-east-1"
        )

        # Deploy static UI (/ui folder) into the UI bucket
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
        list_input_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[input_bucket.bucket_arn])
        )

        # ---------------- List Output Lambda (reuse same handler) ----------------
        list_output_fn = _lambda.Function(
            self, "ListOutputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={"BUCKET": output_bucket.bucket_name},
        )
        list_output_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[output_bucket.bucket_arn])
        )

        # ---------------- Convert Lambda (NEW) ----------------
        # Optionally pass the Split State Machine ARN from context or env:
        # cdk synth/deploy with: -c splitSmArn=arn:aws:states:...
        split_sm_arn = self.node.try_get_context("splitSmArn") or os.getenv("SPLIT_SM_ARN", "")

        convert_fn = _lambda.Function(
            self, "ConvertFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="convert.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "SPLIT_SM_ARN": split_sm_arn,  # may be empty if not used by your handler
            },
        )

        # If a specific SM ARN is provided, grant StartExecution on it
        if split_sm_arn:
            convert_fn.add_to_role_policy(iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[split_sm_arn],
            ))

        # ---------------- HTTP API with CORS ----------------
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["Content-Type"],
                allow_methods=[apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.OPTIONS],
                allow_origins=["*"],
                max_age=Duration.days(10),
            ),
        )

        list_input_integ  = apigw_int.HttpLambdaIntegration("ListInputIntegration", handler=list_input_fn)
        list_output_integ = apigw_int.HttpLambdaIntegration("ListOutputIntegration", handler=list_output_fn)
        convert_integ     = apigw_int.HttpLambdaIntegration("ConvertIntegration", handler=convert_fn)

        http_api.add_routes(path="/list-input",  methods=[apigw.HttpMethod.GET],  integration=list_input_integ)
        http_api.add_routes(path="/list-output", methods=[apigw.HttpMethod.GET],  integration=list_output_integ)
        http_api.add_routes(path="/convert",     methods=[apigw.HttpMethod.POST], integration=convert_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName",   value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint",     value=http_api.api_endpoint)
