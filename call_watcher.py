"""Background call watcher and meeting team coordinator.
1. When Teams, Zoom or Slack is in a call, it asks "Record this call?" and records (the
   meeting-recorder-cn job) only after you click Record. It stops when the call ends.
2. While any recording runs (started here or by the meeting-recorder-cn agent), it runs the
   meeting-qa-cn agent every minute and shows its <t>.qa.md in a "Live Q&A" window.
3. When the recording stops, it runs meeting-qa-cn's final pass, then meeting-minutes-cn,
   then pops a "Meeting minutes ready" notice.
Agents run headless through kiro-cli. Usage:  pythonw call_watcher.py  (Task Scheduler starts it at logon)
Logs: notes/.watcher.log.txt (watcher), notes/.team.log.txt (agent runs)
"""
import ctypes
import os
import subprocess
import sys
import time
import tkinter as tk
import winreg
from datetime import datetime
from pathlib import Path

TOOL = Path(__file__).resolve().parent
NOTES = TOOL / "notes"
REC, STOP = NOTES / ".recording", NOTES / ".stop"
AGENTS = Path.home() / ".kiro" / "agents"
QA_AGENT, MINUTES_AGENT = AGENTS / "meeting-qa-cn.md", AGENTS / "meeting-minutes-cn.md"
# ponytail: each kiro-cli run takes 40 to 60 s, so at 60 s the live passes run almost back to back
# and the window trails speech by 1 to 2 minutes. Only one agent runs at a time, so a final pass
# can wait up to a minute for a live pass to finish. Upgrade path: a faster model for UPDATE.
QA_EVERY = 60  # seconds between the starts of live Q&A passes
QA_FIRST = 60  # first live pass this long after recording starts
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
        p = subprocess.Popen(["kiro-cli", "chat", "--no-interactive", "--trust-tools=fs_read,fs_write,read,write",
                              prompt], cwd=NOTES, stdout=f, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    log(f"{agent.stem} {task} -> {t.name}")
    return p


DARK, TEXT, MUTED = "#161D26", "#FFFFFF", "#C0C6CE"


class Team:
    """Hands each recording from the recorder to the Q&A tracker, then to the minutes writer.
    Runs one agent at a time. Driven by the watcher's poll loop."""

    def __init__(self, root):
        self.root = root
        self.live = None  # transcript being recorded
        self.no_live = False
        self.done = []  # stopped recordings waiting for Q&A final + minutes
        self.job = self.job_kind = self.job_t = None
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

        if self.job and self.job.poll() is not None:
            kind, t, code = self.job_kind, self.job_t, self.job.returncode
            self.job = self.job_kind = None
            log(f"team: {kind} for {t.name} finished (code {code})")
            if kind == "final":
                self.job_kind, self.job_t = "minutes", t
                self.job = run_agent(MINUTES_AGENT, "MINUTES", t)
            elif kind == "minutes":
                self.notify(t)
        if self.job is None:
            if self.done:
                t = self.done.pop(0)
                if has_speech(t):
                    self.job_kind, self.job_t = "final", t
                    self.job = run_agent(QA_AGENT, "FINAL", t)
                else:
                    log(f"team: no speech in {t.name}, no Q&A or minutes")
                    self.close_window()
            elif self.live and not self.no_live and now - self.last_qa >= QA_EVERY:
                size = self.live.stat().st_size if self.live.exists() else 0
                self.last_qa = now
                if size != self.qa_size and has_speech(self.live):
                    self.qa_size = size
                    self.job_kind, self.job_t = "update", self.live
                    self.job = run_agent(QA_AGENT, "UPDATE", self.live)
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
            self.win_t, self.win_mtime = None, None
        qa = t.with_suffix(".qa.md")
        mtime = qa.stat().st_mtime if qa.exists() else None
        if (t, mtime) == (self.win_t, self.win_mtime):
            return
        self.win_t, self.win_mtime = t, mtime
        body = qa.read_text(encoding="utf-8") if qa.exists() else \
            "Questions and answers asked in this meeting appear here, updated about every minute."
        self.box.delete("1.0", "end")
        self.box.insert("1.0", body.replace("**", ""))

    def close_window(self):
        if self.win:
            self.win.destroy()
        self.win = self.box = None

    def notify(self, t: Path):
        self.close_window()
        ok = "## Structured Notes" in t.read_text(encoding="utf-8")
        log(f"team: minutes for {t.name} {'ready' if ok else 'MISSING, see .team.log.txt'}")
        w = tk.Toplevel(self.root, bg=DARK)
        w.title("Meeting minutes")
        w.attributes("-topmost", True)
        w.geometry(f"420x150+{w.winfo_screenwidth() - 440}+40")
        msg = (f"Meeting minutes ready:\n{t.name}" if ok else
               f"Minutes could not be written for {t.name}.\nAsk meeting-minutes-cn to \"summarize my notes\".")
        tk.Label(w, text=msg, fg=TEXT, bg=DARK, font=("Segoe UI", 12), justify="left").pack(padx=16, pady=(14, 4), anchor="w")
        row = tk.Frame(w, bg=DARK)
        row.pack(pady=12)
        if ok:
            tk.Button(row, text="Open", width=12, command=lambda: (os.startfile(t), w.destroy())).pack(side="left", padx=6)
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
