"""
Transcribe-only helper.

Transcribes an audio/video file to text using OpenAI Whisper (runs locally).
Produces both a plain-text (.txt) and a timestamped WebVTT (.vtt) transcript.

Usage:
    python transcribe_only.py "<audio_or_video_file>" [--model <whisper_model>] [--output-dir <dir>]
"""

import argparse
import os
import sys
from pathlib import Path

import whisper


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def main():
    parser = argparse.ArgumentParser(description="Transcribe audio/video to text with Whisper.")
    parser.add_argument("input_file", help="Path to the audio/video file.")
    parser.add_argument("--model", "-m", default="base",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model size. Default: base")
    parser.add_argument("--output-dir", "-d", default=None,
                        help="Output directory. Defaults to the input file's directory.")
    parser.add_argument("--language", "-l", default=None,
                        help="Force a language (e.g. 'en'). Omit for auto-detection.")
    args = parser.parse_args()

    input_path = Path(args.input_file).resolve()
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    output_dir = args.output_dir or str(input_path.parent)
    os.makedirs(output_dir, exist_ok=True)
    base_name = input_path.stem.replace(" ", "_")

    txt_path = os.path.join(output_dir, f"{base_name}_transcript.txt")
    vtt_path = os.path.join(output_dir, f"{base_name}_transcript.vtt")

    print(f"[1/2] Loading Whisper model '{args.model}'...")
    model = whisper.load_model(args.model)

    lang_note = args.language if args.language else "auto-detect"
    print(f"[2/2] Transcribing '{input_path}' (language: {lang_note})...")
    result = model.transcribe(str(input_path), verbose=False, language=args.language)

    plain_text = result["text"].strip()
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(plain_text + "\n")

    vtt_lines = ["WEBVTT", ""]
    for segment in result["segments"]:
        vtt_lines.append(f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}")
        vtt_lines.append(segment["text"].strip())
        vtt_lines.append("")
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(vtt_lines))

    print(f"Detected language: {result.get('language', 'unknown')}")
    print(f"Segments: {len(result['segments'])}")
    print(f"Saved: {txt_path}")
    print(f"Saved: {vtt_path}")


if __name__ == "__main__":
    main()
