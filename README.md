# meeting-notes-takers-cn

A Kiro agent that listens to your microphone and your speakers, shows live captions, and writes structured meeting notes. Say "start" to begin and "stop" to finish.

You get a markdown file per meeting with the transcript, then a summary, topics, decisions, action items, and open questions. Transcription runs locally with Whisper, so audio never leaves your machine.

## Requirements

- Windows (speaker capture uses WASAPI loopback; on other systems it records the microphone only, and this is untested)
- Python 3.14 (the version this was tested on) with `pip`
- Kiro
- Internet on first run only, so Whisper can download its speech model (about 140 MB for `base`)
- Disk space for the Whisper install, which also installs PyTorch (a large download)

## Install

1. Copy these files into your Kiro workspace folder, keeping this layout:
   ```
   <your workspace>/
     .kiro/agents/meeting-notes-takers-cn.md
     mic_notes.py
     captions.py
     requirements.txt
   ```
2. In a terminal opened in that folder, run:
   ```
   pip install -r requirements.txt
   ```
3. Create your glossary (see below). This step is what makes the notes use your team's acronyms correctly.

## Create your glossary

The glossary ships empty because acronyms differ by team. Do this once, then keep adding terms as you go.

Open `.kiro/agents/meeting-notes-takers-cn.md` and find the section "Glossary (memory)". You can fill it in two ways:

- **Tell the agent in chat.** Say "ABC means Account Business Case" and the agent adds it to the `Known` table.
- **Edit the file.** Add a row to the `Known` table:

  | Acronym | Meaning | Often heard as | Notes |
  |---------|---------|----------------|-------|
  | ABC | Account Business Case | AVC, ABCD | Used by the sales team |

"Often heard as" lists the wrong words the speech model usually produces for that term. The agent uses it to correct the transcript.

After your first meeting, the agent lists acronyms it did not recognize and asks what they mean. Answer in chat and it updates the glossary for you.

## Use

1. Open a chat with the `meeting-notes-takers-cn` agent in Kiro.
2. Type `start`. The agent starts recording and opens a small caption window. The first caption takes 20 to 30 seconds while the speech model loads.
3. Type `stop` when the meeting ends. The agent finishes the last audio, then writes the structured notes at the end of the transcript file.

Files are saved to `notes/<date>_<time>.md`. To redo the summary later, say "summarize my notes".

Useful phrases:
- "start without captions" turns off the caption window and uses longer chunks for better accuracy.
- "start, language zh" sets the language. Use this for Mandarin meetings. Other language codes work too, for example `ja` or `en`.

## Options

You can also run the recorder by hand:

```
python mic_notes.py --model small --chunk 30 --language zh --out notes/my-meeting.md
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--model` | `base` | `tiny`, `base`, `small`, `medium`. Larger is more accurate and slower |
| `--chunk` | `30` | Seconds of audio per transcription |
| `--language` | auto | Language code. Setting it avoids wrong guesses on quiet moments |
| `--no-speaker` | off | Record the microphone only |
| `--out` | `notes/<timestamp>.md` | Output file |

Stop it with Ctrl+C, or by creating `notes/.stop`.

## What to know

- **Use a headset.** With open speakers, the microphone also hears the speakers and lines get duplicated.
- **Default device only.** Speaker capture uses whichever device is your Windows default output when you start. Switch devices before you start, not during the meeting.
- **Lines are tagged.** `[Me]` is your microphone. `[Them]` is the speaker output, such as the other side of a call. It does not identify individual speakers.
- **Captions lag.** They appear about 10 seconds behind speech, because audio is transcribed in chunks.
- **Accuracy varies.** Mixed languages and technical terms are the weakest area. Use `--language` and the `small` model for better results. A glossary helps with acronyms.
- **Screen sharing.** The caption window is visible if you share your whole screen.
- **Notes can hold sensitive content.** Do not commit or share the `notes/` folder. The `.gitignore` in this repo excludes it.

## Recording consent

This tool records other people's voices. Check your company's policy and get consent from participants before you record a meeting.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Speaker capture unavailable" in the log | The agent records the microphone only. Check that a default output device is set in Windows sound settings |
| Strange text in the wrong language | Set `--language` explicitly. Auto-detect can guess wrong on silence or noise |
| Recording will not stop | The agent waits 90 seconds, then ends the process. The last few seconds may be missing |
| No captions appear | Wait 30 seconds for the model to load. Check that `captions.py` is in the workspace root |
