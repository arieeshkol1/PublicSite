<#
.SYNOPSIS
    Sets up slashmycloudbill.com to serve the SlashMyBill flow via CloudFront.
    
.DESCRIPTION
    This script:
    1. Requests an ACM SSL certificate for slashmycloudbill.com + www.slashmycloudbill.com
    2. Adds DNS validation records to Route 53
    3. Waits for certificate validation
    4. Adds slashmycloudbill.com as an alternate domain on the existing CloudFront distribution
    5. Creates Route 53 A/AAAA alias records pointing to CloudFront
    
    After this runs, both domains serve the same S3 content.
    A CloudFront Function handles the routing:
      - slashmycloudbill.com/ → /slashMyBill/index.html
      - slashmycloudbill.com/members/ → /members/index.html
      - eshkolai.com/* → unchanged (existing behavior)

.NOTES
    Run this once. Requires AWS CLI with permissions for:
    acm:RequestCertificate, acm:DescribeCertificate, acm:ListCertificates
    cloudfront:UpdateDistribution, cloudfront:GetDistribution
    route53:ChangeResourceRecordSets
#>

$DISTRIBUTION_ID = "E12JIHGHK40OLE"
$HOSTED_ZONE_ID = "Z08610352PUNQ7MUZTRVI"
$DOMAIN = "slashmycloudbill.com"
$WWW_DOMAIN = "www.slashmycloudbill.com"
$REGION = "us-east-1"

Write-Host "=== SlashMyCloudBill.com Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Request ACM Certificate ──────────────────────────────────────
Write-Host "Step 1: Requesting SSL certificate for $DOMAIN..." -ForegroundColor Yellow

$certArn = aws acm request-certificate `
    --domain-name $DOMAIN `
    --subject-alternative-names $WWW_DOMAIN `
    --validation-method DNS `
    --region $REGION `
    --query "CertificateArn" `
    --output text 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR requesting certificate: $certArn" -ForegroundColor Red
    exit 1
}
Write-Host "Certificate ARN: $certArn" -ForegroundColor Green

# ── Step 2: Get DNS validation records ───────────────────────────────────
Write-Host ""
Write-Host "Step 2: Getting DNS validation records..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$certDetails = aws acm describe-certificate `
    --certificate-arn $certArn `
    --region $REGION `
    --query "Certificate.DomainValidationOptions" `
    --output json | ConvertFrom-Json

# Add validation CNAME records to Route 53
$changes = @()
foreach ($dv in $certDetails) {
    if ($dv.ResourceRecord) {
        $changes += @{
            Action = "UPSERT"
            ResourceRecordSet = @{
                Name = $dv.ResourceRecord.Name
                Type = $dv.ResourceRecord.Type
                TTL = 300
                ResourceRecords = @(@{ Value = $dv.ResourceRecord.Value })
            }
        }
        Write-Host "  Adding CNAME: $($dv.ResourceRecord.Name)" -ForegroundColor Gray
    }
}

if ($changes.Count -gt 0) {
    $changeBatch = @{ Changes = $changes } | ConvertTo-Json -Depth 10
    aws route53 change-resource-record-sets `
        --hosted-zone-id $HOSTED_ZONE_ID `
        --change-batch $changeBatch | Out-Null
    Write-Host "DNS validation records added." -ForegroundColor Green
}

# ── Step 3: Wait for certificate validation ───────────────────────────────
Write-Host ""
Write-Host "Step 3: Waiting for certificate validation (may take 2-5 minutes)..." -ForegroundColor Yellow
$maxWait = 600
$waited = 0
do {
    Start-Sleep -Seconds 15
    $waited += 15
    $status = aws acm describe-certificate `
        --certificate-arn $certArn `
        --region $REGION `
        --query "Certificate.Status" `
        --output text
    Write-Host "  Status: $status ($waited s)" -ForegroundColor Gray
} while ($status -ne "ISSUED" -and $waited -lt $maxWait)

if ($status -ne "ISSUED") {
    Write-Host "Certificate not yet issued after $maxWait seconds." -ForegroundColor Red
    Write-Host "Re-run this script later, or check ACM console." -ForegroundColor Yellow
    Write-Host "Certificate ARN to use: $certArn" -ForegroundColor Cyan
    exit 1
}
Write-Host "Certificate ISSUED!" -ForegroundColor Green

# ── Step 4: Add domain to CloudFront distribution ────────────────────────
Write-Host ""
Write-Host "Step 4: Adding $DOMAIN to CloudFront distribution $DISTRIBUTION_ID..." -ForegroundColor Yellow

# Get current distribution config
$distConfig = aws cloudfront get-distribution-config `
    --id $DISTRIBUTION_ID `
    --output json | ConvertFrom-Json

$etag = $distConfig.ETag
$config = $distConfig.DistributionConfig

# Add new aliases
$existingAliases = $config.Aliases.Items
if ($existingAliases -notcontains $DOMAIN) {
    $config.Aliases.Items += $DOMAIN
    $config.Aliases.Quantity = $config.Aliases.Items.Count
}
if ($existingAliases -notcontains $WWW_DOMAIN) {
    $config.Aliases.Items += $WWW_DOMAIN
    $config.Aliases.Quantity = $config.Aliases.Items.Count
}

# Add certificate
$config.ViewerCertificate.ACMCertificateArn = $certArn
$config.ViewerCertificate.SSLSupportMethod = "sni-only"
$config.ViewerCertificate.MinimumProtocolVersion = "TLSv1.2_2021"
$config.ViewerCertificate.CloudFrontDefaultCertificate = $false

$configJson = $config | ConvertTo-Json -Depth 20
aws cloudfront update-distribution `
    --id $DISTRIBUTION_ID `
    --distribution-config $configJson `
    --if-match $etag | Out-Null

Write-Host "CloudFront distribution updated." -ForegroundColor Green

# ── Step 5: Add Route 53 DNS records ─────────────────────────────────────
Write-Host ""
Write-Host "Step 5: Adding Route 53 DNS records for $DOMAIN..." -ForegroundColor Yellow

$cfDomain = "d13k71im98zj35.cloudfront.net"

$dnsChanges = @{
    Changes = @(
        @{
            Action = "UPSERT"
            ResourceRecordSet = @{
                Name = $DOMAIN
                Type = "A"
                AliasTarget = @{
                    HostedZoneId = "Z2FDTNDATAQYW2"  # CloudFront hosted zone ID (always this value)
                    DNSName = $cfDomain
                    EvaluateTargetHealth = $false
                }
            }
        },
        @{
            Action = "UPSERT"
            ResourceRecordSet = @{
                Name = $DOMAIN
                Type = "AAAA"
                AliasTarget = @{
                    HostedZoneId = "Z2FDTNDATAQYW2"
                    DNSName = $cfDomain
                    EvaluateTargetHealth = $false
                }
            }
        },
        @{
            Action = "UPSERT"
            ResourceRecordSet = @{
                Name = $WWW_DOMAIN
                Type = "A"
                AliasTarget = @{
                    HostedZoneId = "Z2FDTNDATAQYW2"
                    DNSName = $cfDomain
                    EvaluateTargetHealth = $false
                }
            }
        }
    )
} | ConvertTo-Json -Depth 10

aws route53 change-resource-record-sets `
    --hosted-zone-id $HOSTED_ZONE_ID `
    --change-batch $dnsChanges | Out-Null

Write-Host "DNS records created." -ForegroundColor Green

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next step: Create a CloudFront Function to route slashmycloudbill.com" -ForegroundColor Yellow
Write-Host "to /slashMyBill/ automatically. Run: setup-cf-function.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "DNS propagation may take up to 48 hours." -ForegroundColor Gray
Write-Host "Test with: https://slashmycloudbill.com/slashMyBill/" -ForegroundColor Cyan
