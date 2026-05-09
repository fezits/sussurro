from __future__ import annotations

import ctypes


WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Windows 10 2004+


def _user32():
    return ctypes.windll.user32  # type: ignore[attr-defined]


def set_window_invisible_to_capture(hwnd: int, enabled: bool) -> bool:
    """Apply or remove the WDA_EXCLUDEFROMCAPTURE flag on a window handle.

    Returns True on success, False if the API call failed (older Windows or
    unprivileged process).
    """
    flag = WDA_EXCLUDEFROMCAPTURE if enabled else WDA_NONE
    try:
        result = _user32().SetWindowDisplayAffinity(int(hwnd), flag)
    except Exception:
        return False
    return bool(result)
