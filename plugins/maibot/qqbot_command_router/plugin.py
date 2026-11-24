from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from pathlib import Path
from typing import ClassVar

import asyncio
import sqlite3

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder
from qqbot_common.message_facts import leading_mention_targets


class PluginSection(PluginConfigBase):
    enabled: bool = Field(default=False)
    config_version: str = Field(default="0.1.0")


class RoutingSection(PluginConfigBase):
    account_ids: list[str] = Field(default_factory=list, description="参与群固定指令认领的账号")
    database_path: str = Field(default="", description="所有参与账号共用的本机 SQLite 文件绝对路径")


class CommandRouterConfig(PluginConfigBase):
    plugin: PluginSection = Field(default_factory=PluginSection)
    routing: RoutingSection = Field(default_factory=RoutingSection)


class QQBotCommandRouterPlugin(MaiBotPlugin):
    config_model: ClassVar[type[PluginConfigBase] | None] = CommandRouterConfig
    _database: Path | None = None

    async def on_load(self) -> None:
        self._database = None
        if not self.config.plugin.enabled:
            return
        routing = self.config.routing
        if not routing.account_ids or not all(qq.isascii() and qq.isdecimal() for qq in routing.account_ids):
            raise ValueError("routing.account_ids 必须包含参与认领的 QQ 号")
        database = Path(routing.database_path).expanduser()
        if not database.is_absolute():
            raise ValueError("routing.database_path 必须是本机数据库文件的绝对路径")
        await asyncio.to_thread(self._prepare_database, database)
        self._database = database
        self.ctx.logger.info("QQBot 固定指令认领已就绪，参与账号数=%s，数据库=%s", len(set(routing.account_ids)), database)

    async def on_unload(self) -> None:
        self._database = None

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del config_data, version
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            await self.on_load()

    @HookHandler(
        "chat.command.before_execute",
        name="qqbot_claim_group_command",
        description="在执行前认领群固定指令",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        timeout_ms=1500,
        error_policy=ErrorPolicy.ABORT,
    )
    async def claim_group_command(
        self,
        message: dict[str, object],
        plugin_id: str,
        **kwargs: object,
    ) -> dict[str, str]:
        del kwargs
        allowed = {"action": "continue"}
        blocked = {"action": "abort"}
        if not self.config.plugin.enabled or not plugin_id.startswith("mlj.qqbot-") or message.get("platform") != "qq":
            return allowed
        info = message.get("message_info")
        group = info.get("group_info") if isinstance(info, Mapping) else None
        if not isinstance(group, Mapping):
            return allowed
        group_id = str(group.get("group_id") or "")
        if not group_id:
            return allowed
        extra = info.get("additional_config")
        account_id = str(extra.get("self_id") or "") if isinstance(extra, Mapping) else ""
        accounts = set(self.config.routing.account_ids)
        database = self._database
        if account_id not in accounts or database is None:
            self.ctx.logger.warning("跳过群固定指令，当前账号或认领库未就绪")
            return blocked
        targets = leading_mention_targets(message)
        if targets and account_id not in targets and "all" not in targets:
            return blocked

        seq = str(extra.get("napcat_group_real_seq") or "")
        if seq and seq.isascii() and seq.isdecimal():
            source, message_id = "group", seq
        elif len(accounts) == 1 and message.get("message_id"):
            source, message_id = account_id, str(message["message_id"])
        else:
            self.ctx.logger.warning("跳过群固定指令，缺少可用于认领的消息标识")
            return blocked

        try:
            claimed = await asyncio.to_thread(self._claim, database, source, group_id, message_id, account_id)
        except sqlite3.Error as exc:
            self.ctx.logger.warning("群固定指令认领失败：%s", exc)
            return blocked
        return allowed if claimed else blocked

    @staticmethod
    def _prepare_database(database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(database, timeout=2.0)) as conn, conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                create table if not exists group_command_claims (
                    source text not null,
                    group_id text not null,
                    message_id text not null,
                    account_id text not null,
                    primary key (source, group_id, message_id)
                ) without rowid
                """
            )

    @staticmethod
    def _claim(database: Path, source: str, group_id: str, message_id: str, account_id: str) -> bool:
        with closing(sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=0.25)) as conn, conn:
            result = conn.execute(
                """
                insert into group_command_claims (source, group_id, message_id, account_id)
                values (?, ?, ?, ?)
                on conflict (source, group_id, message_id) do nothing
                """,
                (source, group_id, message_id, account_id),
            )
            return result.rowcount == 1


def create_plugin() -> QQBotCommandRouterPlugin:
    return QQBotCommandRouterPlugin()
