from aws_cdk import (
    Stack, Duration, CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_int,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,
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

        # ---------------- ECS / Fargate (Tiler) ----------------
        # Use the default VPC (or replace with fromLookup to your VPC)
        vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)

        # ECS Cluster
        cluster = ecs.Cluster(self, "TilerCluster", vpc=vpc)

        # Logs for Fargate tasks
        tiler_logs = logs.LogGroup(
            self, "TilerLogGroup",
            log_group_name="/ecs/tsg-jp2-tiler",
            retention=logs.RetentionDays.ONE_MONTH
        )

        # Task role (container permissions)
        tiler_task_role = iam.Role(
            self, "TilerTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        # S3 read on input bucket
        tiler_task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[input_bucket.bucket_arn, input_bucket.arn_for_objects("*")]
        ))
        # S3 write on output bucket
        tiler_task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListBucket"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))
        # If buckets use KMS, add decrypt/encrypt permissions for that key.

        # Fargate Task Definition (uses your GDAL image)
        tiler_taskdef = ecs.FargateTaskDefinition(
            self, "TilerTaskDef",
            cpu=1024,               # 1 vCPU
            memory_limit_mib=2048,  # 2 GB (increase for large scenes)
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64
            ),
            task_role=tiler_task_role
        )

        # Your ECR image URI with GDAL already baked in
        tiler_image_uri = (
            "991105135552.dkr.ecr.us-east-1.amazonaws.com/"
            "cdk-hnb659fds-container-assets-991105135552-us-east-1:"
            "edfcf89c0236c949848d9ccd83d731a69fd6fc85308fa3d3a3313ea50b05a526"
        )

        tiler_container = tiler_taskdef.add_container(
            "tiler",
            image=ecs.ContainerImage.from_registry(tiler_image_uri),
            essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix="tiler", log_group=tiler_logs),
            environment={
                # Default creation options; ConvertFn can override per task via containerOverrides
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"
            }
        )
        # Command is from your Dockerfile: ["python3","/app/tiler.py"] — no port mapping needed

        # Security group for tasks (egress-only)
        tiler_sg = ec2.SecurityGroup(self, "TilerTaskSG", vpc=vpc, allow_all_outbound=True)

        # We'll run tasks in PUBLIC subnets and assign a public IP by default;
        # if you prefer private subnets with NAT, switch to vpc.private_subnets and set ASSIGN_PUBLIC_IP=DISABLED.
        public_subnet_ids = [s.subnet_id for s in vpc.public_subnets]

        # ---------------- Convert Lambda (controller that runs Fargate per file) ----------------
        convert_fn = _lambda.Function(
            self, "ConvertFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="convert.handler",  # lambda/convert.py
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=2048,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                # ECS wiring for ConvertFn
                "ECS_CLUSTER_ARN": cluster.cluster_arn,
                "TASK_DEF_ARN": tiler_taskdef.task_definition_arn,
                "SUBNET_IDS": ",".join(public_subnet_ids),
                "SECURITY_GROUP_ID": tiler_sg.security_group_id,
                "ASSIGN_PUBLIC_IP": "ENABLED",  # using public subnets; set DISABLED if you switch to private
                # optional default create opts passed to container
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2",
            },
        )

        # Permissions for ConvertFn to run ECS tasks and pass the task role
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask", "ecs:DescribeTasks"],
            resources=["*"]  # you can scope RunTask to tiler_taskdef.task_definition_arn if you prefer
        ))
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))
        # ConvertFn still needs S3 list/get to validate or enrich responses if you add that later
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetObject"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        # ---------------- HTTP API ----------------
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["Content-Type"],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.OPTIONS
                ],
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

        # Integrations & Routes (same HttpApi)
        copy_files_integ = apigw_int.HttpLambdaIntegration("CopyFilesIntegration", handler=copy_files_fn)
        delete_files_integ = apigw_int.HttpLambdaIntegration("DeleteFilesIntegration", handler=delete_files_fn)
        download_file_integ = apigw_int.HttpLambdaIntegration("DownloadFileIntegration", handler=download_file_fn)

        http_api.add_routes(path="/copy-files", methods=[apigw.HttpMethod.POST], integration=copy_files_integ)
        http_api.add_routes(path="/delete-files", methods=[apigw.HttpMethod.POST], integration=delete_files_integ)
        http_api.add_routes(path="/download-file", methods=[apigw.HttpMethod.POST], integration=download_file_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName", value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)

        # Helpful ECS outputs
        CfnOutput(self, "EcsClusterArn", value=cluster.cluster_arn)
        CfnOutput(self, "TilerTaskDefArn", value=tiler_taskdef.task_definition_arn)
