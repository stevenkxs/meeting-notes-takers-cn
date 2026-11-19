"""Self-check for the Live Q&A window text in call_watcher.py. Run: python test_live_qa.py"""
from call_watcher import live_qa_text

transcript = """# Meeting notes
- **10:00:02** [Them] Can you hear me okay?
- **10:00:10** [Them] When is the launch date?
- **10:00:16** [Me] December 3rd.
- **10:01:05** [Them] 这个预算批下来了吗？
- **10:01:20** [Them] Who owns the vendor review?
"""
qa = """# Questions and answers: m.md
Status: live. Covers transcript up to 10:00:16.

## Answered
- **10:00:10 [Them]** When is the launch date?
  - **Answer (10:00:16 [Me]):** December 3rd.
"""
body = live_qa_text(transcript, qa)
assert "When is the launch date?" in body and "**" not in body
pending = body.split("Possible questions")[1]
assert "预算" in pending and "vendor review" in pending, pending  # new lines, spotted at once
assert "launch date" not in pending  # already checked by the agent
assert "hear me" not in pending  # a request/check, not a question
assert "Possible questions" not in live_qa_text(transcript[:transcript.index("- **10:01")], qa)
assert "Possible questions" in live_qa_text(transcript, "")  # before the first agent pass
print("ok")
