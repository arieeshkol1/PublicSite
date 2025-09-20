from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda as _lambda,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_int,
    aws_iam as iam,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_ecr as ecr,
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

        # ---------------- Controller Lambda ----------------
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
                # STATE_MACHINE_ARN / _UNITE set after SMs are created
            },
        )
        # Allow listing/reading output where needed by controller
        controller_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[output_bucket.bucket_arn])
        )
        output_bucket.grant_read(controller_fn)

        # ---------------- List Input Lambda ----------------
        list_input_fn = _lambda.Function(
            self, "ListInputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={"INPUT_BUCKET": input_bucket.bucket_name},
        )
        list_input_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[input_bucket.bucket_arn])
        )
        input_bucket.grant_read(list_input_fn)

        # ---------------- List Output Lambda (NEW) ----------------
        list_output_fn = _lambda.Function(
            self, "ListOutputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_output.handler",  # implement same pattern as lambda_list_input
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(15),
            memory_size=256,
            environment={"OUTPUT_BUCKET": output_bucket.bucket_name},
        )
        list_output_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[output_bucket.bucket_arn])
        )
        output_bucket.grant_read(list_output_fn)

        # ---------------- ECS Fargate for Split ----------------
        # VPC with public subnets (no NAT)
        vpc = ec2.Vpc(
            self, "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="public", subnet_type=ec2.SubnetType.PUBLIC)
            ],
        )
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        # Use prebuilt image from ECR (no local Docker build)
        repo = ecr.Repository.from_repository_arn(
            self, "TilerRepo",
            "arn:aws:ecr:us-east-1:991105135552:repository/jp2-split"
        )
        image_tag = self.node.try_get_context("tilerTag") or "latest"

        # Task definition: 8 vCPU, 16 GiB
        task_def = ecs.FargateTaskDefinition(
            self, "SplitTaskDef",
            cpu=8192,                   # 8 vCPU
            memory_limit_mib=16384,     # 16 GiB
        )

        # Allow ECS execution role to pull from ECR
        repo.grant_pull(task_def.obtain_execution_role())

        # Task role: S3 read input / read-write output
        task_def.add_to_task_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[input_bucket.bucket_arn, input_bucket.arn_for_objects("*")]
        ))
        task_def.add_to_task_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:ListBucket", "s3:GetObject"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        # CloudWatch logs
        log_group = logs.LogGroup(
            self, "SplitLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY
        )

        container = task_def.add_container(
            "Tiler",
            image=ecs.ContainerImage.from_ecr_repository(repo, image_tag),
            logging=ecs.LogDriver.aws_logs(stream_prefix="split", log_group=log_group),
            environment={
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"
            }
        )
        container.add_ulimits(ecs.Ulimit(
            name=ecs.UlimitName.NOFILE, soft_limit=102400, hard_limit=102400
        ))

        # ---------------- Unite Worker Lambda ----------------
        unite_worker_fn = _lambda.Function(
            self, "UniteWorkerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="unite_worker.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={"OUTPUT_BUCKET": output_bucket.bucket_name},
        )
        output_bucket.grant_read_write(unite_worker_fn)
        unite_worker_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[output_bucket.bucket_arn])
        )

        # ---------------- Step Functions ----------------
        # Split: run Fargate task with env overrides from input
        split_task = tasks.EcsRunTask(
            self, "SplitTask",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            cluster=cluster,
            task_definition=task_def,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            assign_public_ip=True,  # public subnet, no NAT
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=container,
                    command=["python3", "/app/split_worker.py"],
                    environment=[
                        tasks.TaskEnvironmentVariable(
                            name="INPUT_BUCKET",
                            value=sfn.JsonPath.string_at("$.inputBucket")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="INPUT_KEY",
                            value=sfn.JsonPath.string_at("$.inputKey")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="OUTPUT_BUCKET",
                            value=sfn.JsonPath.string_at("$.outputBucket")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="JOB_ID",
                            value=sfn.JsonPath.string_at("$.jobId")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TILES_TOTAL",
                            value=sfn.JsonPath.string_at("$.params.tilesTotal")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TILES_GRID",
                            value=sfn.JsonPath.string_at("$.params.tilesGrid")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="FORMAT_OPTION",
                            value=sfn.JsonPath.string_at("$.params.formatOption")
                        ),
                    ],
                )
            ],
            result_path="$.splitResult"
        )
        split_sm = sfn.StateMachine(
            self, "SplitStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(split_task),
            timeout=Duration.minutes(60),
        )

        # Unite SM
        unite_task = tasks.LambdaInvoke(
            self, "UniteTask", lambda_function=unite_worker_fn, payload_response_only=True
        )
        unite_sm = sfn.StateMachine(
            self, "UniteStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(unite_task),
            timeout=Duration.minutes(10),
        )

        # Controller -> StepFunctions IAM
        controller_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[split_sm.state_machine_arn, unite_sm.state_machine_arn],
            )
        )
        controller_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:DescribeExecution", "states:GetExecutionHistory"],
                resources=[
                    f"arn:aws:states:{region}:{account}:execution:{split_sm.state_machine_name}:*",
                    f"arn:aws:states:{region}:{account}:execution:{unite_sm.state_machine_name}:*",
                ],
            )
        )
        controller_fn.add_environment("STATE_MACHINE_ARN", split_sm.state_machine_arn)
        controller_fn.add_environment("STATE_MACHINE_ARN_UNITE", unite_sm.state_machine_arn)

        # ---------------- HTTP API with CORS ----------------
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["Content-Type"],  # add "x-api-key" if you use API keys
                allow_methods=[apigw.CorsHttpMethod.GET, apigw.CorsHttpMethod.POST, apigw.CorsHttpMethod.OPTIONS],
                allow_origins=["*"],             # lock this down to your S3 UI origin if desired
                max_age=Duration.days(10),
            ),
        )
        controller_integ   = apigw_int.HttpLambdaIntegration("ControllerIntegration", handler=controller_fn)
        list_input_integ   = apigw_int.HttpLambdaIntegration("ListInputIntegration", handler=list_input_fn)
        list_output_integ  = apigw_int.HttpLambdaIntegration("ListOutputIntegration", handler=list_output_fn)

        http_api.add_routes(path="/split",               methods=[apigw.HttpMethod.POST], integration=controller_integ)
        http_api.add_routes(path="/unite",               methods=[apigw.HttpMethod.POST], integration=controller_integ)
        http_api.add_routes(path="/status/{jobId}",      methods=[apigw.HttpMethod.GET],  integration=controller_integ)
        http_api.add_routes(path="/status-progress",     methods=[apigw.HttpMethod.GET],  integration=controller_integ)
        http_api.add_routes(path="/status-detail/{jobId}", methods=[apigw.HttpMethod.GET], integration=controller_integ)
        http_api.add_routes(path="/status-history/{jobId}", methods=[apigw.HttpMethod.GET], integration=controller_integ)
        http_api.add_routes(path="/list-input",          methods=[apigw.HttpMethod.GET],  integration=list_input_integ)
        # IMPORTANT: route list-output to the dedicated Lambda
        http_api.add_routes(path="/list-output",         methods=[apigw.HttpMethod.GET],  integration=list_output_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName", value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        CfnOutput(self, "SplitStateMachineArn", value=split_sm.state_machine_arn)
        CfnOutput(self, "UniteStateMachineArn", value=unite_sm.state_machine_arn)
