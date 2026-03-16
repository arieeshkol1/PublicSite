# Update script.js with API endpoint
param(
    [Parameter(Mandatory=$true)]
    [string]$ApiEndpoint
)

Write-Host "Updating script.js with API endpoint..." -ForegroundColor Yellow
Write-Host "Endpoint: $ApiEndpoint" -ForegroundColor Cyan
Write-Host ""

$scriptPath = "script.js"
$content = Get-Content $scriptPath -Raw

$content = $content -replace "const apiEndpoint = 'YOUR_API_GATEWAY_ENDPOINT_HERE';", "const apiEndpoint = '$ApiEndpoint';"

$content | Set-Content $scriptPath -NoNewline

Write-Host "✓ script.js updated!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. git add script.js"
Write-Host "2. git commit -m 'Add contact form API endpoint'"
Write-Host "3. git push origin main"
Write-Host ""
