from __future__ import annotations

import sys
from pathlib import Path

from src.app import SussurroApp


def main() -> int:
    root = Path(__file__).resolve().parent
    config_path = root / "config.yaml"
    if not config_path.exists():
        print(f"config.yaml não encontrado em {config_path}", file=sys.stderr)
        return 2
    app = SussurroApp(config_path)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
