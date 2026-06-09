from __future__ import annotations

import re

_ACTION_DESCRIPTION_PATTERN = re.compile(r"[\(（]([^()\n（）]{1,32})[\)）]")
_ACTION_KEYWORDS = (
    "动作",
    "表情",
    "尾巴",
    "耳朵",
    "猫耳",
    "歪头",
    "眨",
    "摇",
    "甩",
    "抱",
    "缩",
    "蹭",
    "贴",
    "扑",
    "摸头",
    "捂脸",
    "脸红",
    "低头",
    "抬头",
    "点头",
    "摇头",
    "耷拉",
    "竖起",
    "挺起",
    "掏出",
    "写下",
    "认真脸",
    "期待",
    "委屈",
    "心虚",
    "害羞",
    "羞愧",
    "困惑",
    "小声",
    "悄悄",
    "假装",
    "轻笑",
    "挑眉",
    "抿",
    "撩",
    "跪",
)

_TECHNICAL_SCENE_MARKERS = (
    "报错",
    "异常",
    "日志",
    "代码",
    "源码",
    "配置",
    "兼容",
    "组件",
    "沙盒",
    "存档",
    "重启",
    "排查",
    "怎么修",
    "怎么解决",
    "怎么处理",
    "怎么办",
)
_MANAGEMENT_SCENE_MARKERS = (
    "群文件",
    "清理",
    "管理员",
    "权限",
    "删除",
    "上传",
    "备份",
    "凭据",
    "token",
    "secret",
    "credentials",
    "auth.json",
    ".kube/config",
)
_RECOMMENDATION_SCENE_MARKERS = ("推荐", "玩什么", "游戏", "愿望单")
_CAT_TAIL_PATTERN = re.compile(r"(?<=\S)(喵|喵[。！？!?.，,~～]*)$", re.I)
_PLAYFUL_TECH_REPLACEMENTS = {
    "抽风": "异常",
    "硬上": "继续尝试",
    "肝先冒烟": "精力先被耗完",
    "肝冒烟": "精力被耗完",
}
_GAME_PERSONIFICATION_MARKERS = (
    "会吃醋",
    "吃醋",
    "正宫",
    "哄哄它",
    "陪 shapez",
    "陪shapez",
    "回来切两刀",
    "回来陪",
    "外出取材",
)
_FOLLOWUP_TAIL_BOUNDARY = re.compile(r"(?<=[。！？!?；;])")
_FOLLOWUP_INVITATION_MARKERS = (
    "如果你愿意",
    "如果愿意",
    "你如果愿意",
    "你要是愿意",
    "要是你",
    "要的话",
    "需要的话",
    "想要的话",
    "愿意的话",
    "你把",
    "把具体",
    "具体名字发",
    "具体软件名发",
    "发我",
    "告诉我",
    "我可以再",
    "我也可以",
    "我还能",
    "我可以帮",
    "我能帮",
    "我帮你",
    "帮你挑",
    "帮你看",
    "帮你认",
    "帮你分辨",
    "教你怎么",
)
_FOLLOWUP_QUESTION_MARKERS = (
    "要不要",
    "需不需要",
    "是否需要",
    "要我",
    "需要我",
    "你想",
    "你要",
    "可以吗",
    "行吗",
)


def sanitize_ai_output_text(text: str) -> str:
    lines = []
    in_fence = False
    for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            line = _strip_block_markdown(line)
            line = _strip_inline_markdown(line)
            line = _strip_parenthesized_action_descriptions(line)
        if line:
            lines.append(line)
    cleaned = _strip_repeated_short_tail("\n".join(lines).strip())
    return _strip_followup_invitation_tail(cleaned)


def sanitize_group_ai_reply_text(text: str, *, prompt: str = "", group_id: int | str | None = None) -> str:
    cleaned = sanitize_ai_output_text(text)
    if not cleaned:
        return ""
    compact_prompt = re.sub(r"\s+", "", prompt)
    if _looks_like_identity_bait(compact_prompt, cleaned):
        return "不乱认亲啦，继续说正事吧喵。"

    scene_text = f"{prompt}\n{cleaned}"
    strict_tone = _looks_like_practical_scene(scene_text)
    lines: list[str] = []
    for line in cleaned.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_game_personification_line(stripped, group_id=group_id):
            continue
        if strict_tone:
            stripped = _strip_chatty_tone(stripped)
        lines.append(stripped)
    return "\n".join(lines).strip()


def _looks_like_identity_bait(prompt: str, reply: str) -> bool:
    compact_reply = re.sub(r"\s+", "", reply)
    prompt_markers = ("你妈", "妈妈", "叫妈妈", "你没有妈", "这是你妈", "乱认亲")
    reply_markers = (
        "作者和主人",
        "作者/主人",
        "主人是",
        "作者是",
        "最高管理者",
        "妈妈设定",
        "没有妈妈",
        "不许乱认亲",
    )
    return any(marker in prompt for marker in prompt_markers) and any(
        marker in compact_reply for marker in reply_markers
    )


def _looks_like_practical_scene(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.lower())
    return any(marker in compact for marker in _TECHNICAL_SCENE_MARKERS + _MANAGEMENT_SCENE_MARKERS + _RECOMMENDATION_SCENE_MARKERS)


def _is_game_personification_line(line: str, *, group_id: int | str | None) -> bool:
    normalized = re.sub(r"\s+", "", line.lower())
    if any(marker.replace(" ", "").lower() in normalized for marker in _GAME_PERSONIFICATION_MARKERS):
        return True
    if str(group_id or "") == "1163635014" and "shapez" in normalized and any(
        marker in normalized for marker in ("它", "正宫", "吃醋", "哄", "陪")
    ):
        return True
    return False


def _strip_chatty_tone(line: str) -> str:
    current = line.strip()
    for source, target in _PLAYFUL_TECH_REPLACEMENTS.items():
        current = current.replace(source, target)
    current = _CAT_TAIL_PATTERN.sub("", current).rstrip()
    current = re.sub(r"(啦|呀)([。！？!?])?$", _replace_soft_tail, current).rstrip()
    current = re.sub(r"^那我小声推荐[:：]?", "推荐：", current).strip()
    current = re.sub(r"^小声点小声点[，,]?", "", current).strip()
    return current


def _replace_soft_tail(match: re.Match[str]) -> str:
    return match.group(2) or ""


def _strip_block_markdown(line: str) -> str:
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^>\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"^\s*(\d+)\.\s+", r"\1、", line)
    return line


def _strip_inline_markdown(line: str) -> str:
    line = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace_markdown_link, line)
    line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_markdown_link, line)
    for marker in ("**", "__", "~~", "`", "*", "_"):
        line = line.replace(marker, "")
    return line.strip()


def _replace_markdown_link(match: re.Match[str]) -> str:
    label = match.group(1).strip()
    url = match.group(2).strip()
    if label and url:
        return f"{label} {url}"
    return label or url


def _strip_parenthesized_action_descriptions(line: str) -> str:
    line = _ACTION_DESCRIPTION_PATTERN.sub(_replace_action_description, line)
    line = re.sub(r"\s+([。！？!?，,；;：:])", r"\1", line)
    line = re.sub(r"([。！？!?~～])\s+([\U0001F300-\U0001FAFF])", r"\1\2", line)
    line = re.sub(r" {2,}", " ", line)
    return line.strip()


def _replace_action_description(match: re.Match[str]) -> str:
    body = match.group(1).strip()
    if any(keyword in body for keyword in _ACTION_KEYWORDS):
        return ""
    return match.group(0)


def _strip_repeated_short_tail(text: str) -> str:
    current = text.strip()
    if not current:
        return ""
    punctuation = "。！？!?；;，,"
    for size in range(3, 0, -1):
        pattern = re.compile(
            rf"(?P<body>.+?)(?P<punct>[{re.escape(punctuation)}])(?P<tail>[\u4e00-\u9fffA-Za-z0-9]{{{size}}})(?P=punct)$",
            re.S,
        )
        match = pattern.fullmatch(current)
        if match is None:
            continue
        body = match.group("body")
        tail = match.group("tail")
        if not body.endswith(tail):
            continue
        return f"{body}{match.group('punct')}".strip()
    return current


def _strip_followup_invitation_tail(text: str) -> str:
    current = text.strip()
    if not current:
        return ""
    lines = current.split("\n")
    stripped_any = False
    while lines:
        line = lines[-1].strip()
        stripped = _strip_followup_invitation_from_line(line)
        if stripped == line:
            break
        stripped_any = True
        if stripped:
            lines[-1] = stripped
            break
        lines.pop()
    result = "\n".join(line for line in lines if line.strip()).strip()
    if result:
        return result
    return "" if stripped_any else current


def _strip_followup_invitation_from_line(line: str) -> str:
    parts = [part.strip() for part in _FOLLOWUP_TAIL_BOUNDARY.split(line) if part.strip()]
    if not parts:
        return ""
    while parts and _is_followup_invitation_sentence(parts[-1]):
        parts.pop()
    return "".join(parts).strip()


def _is_followup_invitation_sentence(sentence: str) -> bool:
    compact = re.sub(r"\s+", "", sentence)
    if not compact:
        return False
    if any(marker in compact for marker in _FOLLOWUP_INVITATION_MARKERS):
        return True
    if compact.endswith(("?", "？")):
        return True
    return False
