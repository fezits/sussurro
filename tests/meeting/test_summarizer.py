from datetime import datetime

from meeting.intelligence.summarizer import Summarizer
from meeting.transcribe.turn import Speaker, Turn


class _StubLlm:
    def complete(self, messages):
        return "## Tópicos\n- A\n## Action items\n- foo"


def test_summarizer_returns_markdown():
    s = Summarizer(llm=_StubLlm(), model="x")
    turns = [Turn(Speaker.THEM, 0, 1, "ola", datetime.now()),
             Turn(Speaker.YOU, 1, 2, "oi", datetime.now())]
    md = s.summarize(turns)
    assert "Tópicos" in md
    assert "Action items" in md
