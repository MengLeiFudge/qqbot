from __future__ import annotations

import asyncio

from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot

from qqbot.config import load_settings
from qqbot.services.arc_alias_service import ArcAliasService
from qqbot.services.arc_alias_service import load_song_titles
from qqbot.services.arc_background_service import ArcBackgroundService
from qqbot.services.arc_constant_service import ArcConstantService
from qqbot.services.arc_event_service import ArcEventService, _fetch_latest_arc_version
from qqbot.services.arc_guess_service import ArcGuessService
from qqbot.services.codex_self_update_service import publish_pending_codex_self_update_notices
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.settings_store import get_settings_store

driver = get_driver()
_ARC_BACKGROUND_TASKS: dict[str, asyncio.Task] = {}


def get_arc_alias_service() -> ArcAliasService:
    settings = load_settings()
    return ArcAliasService(
        assets_root=settings.arc_assets_root,
        cache_path=settings.data_root / "data" / "arc" / "guess_aliases.json",
    )


def get_arc_constant_service() -> ArcConstantService:
    settings = load_settings()
    return ArcConstantService(cache_path=settings.data_root / "data" / "arc" / "constants.json")


def load_arc_song_titles() -> list[dict[str, str]]:
    settings = load_settings()
    return load_song_titles(settings.arc_assets_root / "官谱" / "songlist")


def get_arc_background_service() -> ArcBackgroundService:
    settings = load_settings()
    return ArcBackgroundService(
        state_path=settings.data_root / "data" / "arc" / "background_state.json",
        settings_store=get_settings_store(),
        arc_feature=get_feature_by_menu_key("Arc"),
        author_qq=settings.author_qq,
        version_fetcher=_fetch_latest_arc_version,
        event_service=ArcEventService(timezone=settings.timezone),
        alias_service=get_arc_alias_service(),
        guess_service=ArcGuessService(
            assets_root=settings.arc_assets_root,
            alias_cache_path=settings.data_root / "data" / "arc" / "guess_aliases.json",
            state_path=settings.data_root / "data" / "arc" / "guess_sessions.json",
        ),
        constant_service=get_arc_constant_service(),
        constant_song_loader=load_arc_song_titles,
        timezone_name=settings.timezone,
    )


@driver.on_startup
async def log_startup() -> None:
    settings = load_settings()
    logger.info("QQBot startup ready. Reverse WS endpoint: {}", settings.onebot_ws_url)


@driver.on_bot_connect
async def log_bot_connect(bot: Bot) -> None:
    logger.success("OneBot bot connected: {}", bot.self_id)
    settings = load_settings()
    try:
        await publish_pending_codex_self_update_notices(bot, settings.data_root)
    except Exception as exc:
        logger.exception("Failed to publish Codex self-update notices: {}", exc)
    if bot.self_id in _ARC_BACKGROUND_TASKS:
        return
    _ARC_BACKGROUND_TASKS[bot.self_id] = asyncio.create_task(run_arc_background_loop(bot))


@driver.on_bot_disconnect
async def log_bot_disconnect(bot: Bot) -> None:
    logger.warning("OneBot bot disconnected: {}", bot.self_id)
    task = _ARC_BACKGROUND_TASKS.pop(bot.self_id, None)
    if task is not None:
        task.cancel()


async def run_arc_background_loop(bot: Bot) -> None:
    service = get_arc_background_service()
    try:
        while True:
            await service.run_once(bot)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Arc background loop crashed: {}", exc)
