# configure-frontend.ps1
# Post-deployment configuration script for frontend instance
# Run this script via SSM Session Manager after instance is launched

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Frontend Configuration Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Install .NET 6 Runtime
Write-Host "Installing .NET 6 Runtime..." -ForegroundColor Yellow
$dotnetUrl = "https://download.visualstudio.microsoft.com/download/pr/c6a74d6b-576c-4ab0-bf55-d46d45610730/f70d2252c9f452c2eb679b8041846466/dotnet-hosting-6.0.25-win.exe"
$dotnetInstaller = "C:\Temp\dotnet-hosting.exe"

New-Item -Path "C:\Temp" -ItemType Directory -Force | Out-Null
Invoke-WebRequest -Uri $dotnetUrl -OutFile $dotnetInstaller -UseBasicParsing
Start-Process $dotnetInstaller -ArgumentList '/quiet /norestart' -Wait
Write-Host "✓ .NET 6 Runtime installed" -ForegroundColor Green

# Configure IIS
Write-Host ""
Write-Host "Configuring IIS..." -ForegroundColor Yellow
Import-Module WebAdministration

# Create application pool
$poolName = "Made4NetPool"
if (!(Test-Path "IIS:\AppPools\$poolName")) {
    New-WebAppPool -Name $poolName
    Set-ItemProperty "IIS:\AppPools\$poolName" -Name managedRuntimeVersion -Value ""
    Set-ItemProperty "IIS:\AppPools\$poolName" -Name enable32BitAppOnWin64 -Value $false
    Write-Host "✓ Application pool created: $poolName" -ForegroundColor Green
} else {
    Write-Host "✓ Application pool already exists: $poolName" -ForegroundColor Green
}

# Create website directory
$sitePath = "C:\inetpub\made4net"
if (!(Test-Path $sitePath)) {
    New-Item -Path $sitePath -ItemType Directory -Force | Out-Null
    Write-Host "✓ Website directory created: $sitePath" -ForegroundColor Green
} else {
    Write-Host "✓ Website directory exists: $sitePath" -ForegroundColor Green
}

# Create default page
$defaultPage = @"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Made4Net WMS - POC</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            padding: 40px;
            max-width: 600px;
            text-align: center;
        }
        h1 {
            color: #667eea;
            margin-bottom: 10px;
        }
        .status {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: left;
        }
        .info h3 {
            margin-top: 0;
            color: #667eea;
        }
        .info ul {
            list-style: none;
            padding: 0;
        }
        .info li {
            padding: 5px 0;
        }
        .info li:before {
            content: "✓ ";
            color: #28a745;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Made4Net WMS</h1>
        <p>Proof of Concept System</p>
        
        <div class="status">
            <strong>✓ Frontend Server Online</strong>
        </div>
        
        <div class="info">
            <h3>System Information</h3>
            <ul>
                <li>IIS 10.0 Web Server</li>
                <li>Windows Server 2022</li>
                <li>.NET 6 Runtime</li>
                <li>AWS Systems Manager Enabled</li>
                <li>CloudWatch Monitoring Active</li>
            </ul>
        </div>
        
        <div class="info">
            <h3>Next Steps</h3>
            <p style="text-align: left;">
                1. Deploy Made4Net WMS application<br>
                2. Configure backend API connection<br>
                3. Set up user authentication<br>
                4. Test inventory management features
            </p>
        </div>
        
        <p style="color: #6c757d; font-size: 14px; margin-top: 30px;">
            Hostname: $env:COMPUTERNAME<br>
            Timestamp: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss UTC")
        </p>
    </div>
</body>
</html>
"@

$defaultPage | Out-File -FilePath "$sitePath\index.html" -Encoding UTF8
Write-Host "✓ Default page created" -ForegroundColor Green

# Create or update website
$siteName = "Made4Net"
if (Test-Path "IIS:\Sites\$siteName") {
    Remove-Website -Name $siteName
}

New-Website -Name $siteName `
    -PhysicalPath $sitePath `
    -ApplicationPool $poolName `
    -Port 80 `
    -Force

Write-Host "✓ Website created: $siteName" -ForegroundColor Green

# Stop default website
Stop-Website -Name "Default Web Site" -ErrorAction SilentlyContinue
Write-Host "✓ Default website stopped" -ForegroundColor Green

# Configure firewall (allow HTTP/HTTPS)
Write-Host ""
Write-Host "Configuring Windows Firewall..." -ForegroundColor Yellow
New-NetFirewallRule -DisplayName "Allow HTTP" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Allow HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue
Write-Host "✓ Firewall rules configured" -ForegroundColor Green

# Install URL Rewrite Module (for HTTPS redirect)
Write-Host ""
Write-Host "Installing IIS URL Rewrite Module..." -ForegroundColor Yellow
$urlRewriteUrl = "https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi"
$urlRewriteInstaller = "C:\Temp\rewrite_amd64.msi"
Invoke-WebRequest -Uri $urlRewriteUrl -OutFile $urlRewriteInstaller -UseBasicParsing
Start-Process msiexec.exe -ArgumentList "/i $urlRewriteInstaller /quiet" -Wait
Write-Host "✓ URL Rewrite Module installed" -ForegroundColor Green

# Create self-signed certificate for HTTPS
Write-Host ""
Write-Host "Creating self-signed SSL certificate..." -ForegroundColor Yellow
$cert = New-SelfSignedCertificate -DnsName "made4net-poc.local" -CertStoreLocation "cert:\LocalMachine\My"
$certThumbprint = $cert.Thumbprint

# Bind HTTPS
New-WebBinding -Name $siteName -Protocol https -Port 443
$binding = Get-WebBinding -Name $siteName -Protocol https
$binding.AddSslCertificate($certThumbprint, "my")
Write-Host "✓ HTTPS binding configured" -ForegroundColor Green

# Test website
Write-Host ""
Write-Host "Testing website..." -ForegroundColor Yellow
Start-Sleep -Seconds 2
try {
    $response = Invoke-WebRequest -Uri "http://localhost" -UseBasicParsing
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ Website is responding" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Website test failed, but configuration is complete" -ForegroundColor Yellow
}

# Display summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Frontend Configuration Summary:" -ForegroundColor Yellow
Write-Host "  IIS Website: $siteName" -ForegroundColor White
Write-Host "  Application Pool: $poolName" -ForegroundColor White
Write-Host "  Physical Path: $sitePath" -ForegroundColor White
Write-Host "  HTTP Port: 80" -ForegroundColor White
Write-Host "  HTTPS Port: 443" -ForegroundColor White
Write-Host "  SSL Certificate: $certThumbprint" -ForegroundColor White
Write-Host ""
Write-Host "Access the website:" -ForegroundColor Yellow
Write-Host "  Internal: http://localhost" -ForegroundColor White
Write-Host "  External: http://<elastic-ip>" -ForegroundColor White
Write-Host "  HTTPS: https://<elastic-ip> (self-signed cert)" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Deploy Made4Net WMS application to $sitePath" -ForegroundColor White
Write-Host "  2. Update web.config with backend API URL" -ForegroundColor White
Write-Host "  3. Configure authentication settings" -ForegroundColor White
Write-Host "  4. Test application functionality" -ForegroundColor White
Write-Host ""
