from __future__ import annotations

import re


DEFAULT_SEGMENTED_REPLY_REGEX = r".*?[。？！~…]+|.+$"
MAX_SEGMENTED_REPLY_PARTS = 3
DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS = 300
FORWARD_NODE_TEXT_CHARS = 4000
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


def sanitize_reply_plain_text(text: str) -> str:
    return strip_followup_tail(strip_markdown_syntax(text))


def normalize_fold_threshold(value: object, *, default: int = DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return default
    if threshold <= 0:
        return 0
    return max(80, min(threshold, 10000))


def should_fold_long_reply(
    text: str,
    *,
    threshold: int = DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS,
) -> bool:
    threshold = normalize_fold_threshold(threshold)
    if threshold <= 0:
        return False
    return len(str(text or "").strip()) > threshold


def split_forward_text(text: str, *, limit: int = FORWARD_NODE_TEXT_CHARS) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    limit = max(1, int(limit or FORWARD_NODE_TEXT_CHARS))
    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > limit:
        split_at = _find_split_index(remaining, limit)
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def build_fold_notice(node_count: int = 1) -> str:
    if node_count > 1:
        return f"内容比较长，已经折叠成 {node_count} 段。"
    return "内容比较长，已经折叠起来了。"


def should_disable_segmented_reply_for_text(
    text: str,
    *,
    regex: str = DEFAULT_SEGMENTED_REPLY_REGEX,
    content_cleanup_rule: str = "",
    max_parts: int = MAX_SEGMENTED_REPLY_PARTS,
) -> bool:
    return (
        count_segmented_reply_parts(
            text,
            regex=regex,
            content_cleanup_rule=content_cleanup_rule,
        )
        > max_parts
    )


def count_segmented_reply_parts(
    text: str,
    *,
    regex: str = DEFAULT_SEGMENTED_REPLY_REGEX,
    content_cleanup_rule: str = "",
) -> int:
    raw_text = str(text or "")
    if not raw_text.strip():
        return 0
    try:
        segments = re.findall(regex, raw_text, re.DOTALL | re.MULTILINE)
    except re.error:
        segments = re.findall(DEFAULT_SEGMENTED_REPLY_REGEX, raw_text, re.DOTALL | re.MULTILINE)
    count = 0
    for segment in segments:
        if isinstance(segment, tuple):
            segment = "".join(part for part in segment if isinstance(part, str))
        if content_cleanup_rule:
            try:
                segment = re.sub(content_cleanup_rule, "", str(segment))
            except re.error:
                pass
        if str(segment).strip():
            count += 1
    return count


def _find_split_index(text: str, limit: int) -> int:
    window = text[:limit]
    for separator in ("\n\n", "\n", "。", "！", "？", "；", "，", " "):
        index = window.rfind(separator)
        if index >= max(1, limit // 2):
            return index + len(separator)
    return limit


def strip_markdown_syntax(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for raw_line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(line)
            continue
        line = _strip_block_markdown(line)
        line = _strip_inline_markdown(line)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


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


def _strip_block_markdown(line: str) -> str:
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^>\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "· ", line)
    line = re.sub(r"^\s*(\d+)\.\s+", r"\1、", line)
    return line


def _strip_inline_markdown(line: str) -> str:
    line = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", _replace_markdown_link, line)
    line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _replace_markdown_link, line)
    line = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", line)
    line = re.sub(r"__([^_\n]+)__", r"\1", line)
    line = re.sub(r"~~([^~\n]+)~~", r"\1", line)
    line = re.sub(r"`([^`\n]+)`", r"\1", line)
    line = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", line)
    line = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", line)
    return line.rstrip()


def _replace_markdown_link(match: re.Match[str]) -> str:
    label = match.group(1).strip()
    url = match.group(2).strip()
    if label and url:
        return f"{label} {url}"
    return label or url
