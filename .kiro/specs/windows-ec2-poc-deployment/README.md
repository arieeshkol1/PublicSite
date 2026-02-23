# Windows EC2 POC Deployment with SSM Integration

Complete deployment package for Made4Net POC system with 2 free-tier Windows EC2 instances and AWS Systems Manager monitoring.

## 📋 Overview

This deployment creates:
- **Frontend EC2**: Windows Server 2022 with IIS web server in public subnet
- **Backend EC2**: Windows Server 2022 with .NET + SQL Server Express in private subnet
- **VPC**: Isolated network with public and private subnets
- **SSM Integration**: Fleet Manager, Session Manager, Patch Manager
- **CloudWatch**: Metrics, logs, and alarms
- **S3**: Automated daily database backups
- **Free Tier**: All resources within AWS Free Tier limits

## 📁 Files Included

| File | Description |
|------|-------------|
| `design.md` | Complete technical design document |
| `infrastructure.yaml` | CloudFormation template |
| `deploy-poc.ps1` | Automated deployment script |
| `configure-frontend.ps1` | Frontend post-deployment configuration |
| `configure-backend.ps1` | Backend post-deployment configuration |
| `README.md` | This file |

## 🚀 Quick Start

### Prerequisites

1. **AWS Account** with Free Tier available
2. **AWS CLI** installed and configured
   ```bash
   aws --version
   aws configure
   ```
3. **PowerShell 5.1+** (Windows) or PowerShell Core (Linux/Mac)
4. **Permissions**: IAM user with EC2, VPC, IAM, S3, CloudWatch, SSM permissions

### Step 1: Deploy Infrastructure

```powershell
# Clone or download this directory
cd windows-ec2-poc-deployment

# Run deployment script
.\deploy-poc.ps1 -Region us-east-1 -WaitForCompletion

# Deployment takes 5-10 minutes
```

### Step 2: Wait for Instances to Initialize

After CloudFormation completes, wait 5-10 minutes for:
- Windows to finish booting
- SSM Agent to register
- CloudWatch Agent to start
- UserData scripts to complete

Check SSM registration:
```bash
aws ssm describe-instance-information --region us-east-1
```

### Step 3: Configure Frontend

```bash
# Get frontend instance ID from CloudFormation outputs
aws cloudformation describe-stacks --stack-name made4net-poc --query 'Stacks[0].Outputs[?OutputKey==`FrontendInstanceId`].OutputValue' --output text

# Connect via Session Manager
aws ssm start-session --target <frontend-instance-id> --region us-east-1

# Inside the session, run:
cd C:\
powershell -ExecutionPolicy Bypass
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/.../configure-frontend.ps1" -OutFile "configure-frontend.ps1"
.\configure-frontend.ps1
```

### Step 4: Configure Backend

```bash
# Get backend instance ID
aws cloudformation describe-stacks --stack-name made4net-poc --query 'Stacks[0].Outputs[?OutputKey==`BackendInstanceId`].OutputValue' --output text

# Connect via Session Manager
aws ssm start-session --target <backend-instance-id> --region us-east-1

# Inside the session, run:
cd C:\
powershell -ExecutionPolicy Bypass
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/.../configure-backend.ps1" -OutFile "configure-backend.ps1"
.\configure-backend.ps1
```

### Step 5: Access the System

Get the frontend public IP:
```bash
aws cloudformation describe-stacks --stack-name made4net-poc --query 'Stacks[0].Outputs[?OutputKey==`FrontendPublicIP`].OutputValue' --output text
```

Access the web interface:
- HTTP: `http://<frontend-public-ip>`
- HTTPS: `https://<frontend-public-ip>` (self-signed certificate)

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              VPC (10.0.0.0/16)                        │  │
│  │                                                        │  │
│  │  ┌──────────────────────┐  ┌──────────────────────┐  │  │
│  │  │  Public Subnet       │  │  Private Subnet      │  │  │
│  │  │  (10.0.1.0/24)       │  │  (10.0.2.0/24)       │  │  │
│  │  │                      │  │                      │  │  │
│  │  │  ┌────────────────┐  │  │  ┌────────────────┐  │  │  │
│  │  │  │   Frontend     │  │  │  │   Backend      │  │  │  │
│  │  │  │   EC2          │──┼──┼─▶│   EC2          │  │  │  │
│  │  │  │   t2.micro     │  │  │  │   t2.micro     │  │  │  │
│  │  │  │   IIS + WMS    │  │  │  │   .NET + SQL   │  │  │  │
│  │  │  │   Elastic IP   │  │  │  │   Private IP   │  │  │  │
│  │  │  └────────────────┘  │  │  └────────────────┘  │  │  │
│  │  └──────────────────────┘  └──────────────────────┘  │  │
│  │           │                          │                │  │
│  └───────────┼──────────────────────────┼────────────────┘  │
│              │                          │                   │
│         ┌────▼────┐              ┌──────▼──────┐            │
│         │   SSM   │              │  CloudWatch │            │
│         │ Manager │              │  Monitoring │            │
│         └─────────┘              └─────────────┘            │
│                                                              │
│         ┌─────────────────────────────────────┐             │
│         │  S3 Bucket (Daily Backups)          │             │
│         └─────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Configuration Details

### Frontend Instance
- **OS**: Windows Server 2022
- **Software**: IIS 10.0, .NET 6, CloudWatch Agent
- **Ports**: 80 (HTTP), 443 (HTTPS)
- **Access**: Public via Elastic IP
- **Management**: SSM Session Manager

### Backend Instance
- **OS**: Windows Server 2022
- **Software**: SQL Server Express 2019, .NET 6, CloudWatch Agent
- **Ports**: 1433 (SQL), 443 (API)
- **Access**: Private subnet only (from frontend)
- **Management**: SSM Session Manager
- **Database**: InventoryDB with Users, InventoryItems, AuditLog tables

### Security Groups

**Frontend SG**:
- Inbound: 80, 443 from 0.0.0.0/0
- Outbound: All

**Backend SG**:
- Inbound: 443, 1433 from Frontend SG only
- Outbound: All

### Database Schema

**Users Table**:
```sql
UserId (GUID), Username, PasswordHash, Role, Email, CreatedAt, LastLogin, IsActive
```

**InventoryItems Table**:
```sql
ItemId (GUID), SKU, Name, Description, Quantity, Location, LastUpdated, UpdatedBy
```

**AuditLog Table**:
```sql
LogId (GUID), Timestamp, UserId, Action, EntityType, EntityId, Changes, IpAddress
```

## 📊 Monitoring

### CloudWatch Metrics
- CPU Utilization
- Memory Usage
- Disk Space
- Network Traffic

### CloudWatch Logs
- Windows System Events
- Windows Application Events
- IIS Logs (frontend)
- SQL Backup Logs (backend)

### CloudWatch Alarms
- High CPU (>80% for 10 minutes)
- Low disk space
- Backup failures

### Systems Manager
- **Fleet Manager**: View instance inventory
- **Session Manager**: Secure shell access (no RDP needed)
- **Patch Manager**: Automated Windows updates (Sundays 2 AM)
- **Run Command**: Execute scripts remotely

## 💾 Backup Strategy

### Automated Daily Backups
- **Schedule**: 2:00 AM UTC daily
- **Method**: SQL Server BACKUP DATABASE with compression
- **Storage**: S3 bucket with encryption
- **Retention**: 30 days (S3 lifecycle policy)
- **Local Retention**: Last 3 backups on instance

### Manual Backup
```powershell
# Connect to backend via SSM
aws ssm start-session --target <backend-instance-id>

# Run backup script
cd C:\SQLBackups
.\backup-database.ps1
```

### Restore from Backup
```powershell
# Download from S3
aws s3 cp s3://made4net-poc-backups-<account-id>/backups/InventoryDB_<timestamp>.bak C:\SQLBackups\

# Restore database
sqlcmd -S localhost\SQLEXPRESS -Q "RESTORE DATABASE InventoryDB FROM DISK = 'C:\SQLBackups\InventoryDB_<timestamp>.bak' WITH REPLACE"
```

## 💰 Cost Analysis

### First 12 Months (Free Tier)
- 2x t2.micro EC2: **$0/month** (750 hours free)
- 60GB EBS storage: **$0/month** (30GB free)
- 1 Elastic IP: **$0/month** (free when attached)
- S3 storage (5GB): **$0/month** (5GB free)
- CloudWatch Logs: **$0/month** (5GB free)
- Data transfer: **$0/month** (15GB free)
- Systems Manager: **$0/month** (always free)

**Total: $0-5/month** (small charges if exceeding limits)

### After 12 Months
- 2x t2.micro: ~$16/month
- 60GB EBS: ~$6/month
- Other services: ~$3/month

**Total: ~$25/month**

## 🔒 Security Best Practices

### Network Security
- Backend in private subnet (no internet access)
- Security groups with least privilege
- No RDP ports exposed (use Session Manager)
- All traffic encrypted (HTTPS/TLS)

### Data Security
- EBS volumes encrypted at rest
- S3 backups encrypted (AES-256)
- SQL Server authentication required
- Passwords hashed with bcrypt

### Access Control
- IAM roles with least privilege
- MFA recommended for AWS console
- Session Manager provides audited access
- CloudWatch Logs retain access logs

### Compliance
- All data in single AWS region
- Audit logs track all changes
- Automated patching via Patch Manager
- Regular security updates

## 🛠️ Troubleshooting

### Instance Not Appearing in SSM

**Problem**: Instance launched but not in Fleet Manager

**Solution**:
1. Wait 5 minutes for SSM Agent to register
2. Check IAM role attached: `aws ec2 describe-instances --instance-ids <id> --query 'Reservations[0].Instances[0].IamInstanceProfile'`
3. Verify internet connectivity (public subnet) or VPC endpoints (private subnet)
4. Check SSM Agent status: Connect via EC2 console and run `Get-Service AmazonSSMAgent`

### Cannot Connect via Session Manager

**Problem**: "Target not connected" error

**Solution**:
1. Verify instance is running: `aws ec2 describe-instances --instance-ids <id>`
2. Check SSM Agent status: `aws ssm describe-instance-information --filters "Key=InstanceIds,Values=<id>"`
3. Restart SSM Agent: Use EC2 console to connect and run `Restart-Service AmazonSSMAgent`

### Frontend Not Accessible

**Problem**: Cannot access website via Elastic IP

**Solution**:
1. Check security group allows port 80/443: `aws ec2 describe-security-groups --group-ids <sg-id>`
2. Verify IIS is running: Connect via SSM and run `Get-Service W3SVC`
3. Check Windows Firewall: `Get-NetFirewallRule -DisplayName "Allow HTTP"`
4. Test locally: `Invoke-WebRequest -Uri http://localhost`

### Backend Database Connection Failed

**Problem**: Frontend cannot connect to backend database

**Solution**:
1. Verify SQL Server running: Connect to backend via SSM and run `Get-Service MSSQL$SQLEXPRESS`
2. Check TCP/IP enabled: `Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\MSSQL15.SQLEXPRESS\MSSQLServer\SuperSocketNetLib\Tcp\IPAll"`
3. Test connection from frontend: `Test-NetConnection -ComputerName <backend-private-ip> -Port 1433`
4. Verify security group allows traffic from frontend SG

### Backup Failed

**Problem**: Scheduled backup task fails

**Solution**:
1. Check backup logs: `Get-Content C:\SQLBackups\backup_*.log | Select-Object -Last 50`
2. Verify disk space: `Get-PSDrive C`
3. Test S3 access: `aws s3 ls s3://made4net-poc-backups-<account-id>/`
4. Run backup manually: `C:\SQLBackups\backup-database.ps1`

## 📚 Additional Resources

### AWS Documentation
- [EC2 Windows Instances](https://docs.aws.amazon.com/AWSEC2/latest/WindowsGuide/)
- [Systems Manager](https://docs.aws.amazon.com/systems-manager/)
- [CloudWatch Agent](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Install-CloudWatch-Agent.html)

### SQL Server
- [SQL Server Express](https://www.microsoft.com/en-us/sql-server/sql-server-downloads)
- [Backup and Restore](https://docs.microsoft.com/en-us/sql/relational-databases/backup-restore/)

### IIS
- [IIS Configuration](https://docs.microsoft.com/en-us/iis/)
- [ASP.NET Core Hosting](https://docs.microsoft.com/en-us/aspnet/core/host-and-deploy/iis/)

## 🧹 Cleanup

To delete all resources and avoid charges:

```powershell
# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name made4net-poc --region us-east-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete --stack-name made4net-poc --region us-east-1

# Empty and delete S3 bucket
aws s3 rm s3://made4net-poc-backups-<account-id> --recursive
aws s3 rb s3://made4net-poc-backups-<account-id>

# Verify all resources deleted
aws cloudformation describe-stacks --stack-name made4net-poc --region us-east-1
```

## 📞 Support

For issues or questions:
1. Check troubleshooting section above
2. Review CloudFormation events: `aws cloudformation describe-stack-events --stack-name made4net-poc`
3. Check CloudWatch Logs for detailed error messages
4. Review design.md for technical specifications

## 📝 License

This deployment package is provided as-is for Made4Net POC purposes.

## 🔄 Version History

- **v1.0** (2024): Initial release with Windows Server 2022, SSM integration, automated backups
