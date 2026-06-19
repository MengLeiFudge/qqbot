from __future__ import annotations

import re


DEFAULT_SEGMENTED_REPLY_REGEX = r".*?[。？！~…]+|.+$"
MAX_SEGMENTED_REPLY_PARTS = 3
DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS = 300
DEFAULT_LONG_INPUT_TLDR_THRESHOLD_CHARS = 300
FORWARD_NODE_TEXT_CHARS = 4000
DANGEROUS_LOCAL_TOOL_NAMES = frozenset(
    {
        "astrbot_execute_shell",
        "astrbot_execute_python",
        "astrbot_execute_ipython",
        "astrbot_file_read_tool",
        "astrbot_read_file_tool",
        "astrbot_file_write_tool",
        "astrbot_file_edit_tool",
        "astrbot_grep_tool",
        "astrbot_upload_file",
        "astrbot_download_file",
        "astrbot_cua_screenshot",
        "astrbot_cua_mouse_click",
        "astrbot_cua_keyboard_type",
        "astrbot_execute_browser",
        "astrbot_execute_browser_batch",
        "astrbot_run_browser_skill",
        "execute_shell",
        "shell",
        "local_python",
        "python",
        "file_read",
        "file_write",
        "file_edit",
        "grep",
        "upload",
        "download",
        "browser",
        "cua",
    }
)
DANGEROUS_LOCAL_TOOL_KEYWORDS = (
    "execute_shell",
    "execute_python",
    "execute_ipython",
    "file_read",
    "read_file",
    "file_write",
    "file_edit",
    "grep",
    "upload_file",
    "download_file",
    "execute_browser",
    "run_browser",
    "cua_",
)
BOT_DISPLAY_NAMES = {
    "1443944862": "😇棉花糖😇",
    "2629227874": "👿棉花糖👿",
}
BOT_RELATION_NAMES = {
    "1443944862": "姐姐",
    "2629227874": "妹妹",
}
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
_PERMISSION_ESCALATION_MARKERS = (
    "webui",
    "管理员列表",
    "管理员",
    "shell权限",
    "shell 权限",
    "文件权限",
    "写文件权限",
    "本机权限",
    "后台权限",
    "开shell",
    "开启shell",
    "开了shell",
    "添加管理员",
    "加进管理员",
    "shell",
)
_PERMISSION_ESCALATION_ACTIONS = (
    "去",
    "进",
    "打开",
    "添加",
    "加进",
    "开启",
    "打开",
    "配置",
    "改",
    "设置",
    "授权",
)


def sanitize_reply_plain_text(text: str) -> str:
    return strip_followup_tail(strip_permission_escalation_advice(strip_markdown_syntax(text)))


def is_dangerous_local_tool_name(name: object) -> bool:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return False
    if normalized in DANGEROUS_LOCAL_TOOL_NAMES:
        return True
    if not normalized.startswith("astrbot_"):
        return False
    return any(keyword in normalized for keyword in DANGEROUS_LOCAL_TOOL_KEYWORDS)


def strip_permission_escalation_advice(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ""
    lines: list[str] = []
    stripped_any = False
    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if is_permission_escalation_advice_line(line):
            stripped_any = True
            continue
        lines.append(raw_line.rstrip())
    result = "\n".join(line for line in lines if line.strip()).strip()
    if result:
        return result
    if stripped_any:
        return "我不能通过聊天申请或开启本机文件、命令执行权限。"
    return normalized


def is_permission_escalation_advice_line(line: str) -> bool:
    compact = re.sub(r"\s+", "", str(line or "")).lower()
    if not compact:
        return False
    has_marker = any(marker.replace(" ", "").lower() in compact for marker in _PERMISSION_ESCALATION_MARKERS)
    has_action = any(action.replace(" ", "").lower() in compact for action in _PERMISSION_ESCALATION_ACTIONS)
    if has_marker and has_action:
        return True
    if "写文件权限" in compact and ("没有" in compact or "没" in compact or "无法" in compact):
        return True
    return (
        ("写文件权限" in compact or "shell权限" in compact or "文件权限" in compact)
        and ("管理员" in compact or "webui" in compact or "授权" in compact)
    )


def normalize_fold_threshold(value: object, *, default: int = DEFAULT_LONG_REPLY_FOLD_THRESHOLD_CHARS) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return default
    if threshold <= 0:
        return 0
    return max(80, min(threshold, 10000))


def normalize_long_input_tldr_threshold(
    value: object,
    *,
    default: int = DEFAULT_LONG_INPUT_TLDR_THRESHOLD_CHARS,
) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return default
    if threshold <= 0:
        return 0
    return max(80, min(threshold, 10000))


def should_reply_too_long_to_read(
    text: str,
    *,
    threshold: int = DEFAULT_LONG_INPUT_TLDR_THRESHOLD_CHARS,
) -> bool:
    threshold = normalize_long_input_tldr_threshold(threshold)
    if threshold <= 0:
        return False
    compact = re.sub(r"\s+", "", str(text or ""))
    return len(compact) > threshold


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


def should_disable_model_regex_segmenting(
    segmented_reply: dict,
    *,
    is_model_result: bool,
    override_enabled: bool = True,
) -> bool:
    if not override_enabled:
        return False
    if not is_model_result:
        return False
    if segmented_reply.get("enable") is not True:
        return False
    if segmented_reply.get("only_llm_result", True) is not True:
        return False
    return str(segmented_reply.get("split_mode", "regex")) == "regex"


def build_delegated_reply_instruction_text(
    *,
    current_id: str,
    current_name: str,
    delegated_from: str,
) -> str:
    delegated_names = ",".join(
        BOT_DISPLAY_NAMES.get(bot_id.strip(), bot_id.strip())
        for bot_id in str(delegated_from or "").split(",")
        if bot_id.strip()
    )
    if not delegated_names:
        delegated_names = "另一个棉花糖"
    if str(current_id or "").strip() == "1443944862":
        opener = f"这是代班接力请求：{delegated_names} 那边在忙，请用 {current_name} 自己的身份先温柔接一下。"
    else:
        opener = f"这是代班接力请求：{delegated_names} 那边忙着呢，请用 {current_name} 自己的身份先顶上。"
    return (
        opener
        + "开头用一句很短的话说明正在接力，不要冒充对方，不要替对方认错、解释或承诺修改。"
        "本轮回复里的“我”必须是当前 bot；不要把自己说成另一个 bot，也不要替另一个 bot 接受夸奖、道歉或表态。"
    )


def build_both_targeted_reply_instruction_text() -> str:
    return (
        "用户这次同时叫到了天使棉花糖和恶魔棉花糖，也是在叫你本人。"
        "请用当前 bot 自己的身份直接完成用户这次请求；如果用户让讲笑话、回答问题、评价或说一句话，你也要给出自己的内容。"
        "不要把任务转给另一个 bot，不要说“让她来讲/让对方回应/我不替她讲”。"
        "如果用户说“我喜欢你们”“谢谢你们”“你们真好”这类同时面向两只的情绪表达，你只能代表当前 bot 独立回应，不能替另一个 bot 接受、感谢或承诺。"
        "这类场景必须使用单数第一人称，例如“谢谢你喜欢我”；不要说“我们收到”“两只都收到”“姐姐和妹妹都收到”。"
        "这类场景最稳妥的回复是一句短感谢，不要追加“不过/但是”转折、姐妹比较或对另一个 bot 的评价。"
        "这类场景不要提另一个 bot 的名字、姐姐、妹妹或其他称谓，除非用户另行要求你评价对方或解释双子关系。"
        "也不要猜测另一个 bot 的心情、反应或态度，例如“她也很开心”“她肯定在偷笑”。"
        "“不替另一个 bot 发言”只表示不能冒充对方、代发对方原话、替对方认错或承诺修改；不表示当前 bot 可以拒绝完成自己被点到的普通请求。"
        "可以自然提到她也被叫到了，但不要解释调度机制。"
    )


def build_delegated_comment_prompt_text(
    *,
    current_id: str,
    responder_id: str,
    original_text: str,
    response_text: str,
) -> str:
    current_name = BOT_DISPLAY_NAMES.get(str(current_id or "").strip(), "当前棉花糖")
    current_relation = BOT_RELATION_NAMES.get(str(current_id or "").strip(), "当前这只")
    responder_name = BOT_DISPLAY_NAMES.get(str(responder_id or "").strip(), "另一个棉花糖")
    return "\n".join(
        [
            "这是双棉花糖代班后的短评论任务。",
            f"你是 {current_name}，也就是原本被用户叫到的{current_relation}。",
            f"{responder_name} 已经用她自己的身份代班回答了。",
            "你现在只能基于原消息和对方回复，用第一人称做一句有实质内容的短评论，不能重新完整回答原问题。",
            "不要说“接住”“我看到了”“已经处理啦”“我补一句”这类空话。",
            "不要再说自己在忙，也不要把自己描述成正在被别人代班的第三人称。",
            "如果对方回复已经跑偏、瞎编或替你表态，你要轻轻纠正核心点，不要继续顺着错设定演。",
            "语气偏 QQ 群日常、轻松一点，但结论要贴合内容。",
            f"原消息：{original_text}",
            f"对方回复：{response_text}",
        ]
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
