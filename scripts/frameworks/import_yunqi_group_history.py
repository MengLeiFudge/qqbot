from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import json
import sqlite3
import sys
import tomllib

from deploy_plugins import WORKSPACE, load_deployment


PLATFORM = "qq"
TARGET = "yunqi"
RUNTIME = WORKSPACE / "maibot-yunqi"
ASTRBOT_DATA = WORKSPACE / "astrbot/data"


def read_group_history():
    config = json.loads((ASTRBOT_DATA / "cmd_config.json").read_text(encoding="utf-8-sig"))
    platforms = [str(item["id"]) for item in config["platform"] if item.get("enable") and item.get("type") == "aiocqhttp"]
    if len(platforms) != 1:
        raise ValueError("需要确认云栖 AstrBot 的唯一 OneBot 平台 ID。")
    prefix = platforms[0] + ":GroupMessage:"
    source = (ASTRBOT_DATA / "data_v4.db").as_uri() + "?mode=ro"
    groups = defaultdict(list)
    with closing(sqlite3.connect(source, uri=True, timeout=3)) as database:
        database.execute("PRAGMA query_only = ON")
        for row_id, origin, sender, name, created_at, content in database.execute(
            """SELECT id, user_id, sender_id, sender_name, created_at, content
               FROM platform_message_history
               WHERE platform_id = ? AND substr(user_id, 1, ?) = ?
               ORDER BY created_at, id""",
            (platforms[0], len(prefix), prefix),
        ):
            group_id = origin[len(prefix):]
            if not group_id.isascii() or not group_id.isdecimal():
                raise ValueError(f"AstrBot 群聊记录 {row_id} 的会话标识无效。")
            time = datetime.fromisoformat(created_at)
            if time.tzinfo is None:
                time = time.replace(tzinfo=timezone.utc)
            groups[group_id].append((row_id, sender, name, time.astimezone().replace(tzinfo=None), json.loads(content)))
    if not groups:
        raise ValueError("没有找到云栖 OneBot 平台的群聊记录。")
    return groups


def convert_message(content, bot_qq):
    parts, text, quote_ids = [], [], []
    is_at = False
    for part in content["message"]:
        kind = part["type"]
        if kind == "plain":
            value = part["text"]
        elif kind == "at":
            target = part["user_id"]
            name = part.get("name") or None
            parts.append({"type": "at", "data": {"target_user_id": target, "target_user_nickname": name}})
            text.append(f"@{name or target}")
            is_at |= target in {bot_qq, "all"}
            continue
        elif kind == "reply":
            if quote_id := part.get("message_id"):
                quote_ids.append(quote_id)
            sender = part.get("sender_name") or "未知发送者"
            excerpt = part.get("text")
            value = f"[引用 {sender}：{excerpt}]" if excerpt else f"[引用 {sender} 的旧消息]"
        else:
            raise ValueError(f"无法导入的 AstrBot 历史消息组件：{kind}")
        parts.append({"type": "text", "data": value})
        text.append(value)
    return parts, " ".join(text), is_at, quote_ids


def main():
    accounts, manifest = load_deployment()
    bot_qq = next(account["qq"] for account in accounts if account["target"] == TARGET)
    stamp = json.loads((RUNTIME / ".qqbot-release.json").read_text(encoding="utf-8"))
    expected = {key: manifest["maibot"][key] for key in ("repository", "tag", "commit")}
    if stamp != expected or (RUNTIME / ".runtime/maibot.pid").exists():
        raise RuntimeError("群聊导入需要清单版本的云栖 MaiBot 处于离线状态。")
    if Path(sys.executable).parent.parent != RUNTIME / ".venv":
        raise RuntimeError("请使用云栖 MaiBot 的独立 Python 环境运行导入。")
    bot = tomllib.loads((RUNTIME / "config/bot_config.toml").read_text(encoding="utf-8-sig"))["bot"]
    adapter = tomllib.loads((RUNTIME / "plugins/napcat_adapter/config.toml").read_text(encoding="utf-8-sig"))
    if (bot["platform"], str(bot["qq_account"]), adapter["napcat_server"]["connection_id"]) != (PLATFORM, bot_qq, TARGET):
        raise RuntimeError("云栖 MaiBot 的账号或 OneBot 会话配置与清单不一致。")

    groups = read_group_history()
    sys.path.insert(0, str(RUNTIME))
    import msgpack
    from sqlmodel import select
    from src.common.database.database import get_db_session, initialize_database
    from src.common.database.database_model import ChatSession, Messages
    from src.common.utils.utils_session import SessionUtils

    initialize_database()
    prefix = f"astrbot:{TARGET}:"
    added = 0
    with get_db_session() as database:
        database.connection().exec_driver_sql("BEGIN IMMEDIATE")
        imported = {
            mid: session_id for mid, session_id in database.exec(
                select(Messages.message_id, Messages.session_id).where(Messages.message_id.startswith(prefix))
            )
        }
        for group_id, rows in groups.items():
            session_id = SessionUtils.calculate_session_id(PLATFORM, group_id=group_id, account_id=bot_qq, scope=TARGET)
            group = database.exec(select(ChatSession).where(ChatSession.session_id == session_id)).one_or_none()
            if group is None:
                database.add(ChatSession(
                    session_id=session_id, platform=PLATFORM, group_id=group_id, account_id=bot_qq, scope=TARGET,
                    created_timestamp=rows[0][3], last_active_timestamp=rows[-1][3],
                ))
            elif (group.platform, group.group_id, group.account_id, group.scope) != (PLATFORM, group_id, bot_qq, TARGET):
                raise ValueError(f"目标数据库的群会话归属冲突：{session_id}")
            else:
                group.created_timestamp = min(group.created_timestamp, rows[0][3])
                group.last_active_timestamp = max(group.last_active_timestamp or rows[-1][3], rows[-1][3])
            for row_id, sender, name, time, content in rows:
                message_id = f"{prefix}{row_id}"
                if message_id in imported:
                    if imported[message_id] != session_id:
                        raise ValueError(f"旧消息已导入其他会话：{message_id}")
                    continue
                role = content.get("type")
                if role == "bot" and (not sender or not sender.isdecimal()):
                    sender = bot_qq
                if role not in {"user", "bot"} or not sender or not sender.isdecimal() or (role == "bot" and sender != bot_qq):
                    raise ValueError(f"无法确认 AstrBot 记录 {row_id} 的发送者。")
                parts, text, is_at, quote_ids = convert_message(content, bot_qq)
                database.add(Messages(
                    message_id=message_id, timestamp=time, platform=PLATFORM, user_id=sender,
                    user_nickname=name or "", group_id=group_id, group_name=group_id, session_id=session_id, is_at=is_at,
                    raw_content=msgpack.packb(parts, use_bin_type=True), processed_plain_text=text,
                    additional_config=json.dumps({"self_id": bot_qq, "connection_id": TARGET, "astrbot_quote_ids": quote_ids}),
                ))
                added += 1
    print(f"[qqbot] {len(groups)} 个群，本次导入 {added} 条，已存在 {sum(map(len, groups.values())) - added} 条。")


if __name__ == "__main__":
    main()
