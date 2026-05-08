from datetime import datetime
from meeting.transcribe.turn import Turn, Speaker
from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.state import MeetingState, SessionId


def test_turn_to_line_formats_with_timestamp():
    t = Turn(
        speaker=Speaker.YOU,
        start=12.0,
        end=15.0,
        text="ola pessoal",
        wall_clock=datetime(2026, 4, 28, 14, 32, 1),
    )
    assert t.to_line() == "14:32:01 [Você]   ola pessoal"


def test_turn_to_line_them_speaker_aligns():
    t = Turn(
        speaker=Speaker.THEM,
        start=0.0,
        end=2.0,
        text="oi",
        wall_clock=datetime(2026, 4, 28, 14, 32, 1),
    )
    assert "[Eles]" in t.to_line()


def test_suggestion_has_kind_and_text():
    s = Suggestion(kind=SuggestionKind.PERSONAL, text="abc", source_turn_id="t1")
    assert s.kind is SuggestionKind.PERSONAL
    assert s.text == "abc"


def test_session_id_is_filesystem_safe():
    sid = SessionId.now(datetime(2026, 4, 28, 14, 32))
    assert sid.value == "2026-04-28_14-32"


def test_meeting_state_transitions():
    ms = MeetingState.IDLE
    assert ms is not MeetingState.RECORDING
    assert MeetingState("recording") is MeetingState.RECORDING
