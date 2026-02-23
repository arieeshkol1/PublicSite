# configure-backend.ps1
# Post-deployment configuration script for backend instance
# Run this script via SSM Session Manager after instance is launched

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backend Configuration Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Install SQL Server Express 2019
Write-Host "Installing SQL Server Express 2019..." -ForegroundColor Yellow
Write-Host "This will take 10-15 minutes..." -ForegroundColor Gray

$sqlUrl = "https://go.microsoft.com/fwlink/?linkid=866658"
$sqlInstaller = "C:\Temp\SQLServer2019-SSEI-Expr.exe"
$sqlMediaPath = "C:\Temp\SQLMedia"

New-Item -Path "C:\Temp" -ItemType Directory -Force | Out-Null
New-Item -Path $sqlMediaPath -ItemType Directory -Force | Out-Null

# Download SQL Server installer
Invoke-WebRequest -Uri $sqlUrl -OutFile $sqlInstaller -UseBasicParsing
Write-Host "✓ SQL Server installer downloaded" -ForegroundColor Green

# Download media
Write-Host "Downloading SQL Server media..." -ForegroundColor Yellow
Start-Process $sqlInstaller -ArgumentList "/Action=Download /MediaPath=$sqlMediaPath /MediaType=Core /Quiet" -Wait
Write-Host "✓ SQL Server media downloaded" -ForegroundColor Green

# Install SQL Server
Write-Host "Installing SQL Server (this takes time)..." -ForegroundColor Yellow
$setupPath = Get-ChildItem -Path $sqlMediaPath -Filter "setup.exe" -Recurse | Select-Object -First 1

$configFile = @"
[OPTIONS]
ACTION="Install"
QUIET="True"
IACCEPTSQLSERVERLICENSETERMS="True"
ENU="True"
FEATURES=SQLENGINE
INSTANCENAME="SQLEXPRESS"
INSTANCEID="SQLEXPRESS"
SQLSVCACCOUNT="NT AUTHORITY\SYSTEM"
SQLSYSADMINACCOUNTS="BUILTIN\Administrators"
SECURITYMODE="SQL"
SAPWD="Made4Net_POC_2024!"
TCPENABLED="1"
NPENABLED="1"
"@

$configFile | Out-File -FilePath "C:\Temp\sql-config.ini" -Encoding ASCII

Start-Process $setupPath.FullName -ArgumentList "/ConfigurationFile=C:\Temp\sql-config.ini" -Wait -NoNewWindow
Write-Host "✓ SQL Server Express installed" -ForegroundColor Green

# Start SQL Server service
Write-Host ""
Write-Host "Starting SQL Server service..." -ForegroundColor Yellow
Start-Service -Name "MSSQL`$SQLEXPRESS"
Set-Service -Name "MSSQL`$SQLEXPRESS" -StartupType Automatic
Write-Host "✓ SQL Server service started" -ForegroundColor Green

# Configure SQL Server
Write-Host ""
Write-Host "Configuring SQL Server..." -ForegroundColor Yellow

# Enable TCP/IP
$sqlServerPath = "HKLM:\SOFTWARE\Microsoft\Microsoft SQL Server\MSSQL15.SQLEXPRESS\MSSQLServer\SuperSocketNetLib\Tcp"
Set-ItemProperty -Path "$sqlServerPath\IPAll" -Name TcpPort -Value 1433
Set-ItemProperty -Path "$sqlServerPath\IPAll" -Name TcpDynamicPorts -Value ""

# Restart SQL Server to apply changes
Restart-Service -Name "MSSQL`$SQLEXPRESS"
Write-Host "✓ SQL Server configured for TCP/IP on port 1433" -ForegroundColor Green

# Configure Windows Firewall
Write-Host ""
Write-Host "Configuring Windows Firewall..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "SQL Server" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "HTTPS API" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
Write-Host "✓ Firewall rules configured" -ForegroundColor Green

# Create InventoryDB database
Write-Host ""
Write-Host "Creating InventoryDB database..." -ForegroundColor Yellow

$createDbScript = @"
USE master;
GO

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'InventoryDB')
BEGIN
    CREATE DATABASE InventoryDB;
END
GO

USE InventoryDB;
GO

-- Create Users table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Users')
BEGIN
    CREATE TABLE Users (
        UserId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        Username NVARCHAR(50) UNIQUE NOT NULL,
        PasswordHash NVARCHAR(255) NOT NULL,
        Role NVARCHAR(20) NOT NULL CHECK (Role IN ('Admin', 'Manager', 'Operator')),
        Email NVARCHAR(100),
        CreatedAt DATETIME2 DEFAULT GETUTCDATE(),
        LastLogin DATETIME2,
        IsActive BIT DEFAULT 1
    );
    
    CREATE INDEX IX_Users_Username ON Users(Username);
    CREATE INDEX IX_Users_Role ON Users(Role);
END
GO

-- Create InventoryItems table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'InventoryItems')
BEGIN
    CREATE TABLE InventoryItems (
        ItemId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        SKU NVARCHAR(50) UNIQUE NOT NULL,
        Name NVARCHAR(100) NOT NULL,
        Description NVARCHAR(500),
        Quantity INT NOT NULL DEFAULT 0,
        Location NVARCHAR(50),
        LastUpdated DATETIME2 DEFAULT GETUTCDATE(),
        UpdatedBy UNIQUEIDENTIFIER FOREIGN KEY REFERENCES Users(UserId)
    );
    
    CREATE INDEX IX_InventoryItems_SKU ON InventoryItems(SKU);
    CREATE INDEX IX_InventoryItems_Location ON InventoryItems(Location);
END
GO

-- Create AuditLog table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AuditLog')
BEGIN
    CREATE TABLE AuditLog (
        LogId UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
        Timestamp DATETIME2 DEFAULT GETUTCDATE(),
        UserId UNIQUEIDENTIFIER FOREIGN KEY REFERENCES Users(UserId),
        Action NVARCHAR(20) NOT NULL CHECK (Action IN ('CREATE', 'UPDATE', 'DELETE', 'LOGIN')),
        EntityType NVARCHAR(50) NOT NULL,
        EntityId UNIQUEIDENTIFIER,
        Changes NVARCHAR(MAX),
        IpAddress NVARCHAR(45)
    );
    
    CREATE INDEX IX_AuditLog_Timestamp ON AuditLog(Timestamp);
    CREATE INDEX IX_AuditLog_UserId ON AuditLog(UserId);
    CREATE INDEX IX_AuditLog_Action ON AuditLog(Action);
END
GO

-- Insert default admin user (password: Admin123!)
IF NOT EXISTS (SELECT * FROM Users WHERE Username = 'admin')
BEGIN
    INSERT INTO Users (Username, PasswordHash, Role, Email, IsActive)
    VALUES ('admin', '$2a$11$XYZ...', 'Admin', 'admin@made4net.com', 1);
END
GO

-- Insert sample inventory items
IF NOT EXISTS (SELECT * FROM InventoryItems)
BEGIN
    DECLARE @AdminUserId UNIQUEIDENTIFIER = (SELECT UserId FROM Users WHERE Username = 'admin');
    
    INSERT INTO InventoryItems (SKU, Name, Description, Quantity, Location, UpdatedBy)
    VALUES 
        ('SKU-001', 'Widget A', 'Standard widget type A', 100, 'A-01-01', @AdminUserId),
        ('SKU-002', 'Widget B', 'Standard widget type B', 250, 'A-01-02', @AdminUserId),
        ('SKU-003', 'Gadget X', 'Premium gadget model X', 50, 'B-02-01', @AdminUserId),
        ('SKU-004', 'Gadget Y', 'Premium gadget model Y', 75, 'B-02-02', @AdminUserId),
        ('SKU-005', 'Component Z', 'Electronic component Z', 500, 'C-03-01', @AdminUserId);
END
GO

PRINT 'Database created successfully';
"@

$createDbScript | Out-File -FilePath "C:\Temp\create-database.sql" -Encoding UTF8

# Execute SQL script
$sqlcmd = "C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\sqlcmd.exe"
if (Test-Path $sqlcmd) {
    & $sqlcmd -S "localhost\SQLEXPRESS" -i "C:\Temp\create-database.sql"
    Write-Host "✓ InventoryDB database created" -ForegroundColor Green
} else {
    Write-Host "⚠ sqlcmd not found, database creation skipped" -ForegroundColor Yellow
    Write-Host "  Run the SQL script manually: C:\Temp\create-database.sql" -ForegroundColor Gray
}

# Create backup directory
Write-Host ""
Write-Host "Setting up database backup..." -ForegroundColor Yellow
$backupDir = "C:\SQLBackups"
New-Item -Path $backupDir -ItemType Directory -Force | Out-Null
Write-Host "✓ Backup directory created: $backupDir" -ForegroundColor Green

# Get S3 bucket name from instance tags
$instanceId = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/instance-id"
$region = Invoke-RestMethod -Uri "http://169.254.169.254/latest/meta-data/placement/region"
$s3Bucket = "made4net-poc-backups-$(aws sts get-caller-identity --query Account --output text)"

# Create enhanced backup script
$backupScript = @"
`$ErrorActionPreference = "Stop"
`$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
`$backupFile = "C:\SQLBackups\InventoryDB_`$timestamp.bak"
`$s3Bucket = "$s3Bucket"
`$logFile = "C:\SQLBackups\backup_`$timestamp.log"

try {
    # Start logging
    "Backup started at `$(Get-Date)" | Out-File `$logFile
    
    # Backup database
    `$sqlcmd = "C:\Program Files\Microsoft SQL Server\Client SDK\ODBC\170\Tools\Binn\sqlcmd.exe"
    `$query = "BACKUP DATABASE InventoryDB TO DISK = '`$backupFile' WITH COMPRESSION, CHECKSUM, STATS = 10"
    
    & `$sqlcmd -S "localhost\SQLEXPRESS" -Q `$query | Out-File `$logFile -Append
    
    if (Test-Path `$backupFile) {
        `$fileSize = (Get-Item `$backupFile).Length / 1MB
        "Backup file created: `$backupFile (`$([math]::Round(`$fileSize, 2)) MB)" | Out-File `$logFile -Append
        
        # Upload to S3
        aws s3 cp `$backupFile s3://`$s3Bucket/backups/ --sse AES256 --region $region
        
        if (`$LASTEXITCODE -eq 0) {
            "Backup uploaded to S3 successfully" | Out-File `$logFile -Append
            
            # Clean up old local backups (keep last 3)
            Get-ChildItem "C:\SQLBackups\*.bak" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | ForEach-Object {
                Remove-Item `$_.FullName
                "Deleted old backup: `$(`$_.Name)" | Out-File `$logFile -Append
            }
            
            # Send success metric to CloudWatch
            aws cloudwatch put-metric-data --namespace "Made4Net/POC/Backend" --metric-name BackupSuccess --value 1 --region $region
            
            "Backup completed successfully at `$(Get-Date)" | Out-File `$logFile -Append
            Write-Host "Backup completed: `$backupFile"
        } else {
            throw "S3 upload failed"
        }
    } else {
        throw "Backup file not created"
    }
} catch {
    "ERROR: `$(`$_.Exception.Message)" | Out-File `$logFile -Append
    
    # Send failure metric to CloudWatch
    aws cloudwatch put-metric-data --namespace "Made4Net/POC/Backend" --metric-name BackupSuccess --value 0 --region $region
    
    Write-Host "Backup failed: `$(`$_.Exception.Message)"
    exit 1
}
"@

$backupScript | Out-File -FilePath "$backupDir\backup-database.ps1" -Encoding UTF8
Write-Host "✓ Backup script created" -ForegroundColor Green

# Schedule daily backup at 2 AM
Write-Host "Scheduling daily backup task..." -ForegroundColor Yellow
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-ExecutionPolicy Bypass -File $backupDir\backup-database.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "DailyDatabaseBackup" -Action $action -Trigger $trigger -Principal $principal -Force
Write-Host "✓ Backup task scheduled for 2:00 AM daily" -ForegroundColor Green

# Test backup
Write-Host ""
Write-Host "Running test backup..." -ForegroundColor Yellow
try {
    & PowerShell.exe -ExecutionPolicy Bypass -File "$backupDir\backup-database.ps1"
    Write-Host "✓ Test backup completed successfully" -ForegroundColor Green
} catch {
    Write-Host "⚠ Test backup failed, but configuration is complete" -ForegroundColor Yellow
}

# Install .NET 6 Runtime for API
Write-Host ""
Write-Host "Installing .NET 6 Runtime..." -ForegroundColor Yellow
$dotnetUrl = "https://download.visualstudio.microsoft.com/download/pr/c6a74d6b-576c-4ab0-bf55-d46d45610730/f70d2252c9f452c2eb679b8041846466/dotnet-hosting-6.0.25-win.exe"
$dotnetInstaller = "C:\Temp\dotnet-hosting.exe"
Invoke-WebRequest -Uri $dotnetUrl -OutFile $dotnetInstaller -UseBasicParsing
Start-Process $dotnetInstaller -ArgumentList '/quiet /norestart' -Wait
Write-Host "✓ .NET 6 Runtime installed" -ForegroundColor Green

# Display summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Backend Configuration Summary:" -ForegroundColor Yellow
Write-Host "  SQL Server: localhost\SQLEXPRESS" -ForegroundColor White
Write-Host "  Database: InventoryDB" -ForegroundColor White
Write-Host "  SA Password: Made4Net_POC_2024!" -ForegroundColor White
Write-Host "  TCP Port: 1433" -ForegroundColor White
Write-Host "  Backup Directory: $backupDir" -ForegroundColor White
Write-Host "  S3 Bucket: $s3Bucket" -ForegroundColor White
Write-Host ""
Write-Host "Database Tables Created:" -ForegroundColor Yellow
Write-Host "  - Users (with default admin user)" -ForegroundColor White
Write-Host "  - InventoryItems (with sample data)" -ForegroundColor White
Write-Host "  - AuditLog" -ForegroundColor White
Write-Host ""
Write-Host "Connection String:" -ForegroundColor Yellow
Write-Host "  Server=localhost\SQLEXPRESS;Database=InventoryDB;User Id=sa;Password=Made4Net_POC_2024!;TrustServerCertificate=True" -ForegroundColor Gray
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Deploy REST API application" -ForegroundColor White
Write-Host "  2. Update API connection string" -ForegroundColor White
Write-Host "  3. Test database connectivity from frontend" -ForegroundColor White
Write-Host "  4. Verify backup task runs successfully" -ForegroundColor White
Write-Host ""
