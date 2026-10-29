"""Listen to the microphone AND the default speaker (WASAPI loopback) and append
labelled, timestamped transcripts to a markdown file.

Lines are tagged "Me" (microphone) or "Them" (what plays through your speakers/headset,
e.g. the other side of a Teams or Chime call).

Usage:  python mic_notes.py [--model base] [--chunk 30] [--language zh] [--no-speaker] [--out notes/<timestamp>.md]
Stop with Ctrl+C, or by creating notes/.stop. Audio stays local (Whisper runs on this machine).
Tip: use a headset. With open speakers the mic also hears the speakers and lines get duplicated.
"""
import argparse
import queue
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
import sounddevice as sd
import whisper

RATE = 16000  # Whisper expects 16 kHz mono

# Redirected stdout defaults to the system code page (GBK here) and crashes on other scripts.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

p = argparse.ArgumentParser()
p.add_argument("--model", default="base", help="tiny/base/small/medium (bigger = slower, more accurate)")
p.add_argument("--chunk", type=int, default=30, help="seconds of audio per transcription")
p.add_argument("--out", default=f"notes/{datetime.now():%Y-%m-%d_%H%M}.md")
p.add_argument("--language", default=None, help="e.g. en, zh; default auto-detects")
p.add_argument("--no-speaker", action="store_true", help="record the microphone only")
args = p.parse_args()

out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
STOP = out.parent / ".stop"
STOP.unlink(missing_ok=True)  # clear any stale signal
if not out.exists():
    out.write_text(f"# Meeting notes {datetime.now():%Y-%m-%d %H:%M}\n\n", encoding="utf-8")

print(f"Loading Whisper '{args.model}'...")
model = whisper.load_model(args.model)
audio_q: queue.Queue = queue.Queue()  # items: (label, mono float32 @ RATE)


def to_16k_mono(x: np.ndarray, rate: int) -> np.ndarray:
    """x: (frames, channels) float32 -> mono float32 at 16 kHz."""
    mono = x.mean(axis=1)
    if rate == RATE:
        return mono
    n = int(len(mono) * RATE / rate)
    return np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)


def on_mic(indata, frames, t, status):
    audio_q.put(("Me", indata[:, 0].copy()))


# --- speaker loopback (WASAPI) ---
pa = None
loop_stream = None
if not args.no_speaker:
    try:
        pa = pyaudio.PyAudio()
        dev = pa.get_default_wasapi_loopback()
        ch, rate = dev["maxInputChannels"], int(dev["defaultSampleRate"])

        def on_loop(in_data, frame_count, time_info, status):
            x = np.frombuffer(in_data, dtype=np.float32).reshape(-1, ch)
            audio_q.put(("Them", to_16k_mono(x, rate)))
            return (None, pyaudio.paContinue)

        loop_stream = pa.open(format=pyaudio.paFloat32, channels=ch, rate=rate, input=True,
                              input_device_index=dev["index"], frames_per_buffer=rate // 10,
                              stream_callback=on_loop)
        print(f"Speaker capture: {dev['name']}")
    except Exception as e:  # keep the mic working even if loopback is unavailable
        print(f"Speaker capture unavailable ({e}); recording microphone only")
        loop_stream = None

bufs = {"Me": [], "Them": []}
started = {"Me": time.time(), "Them": time.time()}


def flush(label):
    buf, bufs[label] = bufs[label], []
    started[label] = time.time()
    if not buf:
        return
    audio = np.concatenate(buf).astype(np.float32)
    if np.abs(audio).max() < 0.01:  # silence, skip
        return
    text = model.transcribe(audio, language=args.language, fp16=False)["text"].strip()
    if text:
        line = f"- **{datetime.now():%H:%M:%S}** [{label}] {text}"
        with out.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)


def flush_all():
    for label in ("Me", "Them"):
        flush(label)


print(f"Listening ({args.chunk}s chunks) -> {out}  |  Ctrl+C to stop")
try:
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=on_mic):
        while True:
            if STOP.exists():  # external stop signal (used by the meeting-notes-takers-cn agent)
                STOP.unlink()
                raise KeyboardInterrupt
            try:
                label, chunk = audio_q.get(timeout=1)
                bufs[label].append(chunk)
            except queue.Empty:
                pass
            # Loopback sends nothing while the speaker is silent, so flush on wall-clock time, not sample count.
            for label in ("Me", "Them"):
                if time.time() - started[label] >= args.chunk:
                    flush(label)  # ponytail: blocks while transcribing; queue absorbs audio, fine unless model is slower than real time
except KeyboardInterrupt:
    flush_all()
    print(f"\nSaved: {out}")
finally:
    if loop_stream:
        loop_stream.stop_stream()
        loop_stream.close()
    if pa:
        pa.terminate()
sys.exit(0)
