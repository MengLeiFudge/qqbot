from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginSpec:
    id: str
    name: str
    feature_index: int | None = None
    version: str = "1.0"
    legacy_names: tuple[str, ...] = ()
    menu_lines: tuple[str, ...] = ()
    menu_keys: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ("group", "private")
    requires_direct_at: bool = True
    ai_capabilities: tuple[str, ...] = ()
    enabled_by_default: bool = False


PLUGIN_SPECS: tuple[PluginSpec, ...] = (
    PluginSpec(
        id="reread",
        name="随机复读",
        feature_index=1,
        commands=("设置复读",),
        scopes=("group",),
    ),
    PluginSpec(
        id="thunder",
        name="随机禁言",
        feature_index=2,
        commands=("设置禁言概率", "设置禁言时间"),
        scopes=("group",),
    ),
    PluginSpec(
        id="lolicon",
        name="Lolicon美图",
        feature_index=3,
        commands=("来点色图", "美图", "开群色图", "关群色图"),
        scopes=("group", "private"),
    ),
    PluginSpec(
        id="ai",
        name="AI测试",
        commands=("ai",),
        scopes=("private",),
        ai_capabilities=("chat",),
    ),
    PluginSpec(
        id="kun",
        name="养鲲",
        feature_index=11,
        commands=(
            "摸鲲",
            "养鲲",
            "抓鲲",
            "属性",
            "签到",
            "背包",
            "商城",
            "boss",
            "挑战",
        ),
        menu_lines=(
            "摸鲲 / 养鲲 / 抓鲲 / 捕鲲：私聊创建或获取鲲",
            "属性：私聊查看自己的鲲",
            "查看 @对方：查看对方的鲲",
            "洗练攻击10 / 洗练防御10 / 洗练血量10：消耗洗练卡强化属性",
            "签到：领取萌泪币",
            "背包 / 道具：私聊查看道具",
            "商城：私聊查看商品",
            "购买改名卡1 / 出售改名卡1：买卖道具",
            "命名新名字：私聊改名",
            "boss / 查看boss：私聊查看 Boss",
            "挑战：私聊挑战 Boss",
            "等级排行 / 财富排行：查看排行榜",
            "进击 @对方：攻击对方",
            "赠送 @对方 100：赠送萌泪币",
            "开新赛季提示 / 关新赛季提示：私聊切换提示",
        ),
    ),
    PluginSpec(
        id="sakura",
        name="落樱之都",
        feature_index=12,
        commands=("注册樱花勇者", "个人信息", "加经验", "加力量", "恢复"),
        scopes=("group", "private"),
    ),
    PluginSpec(
        id="arc",
        name="Arc",
        feature_index=13,
        legacy_names=("Arc查询", "Arc狼人杀", "Arc吃鸡"),
        menu_lines=(
            "arctj10.5：按 PTT 推荐谱面",
            "zm：开始字符猜歌",
            "开*：开一个非空格字符",
            "10曲名：猜第 10 题",
            "arcqh：开始/继续曲绘猜歌",
            "jx：公布当前 Arc 猜歌答案",
            "archd：查看当前活动梯子",
            "xz / arcxz：查询并下载最新 c 版安装包",
        ),
        menu_keys=("arc", "arcaea"),
        commands=("arctj", "zm", "arczm", "arcqh", "jx", "archd", "xz", "arcxz"),
        scopes=("group", "private"),
        ai_capabilities=("explain",),
    ),
    PluginSpec(
        id="shapez",
        name="异形工厂",
        feature_index=16,
        commands=("i", "p"),
        scopes=("group", "private"),
        ai_capabilities=("render",),
    ),
    PluginSpec(
        id="group_control",
        name="群管",
        commands=("禁言", "解禁", "群禁言", "群解禁", "踢出"),
        scopes=("group",),
    ),
)


def validate_plugin_specs(specs: tuple[PluginSpec, ...] = PLUGIN_SPECS) -> None:
    ids = [spec.id for spec in specs]
    if len(ids) != len(set(ids)):
        raise ValueError("插件 id 不能重复")

    feature_indexes = [spec.feature_index for spec in specs if spec.feature_index is not None]
    if len(feature_indexes) != len(set(feature_indexes)):
        raise ValueError("功能序号不能重复")


def list_visible_plugin_specs() -> list[PluginSpec]:
    validate_plugin_specs()
    return sorted(
        (spec for spec in PLUGIN_SPECS if spec.feature_index is not None),
        key=lambda spec: spec.feature_index or 0,
    )


def get_plugin_spec_by_id(plugin_id: str) -> PluginSpec | None:
    normalized = plugin_id.strip().lower()
    for spec in PLUGIN_SPECS:
        if spec.id == normalized:
            return spec
    return None


def get_plugin_spec_by_feature_index(index: int) -> PluginSpec | None:
    for spec in PLUGIN_SPECS:
        if spec.feature_index == index:
            return spec
    return None


def get_plugin_spec_by_menu_key(key: str) -> PluginSpec | None:
    normalized = key.strip().lower()
    if normalized.isdigit():
        return get_plugin_spec_by_feature_index(int(normalized))

    for spec in list_visible_plugin_specs():
        if normalized == spec.name.lower():
            return spec
        if normalized == spec.id:
            return spec
        if normalized in tuple(name.lower() for name in spec.legacy_names):
            return spec
        if normalized in spec.menu_keys:
            return spec
    return None
