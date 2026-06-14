from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE_ROOT = REPO_ROOT / "astrbot-local-plugins" / "meme_manager"
DEFAULT_SOURCE_INDEX = REPO_ROOT / "data" / "memes" / "mlj_pack" / "index.json"


def main() -> int:
    if str(PLUGIN_SOURCE_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_SOURCE_ROOT.parent))

    from meme_manager.local_index import migrate_mlj_pack_index

    source_index = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE_INDEX
    result = migrate_mlj_pack_index(source_index)
    print(f"source_index={source_index}")
    print(f"copied={result['copied']}")
    print(f"updated={result['updated']}")
    print(f"skipped_missing={result['skipped_missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
