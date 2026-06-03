from __future__ import annotations

from pathlib import Path

import nonebot
from nonebot import logger
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from qqbot.admin_api import register_admin_routes
from qqbot.config import RuntimeSettings
from qqbot.services.onebot_message_throttle import install_onebot_group_message_throttle

_BOOTSTRAPPED = False


def bootstrap(settings: RuntimeSettings) -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    nonebot.init(
        host=settings.host,
        port=settings.port,
        command_start={settings.command_start},
        superusers=settings.superusers,
        onebot_access_token=settings.onebot_access_token,
        log_level=settings.log_level.upper(),
    )
    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)
    install_onebot_group_message_throttle()
    register_admin_routes(driver.server_app, settings)

    plugin_dir = Path(__file__).resolve().parent / "plugins"
    nonebot.load_plugins(str(plugin_dir))
    logger.info("Loaded qqbot plugins from {}", plugin_dir)
    _BOOTSTRAPPED = True
