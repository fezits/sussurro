from unittest.mock import MagicMock

from meeting.ui.invisibility import set_window_invisible_to_capture


def test_invisibility_calls_set_display_affinity(monkeypatch):
    fake_user32 = MagicMock()
    fake_user32.SetWindowDisplayAffinity.return_value = 1
    monkeypatch.setattr(
        "meeting.ui.invisibility._user32",
        lambda: fake_user32,
    )
    ok = set_window_invisible_to_capture(hwnd=12345, enabled=True)
    assert ok is True
    fake_user32.SetWindowDisplayAffinity.assert_called_once()
    args = fake_user32.SetWindowDisplayAffinity.call_args.args
    assert args[0] == 12345


def test_invisibility_returns_false_on_failure(monkeypatch):
    fake_user32 = MagicMock()
    fake_user32.SetWindowDisplayAffinity.return_value = 0
    monkeypatch.setattr("meeting.ui.invisibility._user32", lambda: fake_user32)
    assert set_window_invisible_to_capture(hwnd=1, enabled=True) is False
