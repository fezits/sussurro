from __future__ import annotations

import sys
import traceback
from pathlib import Path

from src import logger as sussurro_logger

log = sussurro_logger.setup()


def main() -> int:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent

    # When frozen, PyInstaller may bundle config.yaml inside _internal/.
    candidates = [
        root / "config.yaml",
        root / "_internal" / "config.yaml",
    ]
    config_path = next((p for p in candidates if p.exists()), candidates[0])
    log.info("Starting Sussurro · root=%s · config=%s", root, config_path)
    if not config_path.exists():
        log.error("config.yaml não encontrado em nenhum de: %s", candidates)
        print(f"config.yaml não encontrado em {candidates}", file=sys.stderr)
        return 2
    try:
        from src.app import SussurroApp
        app = SussurroApp(config_path)
        return app.run()
    except Exception:
        log.exception("Fatal error in main()")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
