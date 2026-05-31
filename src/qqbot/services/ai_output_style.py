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
    return _strip_repeated_short_tail("\n".join(lines).strip())


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
