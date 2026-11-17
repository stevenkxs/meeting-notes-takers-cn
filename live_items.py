"""Live action items and open questions. Watches a transcript written by mic_notes.py and keeps
a plain-text file of candidate items up to date while the meeting runs.

Usage:  python live_items.py notes/<file>.md [--out notes/<file>.live.txt] [--no-window]
Shows the items in a floating window by default. Exits by itself when notes/.recording
disappears (recording stopped).
The agent writes the final, cleaned-up Action Items and Open Questions at STOP; this file is the
live draft so you can see what is being picked up during the call.
"""
import argparse
import re
import time
from datetime import datetime
from pathlib import Path

LINE = re.compile(r"^- \*\*(\d\d:\d\d:\d\d)\*\* \[(Me|Them)\] (.+)$")

# ponytail: keyword heuristics, English + Mandarin. Misses indirect phrasing and catches some
# chatter ("please" in small talk). Upgrade path: send each new line to a small local LLM.
ACTION = re.compile(
    r"\b(i'll|i will|we'll|we will|you'll|will you|can you|could you|would you mind|please|"
    r"action item|follow[- ]?up|take care of|take the|let's|need to|needs to|have to|"
    r"make sure|send (?:it|this|over|out)|share (?:the|it|this)|set up|schedule|owner|todo|to-do|"
    r"by (?:monday|tuesday|wednesday|thursday|friday|tomorrow|eod|cob|end of|next week))\b"
    r"|我来|我会|我去|你来|你负责|负责|跟进|安排|记得|麻烦|帮忙|需要|下周|明天|截止|待办|落实|发给|同步一下",
    re.IGNORECASE)
QUESTION = re.compile(
    r"[?？]\s*$"
    r"|^(what|why|how|when|where|who|which|do|does|did|is|are|can|could|should|will|would|have|has)\b"
    r"|[吗呢]\s*[。.]?$|什么|怎么|为什么|是否|有没有|是不是|哪|谁|多少",
    re.IGNORECASE)


def classify(text):
    """Return "action", "question", or None. A request phrased as a question counts as an action."""
    if ACTION.search(text):
        return "action"
    if QUESTION.search(text):
        return "question"
    return None


def extract(transcript):
    """Parse transcript text into (actions, questions), each a list of 'HH:MM:SS [Who] text'."""
    found = {"action": [], "question": []}
    seen = set()
    for raw in transcript.splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        ts, who, text = m.groups()
        key = re.sub(r"\W+", "", text.lower())
        if not key or key in seen:  # skip echoes ([Me] repeating [Them] on open speakers)
            continue
        seen.add(key)
        kind = classify(text)
        if kind:
            found[kind].append(f"{ts} [{who}] {text}")
    return found["action"], found["question"]


def render(src, actions, questions, final=False):
    status = "Recording stopped" if final else f"Live, updated {datetime.now():%H:%M:%S}"
    body = [f"LIVE ITEMS: {src.name}", status, "Candidates picked up by keyword. Final notes are written at stop.", ""]
    body += [f"ACTION ITEMS ({len(actions)})"] + ([f"[ ] {a}" for a in actions] or ["None yet"])
    body += ["", f"OPEN QUESTIONS ({len(questions)})"] + ([f"? {q}" for q in questions] or ["None yet"])
    return "\n".join(body) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--out", help="default: <transcript>.live.txt next to the transcript")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between checks")
    p.add_argument("--no-window", action="store_true", help="only write the file, no floating window")
    args = p.parse_args()

    src = Path(args.file)
    out = Path(args.out) if args.out else src.with_suffix(".live.txt")
    flag = src.parent / ".recording"
    t0, last = time.time(), [-1]

    def running():
        return flag.exists() or time.time() - t0 < 10  # 10 s grace for startup, like captions.py

    def poll(final=False):
        """Rewrite the live file when the transcript changed. Returns the new text, or None."""
        size = src.stat().st_size if src.exists() else 0
        if size == last[0] and not final:
            return None
        last[0] = size
        text = src.read_text(encoding="utf-8") if src.exists() else ""
        body = render(src, *extract(text), final=final)
        out.write_text(body, encoding="utf-8")
        return body

    if args.no_window:
        while running():
            poll()
            time.sleep(args.interval)
        poll(final=True)
        return

    import tkinter as tk  # same look as captions.py, docked top-right so it stays clear of captions
    root = tk.Tk()
    root.title("Live items")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.92)
    root.configure(bg="#161D26")
    w, h = 460, 420
    root.geometry(f"{w}x{h}+{root.winfo_screenwidth() - w - 20}+60")
    box = tk.Text(root, fg="#FFFFFF", bg="#161D26", font=("Segoe UI", 11), wrap="word",
                  relief="flat", padx=12, pady=10, insertbackground="#FFFFFF")
    box.pack(fill="both", expand=True)

    def tick():
        if not running():
            poll(final=True)
            root.destroy()
            return
        body = poll()
        if body is not None:
            box.delete("1.0", "end")
            box.insert("1.0", body)
            box.see("end")  # newest items are at the bottom of each list
        root.after(int(args.interval * 1000), tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    main()
