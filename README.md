# YouTube Channel Transcription Automation

This project polls a YouTube channel for new uploads, downloads the audio, and generates transcripts using OpenAI Whisper. The transcript is returned as a string and optionally saved as a `.txt` document for later download.

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
- `YOUTUBE_CHANNEL_HANDLE` – channel handle such as `@GarethSolowayProTrader`
- `OPENAI_API_KEY` – OpenAI API key with Whisper access

Optional overrides:

- `POLL_INTERVAL_SECONDS` (default `900`)
- `DOWNLOADS_DIR` (default `downloads/`)
- `TRANSCRIPTS_DIR` (default `transcripts/`)
- `STATE_FILE` (default `last_video_id.json`)
- `WHISPER_MODEL` (default `whisper-1`)

Example `.env`:

```
YOUTUBE_API_KEY=AIzaSy...
YOUTUBE_CHANNEL_HANDLE=@GarethSolowayProTrader
OPENAI_API_KEY=sk-...
POLL_INTERVAL_SECONDS=1800
```

## Usage

Run a single check for a new upload:

```bash
python main.py --mode once
```

Run continuously on the configured interval:

```bash
python main.py --mode loop
```

If a new video is detected, the script downloads the audio, transcribes it via Whisper, prints log output, and saves the transcript under `transcripts/`. The last processed video ID is stored in `last_video_id.json` to avoid duplicate work.

## Output

The transcript text is returned from the transcriber and also saved as `<video-title>.txt` inside the transcripts directory, which can be shared or downloaded as needed. Adjust `TRANSCRIPTS_DIR` if you want to store the documents elsewhere.