from __future__ import annotations

import re


_TAIL_BOUNDARY = re.compile(r"(?<=[。！？!?；;])")
_FOLLOWUP_MARKERS = (
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


def strip_followup_tail(text: str) -> str:
    current = text.strip()
    if not current:
        return ""
    lines = current.split("\n")
    stripped_any = False
    while lines:
        line = lines[-1].strip()
        stripped = strip_followup_from_line(line)
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


def strip_followup_from_line(line: str) -> str:
    parts = [part.strip() for part in _TAIL_BOUNDARY.split(line) if part.strip()]
    if not parts:
        return ""
    while parts and is_followup_sentence(parts[-1]):
        parts.pop()
    return "".join(parts).strip()


def is_followup_sentence(sentence: str) -> bool:
    compact = re.sub(r"\s+", "", sentence)
    if not compact:
        return False
    if any(marker in compact for marker in _FOLLOWUP_MARKERS):
        return True
    if compact.endswith(("?", "？")):
        return True
    return False
