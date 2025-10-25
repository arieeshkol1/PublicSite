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
from aws_cdk import aws_s3_notifications as s3n  # <-- minimal addition
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

        tiler_image_uri = (
            "991105135552.dkr.ecr.us-east-1.amazonaws.com/"
            "cdk-hnb659fds-container-assets-991105135552-us-east-1:"
            "edfcf89c0236c949848d9ccd83d731a69fd6fc85308fa3d3a3313ea50b05a526"
        )

        tiler_taskdef.add_container(
            "tiler",
            image=ecs.ContainerImage.from_registry(tiler_image_uri),
            essential=True,
            logging=ecs.LogDriver.aws_logs(stream_prefix="tiler", log_group=tiler_logs),
            environment={
                # predictor-safe (add NBITS=16 to guarantee compatibility)
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,NBITS=16,PREDICTOR=1",
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
                # predictor-safe (match container defaults)
                "CREATE_OPTS": "TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,NBITS=16,PREDICTOR=1",
                "PREDICTOR_POLICY": "FORCE_1",
                "TIFF_FORCE_16BIT": "true",
            },
        )
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask", "ecs:DescribeTasks"],
            resources=["*"]
        ))
        # Allow passing TASK ROLE
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))
        # Allow passing EXECUTION ROLE (needed for RunTask)  <-- added
        exec_role = tiler_taskdef.obtain_execution_role()
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[exec_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket", "s3:GetObject"],
            resources=[output_bucket.bucket_arn, output_bucket.arn_for_objects("*")]
        ))

        # ---------------- Split/Unite State Machines (unchanged structure) ----------------
        # Split via ECS
        split_task = tasks.EcsRunTask(
            self, "RunSplitOnFargate",
            cluster=cluster,
            task_definition=tiler_taskdef,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            assign_public_ip=True,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            container_overrides=[tasks.ContainerOverride(
                container_definition=tiler_taskdef.default_container,
                environment=[
                    tasks.TaskEnvironmentVariable(name="INPUT_BUCKET",  value=sfn.JsonPath.string_at("$.inputBucket")),
                    tasks.TaskEnvironmentVariable(name="OUTPUT_BUCKET", value=sfn.JsonPath.string_at("$.outputBucket")),
                    tasks.TaskEnvironmentVariable(name="INPUT_KEY",     value=sfn.JsonPath.string_at("$.inputKey")),
                    tasks.TaskEnvironmentVariable(name="FORMAT_OPTION", value=sfn.JsonPath.string_at("$.params.formatOption")),
                    tasks.TaskEnvironmentVariable(name="TILES_TOTAL",   value=sfn.JsonPath.string_at("$.params.tilesTotal")),
                    tasks.TaskEnvironmentVariable(name="TILES_GRID",    value=sfn.JsonPath.string_at("$.params.tilesGrid")),
                    tasks.TaskEnvironmentVariable(name="JOB_ID",        value=sfn.JsonPath.string_at("$.jobId")),
                    # predictor-safe
                    tasks.TaskEnvironmentVariable(name="CREATE_OPTS",   value="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,NBITS=16,PREDICTOR=1"),
                    tasks.TaskEnvironmentVariable(name="PREDICTOR_POLICY", value="FORCE_1"),
                    tasks.TaskEnvironmentVariable(name="TIFF_FORCE_16BIT", value="true"),
                ],
            )],
            result_path="$.ecsResult",
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            security_groups=[tiler_sg],
        )

        split_state_machine = sfn.StateMachine(
            self, "SplitStateMachine",
            definition=split_task,
            timeout=Duration.minutes(60)
        )
        split_state_machine.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask", "ecs:DescribeTasks"],
            resources=[tiler_taskdef.task_definition_arn]
        ))
        split_state_machine.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))

        split_controller_fn = _lambda.Function(
            self, "SplitControllerFn",
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
        split_controller_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["states:StartExecution"],
            resources=[split_state_machine.state_machine_arn]
        ))

        # Unite via ECS
        unite_task = tasks.EcsRunTask(
            self, "RunUniteOnFargate",
            cluster=cluster,
            task_definition=tiler_taskdef,
            launch_target=tasks.EcsFargateLaunchTarget(
                platform_version=ecs.FargatePlatformVersion.LATEST
            ),
            assign_public_ip=True,
            integration_pattern=sfn.IntegrationPattern.RUN_JOB,
            container_overrides=[tasks.ContainerOverride(
                container_definition=tiler_taskdef.default_container,
                environment=[
                    tasks.TaskEnvironmentVariable(name="MODE",          value="unite"),
                    tasks.TaskEnvironmentVariable(name="JOB_ID",        value=sfn.JsonPath.string_at("$.jobId")),
                    tasks.TaskEnvironmentVariable(name="TILES_PREFIX",  value=sfn.JsonPath.string_at("$.tilesPrefix")),
                    tasks.TaskEnvironmentVariable(name="OUTPUT_BUCKET", value=sfn.JsonPath.string_at("$.outputBucket")),
                    tasks.TaskEnvironmentVariable(name="FINAL_KEY",     value=sfn.JsonPath.string_at("$.finalKey")),
                    tasks.TaskEnvironmentVariable(name="FORMAT_OPTION", value=sfn.JsonPath.string_at("$.formatOption")),
                    # predictor-safe
                    tasks.TaskEnvironmentVariable(name="CREATE_OPTS",   value="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,NBITS=16,PREDICTOR=1"),
                    tasks.TaskEnvironmentVariable(name="PREDICTOR_POLICY", value="FORCE_1"),
                    tasks.TaskEnvironmentVariable(name="TIFF_FORCE_16BIT", value="true"),
                ],
            )],
            result_path="$.ecsResult",
            subnets=ec2.SubnetSelection(subnets=vpc.public_subnets),
            security_groups=[tiler_sg],
        )

        unite_state_machine = sfn.StateMachine(
            self, "UniteStateMachine",
            definition=unite_task,
            timeout=Duration.minutes(60)
        )
        unite_state_machine.add_to_role_policy(iam.PolicyStatement(
            actions=["ecs:RunTask", "ecs:DescribeTasks"],
            resources=[tiler_taskdef.task_definition_arn]
        ))
        unite_state_machine.add_to_role_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[tiler_task_role.role_arn],
            conditions={"StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}}
        ))

        unite_controller_fn = _lambda.Function(
            self, "UniteControllerFn",
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
        unite_controller_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["states:StartExecution"],
            resources=[unite_state_machine.state_machine_arn]
        ))

        # ---------------- Convert Logs Lambda ----------------
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

        # ---------------- RAW/JSON Finalizer Lambda (ENVI .bin+.hdr -> .raw + .json) ----------------
        rsjson_fn = _lambda.Function(
            self, "RsJsonFinalizeFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_envi_to_rawjson.handler",  # <-- minimal change (new handler)
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.minutes(2),
            memory_size=512,
            environment={
                "DEFAULT_BUCKET": output_bucket.bucket_name,
            },
        )
        rsjson_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"],
            resources=[output_bucket.bucket_arn]
        ))
        rsjson_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject","s3:PutObject","s3:CopyObject","s3:DeleteObject"],
            resources=[output_bucket.arn_for_objects("*")]
        ))

        # Auto-finalize: trigger on creation of any ENVI .bin in the OUTPUT bucket
        output_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(rsjson_fn),        # <-- minimal addition (S3 trigger)
            s3.NotificationKeyFilter(suffix=".bin"),
        )

        # Allow convert to invoke finalizer if desired
        convert_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["lambda:InvokeFunction"],
            resources=[rsjson_fn.function_arn]
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
        split_integ       = apigw_int.HttpLambdaIntegration("SplitIntegration", handler=split_controller_fn)
        unite_integ       = apigw_int.HttpLambdaIntegration("UniteIntegration", handler=unite_controller_fn)
        convert_logs_integ = apigw_int.HttpLambdaIntegration("ConvertLogsIntegration", handler=convert_logs_fn)
        rsjson_integ      = apigw_int.HttpLambdaIntegration("RsJsonIntegration", handler=rsjson_fn)

        http_api.add_routes(path="/list-input",   methods=[apigw.HttpMethod.GET],  integration=list_input_integ)
        http_api.add_routes(path="/list-output",  methods=[apigw.HttpMethod.GET],  integration=list_output_integ)
        http_api.add_routes(path="/convert",      methods=[apigw.HttpMethod.POST], integration=convert_integ)
        http_api.add_routes(path="/split",        methods=[apigw.HttpMethod.POST], integration=split_integ)
        http_api.add_routes(path="/unite",        methods=[apigw.HttpMethod.POST], integration=unite_integ)
        http_api.add_routes(path="/convert/logs", methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS], integration=convert_logs_integ)
        http_api.add_routes(path="/rawpair/finalize", methods=[apigw.HttpMethod.POST], integration=rsjson_integ)

        # ---------------- File Manager Lambdas ----------------
        fm_env = {"INPUT_BUCKET": input_bucket.bucket_name, "OUTPUT_BUCKET": output_bucket.bucket_name}

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
                resources=[input_bucket.arn_for_objects("*"), output_bucket.arn_for_objects("*")]
            ))

        copy_files_integ     = apigw_int.HttpLambdaIntegration("CopyFilesIntegration", handler=copy_files_fn)
        delete_files_integ   = apigw_int.HttpLambdaIntegration("DeleteFilesIntegration", handler=delete_files_fn)
        download_file_integ  = apigw_int.HttpLambdaIntegration("DownloadFileIntegration", handler=download_file_fn)
        http_api.add_routes(path="/copy-files",   methods=[apigw.HttpMethod.POST], integration=copy_files_integ)
        http_api.add_routes(path="/delete-files", methods=[apigw.HttpMethod.POST], integration=delete_files_integ)
        http_api.add_routes(path="/download-file",methods=[apigw.HttpMethod.POST], integration=download_file_integ)

        # ---------------- Status Lambdas ----------------
        status_progress_fn = _lambda.Function(
            self, "StatusProgressFn",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="status_progress.handler",
            code=_lambda.Code.from_asset(lambda_code_dir),
            timeout=Duration.seconds(20),
            memory_size=256,
            environment={"OUTPUT_BUCKET": output_bucket.bucket_name},
        )
        status_progress_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], resources=[output_bucket.bucket_arn]
        ))
        status_progress_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject"], resources=[output_bucket.arn_for_objects("*")]
        ))
        status_progress_integ = apigw_int.HttpLambdaIntegration("StatusProgressInteg", handler=status_progress_fn)
        http_api.add_routes(path="/status-progress", methods=[apigw.HttpMethod.GET], integration=status_progress_integ)

        status_history_fn = _lambda.Function(
            self, "StatusHistoryFn",
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
        status_history_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["states:GetExecutionHistory", "states:DescribeExecution"],
            resources=["*"]
        ))
        status_history_integ_hist = apigw_int.HttpLambdaIntegration("StatusHistoryInteg", handler=status_history_fn)
        status_history_integ_det  = apigw_int.HttpLambdaIntegration("StatusDetailInteg",  handler=status_history_fn)
        http_api.add_routes(path="/status-history/{jobId}", methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS], integration=status_history_integ_hist)
        http_api.add_routes(path="/status-detail/{executionArn}", methods=[apigw.HttpMethod.GET, apigw.HttpMethod.OPTIONS], integration=status_history_integ_det)

        # ---------------- Outputs ----------------
        CfnOutput(self, "UiBucketName", value="jp2-ui-991105135552-us-east-1")
        CfnOutput(self, "InputBucketName", value=input_bucket.bucket_name)
        CfnOutput(self, "OutputBucketName", value=output_bucket.bucket_name)
        CfnOutput(self, "ApiEndpoint", value=http_api.api_endpoint)
        CfnOutput(self, "EcsClusterArn", value=cluster.cluster_arn)
        CfnOutput(self, "TilerTaskDefArn", value=tiler_taskdef.task_definition_arn)
        CfnOutput(self, "SplitStateMachineArn", value=split_state_machine.state_machine_arn)
        CfnOutput(self, "UniteStateMachineArn", value=unite_state_machine.state_machine_arn)
        CfnOutput(self, "StatusProgressRoute", value=f"{http_api.api_endpoint}/status-progress")
        CfnOutput(self, "StatusHistoryRoute", value=f"{http_api.api_endpoint}/status-history/{{jobId}}")
        CfnOutput(self, "ConvertLogsRoute", value=f"{http_api.api_endpoint}/convert/logs")
        CfnOutput(self, "RsJsonFinalizeRoute", value=f"{http_api.api_endpoint}/rawpair/finalize")
