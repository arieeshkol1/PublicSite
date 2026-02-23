from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_iam as iam,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct
import json

class Made4NetFortressStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================================
        # 1. COGNITO - Enterprise SSO Simulation
        # ========================================
        user_pool = cognito.UserPool(
            self, "Made4NetUserPool",
            user_pool_name="made4net-fortress-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True
            ),
            mfa=cognito.Mfa.OPTIONAL,
            removal_policy=RemovalPolicy.DESTROY
        )

        user_pool_client = user_pool.add_client(
            "Made4NetWebClient",
            auth_flows=cognito.AuthFlow(user_password=True),
            generate_secret=False
        )

        # ========================================
        # 2. DYNAMODB - Operational Metrics Store
        # ========================================
        metrics_table = dynamodb.Table(
            self, "MetricsTable",
            table_name="made4net-fortress-metrics",
            partition_key=dynamodb.Attribute(
                name="metricType",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.NUMBER
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,  # DR best practice
            encryption=dynamodb.TableEncryption.AWS_MANAGED  # KMS encryption
        )

        # ========================================
        # 3. LAMBDA - Metrics Generator
        # ========================================
        metrics_lambda = lambda_.Function(
            self, "MetricsGenerator",
            function_name="made4net-metrics-generator",
            runtime=lambda_.Runtime.NODEJS_18_X,
            handler="index.handler",
            code=lambda_.Code.from_asset("infrastructure/lambda"),
            environment={
                "METRICS_TABLE": metrics_table.table_name
            },
            timeout=Duration.seconds(30),
            memory_size=256
        )

        metrics_table.grant_read_write_data(metrics_lambda)

        # Lambda for reading metrics
        reader_lambda = lambda_.Function(
            self, "MetricsReader",
            function_name="made4net-metrics-reader",
            runtime=lambda_.Runtime.NODEJS_18_X,
            handler="reader.handler",
            code=lambda_.Code.from_asset("infrastructure/lambda"),
            environment={
                "METRICS_TABLE": metrics_table.table_name
            },
            timeout=Duration.seconds(10),
            memory_size=128
        )

        metrics_table.grant_read_data(reader_lambda)

        # ========================================
        # 4. API GATEWAY - REST API
        # ========================================
        api = apigw.RestApi(
            self, "Made4NetAPI",
            rest_api_name="made4net-fortress-api",
            description="Made4Net Fortress & Factory Monitoring API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "Authorization"]
            ),
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=1000,
                throttling_burst_limit=2000
            )
        )

        # POST /metrics - Generate new metrics
        metrics_resource = api.root.add_resource("metrics")
        metrics_resource.add_method(
            "POST",
            apigw.LambdaIntegration(metrics_lambda)
        )

        # GET /metrics - Read metrics
        metrics_resource.add_method(
            "GET",
            apigw.LambdaIntegration(reader_lambda)
        )

        # GET /health - Health check
        health_resource = api.root.add_resource("health")
        health_resource.add_method(
            "GET",
            apigw.MockIntegration(
                integration_responses=[{
                    "statusCode": "200",
                    "responseTemplates": {
                        "application/json": json.dumps({
                            "status": "healthy",
                            "service": "Made4Net Fortress & Factory",
                            "timestamp": "$context.requestTime"
                        })
                    }
                }],
                request_templates={
                    "application/json": json.dumps({"statusCode": 200})
                }
            ),
            method_responses=[{"statusCode": "200"}]
        )

        # ========================================
        # 5. S3 + CLOUDFRONT - Dashboard Hosting
        # ========================================
        dashboard_bucket = s3.Bucket(
            self, "DashboardBucket",
            bucket_name=f"made4net-fortress-dashboard-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True  # Best practice for compliance
        )

        # CloudFront distribution
        distribution = cloudfront.Distribution(
            self, "DashboardDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(dashboard_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                compress=True
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html"
                )
            ],
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021  # Security best practice
        )

        # Deploy dashboard files
        s3deploy.BucketDeployment(
            self, "DeployDashboard",
            sources=[s3deploy.Source.asset("dashboard")],
            destination_bucket=dashboard_bucket,
            distribution=distribution,
            distribution_paths=["/*"]
        )

        # ========================================
        # OUTPUTS
        # ========================================
        CfnOutput(self, "APIEndpoint",
            value=api.url,
            description="API Gateway endpoint"
        )

        CfnOutput(self, "DashboardURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="CloudFront dashboard URL"
        )

        CfnOutput(self, "UserPoolId",
            value=user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )

        CfnOutput(self, "UserPoolClientId",
            value=user_pool_client.user_pool_client_id,
            description="Cognito Client ID"
        )

        CfnOutput(self, "MetricsTableName",
            value=metrics_table.table_name,
            description="DynamoDB Metrics Table"
        )
