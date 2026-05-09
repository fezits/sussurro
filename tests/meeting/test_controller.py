from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from meeting.controller import MeetingController, MeetingDeps
from meeting.intelligence.types import Suggestion, SuggestionKind
from meeting.state import MeetingState
from meeting.transcribe.turn import Speaker, Turn


def _make_deps(tmp_path: Path) -> MeetingDeps:
    return MeetingDeps(
        mic_capture=MagicMock(),
        system_capture=MagicMock(),
        pipeline=MagicMock(),
        responder=MagicMock(),
        summarizer=MagicMock(),
        session_writer_factory=MagicMock(),
        live_window=MagicMock(),
        question_detector=MagicMock(),
        config={"intelligence": {"context_window_minutes": 2, "suggestion_ttl_seconds": 90,
                                  "auto_suggest": True, "question_detection": True},
                "storage": {"output_dir": str(tmp_path)}},
    )


def test_controller_starts_pipeline_and_changes_state(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    c = MeetingController(deps)

    c.start()
    deps.pipeline.on_turn = c._on_turn

    assert c.state is MeetingState.RECORDING
    deps.mic_capture.open.assert_called_once()
    deps.system_capture.open.assert_called_once()
    deps.pipeline.start.assert_called_once()
    sw.start.assert_called_once()


def test_controller_routes_turn_to_writer_window_and_questiondet(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.question_detector.is_question.return_value = False
    c = MeetingController(deps)
    c.start()
    deps.pipeline.on_turn = c._on_turn

    turn = Turn(Speaker.THEM, 0, 1, "ola", datetime.now())
    c._on_turn(turn)

    sw.append_turn.assert_called_once_with(turn)
    deps.live_window.append_turn.assert_called_once_with(turn)
    deps.question_detector.is_question.assert_called_once()


def test_controller_emits_suggestion_when_question(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.question_detector.is_question.return_value = True
    deps.responder.respond.return_value = Suggestion(SuggestionKind.PERSONAL, "ans", "t1")
    c = MeetingController(deps)
    c.start()
    deps.pipeline.on_turn = c._on_turn
    turn = Turn(Speaker.THEM, 0, 1, "qual sua experiência?", datetime.now())
    c._on_turn(turn)

    # _respond_async runs in a thread — wait briefly for it
    import time
    deadline = time.time() + 2
    while not deps.responder.respond.called and time.time() < deadline:
        time.sleep(0.05)

    deps.responder.respond.assert_called_once()
    deadline = time.time() + 2
    while not deps.live_window.show_suggestion.called and time.time() < deadline:
        time.sleep(0.05)
    deps.live_window.show_suggestion.assert_called_once()


def test_controller_stop_finalizes_writer_and_summary(tmp_path):
    deps = _make_deps(tmp_path)
    sw = MagicMock()
    deps.session_writer_factory.return_value = sw
    deps.summarizer.summarize.return_value = "## Resumo"
    c = MeetingController(deps)
    c.start()
    deps.pipeline.on_turn = c._on_turn
    c._on_turn(Turn(Speaker.YOU, 0, 1, "oi", datetime.now()))
    c.stop()

    deps.pipeline.stop.assert_called_once()
    deps.mic_capture.close.assert_called_once()
    deps.system_capture.close.assert_called_once()
    deps.summarizer.summarize.assert_called_once()
    sw.finalize.assert_called_once_with(summary="## Resumo")
    assert c.state is MeetingState.STOPPED
