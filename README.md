# YouTube Channel Transcription Automation

This project polls a YouTube channel for new uploads and generates transcripts using YouTube's native transcripts when available, falling back to OpenAI Whisper when transcripts are unavailable. The transcript stays in memory and is fed directly into the summarization/email pipeline.

## Project Structure

```
video-summarizer/
├── src/                      # All source code
│   ├── main.py               # Entry point
│   └── services/             # Business logic
│       ├── summarizer.py     # Transcript summarization
│       ├── email_service.py  # Email delivery
│       ├── transcriber.py    # Audio transcription
│       └── youtube_poller.py # YouTube API integration
├── config/                   # ALL configuration (code, templates, examples)
│   └── config.py             # Application configuration code
├── tests/                    # Test suite
│   └── unit/                 # Unit tests
├── data/                     # Data files (gitignored)
│   └── transcript.txt        # Dummy transcript for development mode
├── downloads/                # Temporary audio files (gitignored)
├── requirements.txt          # Python dependencies
└── README.md
```

## Requirements

- Python 3.10+
- A YouTube Data API key with read access
- An OpenAI API key enabled for the Whisper (`whisper-1`) model (for transcription fallback)
- A Hugging Face account and access token (required only when email summaries are enabled)

Install dependencies:

```bash
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

Run a single check for a new upload:

```bash
python -m src.main --mode once
```

Or alternatively:

```bash
python src/main.py --mode once
```

Run continuously on the configured interval:

```bash
python -m src.main --mode loop
```

Or alternatively:

```bash
python src/main.py --mode loop
```

Run in development mode with dummy transcript (skips video download and transcription):

```bash
python -m src.main --mode dev
```

Or alternatively:

```bash
python src/main.py --mode dev
```

The development mode reads a transcript from `data/transcript.txt` instead of downloading videos and creating transcripts. This is useful for testing the summarization and email pipeline without requiring YouTube API access or video downloads. The mode still generates summaries and sends emails if configured.

If a new video is detected, the script attempts to fetch the transcript directly from YouTube first. If no transcript is available, it downloads the audio and transcribes it via OpenAI Whisper. The transcript is kept in memory and printed to the console. The last processed video ID is stored in `last_video_id.json` to avoid duplicate work. When email delivery is configured, the pipeline immediately requests both a concise and comprehensive summary from the Llama model and emails the pair.

## Output

The transcript text is returned from the transcriber and used directly for summarization. Summaries are generated on demand and emailed; no transcript files are created.

## Testing

Run the automated test suite with:

```bash
pytest
```

Run only unit tests:

```bash
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