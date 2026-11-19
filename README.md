# Meeting notes team (Supporting Slack, Zoom and Team)

Three Kiro agents that work as a team on each meeting. One records and shows live captions, one picks up the questions asked and the answers given, and one writes the meeting minutes once recording stops. Transcription runs locally with Whisper, so audio never leaves your machine.

You get three files per meeting in `notes/`:

| File | Contents |
|------|----------|
| `<date>_<time>.md` | The transcript only, as spoken |
| `<date>_<time>.qa.md` | Questions asked and the answers given |
| `<date>_<time>.minutes.md` | The minutes: summary, topics, decisions, action items, questions and answers, open questions |

The fallback agent (below) follows the same rule: its notes go to `<date>_<time>.minutes.md`, and the transcript stays as spoken.

## The team

| Agent | Job | When it works | Writes |
|-------|-----|---------------|--------|
| `meeting-recorder-cn` | Records the microphone and speaker. Shows the caption window | You say `start`, or you click **Record** on a call notice | `notes/<date>_<time>.md` (transcript) |
| `meeting-qa-cn` | Picks up every question and its answer. Shows the "Live Q&A" window | Continuously while recording (a pass about every 40 seconds), then one final pass when recording stops | `notes/<date>_<time>.qa.md` |
| `meeting-minutes-cn` | Writes the minutes. Keeps the acronym glossary | After the Q&A final pass | `notes/<date>_<time>.minutes.md` |

The agents never call each other. They share files in the `notes/` folder, and `call_watcher.py` hands the work from one to the next:

1. The recorder writes the transcript and creates `notes/.recording` while it runs.
2. While `.recording` exists, the watcher runs the Q&A agent through `kiro-cli` again and again, starting a new pass as soon as the last one finishes and the transcript has new lines, and shows its `.qa.md` in the "Live Q&A" window (right side of the screen).
3. When the recording stops, `.recording` is deleted. The watcher runs the Q&A final pass, then the minutes agent.
4. A "Meeting minutes ready" notice pops up with an **Open** button that opens the `.minutes.md` file. This comes about 1 to 2 minutes after the meeting ends.

Each agent does only its own job. Ask the recorder for minutes and it points you to `meeting-minutes-cn`.

### Fallback agent

`meeting-notes-takers-cn` is the earlier single agent that does everything in one chat: recording, captions, a keyword-based "Live items" window (`live_items.py`), and the notes at stop. Use it when the team is not available, for example when `call_watcher.py` is not running or `kiro-cli` is not signed in. A recording it starts is marked `fallback` in `notes/.recording`, so the team leaves that meeting alone and the minutes are not written twice. Its glossary is separate from the team's.

## Requirements

- Windows (speaker capture uses WASAPI loopback; on other systems it records the microphone only, and this is untested)
- Python 3.14 (the version this was tested on) with `pip`
- Kiro, and `kiro-cli` signed in (the watcher runs the Q&A and minutes agents through it)
- Internet on first run only, so faster-whisper can download its speech model (about 140 MB for `base`)

## Install

1. Put the tool files in one folder. This setup uses `C:\Users\stevekxs\Documents\Meeting Notes`:
   ```
   Meeting Notes/
     mic_notes.py        recorder
     captions.py         caption window
     call_watcher.py     call notices and team hand-off
     live_items.py       fallback agent only
     requirements.txt
   ```
2. Put the agent files in your user agents folder, `%USERPROFILE%\.kiro\agents\`, so they work from any workspace. Copies are in this repo's `.kiro/agents/`:
   ```
   meeting-recorder-cn.md
   meeting-qa-cn.md
   meeting-minutes-cn.md
   meeting-notes-takers-cn.md   (fallback)
   meeting-team-runner.json     (lean runner the watcher uses for fast Q&A and minutes passes)
   ```
   The agent files use absolute paths. If your tool folder is somewhere else, change the paths at the top of each file.
3. In a terminal opened in the tool folder, run:
   ```
   pip install -r requirements.txt
   ```
4. Start the watcher at every logon:
   ```powershell
   $T = "C:\Users\stevekxs\Documents\Meeting Notes"
   $a = New-ScheduledTaskAction -Execute (Get-Command pythonw).Source -Argument "`"$T\call_watcher.py`"" -WorkingDirectory $T
   $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
   Register-ScheduledTask -TaskName MeetingNotesCallWatcher -Action $a -Trigger (New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME") -Settings $s
   Start-ScheduledTask MeetingNotesCallWatcher
   ```
5. Create your glossary (see below). This is what makes the minutes use your team's acronyms correctly.

## Create your glossary

The glossary lives in `meeting-minutes-cn.md`, in the section "Glossary (memory)". The Q&A agent reads it too. It ships empty because acronyms differ by team. You can fill it in two ways:

- **Tell the minutes agent in chat.** Say "ABC means Account Business Case" to `meeting-minutes-cn` and it adds it to the `Known` table.
- **Edit the file.** Add a row to the `Known` table:

  | Acronym | Meaning | Often heard as | Notes |
  |---------|---------|----------------|-------|
  | ABC | Account Business Case | AVC, ABCD | Used by the sales team |

"Often heard as" lists the wrong words the speech model usually produces for that term. The agents use it to correct the transcript.

After each meeting, the minutes agent adds acronyms it did not recognize to the "To confirm" table. Tell it what they mean and it moves them to `Known`.

## Use

### Calls on Teams, Zoom and Slack (automatic)

1. Join the call. A "Record this call?" notice appears in the top-right corner.
2. Tell everyone on the call, then click **Record**. "Not now", closing the notice, or no answer within 2 minutes means that call is not recorded.
3. The caption window opens. About a minute after the first words, the "Live Q&A" window opens.
4. Hang up. The recording stops 15 seconds after the call ends. The "Meeting minutes ready" notice follows.

How calls are detected:
- Teams and Slack: when the app starts using your microphone. That happens when the call connects, not while it rings. Test calls also trigger it.
- Zoom: when the Zoom meeting window is open. Zoom Workplace does not always tell Windows it is using the microphone.
- If a recording is already running, it does not ask.

### Any other meeting (by chat)

1. Open a chat with `meeting-recorder-cn` and type `start`. The first caption takes 20 to 30 seconds while the speech model loads.
2. Type `stop` when the meeting ends. The Q&A and minutes agents take over on their own.

### Chat with the team

| Ask | Agent | Example |
|-----|-------|---------|
| Start or stop recording | `meeting-recorder-cn` | `start`, `start language zh`, `start without captions`, `start, no live Q&A`, `stop` |
| Questions so far | `meeting-qa-cn` | `questions so far`, `show Q&A` |
| Minutes again | `meeting-minutes-cn` | `summarize my notes`, `summarize 2026-11-17_1132.md` |
| Teach an acronym | `meeting-minutes-cn` | `SPO means Sales Planning Office` |

- `start language zh` sets the language. Without it, the recorder detects the language itself. Other codes work too, for example `ja` or `en`.
- `start without captions` turns off the caption window and uses longer phrases for better accuracy.
- `start, no live Q&A` skips the live Q&A passes. The Q&A agent then runs once, after the meeting.

## Options

You can also run the recorder by hand:

```
python mic_notes.py --model base --out notes/my-meeting.md
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--model` | `base` | `tiny`, `base`, `small`, `medium`. Larger is more accurate and slower |
| `--chunk` | `6` | Maximum seconds of continuous speech per transcription |
| `--pause` | `0.4` | Seconds of quiet that end a phrase. A phrase is transcribed as soon as it ends |
| `--language` | auto | Language code. Setting it avoids wrong guesses on quiet moments |
| `--no-speaker` | off | Record the microphone only |
| `--save-audio` | off | Also save the audio as WAV files in `notes/audio/` |
| `--out` | `notes/<timestamp>.md` | Output file |

Stop it with Ctrl+C, or by creating `notes/.stop`.

## What to know

- **Use a headset.** With open speakers, the microphone also hears the speakers and lines get duplicated.
- **Default device only.** Speaker capture uses whichever device is your Windows default output when recording starts. If the call plays through a different device, the other side is not recorded. Set the device first.
- **Lines are tagged.** `[Me]` is your microphone. `[Them]` is the speaker output, such as the other side of a call. It does not identify individual speakers.
- **Captions lag a little.** Each phrase is transcribed when the speaker pauses, so captions appear about 3 to 6 seconds after a phrase starts.
- **Live Q&A has two speeds.** New questions show within about 5 seconds under "Possible questions (spotted just now, not checked yet)". These come from keyword spotting (English and Mandarin, from `live_items.py`), so expect some misses and some chatter. The agent's pass then checks them, drops false ones, and adds the answers. Run `python test_live_qa.py` to check the window logic. Each Q&A pass runs a Kiro agent and takes about 35 to 50 seconds, so a question shows up about 40 to 90 seconds after it is asked. The watcher runs these passes with `meeting-team-runner` (no MCP servers, file tools only), which skips loading your MCP servers. If that fails, it falls back to the default `kiro-cli` setup on its own. A run that has not finished after 2.5 minutes (5 for the final pass and minutes) is stopped, so one stuck run cannot block the rest.
- **Accuracy varies.** Mixed languages and technical terms are the weakest area. Use `language zh` (or another code) for better results. The `small` model is more accurate but takes about 5 seconds per phrase on a typical laptop CPU, too slow for live captions. A glossary helps with acronyms.
- **Screen sharing.** The caption, Live Q&A and notice windows are visible if you share your whole screen.
- **Agent permissions.** The watcher runs the Q&A and minutes agents with file read and write access only, no shell commands. Their file writes are not limited to the `notes/` folder.
- **Notes can hold sensitive content.** Do not commit or share the `notes/` folder. The `.gitignore` in this repo excludes it.

## Recording consent

This tool records other people's voices. Check your company's policy and get consent from participants before you record a meeting. The call notice reminds you, and nothing is recorded until you click **Record**.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No "Record this call?" notice | Check the watcher is running: `Get-ScheduledTask MeetingNotesCallWatcher`. Then read `notes/.watcher.log.txt` |
| No Live Q&A window, or no minutes | Read `notes/.team.log.txt` for the agent output. Check `kiro-cli` is signed in. To redo the minutes, ask `meeting-minutes-cn` to "summarize my notes" |
| "Speaker capture unavailable" in the log | Only the microphone is recorded. Check that a default output device is set in Windows sound settings |
| Strange text in the wrong language | Start with `start language <code>`. Auto-detect can guess wrong on silence or noise |
| Recording will not stop | The recorder agent and the watcher wait 90 seconds, then end the process. The last few seconds may be missing |
| No captions appear | Wait 30 seconds for the model to load. Check that `captions.py` is in the tool folder |
| Turn the watcher off | `Unregister-ScheduledTask MeetingNotesCallWatcher`, then end the `pythonw` process |
