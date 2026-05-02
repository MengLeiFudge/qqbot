from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.kun_service import KunService


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy mirai kun data into aggregated JSON storage.")
    parser.add_argument("--legacy-root", required=True, help="Legacy mirai kun root, e.g. .../run/data/kun")
    parser.add_argument("--data-root", required=True, help="Target qqbot data root, e.g. .../run")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    service = KunService(data_root / "data" / "kun" / "users.json")
    imported = service.migrate_legacy_data(Path(args.legacy_root))
    print(f"imported_users={imported}")
    print(f"users_file={service.file_path}")
    print(f"boss_file={service.boss_file_path}")
    print(f"now_season_file={service.now_season_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
