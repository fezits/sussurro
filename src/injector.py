from __future__ import annotations

import time

import keyboard
import pyperclip


def paste_text(text: str, *, restore_clipboard: bool = True, trailing_space: bool = True) -> None:
    """Inject text into the currently focused field via clipboard + Ctrl+V.

    Pastes via clipboard so Unicode (accents, punctuation) survives intact,
    which is not guaranteed by simulated keystrokes on Windows.
    """
    if not text:
        return
    payload = text + (" " if trailing_space else "")

    previous: str | None = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None

    pyperclip.copy(payload)
    time.sleep(0.03)

    for mod in ("ctrl", "shift", "alt", "windows", "left windows", "right windows"):
        try:
            keyboard.release(mod)
        except Exception:
            pass

    keyboard.send("ctrl+v")

    if restore_clipboard and previous is not None:
        def _restore() -> None:
            time.sleep(0.25)
            try:
                pyperclip.copy(previous)
            except Exception:
                pass

        import threading
        threading.Thread(target=_restore, daemon=True).start()
