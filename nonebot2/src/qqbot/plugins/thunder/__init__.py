from __future__ import annotations

from qqbot.services.feature_catalog import get_feature_by_menu_key


def get_thunder_feature():
    return get_feature_by_menu_key("群管助手")
