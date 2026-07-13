from __future__ import annotations

import ast
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins"))

from astrbot_plugin_qqbot_features.group_nickname_store import GroupNicknameStore


class GroupNicknameStoreTest(unittest.TestCase):
    def test_current_group_card_then_current_nickname_then_other_group_nickname(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GroupNicknameStore(Path(temp_dir))
            store.record_group_sender(
                "100",
                "200",
                card="群 A 名片",
                nickname="小明",
                updated_at=10,
            )
            store.record_group_sender(
                "101",
                "200",
                card="群 B 名片",
                nickname="明明",
                updated_at=20,
            )
            store.record_group_sender(
                "102",
                "200",
                card="",
                nickname="本群昵称",
                updated_at=15,
            )

            self.assertEqual(store.resolve_display_name("100", "200"), "群 A 名片")
            self.assertEqual(store.resolve_display_name("102", "200"), "本群昵称")
            self.assertEqual(store.resolve_display_name("103", "200"), "明明")
            self.assertEqual(store.resolve_display_name("103", "201"), "201")

    def test_newer_event_replaces_the_same_group_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GroupNicknameStore(Path(temp_dir))
            store.record_group_sender("100", "200", card="旧名片", nickname="旧昵称", updated_at=20)
            store.record_group_sender("100", "200", card="过期名片", nickname="过期昵称", updated_at=10)
            store.record_group_sender("100", "200", card="", nickname="新昵称", updated_at=30)

            self.assertEqual(store.resolve_display_name("100", "200"), "新昵称")

    def test_blank_sender_names_do_not_create_a_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = GroupNicknameStore(Path(temp_dir))
            store.record_group_sender("100", "200", updated_at=10)

            self.assertEqual(store.resolve_display_name("100", "200"), "200")

    def test_group_nickname_cache_handler_runs_before_stop_capable_handlers(self) -> None:
        source_path = ROOT / "plugins" / "astrbot_plugin_qqbot_features" / "main.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        handler = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "cache_group_nickname"
        )
        decorator = next(
            item
            for item in handler.decorator_list
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and item.func.attr == "event_message_type"
        )
        priority = next(keyword.value for keyword in decorator.keywords if keyword.arg == "priority")

        self.assertIsInstance(priority, ast.Constant)
        self.assertGreaterEqual(priority.value, 3000)
