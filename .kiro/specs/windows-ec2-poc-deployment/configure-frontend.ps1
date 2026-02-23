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
<html>
<head>
    <title>Made4Net WMS - Login</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        .login-container {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            width: 350px;
        }
        h1 {
            text-align: center;
            color: #333;
            margin-bottom: 10px;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: bold;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-sizing: border-box;
            font-size: 14px;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            font-weight: bold;
        }
        button:hover {
            background: #5568d3;
        }
        .footer {
            text-align: center;
            margin-top: 20px;
            color: #999;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Made4Net WMS</h1>
        <p class="subtitle">Warehouse Management System</p>
        <form action="/login" method="post">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" placeholder="Enter your username" required>
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" placeholder="Enter your password" required>
            </div>
            <button type="submit">Login</button>
        </form>
        <div class="footer">
            &copy; 2026 Made4Net - POC Environment
        </div>
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
