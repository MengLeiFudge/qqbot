from __future__ import annotations

import re


_DRAW_POINTS_QUERY_RE = re.compile(
    r"^(?:(?:查|查询|查看|看)(?:一下)?)?(?:我(?:的)?|当前)?(?:生图)?积分(?:余额|情况|多少)?$"
)
_DRAW_POINTS_ENGLISH_QUERY_RE = re.compile(r"^(?:balance|points?)$", re.IGNORECASE)
_DRAW_POINTS_MUTATION_RE = re.compile(
    r"(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充).{0,16}积分"
    r"|积分.{0,16}(?:加|增加|扣|扣除|减|减少|改|修改|设置|设定|送|赠|赠送|充值|充)"
)


def looks_like_rightcodes_draw_points_query(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if _DRAW_POINTS_ENGLISH_QUERY_RE.fullmatch(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return _DRAW_POINTS_QUERY_RE.fullmatch(compact) is not None


def looks_like_rightcodes_draw_points_mutation_request(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    if not compact or "积分" not in compact:
        return False
    return _DRAW_POINTS_MUTATION_RE.search(compact) is not None


def format_rightcodes_draw_points_mutation_denied() -> str:
    return "生图积分只能通过群消息自动累计，并在生图时自动扣除；普通聊天不能手动加分或改分。"
