"""
seed-provider-registry.py — Populate ProviderRegistry table with AWS config.

Values are extracted directly from the existing hardcoded constants in:
- member-handler/lambda_function.py
- agent-action/lambda_function.py
- admin-handler/lambda_function.py
- members/members.js

Run standalone: python infrastructure/seed-provider-registry.py
"""

import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('ProviderRegistry')

SEED_DATA = [
    # ─────────────────────────────────────────────────────────────────────
    # 1. display — Provider branding and metadata
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'display',
        'config': {
            'name': 'Amazon Web Services',
            'icon_url': '/assets/aws-icon.svg',
            'brand_color': '#FF9900',
            'description': 'AWS Cloud Cost Management',
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 2. auth — Cross-account authentication configuration
    # Extracted from: agent-action/lambda_function.py _assume_role()
    #                  member-handler/lambda_function.py
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'auth',
        'config': {
            'auth_type': 'sts_assume_role',
            'role_arn_pattern': 'arn:aws:iam::{accountId}:role/SlashMyBill-{accountId}',
            'external_id_derivation': 'sha256_member_email',
            'session_duration_seconds': 3600,
            'required_iam_actions': [
                'ce:GetCostAndUsage',
                'ce:GetCostForecast',
                'ce:GetReservationUtilization',
                'ce:GetReservationCoverage',
                'ce:GetSavingsPlansUtilization',
                'ce:GetSavingsPlansCoverage',
                'ce:GetSavingsPlansPurchaseRecommendation',
                'ce:GetReservationPurchaseRecommendation',
                'ce:GetRightsizingRecommendation',
                'ce:GetCostCategories',
                'ce:GetDimensionValues',
                'ce:GetTags',
                'ce:ListCostAllocationTags',
                'ce:GetApproximateUsageRecords',
                'ce:UpdatePreferences',
                'ce:GetPreferences',
                'ce:GetCostAndUsageWithResources',
                'invoicing:ListInvoiceSummaries',
                'savingsplans:DescribeSavingsPlans',
                'budgets:ViewBudget',
                'budgets:DescribeBudgets',
                'budgets:DescribeBudgetActionsForAccount',
                'budgets:*',
                'cost-optimization-hub:ListRecommendations',
                'cost-optimization-hub:GetRecommendation',
                'cur:DescribeReportDefinitions',
                'cur:GetClassicReport',
                'cur:GetUsageReport',
                'billing:GetBillingData',
                'billing:GetBillingDetails',
                'support:DescribeTrustedAdvisorChecks',
                'support:DescribeTrustedAdvisorCheckResult',
                'cloudformation:DeleteStack',
                'cloudformation:UpdateStack',
                'cloudformation:CreateStack',
                'cloudformation:DescribeStacks',
                'cloudformation:DescribeStackResources',
                'cloudformation:GetTemplate',
                'iam:GetRole',
                'iam:ListRolePolicies',
                'iam:ListAttachedRolePolicies',
                'iam:DeleteRolePolicy',
                'iam:DetachRolePolicy',
                'iam:DeleteRole',
                'iam:CreateRole',
                'iam:PutRolePolicy',
                'iam:AttachRolePolicy',
                'iam:TagRole',
                'iam:PassRole',
                'ec2:ReleaseAddress',
                'ec2:DeleteVolume',
                'elasticloadbalancing:DeleteLoadBalancer',
                's3:PutBucketLifecycleConfiguration',
                's3:GetBucketLifecycleConfiguration',
                's3:GetBucketLocation',
                's3:ListBucketMultipartUploads',
                's3:AbortMultipartUpload',
                's3:ListBucket',
                's3:GetObject',
                's3:HeadObject',
                's3:DeleteObject',
                's3:DeleteObjects',
                'ec2:StopInstances',
                'ec2:TerminateInstances',
                'ec2:DescribeInstanceAttribute',
                'ec2:ModifyInstanceAttribute',
                'autoscaling:DescribeAutoScalingInstances',
                'autoscaling:DetachInstances',
                'autoscaling:UpdateAutoScalingGroup',
                'ec2:DeleteSnapshot',
                'rds:DeleteDBInstance',
                'rds:DescribeDBInstances',
                'tag:GetResources',
                'tag:GetTagKeys',
                'tag:GetTagValues',
                'tag:TagResources',
                'tag:UntagResources',
                'ec2:CreateTags',
                'ec2:DeleteTags',
                'rds:AddTagsToResource',
                'rds:RemoveTagsFromResource',
                's3:PutBucketTagging',
                's3:GetBucketTagging',
                's3:PutObjectTagging',
                's3:DeleteObjectTagging',
                'elasticloadbalancing:AddTags',
                'elasticloadbalancing:RemoveTags',
                'sqs:TagQueue',
                'sqs:UntagQueue',
                'logs:TagLogGroup',
                'logs:UntagLogGroup',
                'dynamodb:TagResource',
                'dynamodb:UntagResource',
                'lambda:TagResource',
                'lambda:UntagResource',
                'sns:TagResource',
                'sns:UntagResource',
                'kms:TagResource',
                'kms:UntagResource',
                'es:AddTags',
                'es:RemoveTags',
                'elasticache:AddTagsToResource',
                'elasticache:RemoveTagsFromResource',
                'ecs:TagResource',
                'ecs:UntagResource',
                'eks:TagResource',
                'eks:UntagResource',
                'secretsmanager:TagResource',
                'secretsmanager:UntagResource',
                'cloudwatch:TagResource',
                'cloudwatch:UntagResource',
                'kinesis:AddTagsToStream',
                'kinesis:RemoveTagsFromStream',
                'redshift:CreateTags',
                'redshift:DeleteTags',
                'glue:TagResource',
                'glue:UntagResource',
                'stepfunctions:TagResource',
                'stepfunctions:UntagResource',
                'sagemaker:AddTags',
                'sagemaker:DeleteTags',
                'ec2:StartInstances',
                'rds:StopDBInstance',
                'rds:StartDBInstance',
                'eks:UpdateNodegroupConfig',
                'eks:DescribeNodegroup',
                'sagemaker:StopNotebookInstance',
                'sagemaker:StartNotebookInstance',
                'redshift:PauseCluster',
                'redshift:ResumeCluster',
                'workspaces:ModifyWorkspaceProperties',
                'ec2:ModifyVolume',
                'ce:GetAnomalyMonitors',
                'ce:GetAnomalySubscriptions',
                'ce:ListCostAllocationTagBackfillHistory',
                'compute-optimizer:GetEnrollmentStatus',
                'organizations:DescribeOrganization',
                'ce:UpdateCostAllocationTagsStatus',
                'ce:CreateAnomalyMonitor',
                'ce:CreateAnomalySubscription',
                'ce:StartCostAllocationTagBackfill',
                'compute-optimizer:UpdateEnrollmentStatus',
                'freetier:GetFreeTierUsage',
                'ec2:DescribeReservedInstancesOfferings',
            ],
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 3. validation — Account ID validation rules
    # Extracted from: member-handler/lambda_function.py (account ID regex)
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'validation',
        'config': {
            'account_id_regex': r'^\d{12}$',
            'format_description': '12-digit AWS Account ID',
            'placeholder': '123456789012',
            'error_messages': {
                'invalid_format': 'Please enter a valid 12-digit AWS Account ID',
                'empty': 'Account ID is required',
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 4. cost-api — Cost Explorer API configuration
    # Extracted from: agent-action/lambda_function.py _get_cost_data_direct()
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'cost-api',
        'config': {
            'service': 'ce',
            'method': 'get_cost_and_usage',
            'granularities': ['DAILY', 'MONTHLY'],
            'group_by_dimensions': ['SERVICE', 'LINKED_ACCOUNT', 'USAGE_TYPE'],
            'date_format': '%Y-%m-%d',
            'metrics': ['UnblendedCost', 'BlendedCost', 'AmortizedCost'],
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 5. resource-discovery — Per-resource-type API configurations
    # Extracted from: agent-action/lambda_function.py, member-handler/lambda_function.py
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'resource-discovery',
        'config': {
            'resource_types': {
                'ec2': {
                    'service': 'ec2',
                    'method': 'describe_instances',
                    'pagination_token': 'NextToken',
                    'response_list_path': 'Reservations[].Instances[]',
                    'attributes': {
                        'id': 'InstanceId',
                        'type': 'InstanceType',
                        'state': 'State.Name',
                        'launch_time': 'LaunchTime',
                        'name': "Tags[?Key=='Name'].Value | [0]",
                    },
                },
                'rds': {
                    'service': 'rds',
                    'method': 'describe_db_instances',
                    'pagination_token': 'Marker',
                    'response_list_path': 'DBInstances',
                    'attributes': {
                        'id': 'DBInstanceIdentifier',
                        'type': 'DBInstanceClass',
                        'engine': 'Engine',
                        'state': 'DBInstanceStatus',
                        'multi_az': 'MultiAZ',
                    },
                },
                'lambda': {
                    'service': 'lambda',
                    'method': 'list_functions',
                    'pagination_token': 'NextMarker',
                    'response_list_path': 'Functions',
                    'attributes': {
                        'name': 'FunctionName',
                        'runtime': 'Runtime',
                        'memory': 'MemorySize',
                        'timeout': 'Timeout',
                        'last_modified': 'LastModified',
                    },
                },
                's3': {
                    'service': 's3',
                    'method': 'list_buckets',
                    'pagination_token': None,
                    'response_list_path': 'Buckets',
                    'attributes': {
                        'name': 'Name',
                        'created': 'CreationDate',
                    },
                },
                'ebs': {
                    'service': 'ec2',
                    'method': 'describe_volumes',
                    'pagination_token': 'NextToken',
                    'response_list_path': 'Volumes',
                    'attributes': {
                        'id': 'VolumeId',
                        'size_gb': 'Size',
                        'type': 'VolumeType',
                        'state': 'State',
                        'iops': 'Iops',
                    },
                },
                'nat': {
                    'service': 'ec2',
                    'method': 'describe_nat_gateways',
                    'pagination_token': 'NextToken',
                    'response_list_path': 'NatGateways',
                    'attributes': {
                        'id': 'NatGatewayId',
                        'vpc_id': 'VpcId',
                        'subnet_id': 'SubnetId',
                        'state': 'State',
                    },
                },
                'vpc': {
                    'service': 'ec2',
                    'method': 'describe_vpc_endpoints',
                    'pagination_token': 'NextToken',
                    'response_list_path': 'VpcEndpoints',
                    'attributes': {
                        'id': 'VpcEndpointId',
                        'type': 'VpcEndpointType',
                        'service_name': 'ServiceName',
                        'state': 'State',
                    },
                },
                'eks': {
                    'service': 'eks',
                    'method': 'list_clusters',
                    'pagination_token': 'nextToken',
                    'response_list_path': 'clusters',
                    'attributes': {
                        'name': 'clusterName',
                    },
                },
                'ecs': {
                    'service': 'ecs',
                    'method': 'list_clusters',
                    'pagination_token': 'nextToken',
                    'response_list_path': 'clusterArns',
                    'attributes': {
                        'arn': 'clusterArn',
                    },
                },
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 6. connection-setup — CloudFormation template generation parameters
    # Extracted from: member-handler/lambda_function.py
    # Platform account: 991105135552
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'connection-setup',
        'config': {
            'template_type': 'cloudformation',
            'role_name_pattern': 'SlashMyBill-{accountId}',
            'trust_policy': {
                'Version': '2012-10-17',
                'Statement': [{
                    'Effect': 'Allow',
                    'Principal': {'AWS': 'arn:aws:iam::991105135552:root'},
                    'Action': 'sts:AssumeRole',
                    'Condition': {
                        'StringEquals': {'sts:ExternalId': '{externalId}'},
                    },
                }],
            },
            'managed_policy_arns': [],
            'console_urls': {
                'cloudformation': 'https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?stackName=SlashMyBill-Access&templateURL={templateUrl}',
                'iam': 'https://console.aws.amazon.com/iam/home#/roles',
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 7. scheduler-actions — Supported scheduler operations
    # Extracted from: member-handler/lambda_function.py, scheduler-executor/lambda_function.py
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'scheduler-actions',
        'config': {
            'actions': {
                'ec2': {
                    'stop': {
                        'service': 'ec2',
                        'method': 'stop_instances',
                        'params': ['InstanceIds'],
                        'description': 'Stop EC2 instances',
                    },
                    'start': {
                        'service': 'ec2',
                        'method': 'start_instances',
                        'params': ['InstanceIds'],
                        'description': 'Start EC2 instances',
                    },
                },
                'rds': {
                    'stop': {
                        'service': 'rds',
                        'method': 'stop_db_instance',
                        'params': ['DBInstanceIdentifier'],
                        'description': 'Stop RDS instance',
                    },
                    'start': {
                        'service': 'rds',
                        'method': 'start_db_instance',
                        'params': ['DBInstanceIdentifier'],
                        'description': 'Start RDS instance',
                    },
                },
                'eks': {
                    'scale_down': {
                        'service': 'eks',
                        'method': 'update_nodegroup_config',
                        'params': ['clusterName', 'nodegroupName', 'scalingConfig'],
                        'description': 'Scale down EKS nodegroup',
                    },
                    'scale_up': {
                        'service': 'eks',
                        'method': 'update_nodegroup_config',
                        'params': ['clusterName', 'nodegroupName', 'scalingConfig'],
                        'description': 'Scale up EKS nodegroup',
                    },
                },
                'ecs': {
                    'scale_down': {
                        'service': 'ecs',
                        'method': 'update_service',
                        'params': ['cluster', 'service', 'desiredCount'],
                        'description': 'Scale down ECS service',
                    },
                    'scale_up': {
                        'service': 'ecs',
                        'method': 'update_service',
                        'params': ['cluster', 'service', 'desiredCount'],
                        'description': 'Scale up ECS service',
                    },
                },
                'sagemaker': {
                    'stop': {
                        'service': 'sagemaker',
                        'method': 'stop_notebook_instance',
                        'params': ['NotebookInstanceName'],
                        'description': 'Stop SageMaker notebook instance',
                    },
                    'start': {
                        'service': 'sagemaker',
                        'method': 'start_notebook_instance',
                        'params': ['NotebookInstanceName'],
                        'description': 'Start SageMaker notebook instance',
                    },
                },
                'redshift': {
                    'pause': {
                        'service': 'redshift',
                        'method': 'pause_cluster',
                        'params': ['ClusterIdentifier'],
                        'description': 'Pause Redshift cluster',
                    },
                    'resume': {
                        'service': 'redshift',
                        'method': 'resume_cluster',
                        'params': ['ClusterIdentifier'],
                        'description': 'Resume Redshift cluster',
                    },
                },
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 8. pricing — Instance pricing tables and Pricing API config
    # Extracted from: design document pricing category schema
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'pricing',
        'config': {
            'instance_pricing': {
                't3.micro': '0.0104',
                't3.small': '0.0208',
                't3.medium': '0.0416',
                'm5.large': '0.096',
                'm5.xlarge': '0.192',
            },
            'platform_multipliers': {
                'Linux': '1.0',
                'Windows': '1.46',
                'RHEL': '1.3',
                'SUSE': '1.2',
            },
            'pricing_api': {
                'service_code': 'AmazonEC2',
                'filters': {
                    'operatingSystem': 'Linux',
                    'tenancy': 'Shared',
                    'capacitystatus': 'Used',
                    'preInstalledSw': 'NA',
                },
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 9. ai-prompts — AI system prompt fragments and response templates
    # Extracted from: design document ai-prompts category schema
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'ai-prompts',
        'config': {
            'system_prompt_fragments': {
                'cost_optimization_context': 'You are a cloud cost optimization expert specializing in AWS. Analyze costs, identify waste, and recommend savings opportunities using Reserved Instances, Savings Plans, rightsizing, and resource cleanup.',
                'service_explanations': {
                    'AmazonEC2': 'EC2 provides resizable compute capacity in the cloud. Key cost drivers: instance type, running hours, and pricing model (On-Demand vs Reserved vs Spot).',
                    'AmazonRDS': 'RDS is a managed relational database service. Key cost drivers: instance class, storage type/size, Multi-AZ deployment, and backup retention.',
                    'AmazonS3': 'S3 is object storage with industry-leading scalability. Key cost drivers: storage class, data volume, request counts, and data transfer.',
                    'AWSLambda': 'Lambda is serverless compute that runs code in response to events. Key cost drivers: number of invocations, duration, and memory allocated.',
                    'AmazonEBS': 'EBS provides block-level storage volumes for EC2. Key cost drivers: volume type (gp2/gp3/io1), size, provisioned IOPS, and snapshots.',
                    'AmazonVPC': 'VPC provides isolated cloud networking. Key cost drivers: NAT Gateways, VPC Endpoints, data transfer between AZs and regions.',
                    'AmazonEKS': 'EKS is managed Kubernetes. Key cost drivers: cluster fee ($0.10/hr), worker node EC2 instances, and Fargate pod compute.',
                    'AmazonECS': 'ECS is container orchestration. Key cost drivers: underlying EC2 instances or Fargate vCPU/memory hours.',
                },
            },
            'pricing_rules': {
                'reserved_discount': 'Up to 72% savings with 3-year All Upfront RI',
                'spot_discount': 'Up to 90% savings for fault-tolerant workloads',
                'savings_plans': 'Up to 66% savings with 1-year Compute Savings Plan',
            },
            'response_templates': {
                'cost_summary': 'Your {service} costs for {period}: ${amount}',
                'savings_opportunity': 'Potential savings: ${amount}/month by {action}',
            },
        },
    },

    # ─────────────────────────────────────────────────────────────────────
    # 10. ui-config — Frontend display mappings and interaction templates
    # Extracted from: members/members.js (svcTopicMap, service display names)
    # ─────────────────────────────────────────────────────────────────────
    {
        'providerId': 'aws',
        'configCategory': 'ui-config',
        'config': {
            'service_display_names': {
                'AmazonEC2': 'EC2 Instances',
                'AmazonRDS': 'RDS Databases',
                'AmazonS3': 'S3 Storage',
                'AWSLambda': 'Lambda Functions',
                'AmazonEBS': 'EBS Volumes',
                'AmazonVPC': 'VPC & Networking',
                'AmazonEKS': 'EKS Clusters',
                'AmazonECS': 'ECS Services',
                'AmazonCloudWatch': 'CloudWatch',
                'AmazonRoute53': 'Route 53',
                'AmazonCloudFront': 'CloudFront',
                'AmazonElastiCache': 'ElastiCache',
                'AmazonDynamoDB': 'DynamoDB',
                'AWSKeyManagementService': 'KMS',
                'AmazonElasticLoadBalancing': 'Load Balancers',
            },
            'follow_up_questions': [
                'What are my top cost drivers this month?',
                'How can I reduce my EC2 spending?',
                'Show me unused resources I can delete',
                'What savings plans should I consider?',
            ],
            'topic_to_service_mapping': {
                'compute': ['AmazonEC2', 'AWSLambda', 'AmazonECS', 'AmazonEKS'],
                'storage': ['AmazonS3', 'AmazonEBS'],
                'database': ['AmazonRDS', 'AmazonDynamoDB'],
                'networking': ['AmazonVPC', 'AmazonElasticLoadBalancing', 'AmazonCloudFront'],
            },
            'service_topic_map': {
                'Amazon Relational Database Service': 'Is my RDS right-sized? Show CPU and pricing options',
                'Amazon Elastic Compute Cloud - Compute': 'Are my EC2 instances right-sized? Show Savings Plan options',
                'EC2 - Other': 'Break down my EC2-Other costs (EBS, NAT, data transfer)',
                'Amazon Virtual Private Cloud': 'Break down my VPC costs and find idle resources',
                'Amazon Elastic Load Balancing': 'Are any of my load balancers idle or underused?',
                'AWS Key Management Service': 'List my KMS keys and which are unused',
                'Amazon Simple Storage Service': 'Analyze my S3 buckets for storage class optimization',
                'AWS Lambda': 'Show my Lambda functions with invocation counts and errors',
                'AmazonCloudWatch': 'Can I reduce my CloudWatch costs?',
                'Amazon Route 53': 'List my Route 53 hosted zones with record counts',
                'Amazon CloudFront': 'How can I optimize my CloudFront cache hit ratio?',
                'Amazon ElastiCache': 'Is my ElastiCache right-sized? Show CPU and memory usage',
                'Amazon DynamoDB': 'Should my DynamoDB tables use on-demand or provisioned capacity?',
                'Amazon Elastic Container Service': 'Show my ECS clusters with running tasks and utilization',
                'Amazon Elastic Kubernetes Service': 'Show my EKS clusters with status and version',
                'AWS Secrets Manager': 'How many secrets do I have and can I consolidate?',
                'Amazon Elastic Block Store': 'List my EBS volumes with IOPS usage and rightsizing',
                'Amazon Elastic Container Registry (ECR)': 'Can I clean up old ECR images to save storage?',
                'AWS Config': 'Can I reduce AWS Config costs by limiting recorded resources?',
                'Amazon GuardDuty': 'What is my GuardDuty finding volume and cost breakdown?',
                'AWS Security Hub': 'Can I optimize Security Hub by disabling unused standards?',
                'Amazon Bedrock': 'What is my Bedrock model usage and cost per invocation?',
            },
        },
    },
]


def seed():
    """Write all seed data items to the ProviderRegistry table using batch_writer."""
    now = datetime.now(timezone.utc).isoformat()

    with table.batch_writer() as batch:
        for item in SEED_DATA:
            item['version'] = 1
            item['updatedAt'] = now
            batch.put_item(Item=item)

    print(f"Seeded {len(SEED_DATA)} items to ProviderRegistry table")
    print("Categories seeded:")
    for item in SEED_DATA:
        print(f"  - {item['configCategory']}")


if __name__ == '__main__':
    seed()
