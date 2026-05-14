"""Run after `pyinstaller Sussurro.spec` to copy user-writable assets
into dist/Sussurro/ so the exe runs out of the box.

What this copies:
- config.yaml (next to exe so main.py picks it up)
- models/ (Whisper model — too big for the spec datas)

What it does NOT copy:
- knowledge/ — created automatically by the app on first meeting start
- reunioes/ — created automatically when stopping a meeting
"""
from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Sussurro"


def copy_dir(src: Path, dst: Path) -> None:
    if not src.exists():
        print(f"  SKIP {src.name} (source missing)")
        return
    if dst.exists():
        print(f"  SKIP {dst.name} (already present)")
        return
    print(f"  COPY {src} -> {dst}")
    shutil.copytree(src, dst)


def copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        print(f"  SKIP {src.name} (source missing)")
        return
    if dst.exists():
        print(f"  SKIP {dst.name} (already present)")
        return
    print(f"  COPY {src} -> {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if not DIST.exists():
        raise SystemExit(f"dist/Sussurro not found at {DIST}. Run PyInstaller first.")

    print(f"Finalizing {DIST}")
    copy_file(ROOT / "config.yaml", DIST / "config.yaml")
    copy_dir(ROOT / "models", DIST / "models")
    print("Done.")


if __name__ == "__main__":
    main()
