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
    imported = store.backfill_from_group_logs()
    print(f"已从管理端群消息日志回填 {imported} 条聊天记忆。")
    print("重复运行会按 group_id + direction + message_id 去重，不会重复导入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
