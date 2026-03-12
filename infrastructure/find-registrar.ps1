# Find where eshkol.ai is registered

$Domain = "eshkol.ai"

Write-Host "=== Finding Registrar for $Domain ===" -ForegroundColor Cyan
Write-Host ""

# Check AWS Route 53 Domains
Write-Host "Checking AWS Route 53 Domains..." -ForegroundColor Yellow
$awsDomains = aws route53domains list-domains --region us-east-1 --output json 2>$null | ConvertFrom-Json

$foundInAWS = $false
if ($awsDomains.Domains) {
    foreach ($d in $awsDomains.Domains) {
        if ($d.DomainName -eq $Domain) {
            $foundInAWS = $true
            Write-Host "FOUND in AWS Route 53 Domains!" -ForegroundColor Green
            Write-Host "Account: 991105135552" -ForegroundColor Gray
            break
        }
    }
}

if (-not $foundInAWS) {
    Write-Host "NOT found in AWS Route 53 Domains (account 991105135552)" -ForegroundColor Red
}

Write-Host ""

# Check current nameservers
Write-Host "Current nameservers (what the internet sees):" -ForegroundColor Yellow
$nsLookup = nslookup -type=NS $Domain 8.8.8.8 2>&1 | Out-String
Write-Host $nsLookup -ForegroundColor Gray

# Analyze nameservers
if ($nsLookup -match "registrar-servers.com") {
    Write-Host "Analysis: Domain is using generic registrar nameservers" -ForegroundColor Yellow
    Write-Host "This suggests the domain is registered with a third-party registrar" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Common registrars that use 'registrar-servers.com':" -ForegroundColor Cyan
    Write-Host "  - Namecheap" -ForegroundColor White
    Write-Host "  - Name.com" -ForegroundColor White
    Write-Host "  - eNom" -ForegroundColor White
    Write-Host "  - ResellerClub" -ForegroundColor White
}
elseif ($nsLookup -match "awsdns") {
    Write-Host "Analysis: Domain is using AWS Route 53 nameservers" -ForegroundColor Green
    Write-Host "Nameservers are configured correctly!" -ForegroundColor Green
}
else {
    Write-Host "Analysis: Domain is using custom nameservers" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== How to Find Your Registrar ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Check your email for domain purchase confirmation" -ForegroundColor White
Write-Host "   Search for: 'eshkol.ai' or 'domain registration'" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Check these common registrars:" -ForegroundColor White
Write-Host "   - Namecheap: https://www.namecheap.com" -ForegroundColor Gray
Write-Host "   - GoDaddy: https://www.godaddy.com" -ForegroundColor Gray
Write-Host "   - Google Domains: https://domains.google.com" -ForegroundColor Gray
Write-Host "   - Cloudflare: https://www.cloudflare.com" -ForegroundColor Gray
Write-Host "   - Name.com: https://www.name.com" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Check AWS Console:" -ForegroundColor White
Write-Host "   - Route 53 > Registered domains" -ForegroundColor Gray
Write-Host "   - Make sure you're in account: 991105135552" -ForegroundColor Gray
Write-Host "   - Check if domain is listed there" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Once you find the registrar:" -ForegroundColor White
Write-Host "   - Log in to the registrar" -ForegroundColor Gray
Write-Host "   - Find 'eshkol.ai' in your domain list" -ForegroundColor Gray
Write-Host "   - Update nameservers to:" -ForegroundColor Gray
Write-Host "     ns-1673.awsdns-17.co.uk" -ForegroundColor Cyan
Write-Host "     ns-286.awsdns-35.com" -ForegroundColor Cyan
Write-Host "     ns-690.awsdns-22.net" -ForegroundColor Cyan
Write-Host "     ns-1252.awsdns-28.org" -ForegroundColor Cyan
