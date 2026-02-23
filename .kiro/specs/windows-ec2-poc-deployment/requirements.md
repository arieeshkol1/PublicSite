# Requirements Document: Windows EC2 POC Deployment with SSM Integration

## Introduction

This document specifies the requirements for deploying a proof-of-concept (POC) Windows-based warehouse management system on AWS using free-tier resources. The system consists of two Windows Server 2022 EC2 instances (frontend web server and backend application server) with comprehensive monitoring via AWS Systems Manager, CloudWatch metrics and alarms, and automated S3 backups. The architecture implements network isolation, secure access controls, and cost optimization to remain within AWS Free Tier limits.

## Glossary

- **Frontend_Instance**: Windows Server 2022 t2.micro EC2 instance hosting IIS web server in public subnet
- **Backend_Instance**: Windows Server 2022 t2.micro EC2 instance hosting .NET application and SQL Server Express in private subnet
- **SSM**: AWS Systems Manager service providing fleet management, session management, and patch management
- **CloudWatch_Agent**: AWS agent collecting system metrics and logs from EC2 instances
- **Deployment_System**: The automated infrastructure deployment process using CloudFormation or CDK
- **Backup_System**: Automated daily database backup process uploading to S3
- **Security_Group**: AWS firewall rules controlling network traffic to/from instances
- **Session_Manager**: SSM component providing secure shell access without SSH/RDP ports
- **Fleet_Manager**: SSM component displaying instance inventory and status
- **Patch_Manager**: SSM component managing Windows updates and security patches
- **Free_Tier**: AWS free tier limits (750 hours t2.micro, 30GB EBS, 5GB S3, etc.)

## Requirements

### Requirement 1: VPC Network Infrastructure

**User Story:** As a system architect, I want isolated network infrastructure with public and private subnets, so that I can deploy frontend and backend instances with appropriate network isolation.

#### Acceptance Criteria

1. THE Deployment_System SHALL create a VPC with CIDR block 10.0.0.0/16
2. THE Deployment_System SHALL create a public subnet with CIDR block 10.0.1.0/24
3. THE Deployment_System SHALL create a private subnet with CIDR block 10.0.2.0/24
4. THE Deployment_System SHALL attach an Internet Gateway to the VPC
5. THE Deployment_System SHALL configure the public subnet route table to route 0.0.0.0/0 traffic to the Internet Gateway
6. THE Deployment_System SHALL enable DNS hostnames and DNS support in the VPC

### Requirement 2: Frontend EC2 Instance Deployment

**User Story:** As a system administrator, I want a Windows web server in the public subnet, so that warehouse users can access the WMS application over the internet.

#### Acceptance Criteria

1. THE Deployment_System SHALL launch a t2.micro EC2 instance with Windows Server 2022 AMI in the public subnet
2. THE Deployment_System SHALL attach a 30GB encrypted gp3 EBS volume to the Frontend_Instance
3. THE Deployment_System SHALL allocate and associate an Elastic IP address to the Frontend_Instance
4. THE Deployment_System SHALL attach the frontend security group to the Frontend_Instance
5. THE Deployment_System SHALL attach the SSM IAM instance profile to the Frontend_Instance
6. WHEN the Frontend_Instance launches, THE Deployment_System SHALL execute UserData script to install IIS, .NET Framework, and CloudWatch Agent

### Requirement 3: Backend EC2 Instance Deployment

**User Story:** As a system administrator, I want a Windows application server in the private subnet, so that the database and business logic are isolated from direct internet access.

#### Acceptance Criteria

1. THE Deployment_System SHALL launch a t2.micro EC2 instance with Windows Server 2022 AMI in the private subnet
2. THE Deployment_System SHALL attach a 30GB encrypted gp3 EBS volume to the Backend_Instance
3. THE Deployment_System SHALL NOT assign a public IP address to the Backend_Instance
4. THE Deployment_System SHALL attach the backend security group to the Backend_Instance
5. THE Deployment_System SHALL attach the SSM IAM instance profile to the Backend_Instance
6. WHEN the Backend_Instance launches, THE Deployment_System SHALL execute UserData script to install SQL Server Express, .NET Runtime, and CloudWatch Agent

### Requirement 4: Network Security Controls

**User Story:** As a security engineer, I want strict security group rules, so that only authorized traffic can reach each instance.

#### Acceptance Criteria

1. THE Frontend_Instance security group SHALL allow inbound TCP traffic on port 443 from 0.0.0.0/0
2. THE Frontend_Instance security group SHALL allow inbound TCP traffic on port 80 from 0.0.0.0/0
3. THE Backend_Instance security group SHALL allow inbound TCP traffic on port 443 only from the Frontend_Instance security group
4. THE Backend_Instance security group SHALL allow inbound TCP traffic on port 1433 only from the Frontend_Instance security group
5. THE Backend_Instance security group SHALL NOT allow any inbound traffic from 0.0.0.0/0
6. THE Frontend_Instance security group SHALL allow all outbound traffic
7. THE Backend_Instance security group SHALL allow all outbound traffic

### Requirement 5: Systems Manager Integration

**User Story:** As a system administrator, I want both instances registered with AWS Systems Manager, so that I can manage them securely without exposing RDP ports.

#### Acceptance Criteria

1. WHEN an EC2 instance is running with the SSM IAM role, THE SSM Agent SHALL register the instance with Fleet Manager within 5 minutes
2. WHEN an instance is registered with SSM, THE Session_Manager SHALL enable secure shell access to the instance
3. THE SSM IAM role SHALL grant permissions for ssm:UpdateInstanceInformation, ssmmessages:CreateControlChannel, and ssmmessages:OpenDataChannel
4. WHEN an administrator initiates a session, THE Session_Manager SHALL establish a secure connection without requiring open RDP or SSH ports
5. THE Session_Manager SHALL log all session activity to CloudWatch Logs

### Requirement 6: CloudWatch Monitoring

**User Story:** As a system administrator, I want comprehensive monitoring of instance health and performance, so that I can detect and respond to issues proactively.

#### Acceptance Criteria

1. THE CloudWatch_Agent SHALL collect CPU utilization metrics every 60 seconds
2. THE CloudWatch_Agent SHALL collect memory utilization metrics every 60 seconds
3. THE CloudWatch_Agent SHALL collect disk free space metrics every 60 seconds
4. THE CloudWatch_Agent SHALL send metrics to namespace "Made4Net/POC/Frontend" for the Frontend_Instance
5. THE CloudWatch_Agent SHALL send metrics to namespace "Made4Net/POC/Backend" for the Backend_Instance
6. THE CloudWatch_Agent SHALL collect Windows System event logs with ERROR and WARNING levels
7. THE CloudWatch_Agent SHALL collect Windows Application event logs with ERROR and WARNING levels
8. WHEN the Frontend_Instance is running, THE CloudWatch_Agent SHALL collect IIS access logs from C:\inetpub\logs\LogFiles\W3SVC1\

### Requirement 7: CloudWatch Alarms

**User Story:** As a system administrator, I want automated alerts when instances exceed performance thresholds, so that I can take corrective action before users are impacted.

#### Acceptance Criteria

1. WHEN CPU utilization exceeds 80% for 5 consecutive minutes, THE CloudWatch alarm SHALL transition to ALARM state
2. WHEN memory utilization exceeds 85% for 5 consecutive minutes, THE CloudWatch alarm SHALL transition to ALARM state
3. WHEN disk free space falls below 15% for 2 consecutive data points, THE CloudWatch alarm SHALL transition to ALARM state
4. WHEN an alarm transitions to ALARM state, THE CloudWatch alarm SHALL send a notification to the configured SNS topic

### Requirement 8: Automated Database Backups

**User Story:** As a database administrator, I want automated daily backups of the SQL Server database, so that I can recover data in case of corruption or accidental deletion.

#### Acceptance Criteria

1. THE Backup_System SHALL execute a database backup daily at 02:00 UTC
2. WHEN a backup executes, THE Backup_System SHALL create a compressed SQL Server backup file with CHECKSUM validation
3. WHEN a backup file is created, THE Backup_System SHALL upload it to the S3 bucket with AES-256 encryption
4. WHEN a backup is uploaded to S3, THE Backup_System SHALL verify the uploaded file size matches the local file size
5. THE Backup_System SHALL retain the 3 most recent local backup files and delete older files
6. WHEN a backup completes successfully, THE Backup_System SHALL log the completion to CloudWatch Logs
7. IF a backup fails, THEN THE Backup_System SHALL log the error to CloudWatch Logs and trigger a CloudWatch alarm

### Requirement 9: S3 Backup Storage

**User Story:** As a system administrator, I want secure and durable storage for database backups, so that I can restore data when needed.

#### Acceptance Criteria

1. THE Deployment_System SHALL create an S3 bucket with a unique name for backup storage
2. THE S3 bucket SHALL enable server-side encryption with AES-256
3. THE S3 bucket SHALL block all public access
4. THE S3 bucket SHALL have a lifecycle policy to delete backups older than 30 days
5. THE SSM IAM role SHALL grant s3:PutObject, s3:GetObject, and s3:ListBucket permissions for the backup bucket

### Requirement 10: Patch Management

**User Story:** As a security engineer, I want automated patching of Windows instances, so that security vulnerabilities are addressed promptly.

#### Acceptance Criteria

1. THE Patch_Manager SHALL define a patch baseline for Windows Server 2022 including CriticalUpdates and SecurityUpdates
2. THE Patch_Manager SHALL approve patches with MSRC severity Critical or Important within 7 days of release
3. THE Patch_Manager SHALL create a maintenance window scheduled for Sunday at 02:00 UTC
4. WHEN the maintenance window executes, THE Patch_Manager SHALL install approved patches on all instances tagged with Environment:POC
5. THE maintenance window SHALL have a duration of 4 hours and a cutoff of 1 hour

### Requirement 11: IAM Access Control

**User Story:** As a security engineer, I want least-privilege IAM permissions, so that instances can only access the AWS services they require.

#### Acceptance Criteria

1. THE SSM IAM role SHALL grant AmazonSSMManagedInstanceCore managed policy permissions
2. THE SSM IAM role SHALL grant CloudWatchAgentServerPolicy managed policy permissions
3. THE SSM IAM role SHALL grant S3 read/write permissions only to the backup bucket
4. THE SSM IAM role SHALL NOT grant permissions to create, delete, or modify EC2 instances
5. THE SSM IAM role SHALL NOT grant permissions to modify IAM policies or roles
6. THE EC2 service SHALL be the only principal allowed to assume the SSM IAM role

### Requirement 12: Free Tier Compliance

**User Story:** As a cost-conscious stakeholder, I want the deployment to remain within AWS Free Tier limits, so that the POC incurs minimal or zero cost.

#### Acceptance Criteria

1. THE Deployment_System SHALL deploy exactly 2 EC2 instances of type t2.micro
2. THE Deployment_System SHALL deploy a total of 60GB or less of EBS storage across all instances
3. THE Deployment_System SHALL allocate exactly 1 Elastic IP address and keep it associated with a running instance
4. THE Deployment_System SHALL NOT deploy NAT Gateways, load balancers, or other services that incur charges
5. THE S3 bucket SHALL store less than 5GB of backup data within the first month
6. THE CloudWatch Logs SHALL ingest less than 5GB of log data per month

### Requirement 13: Instance Initialization

**User Story:** As a system administrator, I want instances to be fully configured on first boot, so that manual configuration is minimized.

#### Acceptance Criteria

1. WHEN the Frontend_Instance first boots, THE UserData script SHALL install IIS with ASP.NET support
2. WHEN the Frontend_Instance first boots, THE UserData script SHALL install .NET Framework 4.8 or .NET 6
3. WHEN the Frontend_Instance first boots, THE UserData script SHALL configure the CloudWatch Agent with the frontend configuration
4. WHEN the Backend_Instance first boots, THE UserData script SHALL install SQL Server Express 2019
5. WHEN the Backend_Instance first boots, THE UserData script SHALL create the C:\SQLBackups directory
6. WHEN the Backend_Instance first boots, THE UserData script SHALL create and schedule the daily backup task
7. WHEN the Backend_Instance first boots, THE UserData script SHALL configure the CloudWatch Agent with the backend configuration

### Requirement 14: Network Connectivity

**User Story:** As a system architect, I want the frontend to communicate with the backend over HTTPS, so that API traffic is encrypted in transit.

#### Acceptance Criteria

1. WHEN the Frontend_Instance sends a request to the Backend_Instance, THE request SHALL use HTTPS on port 443
2. WHEN the Backend_Instance is running, THE Backend_Instance SHALL accept HTTPS connections from the Frontend_Instance
3. THE Frontend_Instance SHALL be able to resolve the Backend_Instance private IP address via VPC DNS
4. THE Backend_Instance SHALL NOT be reachable from the public internet
5. THE Frontend_Instance SHALL be reachable from the public internet via its Elastic IP address

### Requirement 15: Data Encryption

**User Story:** As a security engineer, I want all data encrypted at rest and in transit, so that sensitive information is protected.

#### Acceptance Criteria

1. THE Deployment_System SHALL enable encryption on all EBS volumes
2. THE S3 bucket SHALL encrypt all objects with AES-256 server-side encryption
3. WHEN the Frontend_Instance communicates with the Backend_Instance, THE communication SHALL use TLS 1.2 or higher
4. WHEN users access the Frontend_Instance, THE communication SHALL use HTTPS with TLS 1.2 or higher
5. THE SQL Server database SHALL support encrypted connections

### Requirement 16: Deployment Automation

**User Story:** As a DevOps engineer, I want fully automated infrastructure deployment, so that I can deploy and tear down the environment consistently.

#### Acceptance Criteria

1. THE Deployment_System SHALL deploy all infrastructure using CloudFormation or AWS CDK
2. WHEN the deployment completes successfully, THE Deployment_System SHALL output the Frontend_Instance public IP address
3. WHEN the deployment completes successfully, THE Deployment_System SHALL output the Backend_Instance private IP address
4. IF any resource fails to create, THEN THE Deployment_System SHALL rollback all created resources
5. THE Deployment_System SHALL tag all resources with Environment:POC for identification

### Requirement 17: Health Monitoring

**User Story:** As a system administrator, I want health check endpoints, so that I can verify instances are functioning correctly.

#### Acceptance Criteria

1. THE Frontend_Instance SHALL expose an HTTPS health check endpoint at /health
2. WHEN the Frontend_Instance is healthy, THE health check endpoint SHALL return HTTP 200 status code
3. THE Backend_Instance SHALL expose an HTTPS health check endpoint at /api/health
4. WHEN the Backend_Instance is healthy, THE health check endpoint SHALL return HTTP 200 status code
5. WHEN the Backend_Instance database is accessible, THE health check SHALL include database connectivity status

### Requirement 18: Logging and Audit Trail

**User Story:** As a compliance officer, I want comprehensive logging of all system activities, so that I can audit access and changes.

#### Acceptance Criteria

1. THE Session_Manager SHALL log all session start and end events to CloudWatch Logs
2. THE Session_Manager SHALL log all commands executed during sessions to CloudWatch Logs
3. THE Backup_System SHALL log all backup operations (success and failure) to CloudWatch Logs
4. THE CloudWatch_Agent SHALL retain logs for at least 30 days
5. THE IIS web server SHALL log all HTTP requests to CloudWatch Logs

### Requirement 19: Disaster Recovery

**User Story:** As a database administrator, I want the ability to restore from backups, so that I can recover from data loss or corruption.

#### Acceptance Criteria

1. WHEN a backup file exists in S3, THE database administrator SHALL be able to download it to the Backend_Instance
2. WHEN a backup file is downloaded, THE SQL Server SHALL be able to restore the database from the backup file
3. THE backup file SHALL include CHECKSUM validation to detect corruption
4. THE backup file SHALL be compressed to minimize storage costs
5. WHEN a restore operation completes, THE SQL Server SHALL verify the database integrity

### Requirement 20: Performance Monitoring

**User Story:** As a system administrator, I want to monitor t2.micro CPU credit balance, so that I can detect when instances are being throttled.

#### Acceptance Criteria

1. THE CloudWatch monitoring SHALL collect CPUCreditBalance metric for both instances
2. THE CloudWatch monitoring SHALL collect CPUCreditUsage metric for both instances
3. WHEN CPU credit balance falls below 10 credits, THE CloudWatch alarm SHALL transition to ALARM state
4. THE CloudWatch dashboard SHALL display CPU credit balance and usage trends

### Requirement 21: Resource Tagging

**User Story:** As a cost management analyst, I want consistent resource tagging, so that I can track costs and identify resources.

#### Acceptance Criteria

1. THE Deployment_System SHALL tag all EC2 instances with Name, Role, and Environment tags
2. THE Deployment_System SHALL tag the Frontend_Instance with Role:WebServer
3. THE Deployment_System SHALL tag the Backend_Instance with Role:AppServer
4. THE Deployment_System SHALL tag all resources with Environment:POC
5. THE Deployment_System SHALL tag the VPC, subnets, and security groups with descriptive Name tags

### Requirement 22: Session Manager Configuration

**User Story:** As a security engineer, I want session activity logged and encrypted, so that administrative access is auditable and secure.

#### Acceptance Criteria

1. THE Session_Manager SHALL encrypt session data in transit using TLS
2. THE Session_Manager SHALL log session activity to a dedicated CloudWatch log group
3. THE Session_Manager SHALL enforce an idle session timeout of 20 minutes
4. THE Session_Manager SHALL enforce a maximum session duration of 60 minutes
5. WHEN a session is terminated, THE Session_Manager SHALL log the termination reason

### Requirement 23: SQL Server Configuration

**User Story:** As a database administrator, I want SQL Server properly configured for the POC workload, so that the application can store and retrieve data reliably.

#### Acceptance Criteria

1. THE Backend_Instance SHALL install SQL Server Express 2019 with the SQLEngine feature
2. THE SQL Server SHALL create a named instance called SQLEXPRESS
3. THE SQL Server SHALL enable SQL Server authentication mode
4. THE SQL Server SHALL listen on TCP port 1433
5. THE SQL Server SHALL create a database named InventoryDB

### Requirement 24: IIS Web Server Configuration

**User Story:** As a web administrator, I want IIS properly configured to host the WMS application, so that users can access the web interface.

#### Acceptance Criteria

1. THE Frontend_Instance SHALL install IIS 10.0 with management tools
2. THE Frontend_Instance SHALL install ASP.NET 4.5 or higher
3. THE IIS SHALL create an application pool named Made4NetPool
4. THE IIS SHALL configure the application pool to use .NET runtime version 4.0 or higher
5. THE IIS SHALL create a website directory at C:\inetpub\made4net

### Requirement 25: Error Handling and Recovery

**User Story:** As a system administrator, I want automatic recovery from common failures, so that the system remains available with minimal manual intervention.

#### Acceptance Criteria

1. IF the SSM Agent service stops, THEN THE Windows Service Control Manager SHALL automatically restart it
2. IF the CloudWatch Agent service stops, THEN THE Windows Service Control Manager SHALL automatically restart it
3. IF the SQL Server service stops unexpectedly, THEN THE Windows Service Control Manager SHALL automatically restart it
4. IF the IIS service stops unexpectedly, THEN THE Windows Service Control Manager SHALL automatically restart it
5. WHEN an instance is stopped and restarted, THE Elastic IP SHALL remain associated with the Frontend_Instance
