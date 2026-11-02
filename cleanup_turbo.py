"""Re-transcribe a recorded meeting with a large whisper.cpp model (slow, more accurate).

Usage:  python cleanup_turbo.py notes/<name>.md [--model <ggml .bin>] [--language zh] [--keep-audio]

Reads notes/audio/<name>_me.wav and _them.wav (saved by `mic_notes.py --save-audio`) and writes
notes/<name>_turbo.md in the same line format as the live transcript. The file appears only when
the pass has finished, so its existence means "done". Audio is deleted after success unless
--keep-audio. Runs at below-normal priority so the laptop stays usable.

Model: --model, else the TURBO_MODEL environment variable, else the Meetily app's
ggml-large-v3-turbo-q5_0.bin. Audio stays local.
"""
import argparse
import ctypes
import json
import os
import sys
import time
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

RATE = 16000
MEETILY = Path(os.environ.get("APPDATA", "")) / "com.meetily.ai" / "models" / "ggml-large-v3-turbo-q5_0.bin"

p = argparse.ArgumentParser()
p.add_argument("transcript", help="the live transcript, e.g. notes/<name>.md")
p.add_argument("--model", default=os.environ.get("TURBO_MODEL") or str(MEETILY))
p.add_argument("--language", default=None, help="e.g. en, zh; default: the language the recording used, else auto")
p.add_argument("--threads", type=int, default=8)
p.add_argument("--window", type=int, default=30, help="seconds of audio per transcription")
p.add_argument("--keep-audio", action="store_true")
args = p.parse_args()

try:  # below-normal priority (Windows only; harmless elsewhere)
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
except Exception:
    pass

live = Path(args.transcript)
adir = live.parent / "audio"
final = live.with_name(live.stem + "_turbo.md")
meta_path = adir / f"{live.stem}.json"
model_path = Path(args.model)
if not model_path.exists():
    sys.exit(f"Model not found: {model_path}. Pass --model or set TURBO_MODEL.")
streams = [(label, adir / f"{live.stem}_{tag}.wav") for label, tag in (("Me", "me"), ("Them", "them"))]
streams = [(label, path) for label, path in streams if path.exists()]
if not streams:
    sys.exit(f"No saved audio in {adir}. Record with --save-audio.")

meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
start = datetime.fromisoformat(meta["start"]) if meta.get("start") else datetime.fromtimestamp(streams[0][1].stat().st_ctime)
lang = args.language or meta.get("language") or ""  # "" = auto-detect

from pywhispercpp.model import Model  # imported late so a bad path fails fast above

print(f"Loading {model_path.name} ...", flush=True)
model = Model(str(model_path), n_threads=args.threads, print_progress=False, print_realtime=False)


def read_wav(path):
    with wave.open(str(path)) as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1, f"unexpected format: {path}"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def windows(x, win, search=3 * RATE):
    """Yield (start, end) sample ranges of about `win` seconds, cut at a quiet moment so words are not split."""
    i, win = 0, win * RATE
    while i < len(x):
        end = min(i + win, len(x))
        if end < len(x):
            seg = np.abs(x[end - search:end].astype(np.float32))
            frames = seg[: len(seg) // 1600 * 1600].reshape(-1, 1600).mean(axis=1)  # 100 ms frames
            end = end - search + int(frames.argmin()) * 1600 + 800
        yield i, end
        i = end


lines, t0 = [], time.time()
for label, path in streams:
    x = read_wav(path)
    wins = list(windows(x, args.window))
    for k, (i, end) in enumerate(wins, 1):
        seg = x[i:end].astype(np.float32) / 32768
        if np.abs(seg).max() >= 0.01:  # skip silence, as the live pass does
            text = " ".join(s.text.strip() for s in model.transcribe(seg, language=lang)).strip()
            if text:
                lines.append((start + timedelta(seconds=i / RATE), label, text))
        print(f"[{label}] {k}/{len(wins)}  elapsed {time.time() - t0:.0f}s", flush=True)

lines.sort(key=lambda r: r[0])
body = "".join(f"- **{t:%H:%M:%S}** [{label}] {text}\n" for t, label, text in lines)
tmp = final.with_suffix(".partial")
tmp.write_text(f"# Meeting notes (turbo) {start:%Y-%m-%d %H:%M}\n\n{body}", encoding="utf-8")
os.replace(tmp, final)  # appears only when complete
print(f"Saved: {final}  ({time.time() - t0:.0f}s)", flush=True)

if not args.keep_audio:
    for _, path in streams:
        path.unlink(missing_ok=True)
    meta_path.unlink(missing_ok=True)
    try:
        adir.rmdir()  # only succeeds when empty
    except OSError:
        pass
    print("Audio deleted.", flush=True)
