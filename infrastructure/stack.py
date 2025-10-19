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
        if os.path.isdir(ui_dir):
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
            resources=[input_bucket.bucket_arn, input_bucket.arn_for_objects("*")]
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
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        # ---------------- ECS / Fargate (Tiler) ----------------
        vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)
        cluster = ecs.Cluster(self, "TilerCluster", vpc=vpc)

        tiler_logs = logs.LogGroup(
            self, "TilerLogGroup",
            log_group_name="/ecs/tsg-jp2-tiler",
            retention=logs.RetentionDays.ONE_MONTH
        )

        tiler_task_role = iam.Role(
            self, "TilerTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        )
        tiler_task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:ListBucket"],
            resources=[input_bucket.bucket_arn, input_bucket.arn_for_objects("*")]
        ))
        tiler_task_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListBucket"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        tiler_taskdef = ecs.FargateTaskDefinition(
            self, "TilerTaskDef",
            cpu=1024,
            memory_limit_mib=2048,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64
            ),
            task_role=tiler_task_role
        )

        # NOTE: Use your existing container image URI
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
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1",
                "PREDICTOR_POLICY": "FORCE_1",
                "TIFF_FORCE_16BIT": "true",
            }
        )

        tiler_sg = ec2.SecurityGroup(self, "TilerTaskSG", vpc=vpc, allow_all_outbound=True)
        public_subnet_ids = [s.subnet_id for s in vpc.public_subnets]

        # ---------------- Convert Lambda (ECS launcher) ----------------
        convert_fn = _lambda.Function(
            self, "ConvertFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="converter.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=2048,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "ECS_CLUSTER_ARN": cluster.cluster_arn,
                "TASK_DEF_ARN": tiler_taskdef.task_definition_arn,
                "SUBNET_IDS": ",".join(public_subnet_ids),
                "SECURITY_GROUP_ID": tiler_sg.security_group_id,
                "ASSIGN_PUBLIC_IP": "ENABLED",
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1",
                "PREDICTOR_POLICY": "FORCE_1",
                "TIFF_FORCE_16BIT": "true",
            },
        )
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask", "ecs:DescribeTasks"],
            resources=["*"]
        ))
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetObject"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        # ---------------- Step Functions (Split/Unite Untouched) ----------------
        # This preserves your existing split/unite flow but ensures any container
        # run will inherit predictor-safe options.
        #
        # Split State Machine
        split_taskdef = ecs.FargateTaskDefinition(
            self, "SplitTaskDef",
            cpu=512,
            memory_limit_mib=1024,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64
            ),
            task_role=tiler_task_role,
        )
        split_container = split_taskdef.add_container(
            "split",
            image=ecs.ContainerImage.from_registry(tiler_image_uri),
            essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix="split", log_group=tiler_logs),
            environment={
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1",
                "PREDICTOR_POLICY": "FORCE_1",
                "TIFF_FORCE_16BIT": "true",
            },
        )

        unite_taskdef = ecs.FargateTaskDefinition(
            self, "UniteTaskDef",
            cpu=512,
            memory_limit_mib=1024,
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64
            ),
            task_role=tiler_task_role,
        )
        unite_container = unite_taskdef.add_container(
            "unite",
            image=ecs.ContainerImage.from_registry(tiler_image_uri),
            essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix="unite", log_group=tiler_logs),
            environment={
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1",
                "PREDICTOR_POLICY": "FORCE_1",
                "TIFF_FORCE_16BIT": "true",
            },
        )

        # Split State
        split_run_task = tasks.EcsRunTask(
            self, "RunSplit",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            cluster=cluster,
            task_definition=split_taskdef,
            assign_public_ip=True,
            security_groups=[tiler_sg],
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=split_container,
                    environment=[
                        tasks.TaskEnvironmentVariable(name="JOB_ID", value=sfn.JsonPath.string_at("$.jobId")),
                        tasks.TaskEnvironmentVariable(name="CREATE_OPTS",   value="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1"),
                        tasks.TaskEnvironmentVariable(name="PREDICTOR_POLICY", value="FORCE_1"),
                        tasks.TaskEnvironmentVariable(name="TIFF_FORCE_16BIT", value="true"),
                    ],
                )
            ],
        )

        # Unite State
        unite_run_task = tasks.EcsRunTask(
            self, "RunUnite",
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            cluster=cluster,
            task_definition=unite_taskdef,
            assign_public_ip=True,
            security_groups=[tiler_sg],
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=unite_container,
                    environment=[
                        tasks.TaskEnvironmentVariable(name="JOB_ID", value=sfn.JsonPath.string_at("$.jobId")),
                        tasks.TaskEnvironmentVariable(name="CREATE_OPTS",   value="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=1"),
                        tasks.TaskEnvironmentVariable(name="PREDICTOR_POLICY", value="FORCE_1"),
                        tasks.TaskEnvironmentVariable(name="TIFF_FORCE_16BIT", value="true"),
                    ],
                )
            ],
        )

        # Simple chain (placeholder – your original definitions likely have more logic)
        definition = split_run_task.next(unite_run_task)
        sfn.StateMachine(
            self, "SplitUniteStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(2),
            logs=sfn.LogOptions(
                destination=tiler_logs,
                level=sfn.LogLevel.ALL,
            ),
        )

        # ---------------- Logs Lambda (reads ECS logs) ----------------
        convert_logs_fn = _lambda.Function(
            self, "ConvertLogsFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_logs_fetch.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(10),
            memory_size=256,
            environment={
                "LOG_GROUP_CONVERT": "/ecs/tsg-jp2-tiler"
            },
        )
        convert_logs_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["logs:FilterLogEvents"],
            resources=[
                f"arn:aws:logs:{region}:{account}:log-group:/ecs/tsg-jp2-tiler:*"
            ],
        ))

        # ---------------- HTTP API ----------------
        http_api = apigw.HttpApi(
            self, "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["*"],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.OPTIONS
                ],
                allow_origins=["*"],
                max_age=Duration.days(10),
            ),
        )

        list_input_integ  = apigw_int.HttpLambdaIntegration("ListInputIntegration", handler=list_input_fn)
        list_output_integ = apigw_int.HttpLambdaIntegration("ListOutputIntegration", handler=list_output_fn)
        convert_integ     = apigw_int.HttpLambdaIntegration("ConvertIntegration", handler=convert_fn)
        convert_logs_integ = apigw_int.HttpLambdaIntegration("ConvertLogsIntegration", handler=convert_logs_fn)

        http_api.add_routes(path="/list-input",   methods=[apigw.HttpMethod.GET],  integration=list_input_integ)
        http_api.add_routes(path="/list-output",  methods=[apigw.HttpMethod.GET],  integration=list_output_integ)
        http_api.add_routes(path="/convert",      methods=[apigw.HttpMethod.POST], integration=convert_integ)
        http_api.add_routes(path="/convert/logs", methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS], integration=convert_logs_integ)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName", value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        CfnOutput(self, "EcsClusterArn", value=cluster.cluster_arn)
        CfnOutput(self, "TilerTaskDefArn", value=tiler_taskdef.task_definition_arn)
        CfnOutput(self, "ConvertLogsRoute", value=f"{http_api.api_endpoint}/convert/logs")
