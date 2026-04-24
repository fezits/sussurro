from __future__ import annotations

import threading
from typing import Callable

import keyboard


class PressToTalk:
    """Press-and-hold hotkey. Fires on_press when ALL keys go down,
    on_release when any one goes up (after having been pressed).

    ``keyboard.add_hotkey`` only fires on down events, so we poll state
    on every relevant key event to detect release reliably.
    """

    def __init__(
        self,
        combo: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self.keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
        self.keys = ["windows" if k in ("win", "windows", "super", "meta") else k for k in self.keys]
        self.on_press = on_press
        self.on_release = on_release
        self._active = False
        self._lock = threading.Lock()
        self._hooks: list = []

    def _all_down(self) -> bool:
        return all(keyboard.is_pressed(k) for k in self.keys)

    def _any_of_combo(self, name: str) -> bool:
        n = name.lower()
        if n in self.keys:
            return True
        if n in ("left ctrl", "right ctrl") and "ctrl" in self.keys:
            return True
        if n in ("left windows", "right windows") and "windows" in self.keys:
            return True
        if n in ("left shift", "right shift") and "shift" in self.keys:
            return True
        if n in ("left alt", "right alt") and "alt" in self.keys:
            return True
        return False

    def _handle(self, event) -> None:
        if not self._any_of_combo(event.name or ""):
            return
        with self._lock:
            if event.event_type == "down" and not self._active and self._all_down():
                self._active = True
                try:
                    self.on_press()
                except Exception:
                    pass
            elif event.event_type == "up" and self._active:
                self._active = False
                try:
                    self.on_release()
                except Exception:
                    pass

    def start(self) -> None:
        self._hooks.append(keyboard.hook(self._handle))

    def stop(self) -> None:
        for h in self._hooks:
            try:
                keyboard.unhook(h)
            except Exception:
                pass
        self._hooks.clear()
