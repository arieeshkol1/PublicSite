# Verify Amazon Bedrock Model Access
# This script checks if the Nova Lite model is accessible

$Region = "us-east-1"
$ModelId = "amazon.nova-lite-v1:0"

Write-Host "Verifying Amazon Bedrock access in $Region..." -ForegroundColor Green
Write-Host ""

# List all available foundation models
Write-Host "Checking available Bedrock models..." -ForegroundColor Yellow
$models = aws bedrock list-foundation-models --region $Region --output json | ConvertFrom-Json

# Filter for Nova Lite
$novaLite = $models.modelSummaries | Where-Object { $_.modelId -like "*nova-lite*" }

if ($novaLite) {
    Write-Host "✓ Nova Lite model found!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Model Details:" -ForegroundColor Cyan
    Write-Host "  Model ID: $($novaLite.modelId)"
    Write-Host "  Model Name: $($novaLite.modelName)"
    Write-Host "  Provider: $($novaLite.providerName)"
    Write-Host ""
    
    # Try to get model details (this will fail if access is not granted)
    Write-Host "Testing model access..." -ForegroundColor Yellow
    try {
        $modelInfo = aws bedrock get-foundation-model --model-identifier $ModelId --region $Region 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Model access is ENABLED!" -ForegroundColor Green
            Write-Host ""
            Write-Host "You can proceed with Lambda function deployment." -ForegroundColor Cyan
        } else {
            Write-Host "✗ Model access may not be enabled." -ForegroundColor Red
            Write-Host ""
            Write-Host "To enable access:" -ForegroundColor Yellow
            Write-Host "1. Go to AWS Console → Amazon Bedrock"
            Write-Host "2. Click 'Model access' in the left sidebar"
            Write-Host "3. Click 'Manage model access'"
            Write-Host "4. Find 'Nova Lite' and enable access"
            Write-Host "5. Wait for access to be granted"
        }
    } catch {
        Write-Host "✗ Error checking model access: $_" -ForegroundColor Red
    }
} else {
    Write-Host "✗ Nova Lite model not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Available models:" -ForegroundColor Yellow
    $models.modelSummaries | Select-Object modelId, modelName, providerName | Format-Table
    Write-Host ""
    Write-Host "Please ensure:" -ForegroundColor Yellow
    Write-Host "1. You're using the correct region (us-east-1)"
    Write-Host "2. Amazon Bedrock is available in your account"
    Write-Host "3. You have requested model access in the Bedrock console"
}
