from datetime import datetime
from pathlib import Path

from meeting.persistence.session_writer import SessionWriter
from meeting.state import SessionId
from meeting.transcribe.turn import Speaker, Turn


def test_writer_creates_session_dir_and_appends(tmp_path: Path):
    sid = SessionId.now(datetime(2026, 4, 28, 14, 30))
    sw = SessionWriter(root=tmp_path, session_id=sid)
    sw.start()

    sw.append_turn(Turn(Speaker.THEM, 0.0, 1.5, "ola", datetime(2026, 4, 28, 14, 30, 1)))
    sw.append_turn(Turn(Speaker.YOU, 1.5, 3.0, "oi tudo bem", datetime(2026, 4, 28, 14, 30, 2)))
    sw.flush_now()

    out = (tmp_path / "2026-04-28_14-30" / "transcript.txt").read_text(encoding="utf-8")
    assert "[Eles]" in out and "ola" in out
    assert "[Você]" in out and "oi tudo bem" in out


def test_writer_finalize_writes_summary(tmp_path: Path):
    sid = SessionId.now(datetime(2026, 4, 28, 14, 30))
    sw = SessionWriter(root=tmp_path, session_id=sid)
    sw.start()
    sw.append_turn(Turn(Speaker.THEM, 0, 1, "tema", datetime(2026, 4, 28, 14, 30, 1)))
    sw.finalize(summary="Reunião sobre tema X.")

    summary = (tmp_path / "2026-04-28_14-30" / "sumario.md").read_text(encoding="utf-8")
    assert "Reunião sobre tema X." in summary
