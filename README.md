# YouTube Channel Transcription Automation

This project polls a YouTube channel for new uploads and generates transcripts using YouTube's native transcripts when available, falling back to OpenAI Whisper when transcripts are unavailable. The transcript stays in memory and is fed directly into the summarization/email pipeline.

## Project Structure

```
video-summarizer/
├── src/                      # All source code
│   ├── main.py               # CLI entry point
│   ├── lambda_handler.py     # AWS Lambda entry point
│   ├── core/                 # Core utilities
│   │   └── aws_services.py   # AWS SDK wrappers (S3, Secrets Manager)
│   └── services/             # Business logic
│       ├── summarizer.py     # Transcript summarization
│       ├── email_service.py  # Email delivery
│       ├── transcriber.py    # Audio transcription
│       └── youtube_poller.py # YouTube API integration
├── config/                   # ALL configuration (code, templates, examples)
│   ├── config.py             # Application configuration code
│   └── lambda_config.yaml    # EventBridge schedule configuration
├── scripts/                  # Deployment and utility scripts
│   └── deploy-lambda.ps1     # Automated Lambda deployment script
├── tests/                    # Test suite
│   └── unit/                 # Unit tests
├── data/                     # Data files (gitignored)
│   └── transcript.txt        # Dummy transcript for development mode
├── downloads/                # Temporary audio files (gitignored)
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker image for Lambda deployment
├── .dockerignore             # Docker build context exclusions
└── README.md
```

## Requirements

- Python 3.10+
- A YouTube Data API key with read access
- An OpenAI API key enabled for the Whisper (`whisper-1`) model (for transcription fallback)
- A Hugging Face account and access token (required only when email summaries are enabled)

Install dependencies:

```powershell
pip install -r requirements.txt
```

**Note:** Using the Hugging Face Inference API means models run on Hugging Face's servers, so no local model downloads are required. You'll only need your HF_TOKEN for authentication.

## Configuration

Set the following environment variables (a `.env` file is recommended):

**Required:**
- `YOUTUBE_API_KEY` – provided key for the YouTube Data API
- `YOUTUBE_CHANNEL_HANDLE` – channel handle such as `@anyYoutubeChannel`
- `OPENAI_API_KEY` – OpenAI API key with Whisper access (required for transcription fallback when YouTube transcripts are unavailable)

**Required when email summaries are enabled:**
- `HF_TOKEN` – Hugging Face access token (required for Llama model access when `EMAIL_SUMMARIES_ENABLED=true`)

**Optional overrides:**

- `POLL_INTERVAL_SECONDS` (default `900`)
- `DOWNLOADS_DIR` (default `downloads/`)
- `STATE_FILE` (default `last_video_id.json`)
- `WHISPER_MODEL` (default `whisper-1`)
- `SUMMARY_MODEL` (default `meta-llama/Llama-3.1-8B-Instruct`)

**For Lambda deployment (used by `scripts/deploy-lambda.ps1`):**

- `AWS_ACCOUNT_ID` – Your AWS account ID (required for deployment)
- `AWS_REGION` – AWS region (default: `us-east-1`)

### Email summary delivery

Set `EMAIL_SUMMARIES_ENABLED=true` to automatically summarize the most recent transcript and email both the short and comprehensive summaries via SMTP. When enabled, you must also provide:

- `HF_TOKEN` – Hugging Face access token (required for summarization)
- `SMTP_SENDER`
- `SMTP_RECIPIENT`
- `SMTP_PASSWORD`
- `SMTP_PORT` (default `587`)

The SMTP host is inferred from the sender domain (e.g., `sender@example.com` -> `smtp.example.com`), and the sender address is re-used as the login username over TLS.

If any of these are missing while email is enabled, the application will raise an error at startup to avoid silent misconfiguration.

### Getting a Hugging Face Token

1. Create a free account at [huggingface.co](https://huggingface.co)
2. Go to Settings → Access Tokens
3. Create a new token with "Read" permissions
4. Copy the token and add it to your `.env` file as `HF_TOKEN`

### Inference API

This project uses Hugging Face Inference API, which runs models on Hugging Face's servers. This means:
- No local model downloads required (saves disk space)
- No GPU/CPU configuration needed
- Faster setup - just provide your HF_TOKEN
- Models are automatically optimized on Hugging Face's infrastructure

Example `.env` (basic configuration without email):

```
YOUTUBE_API_KEY=AIzaSy...
YOUTUBE_CHANNEL_HANDLE=@anyYoutubeChannel
OPENAI_API_KEY=sk-...
POLL_INTERVAL_SECONDS=1800
```

Example `.env` (with email summaries enabled):

```
YOUTUBE_API_KEY=AIzaSy...
YOUTUBE_CHANNEL_HANDLE=@anyYoutubeChannel
OPENAI_API_KEY=sk-...
HF_TOKEN=hf_...
EMAIL_SUMMARIES_ENABLED=true
SMTP_SENDER=sender@example.com
SMTP_RECIPIENT=recipient@example.com
SMTP_PASSWORD=your_smtp_password
SMTP_PORT=587
POLL_INTERVAL_SECONDS=1800
```

## Usage

### Local Development

Run a single check for a new upload:

```powershell
python -m src.main --mode once
```

Run continuously on the configured interval:

```powershell
python -m src.main --mode loop
```

Run in development mode with dummy transcript (skips video download and transcription):

```powershell
python -m src.main --mode dev
```

Development mode reads a transcript from `data/transcript.txt` instead of downloading videos. This is useful for testing the summarization and email pipeline without requiring YouTube API access or video downloads.

### How It Works

If a new video is detected, the script attempts to fetch the transcript directly from YouTube first. If no transcript is available, it downloads the audio and transcribes it via OpenAI Whisper. The transcript is kept in memory and used directly for summarization. The last processed video ID is stored to avoid duplicate work. When email delivery is configured, the pipeline generates both a concise and comprehensive summary and emails them.

## AWS Lambda Deployment

This project can be deployed to AWS Lambda with EventBridge scheduling, S3 for state persistence, and AWS Secrets Manager for credential management.

### Prerequisites

- AWS account with appropriate permissions
- AWS CLI configured with credentials
- Docker installed and running (for container image deployment)
- Python 3.10+ runtime (Lambda supports Python 3.10, 3.11, 3.12)

### AWS Services Required

1. **AWS Lambda**: Serverless function execution
2. **Amazon EventBridge**: Scheduled triggers (replaces polling loop)
3. **Amazon S3**: State file persistence (`last_video_id.json`)
4. **AWS Secrets Manager**: Secure credential storage

### Setup Instructions

#### 1. Create S3 Bucket for State Storage

```powershell
aws s3 mb s3://your-video-summarizer-state-bucket
```

The state file will be stored at: `s3://your-bucket-name/state/last_video_id.json`

#### 2. Create Secrets Manager Secret

Create a JSON secret in AWS Secrets Manager containing all sensitive credentials:

```powershell
aws secretsmanager create-secret `
  --name video-summarizer-credentials `
  --secret-string '{
    "YOUTUBE_API_KEY": "your-youtube-api-key",
    "OPENAI_API_KEY": "your-openai-api-key",
    "HF_TOKEN": "your-huggingface-token",
    "SMTP_SENDER": "sender@example.com",
    "SMTP_RECIPIENT": "recipient@example.com",
    "SMTP_PASSWORD": "your-smtp-password"
  }'
```

Or using a JSON file:

```powershell
aws secretsmanager create-secret `
  --name video-summarizer-credentials `
  --secret-string file://secret.json
```


**Secret Structure:**
```json
{
  "YOUTUBE_API_KEY": "...",
  "OPENAI_API_KEY": "...",
  "HF_TOKEN": "...",
  "SMTP_SENDER": "...",
  "SMTP_RECIPIENT": "...",
  "SMTP_PASSWORD": "..."
}
```

**Note:** Only include fields that are actually needed. For example, if email is disabled, you don't need SMTP fields.

#### 3. Deploy Lambda Function (Choose One Method)

##### Method A: Container Image Deployment (Recommended)

This method uses Docker to build a container image and deploy it to AWS Lambda via Amazon ECR.

**Prerequisites:**
- Docker installed and running
- AWS CLI configured
- ECR repository created

**Quick Start: Automated Deployment**

For automated deployment, use the provided PowerShell script:

1. **Add to `.env` file:**
   ```env
   AWS_ACCOUNT_ID=your-account-id
   AWS_REGION=us-east-1
   ```

2. **Run the script:**
```powershell
# First time deployment
.\scripts\deploy-lambda.ps1 -Action create

# Update existing function
.\scripts\deploy-lambda.ps1 -Action update

# Update with specific image tag
.\scripts\deploy-lambda.ps1 -Action update -ImageTag v1.2.3
```

The script automates:
- Docker image build (linux/amd64 platform)
- ECR authentication
- Image tagging and pushing
- Lambda function creation or update
- Environment variable configuration
- Error handling and validation

**Manual Deployment Steps**

If you prefer manual deployment, follow the steps below:

**Step 1: Create ECR Repository**

```powershell
aws ecr create-repository `
  --repository-name video-summarizer `
  --region us-east-1
```

**Step 2: Authenticate Docker to ECR**

```powershell
aws ecr get-login-password --region us-east-1 | `
  docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
```

**Step 3: Build Docker Image**

```powershell
docker buildx build --platform linux/amd64 -t video-summarizer:latest .
```

**Step 4: Tag Image for ECR**

```powershell
docker tag video-summarizer:latest `
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest
```

**Step 5: Push Image to ECR**

```powershell
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest
```

**Step 6: Create Environment Variables File**

Create `envvars.json` in your project root with the following structure:

```json
{
  "Variables": {
    "S3_STATE_BUCKET": "your-video-summarizer-state-bucket",
    "SECRETS_MANAGER_SECRET_NAME": "video-summarizer-credentials",
    "YOUTUBE_CHANNEL_HANDLE": "@yourChannelHandle",
    "EMAIL_SUMMARIES_ENABLED": "true",
    "SMTP_PORT": "587"
  }
}
```

**Note:** `AWS_REGION` is automatically set by Lambda and cannot be specified as an environment variable.

**Step 7: Create Lambda Function from Container Image**

```powershell
aws lambda create-function `
  --function-name video-summarizer `
  --package-type Image `
  --code ImageUri=<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest `
  --role arn:aws:iam::<ACCOUNT_ID>:role/lambda-execution-role `
  --timeout 900 `
  --memory-size 1024 `
  --environment file:/../envvars.json
```

**Step 8: Update Lambda Function Image (for updates)**

```powershell
# Rebuild and push image
docker buildx build --platform linux/amd64 -t video-summarizer:latest .
docker tag video-summarizer:latest `
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest

# Update Lambda function
aws lambda update-function-code `
  --function-name video-summarizer `
  --image-uri <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest
```

**Container Image Benefits:**
- Larger deployment package size (up to 10GB)
- More control over the runtime environment
- Easier to include system dependencies
- Better for complex dependencies
- Consistent build environment

#### 4. Configure IAM Role Permissions

The Lambda execution role needs the following permissions:

**S3 Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::your-video-summarizer-state-bucket/state/*"
    }
  ]
}
```

**Secrets Manager Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:video-summarizer-credentials-*"
    }
  ]
}
```

**CloudWatch Logs Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

**ECR Permissions (for Container Image Deployment):**

If using container images, the IAM user/role used for deployment also needs ECR permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    }
  ]
}
```

**Note:** The Lambda execution role itself does not need ECR permissions - only the role/user deploying the function.

#### 5. Create EventBridge Rule

Create an EventBridge rule to trigger the Lambda function on a schedule(Mon-FRI 15 UTC):


```powershell
aws events put-rule `
  --name video-summarizer-schedule `
  --schedule-expression "cron(0 15 ? * MON-FRI *)" `
  --description "Trigger video transcription automation every weekday at 10am EST"
```

Add Lambda as a target:

```powershell
aws events put-targets `
  --rule video-summarizer-schedule `
  --targets "Id=1,Arn=arn:aws:lambda:us-east-1:ACCOUNT_ID:function:video-summarizer"
```

**Schedule Options:**
- `rate(15 minutes)` - Every 15 minutes
- `rate(1 hour)` - Every hour
- `cron(0/15 * * * ? *)` - Every 15 minutes (cron format)
- `cron(0 12 * * ? *)` - Daily at 12:00 PM UTC

See `config/lambda_config.yaml` for schedule configuration details.

### Lambda Environment Variables

**Required:**
- `S3_STATE_BUCKET` - S3 bucket name for state storage
- `SECRETS_MANAGER_SECRET_NAME` - Name of the Secrets Manager secret
- `YOUTUBE_CHANNEL_HANDLE` - Channel handle (e.g., `@yourChannelHandle`)

**Note:** All sensitive credentials (API keys, tokens, SMTP passwords) must be stored in Secrets Manager, not in environment variables.

**Optional:**
- `EMAIL_SUMMARIES_ENABLED` - Enable email summaries (`true`/`false`, default: `false`)
- `SMTP_PORT` - SMTP port (default: `587`)
- `WHISPER_MODEL` - Whisper model name (default: `whisper-1`)
- `SUMMARY_MODEL` - Summary model name (default: `meta-llama/Llama-3.1-8B-Instruct`)

### Lambda Configuration Recommendations

- **Timeout:** 900 seconds (15 minutes) - allows time for video downloads and transcription
- **Memory:** 1024 MB - sufficient for audio downloads and processing
- **Architecture:** x86_64 (default)

### Monitoring

Monitor the Lambda function via:
- **CloudWatch Logs:** `/aws/lambda/video-summarizer`
- **CloudWatch Metrics:** Function invocations, duration, errors
- **Lambda Console:** Recent invocations and execution results

### Local Testing

#### Testing Docker Container Locally

Test the Docker container using the AWS Lambda Runtime Interface Emulator (included in the base image):

**1. Build the Docker image:**

```powershell
docker buildx build --load --platform linux/amd64 -t video-summarizer:local .
```

**2. Run the container with environment variables:**

```powershell
docker run -p 9000:8080 `
  --env-file .env `
  -v ${env:USERPROFILE}\.aws:/root/.aws:ro `
  video-summarizer:local
```

**3. Test with a sample event (in another terminal):**

```powershell
curl.exe -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{}'
```

Or use a test event file:

```powershell
# Create test-event.json
@'
{"version":"0","id":"test","detail-type":"Scheduled Event","source":"aws.events"}
'@ | Out-File -FilePath test-event.json -Encoding utf8

# Invoke
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '@test-event.json'
```

#### Testing with Local Environment

Local development uses `.env` files. The application automatically detects the environment:
- **Local:** Uses `.env` file and local filesystem
- **Lambda:** Uses Secrets Manager and S3

To test locally with AWS services:

```powershell
$env:AWS_REGION = "us-east-1"
$env:S3_STATE_BUCKET = "your-bucket-name"
$env:SECRETS_MANAGER_SECRET_NAME = "video-summarizer-credentials"
python -m src.main --mode once
```

### Updating the Lambda Function

#### Container Image Method

```powershell
# Rebuild and push image
docker buildx build --platform linux/amd64 -t video-summarizer:latest .
docker tag video-summarizer:latest `
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:latest

# Update function (no need to update function code separately for images)
# Lambda automatically uses the latest image tag
```

Alternatively, use a specific tag for versioning:

```powershell
docker tag video-summarizer:latest `
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:v1.2.3
docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:v1.2.3

# Update function to use specific tag
aws lambda update-function-code `
  --function-name video-summarizer `
  --image-uri <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/video-summarizer:v1.2.3
```

#### ZIP Deployment Method

```powershell
# Recreate deployment package
pip install -r requirements.txt -t package/
Copy-Item -Path src -Destination package\src -Recurse
Copy-Item -Path config -Destination package\config -Recurse
Compress-Archive -Path package\* -DestinationPath lambda-deployment.zip -Force

# Update function
aws lambda update-function-code `
  --function-name video-summarizer `
  --zip-file fileb://lambda-deployment.zip
```

#### Updating Environment Variables

To update environment variables, modify `envvars.json` and run:

```powershell
aws lambda update-function-configuration `
  --function-name video-summarizer `
  --environment file:/../envvars.json
```

### Docker Image Details

The Dockerfile uses the official AWS Lambda Python base image:
- **Base Image:** `public.ecr.aws/lambda/python:3.10`
- **Handler:** `src.lambda_handler.lambda_handler`
- **Working Directory:** `${LAMBDA_TASK_ROOT}` (set by base image)

The `.dockerignore` file excludes unnecessary files (cache, tests, docs) to optimize build context size and build speed.

## Testing

Run the automated test suite with:

```powershell
pytest
```

Run only unit tests:

```powershell
pytest tests/unit/
```

The tests mock both Hugging Face Inference API and SMTP so they run quickly without external dependencies or API calls.

**Note:** Integration tests can be added to `tests/integration/` when needed.

## Development

This project follows a strict project structure as defined in `.cursorrules`:

- All source code lives in `src/`
- Business logic is organized in `src/services/`
- **All configuration (code, templates, examples) is consolidated in `config/`**
- Tests are organized in `tests/unit/` (integration tests can be added to `tests/integration/` when needed)
- No Python files are placed in the project root (except configuration code in `config/`)

All code follows Python best practices with:
- Comprehensive type annotations
- Google-style docstrings
- PEP 8 compliance (enforced with Ruff)
- High test coverage (target 90%+)