from __future__ import annotations

from astrbot.api import logger
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_rightcodes_draw",
    "local",
    "Deprecated compatibility shell; RightCodes commands are handled by astrbot_plugin_qqbot_features.",
    "0.1.1",
)
class RightCodesDrawPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        logger.info("[RightCodesDraw] command handlers moved to astrbot_plugin_qqbot_features")
