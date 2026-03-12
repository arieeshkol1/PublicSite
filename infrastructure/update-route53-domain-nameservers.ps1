# Update nameservers for a domain registered in Route 53
# This updates the domain registration to use the hosted zone nameservers

$DomainName = "eshkol.ai"
$HostedZoneId = "Z06481861W6WD32QMETRV"

Write-Host "Checking if domain is registered in this AWS account..." -ForegroundColor Cyan

# Check if domain exists in Route 53 Domains
$domains = aws route53domains list-domains --region us-east-1 --output json | ConvertFrom-Json

$domainFound = $false
foreach ($domain in $domains.Domains) {
    if ($domain.DomainName -eq $DomainName) {
        $domainFound = $true
        break
    }
}

if (-not $domainFound) {
    Write-Host "ERROR: Domain $DomainName is NOT registered in this AWS account!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible reasons:" -ForegroundColor Yellow
    Write-Host "1. Domain was registered in a different AWS account"
    Write-Host "2. Domain was registered with a different registrar (not Route 53)"
    Write-Host "3. Domain registration is in a different region"
    Write-Host ""
    Write-Host "Please check:" -ForegroundColor Cyan
    Write-Host "- AWS Console > Route 53 > Registered domains"
    Write-Host "- Make sure you're in the correct AWS account (991105135552)"
    Write-Host "- Check if domain was registered elsewhere (Namecheap, GoDaddy, etc.)"
    exit 1
}

Write-Host "Domain found in Route 53 Domains!" -ForegroundColor Green
Write-Host ""

# Get hosted zone nameservers
Write-Host "Getting nameservers from hosted zone..." -ForegroundColor Cyan
$hostedZone = aws route53 get-hosted-zone --id $HostedZoneId --output json | ConvertFrom-Json
$nameservers = $hostedZone.DelegationSet.NameServers

Write-Host "Hosted zone nameservers:" -ForegroundColor Green
foreach ($ns in $nameservers) {
    Write-Host "  - $ns" -ForegroundColor Gray
}
Write-Host ""

# Update domain nameservers
Write-Host "Updating domain registration nameservers..." -ForegroundColor Cyan

$nameserverJson = $nameservers | ForEach-Object { @{Name=$_} } | ConvertTo-Json -Compress

# Create nameservers JSON array
$nsArray = "["
for ($i = 0; $i -lt $nameservers.Count; $i++) {
    $nsArray += "{`"Name`":`"$($nameservers[$i])`"}"
    if ($i -lt $nameservers.Count - 1) {
        $nsArray += ","
    }
}
$nsArray += "]"

Write-Host "Nameservers JSON: $nsArray" -ForegroundColor Gray

# Update the domain
aws route53domains update-domain-nameservers `
    --region us-east-1 `
    --domain-name $DomainName `
    --nameservers $nsArray

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "SUCCESS! Domain nameservers updated!" -ForegroundColor Green
    Write-Host ""
    Write-Host "DNS propagation will take 1-2 hours (up to 48 hours)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Test with:" -ForegroundColor Cyan
    Write-Host "  nslookup -type=NS eshkol.ai 8.8.8.8" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "ERROR: Failed to update nameservers" -ForegroundColor Red
    Write-Host "You may need to update them manually in the AWS Console:" -ForegroundColor Yellow
    Write-Host "  Route 53 > Registered domains > eshkol.ai > Add or edit name servers"
}
