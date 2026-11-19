"""Background call watcher and meeting team coordinator.
1. When Teams, Zoom or Slack is in a call, it asks "Record this call?" and records (the
   meeting-recorder-cn job) only after you click Record. It stops when the call ends.
2. While any recording runs (started here or by the meeting-recorder-cn agent), it runs the
   meeting-qa-cn agent continuously (back to back) and shows its <t>.qa.md in a "Live Q&A" window.
3. When the recording stops, it runs meeting-qa-cn's final pass, then meeting-minutes-cn,
   then pops a "Meeting minutes ready" notice.
Agents run headless through kiro-cli. Usage:  pythonw call_watcher.py  (Task Scheduler starts it at logon)
Logs: notes/.watcher.log.txt (watcher), notes/.team.log.txt (agent runs)
"""
import ctypes
import os
import re
import subprocess
import sys
import time
import tkinter as tk
import winreg
from datetime import datetime
from pathlib import Path

from live_items import extract  # keyword question spotting, shared with the fallback agent

TOOL = Path(__file__).resolve().parent
NOTES = TOOL / "notes"
REC, STOP = NOTES / ".recording", NOTES / ".stop"
AGENTS = Path.home() / ".kiro" / "agents"
QA_AGENT, MINUTES_AGENT = AGENTS / "meeting-qa-cn.md", AGENTS / "meeting-minutes-cn.md"
# Live passes run back to back: the next starts as soon as one finishes and the transcript has new
# lines. A pass takes about 30 to 60 s with the lean runner below.
# ponytail: one agent runs at a time, so a final pass can wait for a live pass to end.
QA_EVERY = 0  # minimum seconds between the starts of live Q&A passes
QA_FIRST = 20  # first live pass this long after recording starts
# A kiro-cli run that has not exited by then is killed, so one hung run cannot block the team.
JOB_TIMEOUT = {"update": 150, "final": 300, "minutes": 300}
# Lean runner: an agent with no MCP servers and file tools only, so kiro-cli skips loading the
# user's MCP servers. (kiro-cli 3.0 removed the faster v1 engine.) If a run on it fails, the
# watcher falls back to the default kiro-cli setup and logs it.
RUNNER = ["--agent", "meeting-team-runner"]
APPS = {"teams": "Teams", "zoom": "Zoom", "slack": "Slack"}
POLL_MS = 3000
END_GRACE = 15  # seconds the mic must stay free before the call counts as ended (hold, mute toggles)
ASK_TIMEOUT = 120  # an unanswered prompt means "do not record"
NO_WINDOW = subprocess.CREATE_NO_WINDOW
PYTHON = Path(sys.executable).with_name("python.exe")  # console python for the recorder (logs to files)
MIC = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
NOTES.mkdir(exist_ok=True)
LOG = NOTES / ".watcher.log.txt"


def log(msg):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def call_app():
    """Name of a call app in a call right now, else None.
    Windows keeps LastUsedTimeStop = 0 while an app is using the microphone."""
    for sub in (MIC, MIC + r"\NonPackaged"):
        try:
            root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            continue
        with root:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                app = next((v for k, v in APPS.items() if k in name.lower()), None)
                if not app:
                    continue
                try:
                    with winreg.OpenKey(root, name) as k:
                        start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if start and not stop:
                    return app
    # Zoom Workplace often does not report its microphone use to Windows, so also look for its
    # meeting window (window class seen on Zoom Workplace, Nov 2026). Zoom keeps a hidden copy of
    # that window after the meeting ends, so only a visible one counts (minimized still counts).
    if zoom_meeting_visible():
        return "Zoom"
    return None


def zoom_meeting_visible():
    u = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(h, _):
        b = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(ctypes.c_void_p(h), b, 64)
        if b.value == "ConfMultiTabContentWndClass" and u.IsWindowVisible(ctypes.c_void_p(h)):
            found.append(h)
            return False
        return True

    u.EnumWindows(cb, None)
    return bool(found)


def pid_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return f'"{pid}"' in out


def start_recording():
    """Same launch as the agent's START command."""
    out = NOTES / f"{datetime.now():%Y-%m-%d_%H%M}.md"
    with (NOTES / ".log.txt").open("w") as lo, (NOTES / ".err.txt").open("w") as le:
        p = subprocess.Popen([str(PYTHON), "-u", str(TOOL / "mic_notes.py"), "--model", "base", "--out", str(out)],
                             cwd=TOOL, stdout=lo, stderr=le, creationflags=NO_WINDOW)
    REC.write_text(f"{out}\n{p.pid}", encoding="utf-8")
    subprocess.Popen([sys.executable, str(TOOL / "captions.py"), str(out)], cwd=TOOL, creationflags=NO_WINDOW)
    log(f"recording -> {out} (pid {p.pid})")
    return out, p


def has_speech(t: Path):
    return t.exists() and "\n- **" in t.read_text(encoding="utf-8")


def run_agent(agent: Path, task: str, t: Path):
    """Run one team agent headless. `kiro-cli --agent` cannot load these .md agents, so the
    prompt points it at the agent file instead."""
    prompt = (f"You are the agent defined in {agent}. Read that file first and follow it exactly. "
              f"Do its {task} task for the transcript file {t}. "
              f"Nobody is watching this session: do not ask questions.")
    # ponytail: trusts read/write only (no shell); file writes are not limited to the team's files.
    with (NOTES / ".team.log.txt").open("a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {agent.stem} {task} {t.name}\n")
        f.flush()
        p = subprocess.Popen(["kiro-cli", "chat", "--no-interactive", *RUNNER,
                              "--trust-tools=fs_read,fs_write,read,write", prompt],
                             cwd=NOTES, stdout=f, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    log(f"{agent.stem} {task} -> {t.name} ({' '.join(RUNNER) or 'default kiro-cli setup'})")
    return p, time.time()


def runner_failed():
    """A run on the lean runner failed: fall back to the default kiro-cli setup."""
    global RUNNER
    if RUNNER:
        RUNNER = []
        log(f"team: run failed, falling back to {' '.join(RUNNER) or 'default kiro-cli setup'}")
        return True
    return False


DARK, TEXT, MUTED = "#161D26", "#FFFFFF", "#C0C6CE"
COVERED = re.compile(r"Covers transcript up to (\d\d:\d\d:\d\d)")


def live_qa_text(transcript: str, qa: str) -> str:
    """Live Q&A window text: the agent's checked Q&A, then keyword-spotted questions from lines the
    agent has not read yet, so new questions show within seconds instead of after the next pass.
    ponytail: keyword heuristics from live_items.py, so some misses and some chatter; times are
    compared as HH:MM:SS, so a meeting that runs past midnight shows old lines as new."""
    covered = (COVERED.search(qa) or [None, "00:00:00"])[1]
    pending = [q for q in extract(transcript)[1] if q[:8] > covered]
    body = qa.replace("**", "") if qa else "Checked questions and answers appear here after the first pass, about a minute in.\n"
    if pending:
        body += "\n## Possible questions (spotted just now, not checked yet)\n" + "\n".join(f"? {q}" for q in pending) + "\n"
    return body


class Team:
    """Hands each recording from the recorder to the Q&A tracker, then to the minutes writer.
    Runs one agent at a time. Driven by the watcher's poll loop."""

    def __init__(self, root):
        self.root = root
        self.live = None  # transcript being recorded
        self.no_live = False
        self.done = []  # stopped recordings waiting for Q&A final + minutes
        self.job = self.job_kind = self.job_t = None
        self.job_started = 0.0
        self.last_qa = 0.0
        self.qa_size = -1
        self.win = self.box = None
        self.win_t, self.win_mtime = None, None

    def step(self):
        now = time.time()
        try:
            lines = REC.read_text(encoding="utf-8").splitlines()
            rec, no_live = Path(lines[0]), "no-live" in lines[2:]
            if "fallback" in lines[2:]:  # meeting-notes-takers-cn does its own notes
                rec = None
        except (OSError, IndexError):
            rec, no_live = None, False
        if rec and rec != self.live:
            if self.live:
                self.done.append(self.live)
            self.live, self.no_live = rec, no_live
            self.last_qa, self.qa_size = now - QA_EVERY + QA_FIRST, -1
            log(f"team: recording {rec.name}")
        elif not rec and self.live:
            self.done.append(self.live)
            log(f"team: {self.live.name} stopped, finishing")
            self.live = None

        timed_out = False
        if self.job and self.job.poll() is None and now - self.job_started > JOB_TIMEOUT[self.job_kind]:
            # kiro-cli sometimes finishes its work but never exits (seen 2026-11-19: hung 4 h and
            # blocked every later pass). Kill it and carry on; the next step checks the files.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.job.pid)], capture_output=True,
                           creationflags=NO_WINDOW)
            self.job.wait()
            timed_out = True
            log(f"team: {self.job_kind} for {self.job_t.name} timed out after {JOB_TIMEOUT[self.job_kind]} s, killed")
        if self.job and self.job.poll() is not None:
            kind, t, code = self.job_kind, self.job_t, self.job.returncode
            self.job = self.job_kind = None
            if not timed_out:
                log(f"team: {kind} for {t.name} finished (code {code})")
            if code != 0 and not timed_out and runner_failed():  # retry the same task on the fallback setup
                agent, task = {"update": (QA_AGENT, "UPDATE"), "final": (QA_AGENT, "FINAL"),
                               "minutes": (MINUTES_AGENT, "MINUTES")}[kind]
                self.job_kind, self.job_t = kind, t
                self.job, self.job_started = run_agent(agent, task, t)
            elif kind == "final":
                self.job_kind, self.job_t = "minutes", t
                self.job, self.job_started = run_agent(MINUTES_AGENT, "MINUTES", t)
            elif kind == "minutes":
                self.notify(t)
        if self.job is None:
            if self.done:
                t = self.done.pop(0)
                if has_speech(t):
                    self.job_kind, self.job_t = "final", t
                    self.job, self.job_started = run_agent(QA_AGENT, "FINAL", t)
                else:
                    log(f"team: no speech in {t.name}, no Q&A or minutes")
                    self.close_window()
            elif self.live and not self.no_live and now - self.last_qa >= QA_EVERY:
                size = self.live.stat().st_size if self.live.exists() else 0
                self.last_qa = now
                if size != self.qa_size and has_speech(self.live):
                    self.qa_size = size
                    self.job_kind, self.job_t = "update", self.live
                    self.job, self.job_started = run_agent(QA_AGENT, "UPDATE", self.live)
        self.show_qa()

    # --- Live Q&A window -------------------------------------------------------------------
    def show_qa(self):
        """Show <t>.qa.md for the meeting being recorded or being finished."""
        t = self.live if (self.live and not self.no_live) else (self.job_t if self.job_kind in ("final", "minutes") else None)
        if t is None:
            return
        if self.win is None:
            w = self.win = tk.Toplevel(self.root, bg=DARK)
            w.title("Live Q&A")
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.92)
            w.geometry(f"460x420+{w.winfo_screenwidth() - 480}+230")
            self.box = tk.Text(w, fg=TEXT, bg=DARK, font=("Segoe UI", 11), wrap="word", relief="flat", padx=12, pady=10)
            self.box.pack(fill="both", expand=True)
            w.protocol("WM_DELETE_WINDOW", self.close_window)
            self.win_t = self.win_mtime = self.win_size = None
        qa = t.with_suffix(".qa.md")
        mtime = qa.stat().st_mtime if qa.exists() else None
        size = t.stat().st_size if t.exists() else 0
        if (t, mtime, size) == (self.win_t, self.win_mtime, self.win_size):
            return
        self.win_t, self.win_mtime, self.win_size = t, mtime, size
        qa_text = qa.read_text(encoding="utf-8") if qa.exists() else ""
        body = live_qa_text(t.read_text(encoding="utf-8") if t.exists() else "", qa_text)
        self.box.delete("1.0", "end")
        self.box.insert("1.0", body)

    def close_window(self):
        if self.win:
            self.win.destroy()
        self.win = self.box = None

    def notify(self, t: Path):
        self.close_window()
        minutes = t.with_suffix(".minutes.md")
        ok = minutes.exists() and minutes.stat().st_mtime >= t.stat().st_mtime
        log(f"team: minutes for {t.name} {'ready' if ok else 'MISSING, see .team.log.txt'}")
        w = tk.Toplevel(self.root, bg=DARK)
        w.title("Meeting minutes")
        w.attributes("-topmost", True)
        w.geometry(f"420x150+{w.winfo_screenwidth() - 440}+40")
        msg = (f"Meeting minutes ready:\n{minutes.name}" if ok else
               f"Minutes could not be written for {t.name}.\nAsk meeting-minutes-cn to \"summarize my notes\".")
        tk.Label(w, text=msg, fg=TEXT, bg=DARK, font=("Segoe UI", 12), justify="left").pack(padx=16, pady=(14, 4), anchor="w")
        row = tk.Frame(w, bg=DARK)
        row.pack(pady=12)
        if ok:
            tk.Button(row, text="Open", width=12, command=lambda: (os.startfile(minutes), w.destroy())).pack(side="left", padx=6)
        tk.Button(row, text="Close", width=12, command=w.destroy).pack(side="left", padx=6)
        w.after(10 * 60 * 1000, lambda: w.winfo_exists() and w.destroy())


class Watcher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.state = "idle"  # idle | asking | recording | declined | stopping
        self.app = self.out = self.proc = self.prompt = None
        self.free_since = None
        self.asked_at = self.stop_at = 0.0
        self.team = Team(self.root)
        log("watcher started")
        self.adopt()
        self.tick()

    def adopt(self):
        """After a watcher restart, keep managing a recording the previous watcher started."""
        try:
            out, pid = REC.read_text(encoding="utf-8").splitlines()[:2]
            pid = int(pid)
        except (OSError, ValueError):
            return
        if not pid_alive(pid):
            return

        class Proc:  # the poll()/kill() subset of Popen the state machine uses
            returncode = 0
            def poll(self):
                return None if pid_alive(pid) else 0
            def kill(self):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)

        self.out, self.proc, self.state, self.app = Path(out), Proc(), "recording", "The"
        log(f"took over running recording {Path(out).name} (pid {pid})")

    def ask(self, app):
        w = self.prompt = tk.Toplevel(self.root, bg="#161D26")
        w.title("Meeting notes")
        w.attributes("-topmost", True)
        w.geometry(f"420x170+{w.winfo_screenwidth() - 440}+40")
        tk.Label(w, text=f"{app} is using your microphone.\nRecord this call and take notes?",
                 fg="#FFFFFF", bg="#161D26", font=("Segoe UI", 12), justify="left").pack(padx=16, pady=(14, 4), anchor="w")
        tk.Label(w, text="Tell everyone on the call before you record.", fg="#C0C6CE", bg="#161D26",
                 font=("Segoe UI", 10)).pack(padx=16, anchor="w")
        row = tk.Frame(w, bg="#161D26")
        row.pack(pady=14)
        tk.Button(row, text="Record", width=12, command=lambda: self.answer(True)).pack(side="left", padx=6)
        tk.Button(row, text="Not now", width=12, command=lambda: self.answer(False)).pack(side="left", padx=6)
        w.protocol("WM_DELETE_WINDOW", lambda: self.answer(False))
        self.state, self.asked_at = "asking", time.time()
        log(f"{app} call detected, asking")

    def close_prompt(self):
        if self.prompt:
            self.prompt.destroy()
            self.prompt = None

    def answer(self, record):
        self.close_prompt()
        if record and not REC.exists():
            self.out, self.proc = start_recording()
            self.state = "recording"
        else:
            self.state = "declined"
            log("not recording this call")

    def finish(self):
        """Recorder has exited: clean the state files (as the recorder agent's STOP does).
        Deleting .recording hands the meeting to the Q&A tracker and minutes writer."""
        for f in (REC, STOP, NOTES / ".log.txt", NOTES / ".err.txt"):
            f.unlink(missing_ok=True)
        self.state, self.out, self.proc = "idle", None, None

    def tick(self):
        for part in (self.step, self.team.step):
            try:
                part()
            except Exception as e:  # never let one bad poll kill the watcher
                log(f"error in {part.__qualname__}: {e!r}")
        self.root.after(POLL_MS, self.tick)

    def step(self):
        app, now = call_app(), time.time()
        if app:
            self.app, self.free_since = app, None
        elif self.free_since is None:
            self.free_since = now
        call_over = not app and now - self.free_since >= END_GRACE

        if self.state == "idle":
            if app and not REC.exists():  # a recording started by hand is left alone
                self.ask(app)
        elif self.state == "asking":
            if call_over or now - self.asked_at > ASK_TIMEOUT:
                self.close_prompt()
                self.state = "declined" if not call_over else "idle"
                log("prompt closed without an answer, not recording")
        elif self.state == "declined":
            if call_over:
                self.state = "idle"
        elif self.state == "recording":
            if self.proc.poll() is not None:  # stopped by the agent ("stop") or crashed
                log(f"recorder exited on its own (code {self.proc.returncode})")
                if not REC.exists():  # the recorder agent's STOP already cleaned up
                    self.state, self.out, self.proc = "declined" if app else "idle", None, None
                else:
                    self.finish()
            elif call_over:
                log(f"{self.app} call ended, stopping")
                STOP.touch()
                self.state, self.stop_at = "stopping", now
        elif self.state == "stopping":
            if self.proc.poll() is not None:
                self.finish()
            elif now - self.stop_at > 90:
                self.proc.kill()
                log("recorder did not stop in 90 s, killed; the last seconds may be missing")
                self.finish()


if __name__ == "__main__":
    lock = NOTES / ".watcher"
    if lock.exists():
        try:
            if pid_alive(int(lock.read_text().strip())):
                sys.exit(0)  # already running
        except ValueError:
            pass
    lock.write_text(str(os.getpid()))
    try:
        Watcher().root.mainloop()
    finally:
        lock.unlink(missing_ok=True)
