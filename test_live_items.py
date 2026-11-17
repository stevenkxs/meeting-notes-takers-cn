"""Self-check for live_items.py. Run: python test_live_items.py"""
from live_items import classify, extract

assert classify("I'll send the deck by Friday") == "action"
assert classify("Can you share the forecast?") == "action"  # request phrased as a question
assert classify("我来跟进这个问题") == "action"
assert classify("What is the budget for Q3?") == "question"
assert classify("这个上线时间定了吗") == "question"
assert classify("The weather is nice today.") is None

t = """# Meeting notes
- **10:00:01** [Them] What is the launch date?
- **10:00:03** [Me] What is the launch date?
- **10:00:09** [Me] I'll check with the vendor tomorrow.
- **Topic name** (10:00): not a transcript line, ignored
"""
actions, questions = extract(t)
assert actions == ["10:00:09 [Me] I'll check with the vendor tomorrow."], actions
assert questions == ["10:00:01 [Them] What is the launch date?"], questions  # echo dropped
print("ok")
