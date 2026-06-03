from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.mirai_data_migration import run_mirai_data_migration


def main() -> int:
    parser = argparse.ArgumentParser(description="Import selected mirai data into the current qqbot run directory.")
    parser.add_argument("--legacy-run", required=True, help="Legacy mirai run directory")
    parser.add_argument("--data-root", required=True, help="Current qqbot run directory")
    args = parser.parse_args()

    summary = run_mirai_data_migration(
        legacy_run=Path(args.legacy_run),
        data_root=Path(args.data_root),
    )
    for key, value in summary.items():
        print(f"{key}={value}")
    print(f"target_root={Path(args.data_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
