from __future__ import annotations

from importlib import import_module
import pkgutil

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

    plugin_names = _discover_plugin_module_names()
    loaded_plugins = [
        plugin_name
        for plugin_name in plugin_names
        if nonebot.load_plugin(plugin_name) is not None
    ]
    logger.info("Loaded qqbot plugins: {}", ", ".join(loaded_plugins))
    _BOOTSTRAPPED = True


def _discover_plugin_module_names(package_name: str = "qqbot.plugins") -> list[str]:
    package = import_module(package_name)
    return [
        f"{package_name}.{module.name}"
        for module in sorted(pkgutil.iter_modules(package.__path__), key=lambda item: item.name)
        if not module.name.startswith("_")
    ]
