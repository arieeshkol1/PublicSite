# Made4Net WMS POC Deployment - In Progress 🚀

## Deployment Started

**Stack Name:** made4net-wms-poc  
**Region:** us-east-1  
**Status:** CREATE_IN_PROGRESS  
**Stack ID:** arn:aws:cloudformation:us-east-1:960915223703:stack/made4net-wms-poc/2a6c1af0-1097-11f1-b019-121f4763876d

---

## What's Being Created

### Network Infrastructure
- ✅ VPC (10.0.0.0/16)
- ✅ Internet Gateway
- ✅ Public Subnet (10.0.1.0/24)
- ✅ Private Subnet (10.0.2.0/24)
- ✅ Route Tables

### Security
- ✅ Frontend Security Group (HTTPS from internet)
- ✅ Backend Security Group (HTTPS + SQL from frontend only)
- ✅ IAM Role for SSM (AmazonSSMManagedInstanceCore + CloudWatchAgentServerPolicy)
- ✅ S3 Backup Bucket (made4net-poc-backups-960915223703)

### Compute
- 🔄 Frontend EC2 Instance (t2.micro, Windows Server 2022)
  - IIS 10.0 web server
  - CloudWatch Agent
  - Elastic IP
  - 30GB encrypted EBS volume

- 🔄 Backend EC2 Instance (t2.micro, Windows Server 2022)
  - SQL Server Express 2019 (to be installed)
  - CloudWatch Agent
  - Private IP only
  - 30GB encrypted EBS volume
  - Automated backup script

### Monitoring
- ✅ CloudWatch Log Groups (frontend/backend system logs)
- ✅ CloudWatch Alarms (CPU utilization >80%)

---

## Estimated Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| VPC & Network Setup | 1-2 min | ✅ In Progress |
| Security Groups & IAM | 1 min | ✅ In Progress |
| S3 Bucket Creation | 30 sec | ✅ In Progress |
| EC2 Instance Launch | 3-5 min | 🔄 In Progress |
| Windows Initialization | 2-3 min | ⏳ Pending |
| SSM Agent Registration | 1-2 min | ⏳ Pending |
| CloudWatch Agent Setup | 1 min | ⏳ Pending |
| **Total** | **10-15 min** | 🔄 **In Progress** |

---

## Next Steps (After Deployment)

### 1. Verify SSM Registration
```powershell
# Check if instances are registered with SSM
aws ssm describe-instance-information --region us-east-1
```

### 2. Connect to Instances
```powershell
# Frontend
aws ssm start-session --target <frontend-instance-id>

# Backend
aws ssm start-session --target <backend-instance-id>
```

### 3. Install SQL Server Express (Backend)
- Connect via SSM Session Manager
- Download SQL Server Express 2019
- Install with SQLEXPRESS instance name
- Create InventoryDB database

### 4. Configure IIS (Frontend)
- Install .NET Framework 4.8 or .NET 6
- Create Made4Net WMS application pool
- Deploy WMS UI to C:\inetpub\made4net

### 5. Verify Monitoring
- Check CloudWatch metrics (CPU, memory, disk)
- Verify CloudWatch Logs (System events)
- Test CloudWatch Alarms

### 6. Test Connectivity
- Frontend → Backend HTTPS (port 443)
- Frontend → Backend SQL (port 1433)
- Verify backend is NOT accessible from internet

---

## Monitoring Commands

### Check Stack Status
```powershell
aws cloudformation describe-stacks --stack-name made4net-wms-poc --region us-east-1 --query 'Stacks[0].StackStatus'
```

### Get Stack Outputs
```powershell
aws cloudformation describe-stacks --stack-name made4net-wms-poc --region us-east-1 --query 'Stacks[0].Outputs'
```

### Check Stack Events
```powershell
aws cloudformation describe-stack-events --stack-name made4net-wms-poc --region us-east-1 --max-items 20
```

### List EC2 Instances
```powershell
aws ec2 describe-instances --filters "Name=tag:Environment,Values=POC" --region us-east-1 --query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress,PrivateIpAddress,Tags[?Key==`Name`].Value|[0]]' --output table
```

---

## Cost Tracking

### Free Tier Usage (12 months)
- **EC2:** 750 hours/month t2.micro (2 instances = 1,500 hours total, within limit)
- **EBS:** 30GB per instance (60GB total, within 30GB free tier limit)
- **S3:** First 5GB free
- **CloudWatch:** 10 custom metrics free, 5GB log ingestion free

### Expected Monthly Cost
- **Months 1-12:** $0-5/month (within Free Tier)
- **After 12 months:** ~$30-40/month (2x t2.micro + EBS + S3)

---

## Troubleshooting

### If Stack Creation Fails
```powershell
# Check stack events for errors
aws cloudformation describe-stack-events --stack-name made4net-wms-poc --region us-east-1 --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]'

# Delete failed stack
aws cloudformation delete-stack --stack-name made4net-wms-poc --region us-east-1
```

### If Instances Don't Register with SSM
- Wait 5-10 minutes for Windows to fully boot
- Check IAM role is attached to instances
- Verify SSM Agent is running (pre-installed on Windows Server 2022)
- Check security group allows outbound HTTPS (443) to AWS endpoints

### If CloudWatch Agent Doesn't Start
- Connect via SSM Session Manager
- Check agent status: `& "C:\Program Files\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" -a query -m ec2 -c default`
- Review agent logs: `C:\ProgramData\Amazon\AmazonCloudWatchAgent\Logs\`

---

## Current Status

🔄 **CloudFormation stack is being created...**

Please wait 10-15 minutes for the deployment to complete. You can monitor progress using the commands above.

---

**Started:** $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")  
**AWS Account:** 960915223703  
**Region:** us-east-1  
**Stack:** made4net-wms-poc
