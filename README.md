# YouTube Channel Transcription Automation

This project polls a YouTube channel for new uploads, downloads the audio, and generates transcripts using OpenAI Whisper. The transcript stays in memory and is fed directly into the summarization/email pipeline.

## Project Structure

```
video-summarizer/
├── src/                      # All source code
│   ├── main.py               # Entry point
│   ├── core/                 # Utilities (exceptions, logging)
│   └── services/             # Business logic
│       ├── summarizer.py     # Transcript summarization
│       ├── email_service.py  # Email delivery
│       ├── transcriber.py    # Audio transcription
│       └── youtube_poller.py # YouTube API integration
├── config/                   # ALL configuration (code, templates, examples)
│   └── config.py             # Application configuration code
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   └── integration/         # Integration tests
├── downloads/                # Temporary audio files (gitignored)
└── README.md
```

## Requirements

- Python 3.10+
- A YouTube Data API key with read access
- An OpenAI API key enabled for the Whisper (`whisper-1`) model

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Set the following environment variables (a `.env` file is recommended):

- `YOUTUBE_API_KEY` – provided key for the YouTube Data API
- `YOUTUBE_CHANNEL_HANDLE` – channel handle such as `@anyYoutubeChannel`
- `OPENAI_API_KEY` – OpenAI API key with Whisper access

Optional overrides:

- `POLL_INTERVAL_SECONDS` (default `900`)
- `DOWNLOADS_DIR` (default `downloads/`)
- `STATE_FILE` (default `last_video_id.json`)
- `WHISPER_MODEL` (default `whisper-1`)
- `SUMMARY_MODEL` (default `gpt-3.5-turbo`)

### Email summary delivery

Set `EMAIL_SUMMARIES_ENABLED=true` to automatically summarize the most recent transcript and email both the short and comprehensive summaries via SMTP. When enabled, provide:

- `SMTP_SENDER`
- `SMTP_RECIPIENT`
- `SMTP_PASSWORD`
- `SMTP_PORT` (default `587`)

The SMTP host is inferred from the sender domain (e.g., `sender@example.com` -> `smtp.example.com`), and the sender address is re-used as the login username over TLS.

If any of these are missing while email is enabled, the application will raise an error at startup to avoid silent misconfiguration.

Example `.env`:

```
YOUTUBE_API_KEY=AIzaSy...
YOUTUBE_CHANNEL_HANDLE=@anyYoutubeChannel
OPENAI_API_KEY=sk-...
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

If a new video is detected, the script downloads the audio, transcribes it via Whisper, prints log output, and keeps the transcript in memory. The last processed video ID is stored in `last_video_id.json` to avoid duplicate work. When email delivery is configured, the pipeline immediately requests both a concise and comprehensive summary from OpenAI and emails the pair.

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

Run only integration tests:

```bash
pytest tests/integration/
```

The tests mock both OpenAI and SMTP so they run quickly without external dependencies.

## Development

This project follows a strict project structure as defined in `.cursorrules`:

- All source code lives in `src/`
- Business logic is organized in `src/services/`
- **All configuration (code, templates, examples) is consolidated in `config/`**
- Utilities (exceptions, logging) are in `src/core/`
- Tests are separated into `tests/unit/` and `tests/integration/`
- No Python files are placed in the project root (except configuration code in `config/`)

All code follows Python best practices with:
- Comprehensive type annotations
- Google-style docstrings
- PEP 8 compliance (enforced with Ruff)
- High test coverage (target 90%+)