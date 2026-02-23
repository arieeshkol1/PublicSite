# Made4Net WMS POC Deployment - COMPLETE ✅

## Deployment Successful!

**Stack Name:** made4net-wms-poc  
**Region:** us-east-1  
**Status:** ✅ CREATE_COMPLETE  
**Deployment Time:** ~11 minutes  
**AWS Account:** 960915223703

---

## Deployed Resources

### 🌐 Network Infrastructure
- ✅ VPC: `vpc-0da4669f7c534e95a` (10.0.0.0/16)
- ✅ Internet Gateway
- ✅ Public Subnet: 10.0.1.0/24
- ✅ Private Subnet: 10.0.2.0/24
- ✅ Route Tables configured

### 🔒 Security
- ✅ Frontend Security Group (HTTPS 443, HTTP 80 from internet)
- ✅ Backend Security Group (HTTPS 443, SQL 1433 from frontend only)
- ✅ IAM Role: made4net-poc-ssm-role
- ✅ S3 Backup Bucket: `made4net-poc-backups-960915223703`

### 💻 EC2 Instances

#### Frontend Instance (Web Server)
- **Instance ID:** `i-0afda2abace682f7e`
- **Public IP:** `34.194.134.204`
- **Instance Type:** t2.micro
- **OS:** Windows Server 2022
- **Subnet:** Public (10.0.1.0/24)
- **Role:** WebServer
- **Software Installed:**
  - IIS 10.0 with ASP.NET
  - CloudWatch Agent
  - SSM Agent (pre-installed)
- **Storage:** 30GB encrypted EBS (gp3)

#### Backend Instance (App Server)
- **Instance ID:** `i-00005393dae5f6efa`
- **Private IP:** `10.0.2.103`
- **Instance Type:** t2.micro
- **OS:** Windows Server 2022
- **Subnet:** Private (10.0.2.0/24)
- **Role:** AppServer
- **Software Installed:**
  - CloudWatch Agent
  - SSM Agent (pre-installed)
  - Backup script configured
- **Storage:** 30GB encrypted EBS (gp3)
- **Backup:** Scheduled daily at 2:00 AM UTC

### 📊 Monitoring
- ✅ CloudWatch Log Groups:
  - `/aws/ec2/windows/frontend/system`
  - `/aws/ec2/windows/backend/system`
- ✅ CloudWatch Alarms:
  - Frontend CPU >80%
  - Backend CPU >80%

---

## Access Information

### Connect to Frontend via SSM
```powershell
aws ssm start-session --target i-0afda2abace682f7e --region us-east-1
```

### Connect to Backend via SSM
```powershell
aws ssm start-session --target i-00005393dae5f6efa --region us-east-1
```

### Frontend Public Access
- **URL:** `https://34.194.134.204` (after WMS UI deployment)
- **HTTP:** `http://34.194.134.204` (redirects to HTTPS)

### Backend Private Access
- **Internal IP:** `10.0.2.103`
- **Accessible from:** Frontend instance only
- **Ports:** 443 (HTTPS), 1433 (SQL Server)

---

## Next Steps - Configuration Tasks

### 1. ✅ Verify SSM Registration (5 minutes)
```powershell
# Check if instances are registered
aws ssm describe-instance-information --region us-east-1 --query 'InstanceInformationList[*].[InstanceId,PingStatus,PlatformName]' --output table
```

**Expected:** Both instances should show "Online" status

### 2. 🔄 Install SQL Server Express on Backend (30 minutes)
```powershell
# Connect to backend
aws ssm start-session --target i-00005393dae5f6efa --region us-east-1

# Download SQL Server Express 2019
$sqlUrl = "https://go.microsoft.com/fwlink/?linkid=866658"
Invoke-WebRequest -Uri $sqlUrl -OutFile "C:\SQLServer2019-SSEI-Expr.exe"

# Install SQL Server Express
Start-Process "C:\SQLServer2019-SSEI-Expr.exe" -ArgumentList '/ACTION=Install /QUIET /IACCEPTSQLSERVERLICENSETERMS /FEATURES=SQLEngine /INSTANCENAME=SQLEXPRESS /SECURITYMODE=SQL /SAPWD=YourStrongPassword123!' -Wait

# Create InventoryDB database
Invoke-Sqlcmd -Query "CREATE DATABASE InventoryDB" -ServerInstance "localhost\SQLEXPRESS"
```

### 3. 🔄 Configure IIS and Deploy WMS UI on Frontend (20 minutes)
```powershell
# Connect to frontend
aws ssm start-session --target i-0afda2abace682f7e --region us-east-1

# Install .NET 6 (if not already installed)
$dotnetUrl = "https://download.visualstudio.microsoft.com/download/pr/xxx/dotnet-hosting-6.0-win.exe"
Invoke-WebRequest -Uri $dotnetUrl -OutFile "C:\dotnet-hosting.exe"
Start-Process "C:\dotnet-hosting.exe" -ArgumentList '/quiet /norestart' -Wait

# Create IIS Application Pool
Import-Module WebAdministration
New-WebAppPool -Name "Made4NetPool"
Set-ItemProperty IIS:\AppPools\Made4NetPool -Name managedRuntimeVersion -Value "v4.0"

# Deploy WMS UI (placeholder - replace with actual deployment)
# Copy WMS files to C:\inetpub\made4net
# Configure IIS site to use Made4NetPool
```

### 4. 🔄 Test Frontend-Backend Connectivity (10 minutes)
```powershell
# From frontend instance, test backend connectivity
Test-NetConnection -ComputerName 10.0.2.103 -Port 443
Test-NetConnection -ComputerName 10.0.2.103 -Port 1433

# Test SQL Server connection
# Install SQL Server Management Studio or use sqlcmd
```

### 5. 🔄 Verify CloudWatch Monitoring (5 minutes)
```powershell
# Check CloudWatch metrics
aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization --dimensions Name=InstanceId,Value=i-0afda2abace682f7e --start-time 2026-02-23T09:00:00Z --end-time 2026-02-23T10:00:00Z --period 300 --statistics Average --region us-east-1

# Check CloudWatch logs
aws logs tail /aws/ec2/windows/frontend/system --follow --region us-east-1
```

### 6. 🔄 Test Automated Backups (Manual trigger)
```powershell
# Connect to backend
aws ssm start-session --target i-00005393dae5f6efa --region us-east-1

# Manually trigger backup script
PowerShell.exe -File C:\SQLBackups\backup-database.ps1

# Verify backup in S3
aws s3 ls s3://made4net-poc-backups-960915223703/backups/ --region us-east-1
```

---

## Verification Checklist

- [ ] Both EC2 instances are running
- [ ] SSM Agent registered (both instances show "Online")
- [ ] CloudWatch Agent collecting metrics
- [ ] CloudWatch Logs receiving system events
- [ ] SQL Server Express installed on backend
- [ ] InventoryDB database created
- [ ] IIS configured on frontend
- [ ] Made4Net WMS UI deployed
- [ ] Frontend can connect to backend (HTTPS 443)
- [ ] Frontend can connect to backend (SQL 1433)
- [ ] Backend is NOT accessible from internet
- [ ] Automated backup script tested
- [ ] S3 backup bucket contains backup files

---

## Cost Summary

### Current Monthly Cost (Free Tier - First 12 Months)
- **EC2 Instances:** $0 (750 hours/month free per instance)
- **EBS Storage:** $0 (30GB free tier)
- **S3 Storage:** $0 (first 5GB free)
- **CloudWatch:** $0 (10 custom metrics free, 5GB logs free)
- **Data Transfer:** $0 (1GB free)

**Total:** $0-5/month

### After Free Tier (Month 13+)
- **EC2 Instances:** ~$16/month (2x t2.micro @ $0.0116/hour)
- **EBS Storage:** ~$6/month (60GB @ $0.10/GB)
- **S3 Storage:** ~$0.50/month (assuming 20GB backups)
- **CloudWatch:** ~$3/month (custom metrics + logs)
- **Data Transfer:** ~$1/month

**Total:** ~$26.50/month

---

## Monitoring & Management

### CloudWatch Dashboard
Create a custom dashboard to monitor:
- CPU utilization (both instances)
- Memory utilization (both instances)
- Disk free space (both instances)
- Network in/out
- CloudWatch Agent status

### SSM Fleet Manager
Access via AWS Console:
1. Go to AWS Systems Manager
2. Click "Fleet Manager"
3. View both instances with real-time status

### Patch Manager
- Patch baseline created for Windows Server 2022
- Maintenance window: Sunday 02:00 UTC
- Auto-approval: Critical and Important updates within 7 days

---

## Troubleshooting

### If SSM Agent Not Registered
```powershell
# Wait 5-10 minutes for Windows to fully boot
# Check SSM Agent status via RDP or EC2 console
# Restart SSM Agent if needed
```

### If CloudWatch Agent Not Running
```powershell
# Connect via SSM
aws ssm start-session --target <instance-id> --region us-east-1

# Check agent status
& "C:\Program Files\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" -a query -m ec2 -c default

# Restart agent
& "C:\Program Files\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" -a stop -m ec2
& "C:\Program Files\Amazon\AmazonCloudWatchAgent\amazon-cloudwatch-agent-ctl.ps1" -a fetch-config -m ec2 -s -c file:C:\cloudwatch-config.json
```

### If Frontend Not Accessible
- Check security group allows HTTPS (443) from 0.0.0.0/0
- Verify Elastic IP is associated
- Check IIS is running: `Get-Service W3SVC`
- Check Windows Firewall rules

### If Backend Not Accessible from Frontend
- Verify security group allows traffic from frontend SG
- Test connectivity: `Test-NetConnection -ComputerName 10.0.2.103 -Port 443`
- Check SQL Server is running: `Get-Service MSSQL$SQLEXPRESS`

---

## Cleanup (When Done)

### Delete Stack
```powershell
aws cloudformation delete-stack --stack-name made4net-wms-poc --region us-east-1
```

### Verify Deletion
```powershell
aws cloudformation describe-stacks --stack-name made4net-wms-poc --region us-east-1
```

### Manual Cleanup (if needed)
- Empty S3 bucket before deletion
- Detach and delete EBS volumes if DeleteOnTermination=false
- Release Elastic IP if not automatically released

---

## Summary

✅ **Infrastructure Deployed Successfully**

**Resources Created:**
- 1 VPC with public and private subnets
- 2 Windows Server 2022 EC2 instances (t2.micro)
- 1 Elastic IP for frontend
- 2 Security groups with proper isolation
- 1 S3 bucket for backups
- IAM role for SSM and CloudWatch
- CloudWatch log groups and alarms

**Next Actions:**
1. Verify SSM registration
2. Install SQL Server Express on backend
3. Configure IIS and deploy WMS UI on frontend
4. Test connectivity and monitoring
5. Deploy Made4Net WMS application

**Access:**
- Frontend: `https://34.194.134.204`
- Backend: `10.0.2.103` (from frontend only)
- SSM Session Manager for secure access

---

**Deployment Completed:** 2026-02-23 09:11:00 UTC  
**Total Time:** ~11 minutes  
**Status:** ✅ Ready for configuration
