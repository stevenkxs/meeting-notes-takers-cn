# meeting-notes-takers-cn

A Kiro agent that listens to your microphone and your speakers, shows live captions, and writes structured meeting notes. Say "start" to begin and "stop" to finish.

You get a markdown file per meeting with the transcript, then a summary, topics, decisions, action items, and open questions. Transcription runs locally with Whisper, so audio never leaves your machine.

At "stop" the agent can produce two versions of the notes: version A from the fast live transcript, and version B from a slower, more accurate transcript made by a larger model (the turbo pass). See "Turbo pass" below.

## Requirements

- Windows (speaker capture uses WASAPI loopback; on other systems it records the microphone only, and this is untested)
- Python 3.14 (the version this was tested on) with `pip`
- Kiro
- Internet on first run only, so Whisper can download its speech model (about 140 MB for `base`)
- Disk space for the Whisper install, which also installs PyTorch (a large download)
- Optional, for the turbo pass: a whisper.cpp model file (about 550 MB), see "Turbo pass"

## Install

1. Copy these files into your Kiro workspace folder, keeping this layout:
   ```
   <your workspace>/
     .kiro/agents/meeting-notes-takers-cn.md
     mic_notes.py
     captions.py
     cleanup_turbo.py
     requirements.txt
   ```
2. In a terminal opened in that folder, run:
   ```
   pip install -r requirements.txt
   ```
3. Create your glossary (see below). This step is what makes the notes use your team's acronyms correctly.
4. Optional: set up the turbo pass (see below). Without it, the agent still works and gives you version A only.

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
3. Type `stop` when the meeting ends. The agent finishes the last audio, then writes the structured notes (version A) at the end of the transcript file. If the turbo pass is set up, it then waits for the turbo transcript and writes version B (see below).

Files are saved to `notes/<date>_<time>.md`. To redo the summary later, say "summarize my notes".

Useful phrases:
- "start without captions" turns off the caption window and uses longer chunks for better accuracy.
- "start, language zh" sets the language. Use this for Mandarin meetings. Other language codes work too, for example `ja` or `en`.
- "start without turbo" skips saving audio, so there is no turbo pass for that meeting.
- "summarize the turbo notes" writes version B for a finished turbo transcript.

## Turbo pass (optional)

The live transcript uses the small, fast `base` model, so captions keep up with speech. A larger model is much more accurate but slower than real time on a laptop CPU. The turbo pass runs the larger model on the saved audio after the meeting.

What you get:
- `notes/<name>.md`: live transcript and summary A.
- `notes/<name>_turbo.md`: turbo transcript and summary B.

How it works:
1. While recording, the audio is also saved to `notes/audio/`.
2. At "stop", the agent starts `cleanup_turbo.py` in the background and writes summary A.
3. The agent waits for the turbo transcript, writes summary B, and lists where the two versions differ. If you interrupt it, nothing is lost. It writes summary B the next time you send it any command.
4. When the pass succeeds, the saved audio is deleted. Run `cleanup_turbo.py` by hand with `--keep-audio` to keep it.

Setup:
1. `pip install -r requirements.txt` already installs `pywhispercpp`.
2. Download a whisper.cpp model file from the whisper.cpp project (see https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md). It was tested with `ggml-large-v3-turbo-q5_0.bin`, about 550 MB.
3. Tell the script where it is, by either:
   - setting the `TURBO_MODEL` environment variable to the full path of the file, or
   - passing `--model <path>` when you run `cleanup_turbo.py` by hand.
   
   If you use the Meetily app, the script also looks for the model in Meetily's models folder.

Expect it to be slow. On a laptop with no dedicated GPU, a 30-second window of audio took about 40 seconds. A one-hour meeting can take well over an hour, and the laptop will be busy while it runs. Do not start another recording during the pass, because the live transcription would fall behind.

Run it by hand:

```
python cleanup_turbo.py notes/<name>.md [--model <path>] [--language zh] [--keep-audio]
```

## Options

You can also run the recorder by hand:

```
python mic_notes.py --model small --chunk 30 --language zh --save-audio --out notes/my-meeting.md
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--model` | `base` | `tiny`, `base`, `small`, `medium`. Larger is more accurate and slower |
| `--chunk` | `30` | Seconds of audio per transcription |
| `--language` | auto | Language code. Setting it avoids wrong guesses on quiet moments |
| `--no-speaker` | off | Record the microphone only |
| `--save-audio` | off | Also save the audio to `notes/audio/` for the turbo pass |
| `--out` | `notes/<timestamp>.md` | Output file |

Stop it with Ctrl+C, or by creating `notes/.stop`.

## What to know

- **Use a headset.** With open speakers, the microphone also hears the speakers and lines get duplicated.
- **Default device only.** Speaker capture uses whichever device is your Windows default output when you start. Switch devices before you start, not during the meeting.
- **Lines are tagged.** `[Me]` is your microphone. `[Them]` is the speaker output, such as the other side of a call. It does not identify individual speakers.
- **Captions lag.** They appear about 10 seconds behind speech, because audio is transcribed in chunks.
- **Accuracy varies.** Mixed languages and technical terms are the weakest area. Use `--language` and the `small` model for better results. A glossary helps with acronyms.
- **Room noise can create junk lines.** Whisper sometimes writes short phrases such as "Thank you." for background noise. Both the live and turbo transcripts can do this.
- **Screen sharing.** The caption window is visible if you share your whole screen.
- **Notes and audio can hold sensitive content.** Do not commit or share the `notes/` folder. The `.gitignore` in this repo excludes it, including the saved audio.

## Recording consent

This tool records other people's voices. Check your company's policy and get consent from participants before you record a meeting. The turbo pass stores the raw audio on disk until it finishes, so treat that folder as sensitive.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Speaker capture unavailable" in the log | The agent records the microphone only. Check that a default output device is set in Windows sound settings |
| Strange text in the wrong language | Set `--language` explicitly. Auto-detect can guess wrong on silence or noise |
| Recording will not stop | The agent waits 90 seconds, then ends the process. The last few seconds may be missing |
| No captions appear | Wait 30 seconds for the model to load. Check that `captions.py` is in the workspace root |
| "Model not found" from the turbo pass | Set `TURBO_MODEL` to the model file's full path, or pass `--model`. The agent then gives you version A only and keeps the audio |
| "No saved audio" from the turbo pass | The recording was made without `--save-audio`, or you said "start without turbo". There is nothing to re-transcribe |
