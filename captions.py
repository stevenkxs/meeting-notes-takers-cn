"""Floating live-caption window. Shows the latest lines of a transcript file written by mic_notes.py.

Usage:  python captions.py notes/<file>.md [--lines 3]
Closes itself when notes/.recording disappears (recording stopped), or close it with the X.
"""
import argparse
import re
import time
import tkinter as tk
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("file")
p.add_argument("--lines", type=int, default=3, help="how many recent lines to show")
args = p.parse_args()

src = Path(args.file)
flag = src.parent / ".recording"
t0 = time.time()
PREFIX = re.compile(r"^- \*\*\d\d:\d\d:\d\d\*\* ")  # drop the timestamp, keep [Me]/[Them]

root = tk.Tk()
root.title("Live captions")
root.attributes("-topmost", True)
root.attributes("-alpha", 0.92)
root.configure(bg="#161D26")
w, h = 900, 40 + 62 * args.lines
x = (root.winfo_screenwidth() - w) // 2
y = root.winfo_screenheight() - h - 80
root.geometry(f"{w}x{h}+{x}+{y}")

label = tk.Label(root, text="Listening...", fg="#FFFFFF", bg="#161D26", font=("Segoe UI", 15),
                 justify="left", anchor="sw", wraplength=w - 30)
label.pack(fill="both", expand=True, padx=15, pady=10)


def tick():
    if not flag.exists() and time.time() - t0 > 10:  # recording stopped (10 s grace for startup)
        root.destroy()
        return
    if src.exists():
        lines = [PREFIX.sub("", l) for l in src.read_text(encoding="utf-8").splitlines() if l.startswith("- **")]
        if lines:
            label.config(text="\n".join(lines[-args.lines:]))
    root.after(500, tick)


tick()
root.mainloop()
