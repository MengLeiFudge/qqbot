from __future__ import annotations

import re


CATALOG_MARKER = "【RightCodes 生图接口知识】"
RIGHTCODES_DRAW_CATALOG_TEXT = """【RightCodes 生图接口知识】

当前 bot 生图功能：
- 生图模型从 CPA 的图片模型列表读取。使用“生图模型”或“生图价格”查询现行模型和价格，用“切换生图模型 模型名”修改偏好。旧模型下架时会尝试其他可用模型。普通请求生成一张，豆豆眼四张共扣一次。
- 指令为文生图、图生图和头像生图，画幅写在“生”和“图”之间，尺寸档位跟在“图”后，例如“文生竖图2k 一只白猫”“图生动图 换成水彩”。无头像目标时使用发送者头像，真实艾特紧跟命令。积分用“查看积分”或“积分排行”查询。
- 群消息继续累计积分；从首次请求开始扣费，全部生成失败或超时原额退款；部分成功交付全部已有成品，不自动重生。
- 普通标准指令原样提交提示词。图生图使用单张原图，当前附件优先于引用图片。原图获取失败时积分保留。
- 生成豆豆眼头像：固定将发送者本人的头像转为豆豆眼，使用完整韩文v1、中文v3各生成两张，四个独立请求并行，完成后全部发送。原有生图入口及自然语言改图请求含“豆豆眼”并指定头像或图片时，也完全换用该预设，不改写、不拼接。自然语言仍须识别为实际绘图意图，来源不明确先询问。
- 所有开工通知都会明确提示词来源：用户话语（无预设），或豆豆眼预设（完整固定原文）。
- 私聊或明确唤醒后的自然语言请求（如“画只猫”“帮我把我的头像改成水彩”）会先解析为文生图/图生图；完整请求直接开工并回显提示词和来源，歧义先询问，不扣积分。
- 普通聊天回复只能介绍用法或引导明确指令，不得声称已开始绘图、已扣分或已交付；实际执行由生图插件负责。
- 成品统一先保存再发送；保存失败仍尝试交付，并提示未保存。全部图片均未保存且发送失败时退积分，不重复生成。

仅在用户询问接口时说明以下技术信息：
- bot 使用本机 CPA 的 OpenAI Images 接口，API 根地址为 http://127.0.0.1:8317/v1。
- 鉴权使用 CPA 客户端 API Key；渠道选择与优先级由 CPA 配置管理。渠道模型要设置 image: true。
- 文生图：POST /images/generations，JSON body 示例：
{
  "model": "gpt-image-2.6",
  "prompt": "一只白猫",
  "n": 1,
  "size": "4096x4096",
  "response_format": "b64_json",
  "output_format": "png"
}
- 参考图：POST /images/edits，multipart/form-data 单张使用 image 文件字段，多张使用 image[] 文件字段，其余文本参数与文生图相同。
- 同一次 CPA 请求等待最终图片。RC 官方绘图接口另使用 /draw/v1/images/generations、JSON image 数组、async=true 和任务轮询；不能将该协议与当前 CPA Images 接口混用。
- 从返回 data[].b64_json 或 data[].url 取得图片。默认方图 4096x4096，支持 1k、2k、4k 和横竖画幅。

回答约束：模型、价格和用法问题只回答当前 bot 的功能，说明价格时使用人民币“元”。接口 body 问题直接给可复制 JSON，保留缩进，不使用 Markdown 代码围栏。"""

_KEYWORDS = (
    "rightcodes",
    "right code",
    "right.codes",
    "docs.right.codes",
    "gpt-image",
    "nano-banana",
    "nano banana",
    "画图接口",
    "画", "生图", "绘图", "头像", "改图",
    "生图接口",
    "图片生成",
    "图像生成",
    "images/generations",
    "images/edits",
    "generatecontent",
    "v1/tasks",
    "1024x1024",
    "2048x2048",
    "4096x4096",
)


def should_inject_draw_catalog(query: str) -> bool:
    normalized = normalize_catalog_query(query)
    if not normalized:
        return False
    if any(keyword in normalized for keyword in _KEYWORDS):
        return True
    if "size" in normalized and any(term in normalized for term in ("body", "json", "prompt", "model")):
        return True
    return bool(re.search(r"\b(?:1k|2k|4k)\b", normalized)) and any(
        term in normalized for term in ("生图", "画图", "图片", "图像", "draw")
    )


def normalize_catalog_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "").strip().lower())


def extract_current_query(messages: object) -> str:
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or str(message.get("role") or "").lower() != "user":
            continue
        text = flatten_message_content(message.get("content"))
        target_matches = re.findall(r"^- 发言内容：(.+)$", text, flags=re.MULTILINE)
        if target_matches:
            return target_matches[-1].strip()
        if text.strip():
            return text.strip()
    return ""


def inject_catalog_into_messages(messages: object) -> list[dict[str, object]] | None:
    if not isinstance(messages, list):
        return None
    normalized = [dict(message) for message in messages if isinstance(message, dict)]
    if len(normalized) != len(messages):
        return None
    if any(CATALOG_MARKER in flatten_message_content(message.get("content")) for message in normalized):
        return normalized
    for message in normalized:
        if str(message.get("role") or "").lower() != "system":
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = f"{content.rstrip()}\n\n{RIGHTCODES_DRAW_CATALOG_TEXT}"
            return normalized
    normalized.insert(0, {"role": "system", "content": RIGHTCODES_DRAW_CATALOG_TEXT})
    return normalized


def flatten_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and str(item.get("type") or "text").lower() == "text":
            parts.append(str(item.get("text") or ""))
    return "".join(parts)
