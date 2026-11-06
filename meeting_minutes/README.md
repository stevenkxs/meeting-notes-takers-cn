# Meeting Minutes Workflow

Converts audio/video recordings into formatted meeting minutes Word documents.

## Workflow Steps

1. **Transcribe** — Converts audio/video to text using OpenAI Whisper (runs locally)
2. **Summarize** — Generates structured meeting minutes via Amazon Bedrock (Claude)
3. **Save** — Outputs a formatted Word document (.docx)

## Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) installed and in PATH
- AWS credentials configured with Bedrock access (us-east-1)

## Setup

```bash
cd meeting_minutes
pip install -r requirements.txt
```

## Usage

```bash
# Basic usage
python transcribe_and_summarize.py recording.mp4

# With custom output name
python transcribe_and_summarize.py call.mp3 --output "Q3 Planning Meeting"

# With larger model for better accuracy
python transcribe_and_summarize.py interview.wav --model medium

# Specify output directory
python transcribe_and_summarize.py meeting.m4a --output-dir ./output
```

## Whisper Model Options

| Model  | Size   | Speed   | Accuracy |
|--------|--------|---------|----------|
| tiny   | 39MB   | Fastest | Lower    |
| base   | 74MB   | Fast    | Good     |
| small  | 244MB  | Medium  | Better   |
| medium | 769MB  | Slow    | High     |
| large  | 1550MB | Slowest | Highest  |

## Output Files

For an input file `recording.mp4`:
- `recording_transcript.vtt` — Timestamped transcript (WebVTT format)
- `recording_meeting_minutes.docx` — Formatted meeting minutes

## Meeting Minutes Structure

The Word document contains:
1. Meeting Overview
2. Key Takeaways (max 5)
3. Action Items with owners and ETAs (max 5)
4. Discussion Summary
5. Next Steps
6. Appendix: Full Transcript

## Supported Input Formats

Any format supported by ffmpeg: mp3, mp4, wav, m4a, webm, ogg, flac, avi, mkv, etc.
