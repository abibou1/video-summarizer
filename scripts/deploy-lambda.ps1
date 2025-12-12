# scripts/deploy-lambda.ps1
# Minimal Lambda Docker deployment script

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("create", "update")]
    [string]$Action = "update",
    
    [Parameter(Mandatory=$false)]
    [string]$ImageTag = "latest"
)

# Load .env file
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Variable -Name $name -Value $value -Scope Script
        }
    }
} else {
    Write-Host "Error: .env file not found" -ForegroundColor Red
    exit 1
}

# Configuration
$ECR_REPOSITORY_NAME = "video-summarizer"
$LAMBDA_FUNCTION_NAME = "video-summarizer"
$LAMBDA_ROLE_NAME = "lambda-execution-role"
$LAMBDA_TIMEOUT = 900
$LAMBDA_MEMORY_SIZE = 1024
$AWS_REGION = if ($AWS_REGION) { $AWS_REGION } else { "us-east-1" }

# Derived values
$ECR_REGISTRY = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
$ECR_IMAGE_URI = "${ECR_REGISTRY}/${ECR_REPOSITORY_NAME}:${ImageTag}"
$LAMBDA_ROLE_ARN = "arn:aws:iam::${AWS_ACCOUNT_ID}:role/${LAMBDA_ROLE_NAME}"

# Authenticate to ECR
Write-Host "Authenticating to ECR..." -ForegroundColor Cyan
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY
if ($LASTEXITCODE -ne 0) { exit 1 }

# Build image
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker buildx build --platform linux/amd64 --no-cache -t ${ECR_REPOSITORY_NAME}:${ImageTag} .
if ($LASTEXITCODE -ne 0) { exit 1 }

# Tag and push
Write-Host "Tagging and pushing image..." -ForegroundColor Cyan
docker tag ${ECR_REPOSITORY_NAME}:${ImageTag} $ECR_IMAGE_URI
docker push $ECR_IMAGE_URI
if ($LASTEXITCODE -ne 0) { exit 1 }

# Create or update Lambda
if ($Action -eq "create") {
    Write-Host "Creating Lambda function..." -ForegroundColor Cyan
    aws lambda create-function `
        --function-name $LAMBDA_FUNCTION_NAME `
        --package-type Image `
        --code ImageUri=$ECR_IMAGE_URI `
        --role $LAMBDA_ROLE_ARN `
        --timeout $LAMBDA_TIMEOUT `
        --memory-size $LAMBDA_MEMORY_SIZE `
        --environment file://../envvars.json
} else {
    Write-Host "Updating Lambda function..." -ForegroundColor Cyan
    aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --image-uri $ECR_IMAGE_URI
    aws lambda update-function-configuration `
        --function-name $LAMBDA_FUNCTION_NAME `
        --timeout $LAMBDA_TIMEOUT `
        --memory-size $LAMBDA_MEMORY_SIZE `
        --environment file://../envvars.json
}

if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "Deployment complete!" -ForegroundColor Green
