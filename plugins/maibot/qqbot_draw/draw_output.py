"""校验 CPA 生成结果，并在发送前保存完整图片。"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import asyncio
import base64
import os
import uuid

import httpx
from PIL import Image


MAX_OUTPUT_BYTES = 32 * 1024 * 1024


async def load_generated_image(source: str, client: httpx.AsyncClient, *, gif: bool = False) -> bytes:
    """在生图总截止时间内取得并校验 PNG 或 GIF。"""
    if source.startswith("data:image/"):
        header, _, encoded = source.partition(",")
        if ";base64" not in header or len(encoded) > (MAX_OUTPUT_BYTES + 2) // 3 * 4:
            raise ValueError("生图结果格式无效或超过 32 MiB")
        image = base64.b64decode(encoded, validate=True)
    elif source.startswith(("http://", "https://")):
        content = bytearray()
        async with client.stream("GET", source, follow_redirects=True) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > MAX_OUTPUT_BYTES:
                    raise ValueError("生图结果超过 32 MiB")
        image = bytes(content)
    else:
        raise ValueError("生图服务没有返回可读取的图片")
    if not image or len(image) > MAX_OUTPUT_BYTES:
        raise ValueError("生图结果为空或超过 32 MiB")
    if gif:
        return await asyncio.to_thread(_validate_gif, image)
    return await asyncio.to_thread(_normalize_generated_png, image)


def _validate_gif(image: bytes) -> bytes:
    with Image.open(BytesIO(image)) as result:
        if result.format != "GIF" or not result.is_animated:
            raise ValueError("生图服务没有返回有效动图")
        result.verify()
    return image


def _normalize_generated_png(image: bytes) -> bytes:
    """保留有效 PNG 原字节；其他格式转成 PNG，保持实际尺寸，兼容上游忽略请求参数。"""
    with Image.open(BytesIO(image)) as result:
        if result.format == "PNG":
            result.verify()
            return image
        with result.convert("RGBA") as converted:
            output = BytesIO()
            converted.save(output, format="PNG")
            image = output.getvalue()
    if len(image) > MAX_OUTPUT_BYTES:
        raise ValueError("生图结果转换为 PNG 后超过 32 MiB")
    return image


def save_generated_image(image: bytes, data_root: Path, *, gif: bool = False) -> Path:
    """按日期和唯一文件名保存到现有运行数据根，完整写入后才发布。"""
    now = datetime.now()
    directory = data_root / "draw" / "outputs" / now.strftime("%Y%m%d")
    directory.mkdir(parents=True, exist_ok=True)
    suffix = "gif" if gif else "png"
    path = directory / f"{now:%H%M%S_%f}_{uuid.uuid4().hex}.{suffix}"
    partial = path.with_suffix(".part")
    try:
        with partial.open("xb") as stream:
            stream.write(image)
            stream.flush()
            os.fsync(stream.fileno())
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path
