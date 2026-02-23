# Backend Setup Guide

This directory contains scripts to set up the WMS backend server with SQL Server Express and sample data.

## What's on the Backend Server

The backend EC2 instance is configured with:
- Windows Server 2022
- Private subnet (10.0.2.x) - no direct internet access
- VPC Endpoints for AWS services (SSM, CloudWatch, S3)
- Security group allowing connections from frontend on ports 443 and 1433
- CloudWatch Agent for monitoring
- Automated backup scripts (ready for SQL Server)

## Setup Instructions

### Step 1: Connect to Backend

From your local machine:
```bash
aws ssm start-session --target i-0fded341580cdf584
```

### Step 2: Download Setup Scripts

Once connected to the backend via SSM:
```powershell
# Create directory
New-Item -Path "C:\Setup" -ItemType Directory -Force

# Download scripts from GitHub
$repoUrl = "https://raw.githubusercontent.com/arieeshkol1/TAG-SYSTEM-POC/main/.kiro/specs/windows-ec2-poc-deployment/backend"

Invoke-WebRequest -Uri "$repoUrl/install-sqlserver.ps1" -OutFile "C:\Setup\install-sqlserver.ps1" -UseBasicParsing
Invoke-WebRequest -Uri "$repoUrl/create-wms-database.ps1" -OutFile "C:\Setup\create-wms-database.ps1" -UseBasicParsing
```

### Step 3: Install SQL Server Express

```powershell
cd C:\Setup
.\install-sqlserver.ps1
```

This will:
- Download SQL Server Express 2022
- Install with SA authentication
- Enable TCP/IP protocol
- Configure Windows Firewall
- Set SA password to: `Made4Net2026!`

**Installation takes 10-15 minutes**

### Step 4: Create WMS Database

```powershell
cd C:\Setup
.\create-wms-database.ps1
```

This will create:
- Database: `WMS_POC`
- Tables: Users, Products, Locations, Inventory
- Sample data: 3 users, 10 products, 10 locations, 10 inventory records
- View: `vw_InventoryDashboard` for easy querying

## Database Details

**Connection String:**
```
Server=<backend-private-ip>\SQLEXPRESS;Database=WMS_POC;User Id=sa;Password=Made4Net2026!;TrustServerCertificate=True
```

**Sample Users:**
- `admin` / `demo123` (Administrator)
- `warehouse` / `demo123` (Manager)
- `operator` / `demo123` (Operator)

**Tables:**
- `Users` - User accounts and roles
- `Products` - Product catalog (SKU, name, price)
- `Locations` - Warehouse locations (aisle-rack-shelf)
- `Inventory` - Stock levels by product and location

## Testing the Database

### From Backend Server

```powershell
# Test connection
sqlcmd -S localhost\SQLEXPRESS -U sa -P Made4Net2026! -Q "SELECT @@VERSION"

# Query inventory
sqlcmd -S localhost\SQLEXPRESS -U sa -P Made4Net2026! -d WMS_POC -Q "SELECT * FROM vw_InventoryDashboard"

# Check user count
sqlcmd -S localhost\SQLEXPRESS -U sa -P Made4Net2026! -d WMS_POC -Q "SELECT COUNT(*) as UserCount FROM Users"
```

### From Frontend Server

```powershell
# Test connectivity to backend
Test-NetConnection -ComputerName 10.0.2.154 -Port 1433

# Test SQL connection (requires SQL client tools)
sqlcmd -S 10.0.2.154\SQLEXPRESS -U sa -P Made4Net2026! -Q "SELECT @@VERSION"
```

## Architecture

```
Frontend (Public Subnet)          Backend (Private Subnet)
┌─────────────────────┐          ┌──────────────────────┐
│  IIS Web Server     │          │  SQL Server Express  │
│  - Login Page       │◄────────►│  - WMS_POC Database  │
│  - Dashboard        │   1433   │  - Sample Data       │
│  10.0.1.x          │          │  10.0.2.154          │
└─────────────────────┘          └──────────────────────┘
         │                                  │
         │                                  │
         ▼                                  ▼
    Internet Gateway              VPC Endpoints (SSM, S3)
```

## Security

- Backend has NO internet access (private subnet)
- Frontend can connect to backend on port 1433 only
- SSM access via VPC Endpoints (no NAT Gateway needed)
- SQL Server uses strong password
- All traffic stays within AWS network

## Backup Configuration

The backend is pre-configured with automated backup scripts:
- Location: `C:\SQLBackups\`
- Schedule: Daily at 2 AM
- Retention: Last 3 local backups
- S3 Upload: Automatic to `made4net-poc-backups-991105135552`
- Compression: Enabled
- Checksum: Enabled for integrity validation

## Troubleshooting

### SQL Server Not Starting
```powershell
Get-Service -Name "MSSQL`$SQLEXPRESS"
Start-Service -Name "MSSQL`$SQLEXPRESS"
```

### Firewall Blocking Connections
```powershell
New-NetFirewallRule -DisplayName "SQL Server" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow
```

### Check SQL Server Logs
```powershell
Get-Content "C:\Program Files\Microsoft SQL Server\MSSQL15.SQLEXPRESS\MSSQL\Log\ERRORLOG"
```

## Next Steps

1. **Connect Frontend to Backend** - Update frontend to query real data from SQL Server
2. **Create REST API** - Build API layer between frontend and database
3. **Add Authentication** - Implement real user authentication against Users table
4. **Expand Data Model** - Add orders, shipments, and other WMS entities

## Files in This Directory

- `install-sqlserver.ps1` - Installs SQL Server Express 2022
- `create-wms-database.ps1` - Creates WMS database with sample data
- `README.md` - This file
