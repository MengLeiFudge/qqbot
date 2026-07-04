from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "astrbot-local-plugins"))

from astrbot_plugin_qqbot_features.legacy_services.kun.service import KunService
from astrbot_plugin_qqbot_features.legacy_services.lolicon.service import LoliconImageItem
from astrbot_plugin_qqbot_features.legacy_services.lolicon.service import LoliconImageStore
from astrbot_plugin_qqbot_features.legacy_services.sakura.service import SakuraService
from astrbot_plugin_qqbot_features.legacy_services.settings_store import SettingsStore
from astrbot_plugin_qqbot_features.rightcodes_draw_logic import RightCodesDrawQuotaStore
from astrbot_plugin_qqbot_features.runtime_storage import resolve_runtime_db_path


class AstrBotRuntimeStorageMigrationTest(unittest.TestCase):
    def test_settings_store_imports_legacy_json_and_writes_sqlite_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "qqbot_features_runtime"
            settings_root = runtime_root / "settings"
            settings_root.mkdir(parents=True)
            legacy_path = settings_root / "lolicon.json"
            legacy_path.write_text(
                json.dumps({"123": {"group_r18": True, "show_image": False}}, ensure_ascii=False),
                encoding="utf-8",
            )
            legacy_before = legacy_path.read_text(encoding="utf-8")

            store = SettingsStore(runtime_root, 605738729)
            self.assertEqual(store.get_lolicon_config(123), (True, False))
            store.set_lolicon_config(123, False, True)

            self.assertEqual(legacy_path.read_text(encoding="utf-8"), legacy_before)
            self.assertEqual(store.get_lolicon_config(123), (False, True))
            self.assertTrue(resolve_runtime_db_path(runtime_root).exists())

    def test_kun_and_sakura_import_legacy_data_from_runtime_data_then_write_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "qqbot_features_runtime"
            kun_root = runtime_root / "data" / "kun"
            kun_root.mkdir(parents=True)
            kun_users = {
                "10001": {
                    "qq": 10001,
                    "name": "旧鲲",
                    "level": 123,
                    "atk": 2,
                    "def": 3,
                    "hp": 4,
                }
            }
            (kun_root / "users.json").write_text(json.dumps(kun_users, ensure_ascii=False), encoding="utf-8")
            (kun_root / "boss.json").write_text(
                json.dumps({"name": "旧Boss", "level": 9, "atk": 8, "def": 7, "hp": 6}, ensure_ascii=False),
                encoding="utf-8",
            )
            (kun_root / "nowSeason.txt").write_text("1=5\n", encoding="utf-8")
            kun_legacy_before = (kun_root / "users.json").read_text(encoding="utf-8")

            sakura_root = runtime_root / "data" / "sakura"
            sakura_root.mkdir(parents=True)
            sakura_players = {"20002": {"qq": 20002, "name": "旧樱"}}
            (sakura_root / "players.json").write_text(
                json.dumps(sakura_players, ensure_ascii=False),
                encoding="utf-8",
            )
            sakura_legacy_before = (sakura_root / "players.json").read_text(encoding="utf-8")

            kun = KunService(runtime_root / "db" / "kun" / "users.json")
            self.assertEqual(kun.get_user(10001).name, "旧鲲")
            self.assertEqual(kun.boss.name, "旧Boss")
            self.assertEqual(kun.now_season, 5)
            kun.ensure_user(10002)

            sakura = SakuraService(runtime_root / "db" / "sakura" / "players.json")
            self.assertEqual(sakura.get_player(20002).name, "旧樱")
            sakura.register_player(20003, "新樱")

            self.assertEqual((kun_root / "users.json").read_text(encoding="utf-8"), kun_legacy_before)
            self.assertEqual((sakura_root / "players.json").read_text(encoding="utf-8"), sakura_legacy_before)
            self.assertTrue(resolve_runtime_db_path(runtime_root).exists())

    def test_rightcodes_quota_store_imports_legacy_points_and_writes_sqlite_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "qqbot_features_runtime"
            points_path = runtime_root / "ai" / "draw_points.json"
            points_path.parent.mkdir(parents=True)
            points_path.write_text(
                json.dumps({"schema_version": 1, "users": {"10001": {"points": 39}}}, ensure_ascii=False),
                encoding="utf-8",
            )
            legacy_before = points_path.read_text(encoding="utf-8")

            store = RightCodesDrawQuotaStore(runtime_root)
            self.assertEqual(store.get_balance("10001", date_key="2026-07-05").points, 39)
            store.record_group_message("10001")

            self.assertEqual(points_path.read_text(encoding="utf-8"), legacy_before)
            self.assertEqual(store.get_balance("10001", date_key="2026-07-05").points, 40)

    def test_rightcodes_quota_store_merges_legacy_points_created_during_restart_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "qqbot_features_runtime"
            store = RightCodesDrawQuotaStore(runtime_root)
            store.record_group_message("10001", amount=5)
            points_path = runtime_root / "ai" / "draw_points.json"
            points_path.parent.mkdir(parents=True)
            points_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "users": {
                            "10001": {"points": 4},
                            "10002": {"points": 1},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            self.assertEqual(store.get_balance("10001", date_key="2026-07-05").points, 5)
            self.assertEqual(store.get_balance("10002", date_key="2026-07-05").points, 1)

            store.record_group_message("10002", amount=9)
            self.assertEqual(store.get_balance("10002", date_key="2026-07-05").points, 10)

    def test_lolicon_prepare_item_records_metadata_without_downloading_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_root = Path(temp_dir) / "qqbot_features_runtime"
            store = LoliconImageStore(runtime_root)
            item = LoliconImageItem(
                title="测试图",
                pid=123,
                page=0,
                author="作者",
                uid=456,
                url="https://example.invalid/image.jpg",
                r18=False,
                width=100,
                height=100,
                tags=("tag",),
                ext="jpg",
                ai_type=0,
                upload_date=0,
            )

            with patch("astrbot_plugin_qqbot_features.legacy_services.lolicon.service.urlopen") as mocked_urlopen:
                prepared = store.prepare_item(item)

            mocked_urlopen.assert_not_called()
            self.assertIsNone(prepared.local_path)
            self.assertFalse((runtime_root / "data" / "lolicon" / "img").exists())
            with sqlite3.connect(runtime_root / "db" / "lolicon.sqlite3") as conn:
                row = conn.execute("select title, url, local_path from images where pid=? and page=?", (123, 0)).fetchone()
            self.assertEqual(row, ("测试图", "https://example.invalid/image.jpg", ""))


if __name__ == "__main__":
    unittest.main()
