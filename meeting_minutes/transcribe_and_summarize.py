"""
Meeting Minutes Workflow
========================
Step 0: (If URL) Download audio/video from URL
Step 1: Convert video/audio file to transcript (.vtt or .txt)
Step 1.5: Analyze transcript with Amazon Comprehend (entities, key phrases, sentiment)
Step 2: Summarize transcript into meeting minutes (enriched with Comprehend insights)
Step 3: Save as a Word (.docx) file

Usage:
    python transcribe_and_summarize.py <audio_or_video_file_or_url> [--output <output_name>] [--model <whisper_model>]

Examples:
    python transcribe_and_summarize.py meeting_recording.mp4
    python transcribe_and_summarize.py https://example.com/recording.mp4
    python transcribe_and_summarize.py s3://my-bucket/recordings/meeting.mp4
    python transcribe_and_summarize.py call.mp3 --output "Q3 Planning Meeting"
    python transcribe_and_summarize.py interview.wav --model medium

Requirements:
    pip install -r requirements.txt
    ffmpeg must be installed and accessible in PATH
    AWS credentials configured for Bedrock and Comprehend access (us-east-1)
"""

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

import whisper
import boto3
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


def is_url(input_str: str) -> bool:
    """Check if the input string is a URL."""
    return input_str.startswith(("http://", "https://", "s3://"))


def download_from_url(url: str, output_dir: str) -> str:
    """
    Step 0: Download audio/video file from a URL.

    Supports:
    - HTTP/HTTPS URLs (direct links, Chime recordings, etc.)
    - S3 URLs (s3://bucket/key)

    Args:
        url: The URL to download from.
        output_dir: Directory to save the downloaded file.

    Returns:
        Local file path of the downloaded file.
    """
    print(f"[Step 0] Downloading from URL: {url}")

    os.makedirs(output_dir, exist_ok=True)

    if url.startswith("s3://"):
        return _download_from_s3(url, output_dir)
    else:
        return _download_from_http(url, output_dir)


def _download_from_http(url: str, output_dir: str) -> str:
    """Download file from HTTP/HTTPS URL."""
    # Extract filename from URL
    parsed = urllib.parse.urlparse(url)
    path_parts = parsed.path.rstrip("/").split("/")
    filename = path_parts[-1] if path_parts[-1] else "recording"

    # Ensure it has a media extension
    valid_extensions = {".mp4", ".mp3", ".wav", ".m4a", ".webm", ".ogg",
                        ".flac", ".avi", ".mkv", ".wma", ".aac"}
    ext = Path(filename).suffix.lower()
    if ext not in valid_extensions:
        filename = f"{filename}.mp4"  # default to mp4

    local_path = os.path.join(output_dir, filename)

    # Download with progress
    print(f"[Step 0] Saving to: {local_path}")
    try:
        urllib.request.urlretrieve(url, local_path, _download_progress)
        print()  # newline after progress
    except Exception as e:
        # Try with custom headers (some services require User-Agent)
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Meeting-Minutes/1.0"
        })
        with urllib.request.urlopen(req) as response, open(local_path, "wb") as f:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 8192
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r[Step 0] Downloading: {pct:.1f}%", end="", flush=True)
            print()

    file_size = os.path.getsize(local_path)
    print(f"[Step 0] Download complete: {file_size / (1024*1024):.1f} MB")
    return local_path


def _download_from_s3(s3_url: str, output_dir: str) -> str:
    """Download file from S3 URL (s3://bucket/key)."""
    # Parse s3://bucket/key
    parts = s3_url.replace("s3://", "").split("/", 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ""

    filename = key.split("/")[-1] if key else "recording.mp4"
    local_path = os.path.join(output_dir, filename)

    print(f"[Step 0] Downloading from S3: bucket={bucket}, key={key}")

    session = boto3.Session(profile_name="bruno-mcp-prod")
    s3_client = session.client("s3")

    s3_client.download_file(bucket, key, local_path)

    file_size = os.path.getsize(local_path)
    print(f"[Step 0] Download complete: {file_size / (1024*1024):.1f} MB")
    return local_path


def _download_progress(block_num, block_size, total_size):
    """Progress callback for urllib.request.urlretrieve."""
    if total_size > 0:
        downloaded = block_num * block_size
        pct = min(downloaded / total_size * 100, 100)
        print(f"\r[Step 0] Downloading: {pct:.1f}%", end="", flush=True)


def transcribe_audio(file_path: str, model_name: str = "base") -> tuple[str, str]:
    """
    Step 1: Transcribe audio/video file using OpenAI Whisper.

    Args:
        file_path: Path to the audio or video file.
        model_name: Whisper model size (tiny, base, small, medium, large).

    Returns:
        Tuple of (plain text transcript, VTT formatted transcript).
    """
    print(f"[Step 1] Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)

    print(f"[Step 1] Transcribing '{file_path}'...")
    result = model.transcribe(file_path, verbose=False)

    # Build plain text transcript
    plain_text = result["text"].strip()

    # Build VTT format with timestamps
    vtt_lines = ["WEBVTT", ""]
    for segment in result["segments"]:
        start = format_timestamp(segment["start"])
        end = format_timestamp(segment["end"])
        text = segment["text"].strip()
        vtt_lines.append(f"{start} --> {end}")
        vtt_lines.append(text)
        vtt_lines.append("")

    vtt_text = "\n".join(vtt_lines)

    print(f"[Step 1] Transcription complete. {len(result['segments'])} segments found.")
    return plain_text, vtt_text


def format_timestamp(seconds: float) -> str:
    """Convert seconds to VTT timestamp format (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def analyze_with_comprehend(transcript: str, language_code: str = "auto") -> dict:
    """
    Step 1.5: Analyze transcript using Amazon Comprehend for NLP enrichment.

    Extracts entities (people, orgs, dates, locations), key phrases,
    and overall sentiment to enrich the summarization step.

    Args:
        transcript: Plain text transcript.
        language_code: Language code (e.g., 'en', 'zh', 'ja'). 'auto' for detection.

    Returns:
        Dictionary with entities, key_phrases, sentiment, and detected language.
    """
    print("[Step 1.5] Analyzing transcript with Amazon Comprehend...")

    session = boto3.Session(profile_name="bruno-mcp-prod")
    client = session.client("comprehend", region_name="us-east-1")

    # Comprehend has a 5000 byte limit per call — split if needed
    max_bytes = 4500  # leave buffer
    text_chunks = _split_text_for_comprehend(transcript, max_bytes)

    # Detect language if auto
    if language_code == "auto":
        try:
            lang_response = client.detect_dominant_language(Text=text_chunks[0][:1000])
            languages = lang_response["Languages"]
            language_code = languages[0]["LanguageCode"] if languages else "en"
            print(f"[Step 1.5] Detected language: {language_code} "
                  f"(confidence: {languages[0]['Score']:.0%})")
        except Exception as e:
            print(f"[Step 1.5] Language detection failed: {e}. Defaulting to 'en'.")
            language_code = "en"

    # Supported languages for Comprehend features
    supported_languages = [
        "en", "es", "fr", "de", "it", "pt", "ar", "hi", "ja", "ko", "zh", "zh-TW"
    ]

    if language_code not in supported_languages:
        print(f"[Step 1.5] Language '{language_code}' not fully supported by Comprehend. "
              f"Using 'en' as fallback.")
        language_code = "en"

    # Collect results across chunks
    all_entities = []
    all_key_phrases = []
    sentiments = []

    for i, chunk in enumerate(text_chunks):
        if not chunk.strip():
            continue

        # Entity detection
        try:
            entity_response = client.detect_entities(
                Text=chunk, LanguageCode=language_code
            )
            for entity in entity_response["Entities"]:
                if entity["Score"] >= 0.7:  # confidence threshold
                    all_entities.append({
                        "text": entity["Text"],
                        "type": entity["Type"],
                        "score": entity["Score"],
                    })
        except Exception as e:
            print(f"[Step 1.5] Entity detection error on chunk {i+1}: {e}")

        # Key phrase extraction
        try:
            phrase_response = client.detect_key_phrases(
                Text=chunk, LanguageCode=language_code
            )
            for phrase in phrase_response["KeyPhrases"]:
                if phrase["Score"] >= 0.7:
                    all_key_phrases.append({
                        "text": phrase["Text"],
                        "score": phrase["Score"],
                    })
        except Exception as e:
            print(f"[Step 1.5] Key phrase detection error on chunk {i+1}: {e}")

        # Sentiment analysis
        try:
            sentiment_response = client.detect_sentiment(
                Text=chunk, LanguageCode=language_code
            )
            sentiments.append({
                "sentiment": sentiment_response["Sentiment"],
                "scores": sentiment_response["SentimentScore"],
            })
        except Exception as e:
            print(f"[Step 1.5] Sentiment detection error on chunk {i+1}: {e}")

    # Deduplicate entities by text+type
    seen_entities = set()
    unique_entities = []
    for entity in all_entities:
        key = (entity["text"].lower(), entity["type"])
        if key not in seen_entities:
            seen_entities.add(key)
            unique_entities.append(entity)

    # Deduplicate key phrases
    seen_phrases = set()
    unique_phrases = []
    for phrase in all_key_phrases:
        key = phrase["text"].lower()
        if key not in seen_phrases:
            seen_phrases.add(key)
            unique_phrases.append(phrase)

    # Sort by confidence
    unique_entities.sort(key=lambda x: x["score"], reverse=True)
    unique_phrases.sort(key=lambda x: x["score"], reverse=True)

    # Determine overall sentiment
    if sentiments:
        sentiment_counts = {}
        for s in sentiments:
            label = s["sentiment"]
            sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
        overall_sentiment = max(sentiment_counts, key=sentiment_counts.get)
    else:
        overall_sentiment = "UNKNOWN"

    result = {
        "language": language_code,
        "entities": unique_entities[:50],  # top 50
        "key_phrases": unique_phrases[:30],  # top 30
        "overall_sentiment": overall_sentiment,
        "sentiment_details": sentiments,
    }

    # Print summary
    entity_types = {}
    for e in unique_entities:
        entity_types[e["type"]] = entity_types.get(e["type"], 0) + 1

    print(f"[Step 1.5] Comprehend analysis complete:")
    print(f"          Entities: {len(unique_entities)} "
          f"({', '.join(f'{v} {k}' for k, v in entity_types.items())})")
    print(f"          Key phrases: {len(unique_phrases)}")
    print(f"          Overall sentiment: {overall_sentiment}")

    return result


def _split_text_for_comprehend(text: str, max_bytes: int = 4500) -> list[str]:
    """Split text into chunks that fit within Comprehend's byte limit."""
    chunks = []
    current_chunk = ""

    for sentence in text.replace("。", "。\n").replace(". ", ".\n").split("\n"):
        test_chunk = current_chunk + sentence + "\n"
        if len(test_chunk.encode("utf-8")) > max_bytes:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence + "\n"
        else:
            current_chunk = test_chunk

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text[:max_bytes]]


def format_comprehend_context(analysis: dict) -> str:
    """Format Comprehend results into a context block for the summarization prompt."""
    lines = []

    # Entities grouped by type
    if analysis["entities"]:
        lines.append("DETECTED ENTITIES:")
        entity_by_type = {}
        for e in analysis["entities"]:
            entity_by_type.setdefault(e["type"], []).append(e["text"])
        for etype, names in entity_by_type.items():
            lines.append(f"  {etype}: {', '.join(names[:10])}")

    # Key phrases
    if analysis["key_phrases"]:
        lines.append("\nKEY PHRASES (auto-detected):")
        for phrase in analysis["key_phrases"][:20]:
            lines.append(f"  - {phrase['text']}")

    # Sentiment
    lines.append(f"\nOVERALL MEETING SENTIMENT: {analysis['overall_sentiment']}")

    return "\n".join(lines)


def summarize_transcript(transcript: str, vtt_transcript: str = "", comprehend_analysis: dict = None) -> str:
    """
    Step 2: Summarize transcript into structured meeting minutes using Bedrock Claude,
    enriched with Amazon Comprehend NLP insights.

    Args:
        transcript: Plain text transcript of the meeting.
        vtt_transcript: VTT formatted transcript with timestamps.
        comprehend_analysis: Results from Comprehend analysis (entities, phrases, sentiment).

    Returns:
        Structured meeting minutes as text.
    """
    print("[Step 2] Generating meeting minutes summary via Amazon Bedrock...")

    session = boto3.Session(profile_name="bruno-mcp-prod")
    client = session.client("bedrock-runtime", region_name="us-east-1")

    # Use VTT transcript (with timestamps) if available for better references
    transcript_for_prompt = vtt_transcript if vtt_transcript else transcript

    # Build Comprehend context block
    comprehend_context = ""
    if comprehend_analysis:
        comprehend_context = f"""
--- NLP ANALYSIS (via Amazon Comprehend) ---
{format_comprehend_context(comprehend_analysis)}
--- END NLP ANALYSIS ---

Use the above NLP analysis to:
- Correctly identify and spell all people, organizations, and locations mentioned
- Prioritize the auto-detected key phrases when identifying takeaways
- Reflect the overall meeting sentiment in your Discussion Summary tone
- Use detected entities as potential action item owners where relevant

"""

    prompt = f"""You are an expert meeting notes writer following Amazon's RBS RoW AM writing standards.

{comprehend_context}Analyze the following meeting transcript and produce structured meeting minutes with these sections:

1) **Meeting Overview** — One paragraph: date/context (if inferable), attendees mentioned, purpose of the meeting.

2) **Key Takeaways** — Numbered list of macro themes and key decisions. Include all relevant takeaways from the meeting. Focus on outcomes and direction given. Use active voice, data where available, and concise language.

3) **Action Items** — Numbered list ordered by earliest ETA. Include all action items discussed or implied in the meeting. Each must include:
   - Precise description of the action
   - Owner (if mentioned, otherwise mark as TBD)
   - ETA/target date (if mentioned, otherwise mark as TBD)
   - **Reference:** A brief quote or paraphrase from the transcript that supports this action item, with the approximate timestamp or context where it was discussed. Format: "Reference: [quoted/paraphrased statement from transcript — context/timestamp if available]"

4) **Discussion Summary** — Narrative paragraphs covering the main topics discussed. Use active voice, short sentences, and provide the "so what" clearly.

5) **Next Steps** — Brief list of follow-up items or future meeting plans.

Rules:
- Use active voice throughout
- Replace vague language with specifics from the transcript
- Use numerals for numbers 10 and above, spell out numbers below 10
- Use 1), 2), 3) format for lists
- Keep it concise: as short as possible, as long as necessary
- If the transcript is unclear on any point, note it as "[unclear from recording]"
- Every action item MUST include a Reference field tracing it back to the transcript

TRANSCRIPT:
{transcript_for_prompt}

MEETING MINUTES:"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
    })

    response = client.invoke_model(
        modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
        body=body,
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())
    summary = response_body["content"][0]["text"]

    print("[Step 2] Meeting minutes generated.")
    return summary


def save_as_word(
    meeting_title: str,
    transcript: str,
    minutes: str,
    output_path: str,
    comprehend_analysis: dict = None,
) -> str:
    """
    Step 3: Save meeting minutes as a formatted Word document.

    Args:
        meeting_title: Title for the document.
        transcript: Original transcript text.
        minutes: Summarized meeting minutes.
        output_path: Path for the output .docx file.
        comprehend_analysis: Optional Comprehend NLP results to include.

    Returns:
        Path to the saved file.
    """
    print(f"[Step 3] Creating Word document: {output_path}")

    doc = Document()

    # Set default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Calibri"
    font.size = Pt(10)

    # Title
    title_para = doc.add_heading(meeting_title, level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Date
    date_para = doc.add_paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}")
    date_para.runs[0].font.size = Pt(10)
    date_para.runs[0].font.color.rgb = RGBColor(100, 100, 100)

    doc.add_paragraph("")  # spacer

    # Meeting Minutes section
    doc.add_heading("Meeting Minutes", level=1)

    # Parse and add the minutes content
    for line in minutes.split("\n"):
        line = line.strip()
        if not line:
            doc.add_paragraph("")
            continue

        # Handle markdown-style headers
        if line.startswith("## ") or line.startswith("**") and line.endswith("**"):
            clean = line.replace("## ", "").replace("**", "").strip()
            heading = doc.add_heading(clean, level=2)
            continue

        # Handle numbered items
        if len(line) > 2 and line[0].isdigit() and line[1] == ")":
            para = doc.add_paragraph(line, style="List Number")
            continue

        # Regular paragraph
        para = doc.add_paragraph(line)

    # NLP Analysis section (from Comprehend)
    if comprehend_analysis:
        doc.add_page_break()
        doc.add_heading("Appendix A: NLP Analysis (Amazon Comprehend)", level=1)

        # Entities
        if comprehend_analysis.get("entities"):
            doc.add_heading("Detected Entities", level=2)
            entity_by_type = {}
            for e in comprehend_analysis["entities"]:
                entity_by_type.setdefault(e["type"], []).append(e["text"])
            for etype, names in entity_by_type.items():
                para = doc.add_paragraph(f"{etype}: {', '.join(names[:15])}")
                para.runs[0].font.size = Pt(9)

        # Key Phrases
        if comprehend_analysis.get("key_phrases"):
            doc.add_heading("Key Phrases", level=2)
            phrases = [p["text"] for p in comprehend_analysis["key_phrases"][:20]]
            para = doc.add_paragraph(", ".join(phrases))
            para.runs[0].font.size = Pt(9)

        # Sentiment
        doc.add_heading("Meeting Sentiment", level=2)
        sentiment = comprehend_analysis.get("overall_sentiment", "UNKNOWN")
        para = doc.add_paragraph(f"Overall: {sentiment}")
        para.runs[0].font.size = Pt(9)

        # Language
        lang = comprehend_analysis.get("language", "unknown")
        para = doc.add_paragraph(f"Detected language: {lang}")
        para.runs[0].font.size = Pt(9)

    # Appendix: Full Transcript
    doc.add_page_break()
    appendix_label = "Appendix B" if comprehend_analysis else "Appendix"
    doc.add_heading(f"{appendix_label}: Full Transcript", level=1)
    transcript_para = doc.add_paragraph(transcript)
    transcript_para.runs[0].font.size = Pt(9)
    transcript_para.runs[0].font.color.rgb = RGBColor(80, 80, 80)

    # Footer: Amazon Confidential + page number
    section = doc.sections[0]
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.text = "Amazon Confidential"
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.runs[0].font.size = Pt(8)
    footer_para.runs[0].font.color.rgb = RGBColor(150, 150, 150)

    doc.save(output_path)
    print(f"[Step 3] Document saved: {output_path}")
    return output_path


def save_transcript_file(vtt_text: str, output_dir: str, base_name: str) -> str:
    """Save the VTT transcript to a file."""
    vtt_path = os.path.join(output_dir, f"{base_name}_transcript.vtt")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(vtt_text)
    print(f"[Step 1] Transcript saved: {vtt_path}")
    return vtt_path


def main():
    parser = argparse.ArgumentParser(
        description="Convert audio/video to meeting minutes Word document. "
        "Accepts local files, HTTP/HTTPS URLs, or S3 URLs."
    )
    parser.add_argument(
        "input_file",
        help="Path or URL to the audio/video file. "
        "Supports: local files, http(s):// URLs, s3:// URLs.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output name for the meeting (used in filename and title). "
        "Defaults to input filename.",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size. Larger = more accurate but slower. Default: base",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory for output files. Defaults to same directory as input file.",
    )

    args = parser.parse_args()

    # Handle URL or local file
    downloaded_file = None
    if is_url(args.input_file):
        # Set output dir for downloads
        default_output_dir = args.output_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "output"
        )
        os.makedirs(default_output_dir, exist_ok=True)

        download_dir = os.path.join(default_output_dir, "_downloads")
        downloaded_file = download_from_url(args.input_file, download_dir)
        input_path = Path(downloaded_file)
        output_dir = args.output_dir or default_output_dir
    else:
        input_path = Path(args.input_file).resolve()
        if not input_path.exists():
            print(f"Error: File not found: {input_path}")
            sys.exit(1)
        output_dir = args.output_dir or str(input_path.parent)

    # Set output parameters
    base_name = args.output or input_path.stem
    os.makedirs(output_dir, exist_ok=True)

    safe_name = base_name.replace(" ", "_")
    docx_path = os.path.join(output_dir, f"{safe_name}_meeting_minutes.docx")

    print("=" * 60)
    print("  MEETING MINUTES WORKFLOW")
    print("=" * 60)
    if is_url(args.input_file):
        print(f"  Source: {args.input_file}")
        print(f"  Local:  {input_path}")
    else:
        print(f"  Input:  {input_path}")
    print(f"  Model:  {args.model}")
    print(f"  Output: {docx_path}")
    print("=" * 60)
    print()

    # Step 1: Transcribe
    plain_text, vtt_text = transcribe_audio(str(input_path), args.model)
    save_transcript_file(vtt_text, output_dir, safe_name)

    # Step 1.5: Analyze with Comprehend
    try:
        comprehend_analysis = analyze_with_comprehend(plain_text)
    except Exception as e:
        print(f"[Step 1.5] Comprehend analysis failed: {e}. Proceeding without NLP enrichment.")
        comprehend_analysis = None

    # Step 2: Summarize
    minutes = summarize_transcript(plain_text, vtt_text, comprehend_analysis)

    # Step 3: Save as Word
    title = f"Meeting Minutes — {base_name}"
    save_as_word(title, plain_text, minutes, docx_path, comprehend_analysis)

    print()
    print("=" * 60)
    print("  WORKFLOW COMPLETE")
    print(f"  Transcript: {safe_name}_transcript.vtt")
    print(f"  Minutes:    {safe_name}_meeting_minutes.docx")
    print("=" * 60)


if __name__ == "__main__":
    main()
