"""
TAG Video Systems - CDK Stack
Serverless Video Probe Monitoring System
"""
from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_lambda_event_sources as lambda_events,
    aws_iam as iam,
    aws_cognito as cognito,
)
from constructs import Construct


class TagVideoProbeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========== Cognito User Pool ==========
        # User authentication
        user_pool = cognito.UserPool(
            self,
            "TagUserPool",
            user_pool_name="tag-video-users",
            self_sign_up_enabled=False,  # Admin creates users
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Create a default user (admin/TagVideo2024!)
        cognito.CfnUserPoolUser(
            self,
            "DefaultUser",
            user_pool_id=user_pool.user_pool_id,
            username="admin",
            user_attributes=[
                cognito.CfnUserPoolUser.AttributeTypeProperty(
                    name="email",
                    value="admin@tagvideo.local"
                )
            ],
            desired_delivery_mediums=["EMAIL"],
        )

        # User Pool Client
        user_pool_client = cognito.UserPoolClient(
            self,
            "TagUserPoolClient",
            user_pool=user_pool,
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            generate_secret=False,
        )

        # ========== DynamoDB Table ==========
        # Hot store for latest probe status
        probe_table = dynamodb.Table(
            self,
            "ProbeStatusTable",
            partition_key=dynamodb.Attribute(
                name="ProbeID", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ========== SQS Queue ==========
        # Shock absorber for telemetry ingestion
        telemetry_queue = sqs.Queue(
            self,
            "TelemetryQueue",
            visibility_timeout=Duration.seconds(30),
            retention_period=Duration.days(1),
        )

        # ========== Lambda Function (Processor) ==========
        # Processes telemetry from SQS and writes to DynamoDB
        processor_lambda = lambda_.Function(
            self,
            "TelemetryProcessor",
            runtime=lambda_.Runtime.NODEJS_18_X,
            handler="index.handler",
            code=lambda_.Code.from_asset("infrastructure/lambda"),
            timeout=Duration.seconds(10),
            environment={
                "TABLE_NAME": probe_table.table_name,
            },
        )

        # Grant Lambda permissions to write to DynamoDB
        probe_table.grant_write_data(processor_lambda)

        # Add SQS as event source for Lambda
        processor_lambda.add_event_source(
            lambda_events.SqsEventSource(telemetry_queue, batch_size=10)
        )

        # ========== API Gateway (Ingestion) ==========
        # Public REST API for telemetry ingestion
        api = apigw.RestApi(
            self,
            "TelemetryAPI",
            rest_api_name="TAG Video Probe API",
            description="Ingestion API for video probe telemetry",
            deploy_options=apigw.StageOptions(stage_name="prod"),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token",
                ],
            ),
        )

        # POST /telemetry endpoint - sends to SQS
        telemetry_resource = api.root.add_resource("telemetry")
        
        # Create IAM role for API Gateway to send to SQS
        api_role = iam.Role(
            self,
            "ApiGatewaySqsRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
        )
        telemetry_queue.grant_send_messages(api_role)

        # Direct SQS integration (no Lambda)
        telemetry_resource.add_method(
            "POST",
            apigw.AwsIntegration(
                service="sqs",
                path=f"{self.account}/{telemetry_queue.queue_name}",
                integration_http_method="POST",
                options=apigw.IntegrationOptions(
                    credentials_role=api_role,
                    request_parameters={
                        "integration.request.header.Content-Type": "'application/x-www-form-urlencoded'"
                    },
                    request_templates={
                        "application/json": "Action=SendMessage&MessageBody=$input.body"
                    },
                    integration_responses=[
                        apigw.IntegrationResponse(
                            status_code="200",
                            response_templates={"application/json": '{"status":"queued"}'},
                            response_parameters={
                                "method.response.header.Access-Control-Allow-Origin": "'*'",
                            },
                        )
                    ],
                ),
            ),
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": True,
                    },
                )
            ],
        )

        # GET /probes endpoint - reads from DynamoDB
        probes_resource = api.root.add_resource("probes")
        
        # Lambda for reading probe status
        reader_lambda = lambda_.Function(
            self,
            "ProbeReader",
            runtime=lambda_.Runtime.NODEJS_18_X,
            handler="reader.handler",
            code=lambda_.Code.from_asset("infrastructure/lambda"),
            timeout=Duration.seconds(5),
            environment={
                "TABLE_NAME": probe_table.table_name,
            },
        )
        probe_table.grant_read_data(reader_lambda)

        probes_resource.add_method(
            "GET",
            apigw.LambdaIntegration(reader_lambda),
        )

        # ========== S3 Dashboard ==========
        # Static website hosting for dashboard
        dashboard_bucket = s3.Bucket(
            self,
            "DashboardBucket",
            website_index_document="index.html",
            public_read_access=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=False,
                block_public_policy=False,
                ignore_public_acls=False,
                restrict_public_buckets=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy dashboard files
        s3deploy.BucketDeployment(
            self,
            "DeployDashboard",
            sources=[s3deploy.Source.asset("dashboard")],
            destination_bucket=dashboard_bucket,
        )

        # ========== Outputs ==========
        CfnOutput(
            self,
            "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
        )

        CfnOutput(
            self,
            "ApiEndpoint",
            value=api.url,
            description="API Gateway endpoint for telemetry ingestion",
        )

        CfnOutput(
            self,
            "DashboardUrl",
            value=dashboard_bucket.bucket_website_url,
            description="Dashboard URL (S3 static website)",
        )

        CfnOutput(
            self,
            "TableName",
            value=probe_table.table_name,
            description="DynamoDB table name",
        )

        CfnOutput(
            self,
            "QueueUrl",
            value=telemetry_queue.queue_url,
            description="SQS queue URL",
        )
