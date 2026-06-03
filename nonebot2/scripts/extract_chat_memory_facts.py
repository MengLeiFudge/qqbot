from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.config import load_settings
from qqbot.services.chat_memory_store import ChatMemoryStore


def main() -> int:
    settings = load_settings()
    store = ChatMemoryStore(settings.data_root)
    group_ids = store.list_group_ids()
    inserted = 0
    for group_id in group_ids:
        inserted += store.extract_facts_from_recent_messages(group_id, limit=5000)
    print(f"已从 {len(group_ids)} 个群的长期原文记忆中抽取 {inserted} 条事实记忆。")
    print("重复运行会按 group_id + subject + predicate + object 去重。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
