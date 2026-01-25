from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
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
    aws_ecr_assets as ecr_assets,
)
from aws_cdk import aws_s3_notifications as s3n
from constructs import Construct
import os


SAFE_CREATE_OPTS = "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,NBITS=16,PREDICTOR=1"
SAFE_ENV_FLAGS = {
    "CREATE_OPTS": SAFE_CREATE_OPTS,
    "PREDICTOR_POLICY": "FORCE_1",
    "TIFF_FORCE_16BIT": "true",
    "SANITIZE_PREDICTOR": "1",
}

PASS_ROLE_CONDITION_KEY = "StringEquals"
PASS_ROLE_CONDITION_VALUE = {
    "iam:PassedToService": "ecs-tasks.amazonaws.com"
}


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
            bucket_name=f"jp2-ui-{account}-{region}"
        )

        # ---------------- UI Deployment ----------------
        ui_dir = os.path.join(os.path.dirname(__file__), "..", "ui")
        if os.path.isdir(ui_dir):
            s3deploy.BucketDeployment(
                self,
                "UiDeployment",
                sources=[s3deploy.Source.asset(ui_dir)],
                destination_bucket=ui_bucket,
            )

        lambda_code_dir = os.path.join(os.path.dirname(__file__), "lambda")

        ui_origin = ui_bucket.bucket_website_url
        list_input_fn = _lambda.Function(
            self, "ListInputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "UI_ORIGIN": ui_origin,
            },
        )
        input_bucket.grant_read(list_input_fn)

        list_output_fn = _lambda.Function(
            self, "ListOutputFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_list_input.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                "INPUT_BUCKET": output_bucket.bucket_name,
                "UI_ORIGIN": ui_origin,
            },
        )
        output_bucket.grant_read(list_output_fn)

        rsjson_fn = _lambda.Function(
            self, "RsJsonFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_envi_to_rawjson.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "DEFAULT_BUCKET": output_bucket.bucket_name,
            },
        )
        output_bucket.grant_read_write(rsjson_fn)
        output_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(rsjson_fn),
            s3.NotificationKeyFilter(suffix=".bin"),
        )

        # ---------------- ECS / VPC ----------------
        vpc = ec2.Vpc.from_lookup(self, "Vpc", is_default=True)
        cluster = ecs.Cluster(self, "TilerCluster", vpc=vpc)

        tiler_logs = logs.LogGroup.from_log_group_name(
            self,
            "TilerLogGroup",
            log_group_name="/ecs/tsg-jp2-tiler",
        )

        # Task role shared
        tiler_task_role = iam.Role(
            self,
            "TilerTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        tiler_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[input_bucket.bucket_arn, input_bucket.arn_for_objects("*")],
            )
        )
        # include GetObject for output (fix 403 on Head/Get)
        tiler_task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload", "s3:ListBucket"],
                resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")],
            )
        )

        # Base TaskDef (used by split/unite)
        tiler_image_dir = os.path.join(os.path.dirname(__file__), "docker", "tiler")
        tiler_image_asset = ecr_assets.DockerImageAsset(
            self, "TilerImageAsset", directory=tiler_image_dir
        )
        tiler_container_image = ecs.ContainerImage.from_docker_image_asset(tiler_image_asset)

        tiler_taskdef = ecs.FargateTaskDefinition(
            self,
            "TilerTaskDef",
            cpu=1024,
            memory_limit_mib=2048,
            runtime_platform=ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.X86_64),
            task_role=tiler_task_role,
        )

        # Keep container name "tiler"
        tiler_taskdef.add_container(
            "tiler",
            image=tiler_container_image,
            essential=True,
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="tiler", log_group=tiler_logs
            ),
            environment={**SAFE_ENV_FLAGS},
        )

        # Dedicated Convert TaskDef (same container name "tiler", isolates convert env)
        convert_taskdef = ecs.FargateTaskDefinition(
            self,
            "ConvertTaskDef",
            cpu=1024,
            memory_limit_mib=2048,
            runtime_platform=ecs.RuntimePlatform(cpu_architecture=ecs.CpuArchitecture.X86_64),
            task_role=tiler_task_role,
        )
        convert_taskdef.add_container(
            "tiler",  # must match overrides
            image=tiler_container_image,
            essential=True,
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="converter", log_group=tiler_logs
            ),
            environment={
                **SAFE_ENV_FLAGS,
                "MODE": "convert",
                "GDAL_NUM_THREADS": "ALL_CPUS",
                "GDAL_CACHEMAX": "512",
            },
        )

        # ----- EXECUTION ROLES: Inline perms (no managed policy attach) -----
        repo_arn = tiler_image_asset.repository.repository_arn
        # Allow task execution roles to pull the asset image
        tiler_image_asset.repository.grant_pull(tiler_taskdef.obtain_execution_role())
        tiler_image_asset.repository.grant_pull(convert_taskdef.obtain_execution_role())

        # CW Logs ARNs for stream creation/puts
        log_group_arn = f"arn:aws:logs:{region}:{account}:log-group:/ecs/tsg-jp2-tiler"
        log_group_wild = f"{log_group_arn}:*"

        exec_role_base = tiler_taskdef.obtain_execution_role()
        exec_role_conv = convert_taskdef.obtain_execution_role()
        for exec_role in (exec_role_base, exec_role_conv):
            # ECR auth + pull
            exec_role.add_to_policy(
                iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
            )
            exec_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:BatchGetImage",
                        "ecr:GetDownloadUrlForLayer",
                    ],
                    resources=[repo_arn],
                )
            )
            # CloudWatch Logs (log driver)
            exec_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                    ],
                    resources=[log_group_arn, log_group_wild],
                )
            )

        tiler_sg = ec2.SecurityGroup(
            self, "TilerTaskSG", vpc=vpc, allow_all_outbound=True
        )
        public_subnet_ids = [s.subnet_id for s in vpc.public_subnets]

        # ---------------- Convert Lambda (ECS launcher) ----------------
        convert_fn = _lambda.Function(
            self,
            "ConvertFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="converter.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=2048,
            environment={
                **SAFE_ENV_FLAGS,
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "ECS_CLUSTER_ARN": cluster.cluster_arn,
                "TASK_DEF_ARN": convert_taskdef.task_definition_arn,
                "SUBNET_IDS": ",".join(public_subnet_ids),
                "SECURITY_GROUP_ID": tiler_sg.security_group_id,
                "ASSIGN_PUBLIC_IP": "ENABLED",
                "MODE": "convert",
            },
        )
        convert_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["ecs:RunTask", "ecs:DescribeTasks"], resources=["*"])
        )
        # Pass TASK ROLE
        convert_pass_task = iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
        )
        convert_pass_task.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        convert_fn.add_to_role_policy(convert_pass_task)
        # Pass EXECUTION ROLE (convert taskdef)
        convert_exec_role = convert_taskdef.obtain_execution_role()
        convert_pass_exec = iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[convert_exec_role.role_arn],
        )
        convert_pass_exec.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        convert_fn.add_to_role_policy(convert_pass_exec)
        # S3 read if needed by lambda
        convert_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket", "s3:GetObject"],
                resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")],
            )
        )

        # ---------------- Split/Unite State Machines ----------------
        split_task = tasks.EcsRunTask(
            self,
            "RunSplitOnFargate",
            cluster=cluster,
            task_definition=tiler_taskdef,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            assign_public_ip=True,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=tiler_taskdef.default_container,
                    environment=[
                        tasks.TaskEnvironmentVariable(
                            name="INPUT_BUCKET",
                            value=sfn.JsonPath.string_at("$.inputBucket"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="OUTPUT_BUCKET",
                            value=sfn.JsonPath.string_at("$.outputBucket"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="INPUT_KEY",
                            value=sfn.JsonPath.string_at("$.inputKey"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="FORMAT_OPTION",
                            value=sfn.JsonPath.string_at("$.params.formatOption"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TILES_TOTAL",
                            value=sfn.JsonPath.string_at("$.params.tilesTotal"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TILES_GRID",
                            value=sfn.JsonPath.string_at("$.params.tilesGrid"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="JOB_ID", value=sfn.JsonPath.string_at("$.jobId")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="CREATE_OPTS", value=SAFE_CREATE_OPTS
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="PREDICTOR_POLICY",
                            value=SAFE_ENV_FLAGS["PREDICTOR_POLICY"],
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TIFF_FORCE_16BIT",
                            value=SAFE_ENV_FLAGS["TIFF_FORCE_16BIT"],
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="SANITIZE_PREDICTOR",
                            value=SAFE_ENV_FLAGS["SANITIZE_PREDICTOR"],
                        ),
                    ],
                )
            ],
            result_path="$.ecsResult",
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            security_groups=[tiler_sg],
        )

        split_state_machine = sfn.StateMachine(
            self, "SplitStateMachine", definition=split_task, timeout=Duration.minutes(60)
        )
        split_state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask", "ecs:DescribeTasks"],
                resources=[tiler_taskdef.task_definition_arn],
            )
        )
        # Pass TASK ROLE
        split_pass_task = iam.PolicyStatement(
            actions=["iam:PassRole"], resources=[tiler_task_role.role_arn]
        )
        split_pass_task.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        split_state_machine.add_to_role_policy(split_pass_task)
        # Pass EXECUTION ROLE (base taskdef)
        split_exec_role = tiler_taskdef.obtain_execution_role()
        split_pass_exec = iam.PolicyStatement(
            actions=["iam:PassRole"], resources=[split_exec_role.role_arn]
        )
        split_pass_exec.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        split_state_machine.add_to_role_policy(split_pass_exec)

        split_controller_fn = _lambda.Function(
            self,
            "SplitControllerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="controller_split.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "INPUT_BUCKET": input_bucket.bucket_name,
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "SPLIT_SFN_ARN": split_state_machine.state_machine_arn,
            },
        )
        split_controller_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[split_state_machine.state_machine_arn],
            )
        )

        unite_task = tasks.EcsRunTask(
            self,
            "RunUniteOnFargate",
            cluster=cluster,
            task_definition=tiler_taskdef,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            assign_public_ip=True,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            container_overrides=[
                tasks.ContainerOverride(
                    container_definition=tiler_taskdef.default_container,
                    environment=[
                        tasks.TaskEnvironmentVariable(name="MODE", value="unite"),
                        tasks.TaskEnvironmentVariable(
                            name="JOB_ID", value=sfn.JsonPath.string_at("$.jobId")
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TILES_PREFIX",
                            value=sfn.JsonPath.string_at("$.tilesPrefix"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="OUTPUT_BUCKET",
                            value=sfn.JsonPath.string_at("$.outputBucket"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="FINAL_KEY",
                            value=sfn.JsonPath.string_at("$.finalKey"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="FORMAT_OPTION",
                            value=sfn.JsonPath.string_at("$.formatOption"),
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="CREATE_OPTS", value=SAFE_CREATE_OPTS
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="PREDICTOR_POLICY",
                            value=SAFE_ENV_FLAGS["PREDICTOR_POLICY"],
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="TIFF_FORCE_16BIT",
                            value=SAFE_ENV_FLAGS["TIFF_FORCE_16BIT"],
                        ),
                        tasks.TaskEnvironmentVariable(
                            name="SANITIZE_PREDICTOR",
                            value=SAFE_ENV_FLAGS["SANITIZE_PREDICTOR"],
                        ),
                    ],
                )
            ],
            result_path="$.ecsResult",
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            security_groups=[tiler_sg],
        )

        unite_state_machine = sfn.StateMachine(
            self, "UniteStateMachine", definition=unite_task, timeout=Duration.minutes(60)
        )
        unite_state_machine.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask", "ecs:DescribeTasks"],
                resources=[tiler_taskdef.task_definition_arn],
            )
        )
        # Pass TASK ROLE
        unite_pass_task = iam.PolicyStatement(
            actions=["iam:PassRole"], resources=[tiler_task_role.role_arn]
        )
        unite_pass_task.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        unite_state_machine.add_to_role_policy(unite_pass_task)
        # Pass EXECUTION ROLE (base taskdef)
        unite_exec_role = tiler_taskdef.obtain_execution_role()
        unite_pass_exec = iam.PolicyStatement(
            actions=["iam:PassRole"], resources=[unite_exec_role.role_arn]
        )
        unite_pass_exec.add_condition(
            PASS_ROLE_CONDITION_KEY, PASS_ROLE_CONDITION_VALUE
        )
        unite_state_machine.add_to_role_policy(unite_pass_exec)

        unite_controller_fn = _lambda.Function(
            self,
            "UniteControllerFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="controller_unite.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "OUTPUT_BUCKET": output_bucket.bucket_name,
                "UNITE_SFN_ARN": unite_state_machine.state_machine_arn,
                "SPLIT_SFN_ARN": split_state_machine.state_machine_arn,
            },
        )
        unite_controller_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:StartExecution"],
                resources=[unite_state_machine.state_machine_arn],
            )
        )

        # ---------------- Convert Logs Lambda ----------------
        convert_logs_fn = _lambda.Function(
            self,
            "ConvertLogsFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_logs_fetch.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "LOG_GROUP_CONVERT": tiler_logs.log_group_name,
            },
        )
        convert_logs_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["logs:FilterLogEvents"],
                resources=[log_group_arn, log_group_wild],
            )
        )

        status_progress_fn = _lambda.Function(
            self,
            "StatusProgressFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="status_progress.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "OUTPUT_BUCKET": output_bucket.bucket_name,
            },
        )
        output_bucket.grant_read(status_progress_fn)

        status_history_fn = _lambda.Function(
            self,
            "StatusHistoryFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="status_history.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "SPLIT_SFN_ARN": split_state_machine.state_machine_arn,
                "UNITE_SFN_ARN": unite_state_machine.state_machine_arn,
            },
        )
        status_history_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["states:GetExecutionHistory", "states:DescribeExecution"],
                resources=["*"],
            )
        )

        # ---------------- HTTP API ----------------
        http_api = apigw.HttpApi(
            self,
            "HttpApi",
            cors_preflight=apigw.CorsPreflightOptions(
                allow_headers=["*"],
                allow_methods=[
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],
                max_age=Duration.days(10),
            ),
        )

        list_input_integ = apigw_int.HttpLambdaIntegration(
            "ListInputIntegration", handler=list_input_fn
        )
        list_output_integ = apigw_int.HttpLambdaIntegration(
            "ListOutputIntegration", handler=list_output_fn
        )
        convert_integ = apigw_int.HttpLambdaIntegration(
            "ConvertIntegration", handler=convert_fn
        )
        split_integ = apigw_int.HttpLambdaIntegration(
            "SplitIntegration", handler=split_controller_fn
        )
        unite_integ = apigw_int.HttpLambdaIntegration(
            "UniteIntegration", handler=unite_controller_fn
        )
        convert_logs_integ = apigw_int.HttpLambdaIntegration(
            "ConvertLogsIntegration", handler=convert_logs_fn
        )
        rsjson_integ = apigw_int.HttpLambdaIntegration(
            "RsJsonIntegration", handler=rsjson_fn
        )
        status_progress_integ = apigw_int.HttpLambdaIntegration(
            "StatusProgressIntegration", handler=status_progress_fn
        )
        status_history_integ = apigw_int.HttpLambdaIntegration(
            "StatusHistoryIntegration", handler=status_history_fn
        )

        http_api.add_routes(
            path="/list-input",
            methods=[apigw.HttpMethod.GET],
            integration=list_input_integ,
        )
        http_api.add_routes(
            path="/list-output",
            methods=[apigw.HttpMethod.GET],
            integration=list_output_integ,
        )
        http_api.add_routes(
            path="/convert",
            methods=[apigw.HttpMethod.POST],
            integration=convert_integ,
        )
        http_api.add_routes(
            path="/split",
            methods=[apigw.HttpMethod.POST],
            integration=split_integ,
        )
        http_api.add_routes(
            path="/unite",
            methods=[apigw.HttpMethod.POST],
            integration=unite_integ,
        )
        http_api.add_routes(
            path="/convert/logs",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS],
            integration=convert_logs_integ,
        )
        http_api.add_routes(
            path="/rawpair/finalize",
            methods=[apigw.HttpMethod.POST],
            integration=rsjson_integ,
        )
        http_api.add_routes(
            path="/status-progress",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS],
            integration=status_progress_integ,
        )
        http_api.add_routes(
            path="/status-history/{proxy+}",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS],
            integration=status_history_integ,
        )
        http_api.add_routes(
            path="/status-detail/{proxy+}",
            methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS],
            integration=status_history_integ,
        )

        # ---------------- File Manager Lambdas ----------------
        fm_env = {
            "INPUT_BUCKET": input_bucket.bucket_name,
            "OUTPUT_BUCKET": output_bucket.bucket_name,
        }

        copy_files_fn = _lambda.Function(
            self,
            "CopyFilesFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_copy_files.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment=fm_env,
        )
        output_bucket.grant_read(copy_files_fn)
        output_bucket.grant_delete(copy_files_fn)
        input_bucket.grant_write(copy_files_fn)

        delete_files_fn = _lambda.Function(
            self,
            "DeleteFilesFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_delete_files.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=fm_env,
        )
        output_bucket.grant_delete(delete_files_fn)

        download_file_fn = _lambda.Function(
            self,
            "DownloadFileFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_download_file.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=fm_env,
        )
        output_bucket.grant_read(download_file_fn)

        copy_files_integ = apigw_int.HttpLambdaIntegration(
            "CopyFilesIntegration", handler=copy_files_fn
        )
        delete_files_integ = apigw_int.HttpLambdaIntegration(
            "DeleteFilesIntegration", handler=delete_files_fn
        )
        download_file_integ = apigw_int.HttpLambdaIntegration(
            "DownloadFileIntegration", handler=download_file_fn
        )

        http_api.add_routes(
            path="/copy-files",
            methods=[apigw.HttpMethod.POST],
            integration=copy_files_integ,
        )
        http_api.add_routes(
            path="/delete-files",
            methods=[apigw.HttpMethod.POST],
            integration=delete_files_integ,
        )
        http_api.add_routes(
            path="/download-file",
            methods=[apigw.HttpMethod.POST],
            integration=download_file_integ,
        )

        # ---------------- Outputs ----------------
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        CfnOutput(self, "UiBucketWebsiteUrl", value=ui_bucket.bucket_website_url)
