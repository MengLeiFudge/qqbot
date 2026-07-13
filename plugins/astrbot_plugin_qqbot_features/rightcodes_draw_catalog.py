from __future__ import annotations

import re


RIGHTCODES_DRAW_CATALOG_TEXT = """RightCodes 生图接口知识库：
资料来源：Right Code 官方文档 https://docs.right.codes/docs/rc_draw/ ，最近核对 2026-07-13。

基础信息：
- 统一基础地址：https://www.right.codes/draw
- 统一鉴权头：Authorization: Bearer sk-xxxxx
- 总览页列出两个入口：/v1/chat/completions 和 /v1/images/generations。

/v1/images/generations：
- 用途：OpenAI 原生图片生成接口。如果用户只是要生成图并拿图片直链，优先推荐这个接口。
- 方法：POST /v1/images/generations
- 字段：model 必填，prompt 必填，image 可选，size 可选，response_format 可选。
- size 支持形如 1024x1024 的像素写法；用户问 body 里怎么写 1024x1024 时，明确回答写 "size": "1024x1024"。
- 示例 body：
{
  "model": "gpt-image-2",
  "prompt": "一只白猫",
  "image": [],
  "size": "1024x1024",
  "response_format": "url"
}
- 返回里 data[0].url 是常用图片直链。

/v1/chat/completions：
- 用途：兼容 OpenAI 聊天格式，支持纯文本和带图提问。用户要流式输出、避免长请求被 Cloudflare 超时影响时，建议用这个接口并设置 stream=true。
- 方法：POST /v1/chat/completions
- 纯文本 body 结构是 model、stream、messages；messages 里 role=user，content 可以是字符串。
- 带图提问时 content 是数组，包含 type=text 和 type=image_url。
- stream=true 时按 SSE 分片返回，看 choices[0].delta.content，最后一个 chunk 会带 usage。
- chat/completions 文档没有把 size 列为独立图片生成字段；如果用户坚持走 chat/completions 控制尺寸，建议把 1024x1024、方图、1K 写进 content 文本里。

模型说明：
- gpt-image-2：$0.04/次，OpenAI 画图模型，支持 1K。
- gpt-image-2-vip：$0.13/次，OpenAI 官方直连，当前支持 1K；官方已停止 2K、4K。
- nano-banana：$0.14/次，即 gemini-2.5-flash-image，支持 1K。
- nano-banana-2：$0.12/次，即 gemini-3.1-flash-image-preview，支持 1K、2K、4K。
- nano-banana-2-lite：$0.05/次，即 gemini-3.1-flash-lite-image，支持 1K。
- nano-banana-pro：$0.18/次，即 gemini-3-pro-image-preview，支持 1K、2K、4K。

回答风格要求：
- 回答 RightCodes 生图接口问题时，区分 images/generations 和 chat/completions，不要说“没有明确图像参数位”。
- 允许输出保留缩进的 JSON 示例；这是 QQ 纯文本，不要包 Markdown 代码块，不要加 ```。
- 如用户问“body 里写什么”，直接给可复制 JSON。"""


_RIGHTCODES_DRAW_CATALOG_KEYWORDS = (
    "rightcodes",
    "right code",
    "right.codes",
    "docs.right.codes",
    "gpt-image-2",
    "gpt-image-2-vip",
    "nano-banana",
    "nano banana",
    "画图接口",
    "生图接口",
    "图片生成",
    "图像生成",
    "images/generations",
    "chat/completions",
    "1024x1024",
    "2048x2048",
    "4096x4096",
)


def should_inject_rightcodes_draw_catalog(query: str) -> bool:
    normalized = normalize_catalog_query(query)
    if not normalized:
        return False
    if any(keyword in normalized for keyword in _RIGHTCODES_DRAW_CATALOG_KEYWORDS):
        return True
    if "size" in normalized and any(term in normalized for term in ("body", "json", "prompt", "model")):
        return True
    if re.search(r"\b(?:1k|2k|4k)\b", normalized) and any(
        term in normalized for term in ("生图", "画图", "图片", "图像", "draw")
    ):
        return True
    return False


def normalize_catalog_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "").strip().lower())


def format_rightcodes_draw_catalog_injection(query: str) -> str:
    return f"{RIGHTCODES_DRAW_CATALOG_TEXT}\n\n用户当前问题：{str(query or '').strip()}"
