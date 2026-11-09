"""Listen to the microphone AND the default speaker (WASAPI loopback) and append
labelled, timestamped transcripts to a markdown file.
Lines are tagged "Me" (microphone) or "Them" (what plays through your speakers/headset,
e.g. the other side of a Teams or Chime call).
Each phrase is transcribed as soon as the speaker pauses (--pause), or after --chunk seconds
of continuous speech, so captions trail speech by a few seconds. Each source has its own
transcription thread, so "Me" and "Them" never wait for each other.
Usage:  python mic_notes.py [--model base] [--chunk 6] [--pause 0.4] [--language zh] [--no-speaker] [--save-audio] [--out notes/<timestamp>.md]
Stop with Ctrl+C, or by creating notes/.stop. Audio stays local (Whisper runs on this machine).
Tip: use a headset. With open speakers the mic also hears the speakers and lines get duplicated.
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
import numpy as np
import pyaudiowpatch as pyaudio
import sounddevice as sd
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # harmless Windows cache warning
from faster_whisper import WhisperModel
RATE = 16000  # Whisper expects 16 kHz mono
BLOCK = RATE // 10  # 100 ms capture blocks
LABELS = ("Me", "Them")
# ponytail: energy gates, measured on loopback audio (speech ~0.05 RMS, quiet <0.003).
# A block starts a phrase above VOICE_RMS; inside a phrase, a block counts as a pause when it is
# below PAUSE_RATIO of the phrase's average loudness, so breaths between phrases end it.
# A mic whose background noise stays loud never "pauses" and falls back to --chunk.
# Upgrade path: run Silero VAD (faster_whisper.vad) per block instead.
VOICE_RMS = 0.005
PAUSE_RATIO = 0.3
# Each transcription costs ~1 s on CPU however short the audio, so a pause only ends a phrase
# once it is this old. Many tiny phrases would otherwise queue up and add delay.
MIN_PHRASE = 2.0
# Redirected stdout defaults to the system code page (GBK here) and crashes on other scripts.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
p = argparse.ArgumentParser()
p.add_argument("--model", default="base", help="tiny/base/small/medium (bigger = slower, more accurate)")
p.add_argument("--chunk", type=int, default=6, help="max seconds of continuous speech per transcription")
p.add_argument("--pause", type=float, default=0.4, help="seconds of quiet that end a phrase")
p.add_argument("--out", default=f"notes/{datetime.now():%Y-%m-%d_%H%M}.md")
p.add_argument("--language", default=None, help="e.g. en, zh; default auto-detects")
p.add_argument("--no-speaker", action="store_true", help="record the microphone only")
p.add_argument("--save-audio", action="store_true",
               help="also save notes/audio/<name>_me.wav and _them.wav")
args = p.parse_args()
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
STOP = out.parent / ".stop"
STOP.unlink(missing_ok=True)  # clear any stale signal
if not out.exists():
    out.write_text(f"# Meeting notes {datetime.now():%Y-%m-%d %H:%M}\n\n", encoding="utf-8")
print(f"Loading Whisper '{args.model}'...")
# int8 on CPU; num_workers=2 lets the Me and Them threads transcribe in parallel.
model = WhisperModel(args.model, device="cpu", compute_type="int8", num_workers=2)
audio_q: queue.Queue = queue.Queue()  # items: (label, mono float32 @ RATE, capture time)
def to_16k_mono(x: np.ndarray, rate: int) -> np.ndarray:
    """x: (frames, channels) float32 -> mono float32 at 16 kHz."""
    mono = x.mean(axis=1)
    if rate == RATE:
        return mono
    n = int(len(mono) * RATE / rate)
    return np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)
class Wav:
    """Append-only 16 kHz mono WAV kept aligned to wall-clock time.
    Loopback sends nothing while the speaker is silent, so gaps are padded with zeros.
    Padding uses each chunk's capture time (not the time it is dequeued), so a slow
    transcription never shifts the audio.
    """
    def __init__(self, path):
        self.w = wave.open(str(path), "wb")
        self.w.setnchannels(1)
        self.w.setsampwidth(2)
        self.w.setframerate(RATE)
        self.t0, self.n = time.time(), 0
    def add(self, chunk, ts):
        gap = int((ts - self.t0) * RATE) - self.n - len(chunk)
        if gap > RATE // 2:
            self.w.writeframes(np.zeros(gap, dtype=np.int16).tobytes())
            self.n += gap
        self.w.writeframes((np.clip(chunk, -1, 1) * 32767).astype(np.int16).tobytes())
        self.n += len(chunk)
def on_mic(indata, frames, t, status):
    audio_q.put(("Me", indata[:, 0].copy(), time.time()))
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
            audio_q.put(("Them", to_16k_mono(x, rate), time.time()))
            return (None, pyaudio.paContinue)
        loop_stream = pa.open(format=pyaudio.paFloat32, channels=ch, rate=rate, input=True,
                              input_device_index=dev["index"], frames_per_buffer=rate // 10,
                              stream_callback=on_loop)
        print(f"Speaker capture: {dev['name']}")
    except Exception as e:  # keep the mic working even if loopback is unavailable
        print(f"Speaker capture unavailable ({e}); recording microphone only")
        loop_stream = None
bufs = {l: [] for l in LABELS}
first_voice = {l: None for l in LABELS}  # capture time of the first voiced block in the buffer
last_voice = {l: 0.0 for l in LABELS}
loudness = {l: (0.0, 0) for l in LABELS}  # (sum, count) of voiced block RMS in the current phrase
work = {l: queue.Queue() for l in LABELS}  # finished phrases waiting for transcription
write_lock = threading.Lock()
wavs = {}
if args.save_audio:
    adir = out.parent / "audio"
    adir.mkdir(exist_ok=True)
    wavs["Me"] = Wav(adir / f"{out.stem}_me.wav")
    if loop_stream:
        wavs["Them"] = Wav(adir / f"{out.stem}_them.wav")
    (adir / f"{out.stem}.json").write_text(
        json.dumps({"start": datetime.now().isoformat(timespec="seconds"), "language": args.language}),
        encoding="utf-8")
    print(f"Saving audio -> {adir}")
def take(item):
    """Buffer one captured block, track speech/pauses, and write it to its WAV if enabled."""
    label, chunk, ts = item
    if label in wavs:
        wavs[label].add(chunk, ts)
    bufs[label].append(chunk)
    level = float(np.sqrt(np.mean(chunk ** 2)))
    total, n = loudness[label]
    if level >= max(VOICE_RMS, PAUSE_RATIO * total / n if n else 0):
        last_voice[label] = ts
        loudness[label] = (total + level, n + 1)
        if first_voice[label] is None:
            first_voice[label] = ts
    elif first_voice[label] is None:
        del bufs[label][:-3]  # no speech yet: keep only ~0.3 s of lead-in
def flush(label):
    """Hand the buffered phrase to that source's transcription thread."""
    buf, bufs[label] = bufs[label], []
    ts, first_voice[label] = first_voice[label], None
    loudness[label] = (0.0, 0)
    if buf and ts is not None:
        work[label].put((ts, np.concatenate(buf).astype(np.float32)))
def transcriber(label):
    while (job := work[label].get()) is not None:
        ts, audio = job
        try:
            # vad_filter skips non-speech, which otherwise makes Whisper hallucinate slowly.
            segs, _ = model.transcribe(audio, language=args.language, vad_filter=True, without_timestamps=True)
            text = "".join(s.text for s in segs).strip()
        except Exception as e:  # incl. MemoryError: drop this phrase, keep recording
            print(f"transcribe failed for {label} chunk, skipped: {e!r}")
            continue
        if text:
            line = f"- **{datetime.fromtimestamp(ts):%H:%M:%S}** [{label}] {text}"
            with write_lock:
                with out.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
                print(line)
threads = [threading.Thread(target=transcriber, args=(l,), daemon=True) for l in LABELS]
for t in threads:
    t.start()
print(f"Listening (phrases end after {args.pause}s quiet, max {args.chunk}s) -> {out}  |  Ctrl+C to stop")
try:
    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK, callback=on_mic):
        while True:
            if STOP.exists():  # external stop signal (used by the meeting-notes-takers-cn agent)
                STOP.unlink()
                raise KeyboardInterrupt
            try:
                take(audio_q.get(timeout=0.1))
            except queue.Empty:
                pass
            # Loopback sends nothing while the speaker is silent, so pauses are measured on wall-clock time.
            now = time.time()
            for label in LABELS:
                age = now - first_voice[label] if first_voice[label] is not None else -1
                if age >= args.chunk or (age >= MIN_PHRASE and now - last_voice[label] >= args.pause):
                    flush(label)
except KeyboardInterrupt:
    while not audio_q.empty():  # audio captured but not yet buffered
        take(audio_q.get_nowait())
    for label in LABELS:
        flush(label)
        work[label].put(None)  # let each thread finish its queue, then exit
    for t in threads:
        t.join()
    print(f"\nSaved: {out}")
finally:
    for w in wavs.values():
        w.w.close()
    if loop_stream:
        loop_stream.stop_stream()
        loop_stream.close()
    if pa:
        pa.terminate()
sys.exit(0)
