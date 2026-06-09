from __future__ import annotations

from astrbot.api import logger
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_rightcodes_draw",
    "MengLei",
    "RightCodes 生图旧入口兼容壳，实际命令已迁入棉花糖功能合集。",
    "0.1.2",
)
class RightCodesDrawPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        logger.info("[RightCodesDraw] command handlers moved to astrbot_plugin_qqbot_features")
