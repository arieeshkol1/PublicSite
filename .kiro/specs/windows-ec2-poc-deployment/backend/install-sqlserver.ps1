# Install SQL Server Express on Backend
# Run this script via SSM Session Manager

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "SQL Server Express Installation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Create temp directory
New-Item -Path "C:\Temp" -ItemType Directory -Force | Out-Null

# Download SQL Server Express 2022
Write-Host "Downloading SQL Server Express 2022..." -ForegroundColor Yellow
$sqlUrl = "https://go.microsoft.com/fwlink/p/?linkid=2216019&clcid=0x409&culture=en-us&country=us"
$sqlInstaller = "C:\Temp\SQLEXPR_x64_ENU.exe"

Invoke-WebRequest -Uri $sqlUrl -OutFile $sqlInstaller -UseBasicParsing
Write-Host "✓ Downloaded SQL Server Express" -ForegroundColor Green

# Install SQL Server Express
Write-Host ""
Write-Host "Installing SQL Server Express (this may take 10-15 minutes)..." -ForegroundColor Yellow
$installArgs = @(
    "/Q",
    "/ACTION=Install",
    "/FEATURES=SQLEngine",
    "/INSTANCENAME=SQLEXPRESS",
    "/SECURITYMODE=SQL",
    "/SAPWD=Made4Net2026!",
    "/SQLSVCACCOUNT=`"NT AUTHORITY\SYSTEM`"",
    "/SQLSYSADMINACCOUNTS=`"BUILTIN\Administrators`"",
    "/TCPENABLED=1",
    "/IACCEPTSQLSERVERLICENSETERMS"
)

Start-Process -FilePath $sqlInstaller -ArgumentList $installArgs -Wait -NoNewWindow
Write-Host "✓ SQL Server Express installed" -ForegroundColor Green

# Enable TCP/IP protocol
Write-Host ""
Write-Host "Configuring SQL Server..." -ForegroundColor Yellow

# Import SQL Server module
Import-Module "C:\Program Files\Microsoft SQL Server\150\Tools\PowerShell\Modules\SQLPS" -DisableNameChecking

# Enable TCP/IP
$smo = 'Microsoft.SqlServer.Management.Smo.'
$wmi = New-Object ($smo + 'Wmi.ManagedComputer')
$uri = "ManagedComputer[@Name='$env:COMPUTERNAME']/ServerInstance[@Name='SQLEXPRESS']/ServerProtocol[@Name='Tcp']"
$tcp = $wmi.GetSmoObject($uri)
$tcp.IsEnabled = $true
$tcp.Alter()

Write-Host "✓ TCP/IP protocol enabled" -ForegroundColor Green

# Configure Windows Firewall
Write-Host ""
Write-Host "Configuring Windows Firewall..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "SQL Server" -Direction Inbound -Protocol TCP -LocalPort 1433 -Action Allow -ErrorAction SilentlyContinue
Write-Host "✓ Firewall rule created" -ForegroundColor Green

# Restart SQL Server service
Write-Host ""
Write-Host "Restarting SQL Server..." -ForegroundColor Yellow
Restart-Service -Name "MSSQL`$SQLEXPRESS" -Force
Start-Sleep -Seconds 5
Write-Host "✓ SQL Server restarted" -ForegroundColor Green

# Test connection
Write-Host ""
Write-Host "Testing SQL Server connection..." -ForegroundColor Yellow
$connectionString = "Server=localhost\SQLEXPRESS;User Id=sa;Password=Made4Net2026!;TrustServerCertificate=True"
try {
    $connection = New-Object System.Data.SqlClient.SqlConnection($connectionString)
    $connection.Open()
    $connection.Close()
    Write-Host "✓ SQL Server is running and accessible" -ForegroundColor Green
} catch {
    Write-Host "⚠ Connection test failed: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "SQL Server Details:" -ForegroundColor Yellow
Write-Host "  Instance: localhost\SQLEXPRESS" -ForegroundColor White
Write-Host "  SA Password: Made4Net2026!" -ForegroundColor White
Write-Host "  TCP Port: 1433" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Run create-wms-database.ps1 to create the WMS database" -ForegroundColor White
Write-Host "  2. Test connection from frontend" -ForegroundColor White
Write-Host ""
