from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MenuSection:
    name: str
    aliases: tuple[str, ...] = ()
    status: str = "已移植"
    lines: tuple[str, ...] = ()


MENU_SECTIONS: tuple[MenuSection, ...] = (
    MenuSection(
        name="群务管理",
        aliases=("群务", "群管理", "群管", "欢迎", "好友邀请"),
        lines=(
            "通知清理文件：统计超期外层群文件并按大小禁言上传者",
            "棉花记录 [数量] / 棉花导出md [数量]：主人限定，导出公开群上下文到固定 md 目录",
            "好友申请 / 邀请入群：按配置自动同意；自身入群后私聊通知邀请者",
            "入群欢迎：天使和恶魔各自按身份欢迎新成员；双 bot 互相入群不欢迎",
        ),
    ),
    MenuSection(
        name="棉花糖互动",
        aliases=("互动", "聊天", "AI", "生图", "美图"),
        status="混合功能",
        lines=(
            "AI对话：使用 AstrBot 模型、人格、记忆和主动接话链路",
            "RightCodes生图：棉花糖生图 [模型名] 提示词；生图模型 / 生图价格；查看积分",
            "Sub2API用量：用量 查询默认账号；后台定时刷新，群消息直接读缓存；多账号逐个列出",
            "Lolicon美图：来点美图 / 色图 / 混合；作者可开关 R18 和图片显示",
            "复读：群里连续出现相同纯文本时概率复读并冷却",
            "戳一戳：戳机器人时概率文本回应；双 bot 之间不互戳",
        ),
    ),
    MenuSection(
        name="养鲲",
        aliases=("鲲",),
        lines=(
            "摸鲲 / 养鲲 / 抓鲲 / 捕鲲：私聊创建或获取鲲",
            "属性 / 背包 / 商城 / 签到 / 挑战 / 排行 / 进击 / 赠送：使用 AstrBot 迁移后的存档与状态机",
        ),
    ),
    MenuSection(
        name="落樱之都",
        aliases=("樱花", "落樱"),
        status="基础玩法已移植",
        lines=("落樱之都 / 注册 / 改名 / 个人信息 / 加经验 / 嘤 / 加点 / 恢复：使用 AstrBot 迁移后的存档",),
    ),
    MenuSection(
        name="Arcaea",
        aliases=("Arc", "Arc查询", "Arc狼人杀", "Arc吃鸡", "arcaea"),
        status="已移植",
        lines=(
            "arctj10.5：按 PTT 推荐谱面，使用本地曲库和定数缓存",
            "archd / arctz：查看当前活动梯子",
            "zm / arczm：字母猜歌；qh / arcqh：曲绘猜歌；jx / arcjx：揭晓",
            "xz / arcxz：作者限定，查询并下载最新 c 版安装包",
            "后台同步别名、定数缓存、猜歌过期会话和每日活动提醒",
        ),
    ),
    MenuSection(
        name="Factorio",
        aliases=("异星工厂", "太空时代", "Space Age", "spaceage"),
        lines=("Factorio下载链接 / 异星下载链接：获取 Space Age Windows 安装包下载链接",),
    ),
    MenuSection(
        name="异形工厂",
        aliases=("shapez", "Shapez"),
        lines=("i/view/chart/path：渲染 shapez 短代码图片；p/puzzle 在线谜题仍提示未配置 token",),
    ),
)


def find_menu_section(key: str) -> MenuSection | None:
    normalized = key.strip().casefold()
    if not normalized:
        return None
    for section in MENU_SECTIONS:
        names = (section.name, *section.aliases)
        if any(normalized == item.casefold() for item in names):
            return section
    return None
