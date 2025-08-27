from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_int,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
)
from constructs import Construct
import os


class ServerlessJp2Stack(Stack):
    def __init__(self, scope: Construct, cid: str, **kwargs):
        super().__init__(scope, cid, **kwargs)

        account = Stack.of(self).account
        region = Stack.of(self).region

        # ---------------- Buckets ----------------
        input_bucket = s3.Bucket(
            self, "InputBucket",
            bucket_name=f"jp2-input-{account}-{region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        output_bucket = s3.Bucket(
            self, "OutputBucket",
            bucket_name=f"jp2-output-{account}-{region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        ui_bucket = s3.Bucket(
            self, "UiBucket",
            bucket_name=f"jp2-ui-{account}-{region}",
            website_index_document="index.html",
            public_read_access=True,  # demo; prefer CloudFront+OAC for prod
            block_public_access=s3.BlockPublicAccess.BLOCK_ACLS,  # allow public policy, block ACLs
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        lambda_code_dir = os.path.join(os.path.dirname(__file__), "lambda")

        # ---------------- Lambdas ----------------
        # Controller: /split, /unite (stub), /status/{jobId}, /status-progress
        controller_fn = _lambda.Function(
            self, "ControllerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="controller.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                # STATE_MACHINE_ARN filled after we create it
            },
        )

        # List-input Lambda
        list_input_fn = _lambda.Function(
            self, "ListInputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
            },
        )
        # IAM for list
        list_input_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[input_bucket.bucket_arn],
            )
        )

     # ---------------- Split Worker Lambda ----------------
split_worker_fn = _lambda.Function(
    self, "SplitWorkerFn",
    runtime=_lambda.Runtime.PYTHON_3_11,
    handler="split_worker.handler",  # file: split_worker.py ; func: handler
    code=_lambda.Code.from_asset(lambda_code_dir),
    timeout=Duration.minutes(15),
    memory_size=10240,  # 10 GB RAM
    environment={
        "OUTPUT_BUCKET": output_bucket.bucket_name,
    },
)

# Back-compat way to set 10 GiB ephemeral /tmp
from aws_cdk.aws_lambda import CfnFunction
cfn_worker = split_worker_fn.node.default_child
if isinstance(cfn_worker, CfnFunction):
    cfn_worker.ephemeral_storage = CfnFunction.EphemeralStorageProperty(size=10240)  # size in MiB

        # Worker S3 perms
        output_bucket.grant_put(split_worker_fn)
        output_bucket.grant_read_write(split_worker_fn)
        output_bucket.grant_list(split_worker_fn)
        input_bucket.grant_read(split_worker_fn)  # if you later read input

        # ---------------- Step Functions ----------------
        split_task = tasks.LambdaInvoke(
            self,
            "SplitTask",
            lambda_function=split_worker_fn,
            payload_response_only=True,  # Lambda returns JSON dict
        )

        definition = split_task  # simple: one task → success

        state_machine = sfn.StateMachine(
            self,
            "SplitStateMachine",
            definition=definition,
            timeout=Duration.minutes(30),
        )

        # Allow controller to start/describe executions
        controller_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution", "states:DescribeExecution"],
                resources=[state_machine.state_machine_arn],
            )
        )

        # Pass SM ARN into controller env
        controller_fn.add_environment("STATE_MACHINE_ARN", state_machine.state_machine_arn)

        # ---------------- API (HTTP API) with CORS ----------------
        http_api = apigw.HttpApi(
            self,
            "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["Content-Type"],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],  # tighten to UI domain for prod
                max_age=Duration.days(10),
            ),
        )

        controller_integ = apigw_int.HttpLambdaIntegration("ControllerIntegration", handler=controller_fn)
        list_input_integ = apigw_int.HttpLambdaIntegration("ListInputIntegration", handler=list_input_fn)

        # Routes
        http_api.add_routes(path="/split", methods=[apigw.HttpMethod.POST], integration=controller_integ)
        http_api.add_routes(path="/unite", methods=[apigw.HttpMethod.POST], integration=controller_integ)  # stub
        http_api.add_routes(path="/status/{jobId}", methods=[apigw.HttpMethod.GET], integration=controller_integ)
        http_api.add_routes(path="/status-progress", methods=[apigw.HttpMethod.GET], integration=controller_integ)
        http_api.add_routes(path="/list-input", methods=[apigw.HttpMethod.GET], integration=list_input_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketWebsiteUrl", value=ui_bucket.bucket_website_url)
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
