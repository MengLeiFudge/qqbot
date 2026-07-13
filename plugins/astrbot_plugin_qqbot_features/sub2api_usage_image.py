from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

from .sub2api_usage import Sub2APIAccountUsage
from .sub2api_usage import Sub2APIUsageSnapshot
from .sub2api_usage import Sub2APIUserUsage
from .sub2api_usage import format_datetime
from .sub2api_usage import format_sub2api_user_name
from .sub2api_usage import format_usage_window


CANVAS_WIDTH = 1240
MARGIN = 48
BACKGROUND = (242, 246, 251)
PANEL = (255, 255, 255)
INK = (27, 38, 54)
MUTED = (91, 105, 124)
BORDER = (210, 220, 232)
GOOD = (24, 132, 92)
WARNING = (186, 112, 18)
ERROR = (192, 63, 64)
ROW_HEIGHT = 50


def render_sub2api_usage_image(*, snapshot: Sub2APIUsageSnapshot, output_dir: Path) -> Path:
    payload = {
        "kind": "sub2api-usage",
        "snapshot": asdict(snapshot),
        "version": 1,
    }
    image_path = _cached_path(output_dir, payload)
    if image_path.is_file():
        return image_path

    fonts = _Fonts(_find_font_path())
    account_heights = [_account_height(usage) for usage in snapshot.accounts]
    status_height = _status_height(snapshot)
    user_height = _user_table_height(snapshot.users)
    canvas_height = 172 + status_height + 76 + sum(account_heights) + 76 + user_height + 48
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.text((MARGIN, 36), "Sub2API 用量报告", font=fonts.title, fill=INK)
    draw.text(
        (MARGIN + 2, 98),
        "账号额度为后台主动刷新缓存；用户消费为实际扣费，按 Asia/Shanghai 自然日统计。",
        font=fonts.subtitle,
        fill=MUTED,
    )

    y = 156
    y = _draw_status(draw, fonts, snapshot, y)
    y += 34
    draw.text((MARGIN, y), f"账号用量  共 {len(snapshot.accounts)} 个", font=fonts.section, fill=INK)
    y += 44
    if not snapshot.accounts:
        y = _draw_empty_panel(draw, fonts, y, "暂无账号缓存。")
    else:
        for usage, height in zip(snapshot.accounts, account_heights):
            _draw_account_panel(draw, fonts, usage, y, height)
            y += height + 16

    y += 18
    draw.text((MARGIN, y), f"用户实际消费榜  共 {len(snapshot.users)} 人", font=fonts.section, fill=INK)
    y += 44
    _draw_user_table(draw, fonts, snapshot.users, y)

    _save(image, image_path)
    return image_path


def _cached_path(output_dir: Path, payload: dict[str, object]) -> Path:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"sub2api-usage-{digest}.png"


def _status_height(snapshot: Sub2APIUsageSnapshot) -> int:
    lines = _status_lines(snapshot)
    return 30 + sum(max(1, len(_wrap_text(text, 66))) * 30 for text, _ in lines)


def _status_lines(snapshot: Sub2APIUsageSnapshot) -> list[tuple[str, tuple[int, int, int]]]:
    lines: list[tuple[str, tuple[int, int, int]]] = []
    if snapshot.accounts_refreshed_at:
        lines.append((f"账号刷新：{format_datetime(snapshot.accounts_refreshed_at)}", GOOD))
    else:
        lines.append(("账号刷新：暂无成功数据", WARNING))
    if snapshot.accounts_error:
        lines.append((f"账号刷新失败，已保留上次成功缓存：{snapshot.accounts_error}", ERROR))
    if snapshot.users_refreshed_at:
        lines.append((f"用户刷新：{format_datetime(snapshot.users_refreshed_at)}", GOOD))
    else:
        lines.append(("用户刷新：暂无成功数据", WARNING))
    if snapshot.users_error:
        lines.append((f"用户刷新失败，已保留上次成功缓存：{snapshot.users_error}", ERROR))
    return lines


def _draw_status(
    draw: ImageDraw.ImageDraw,
    fonts: _Fonts,
    snapshot: Sub2APIUsageSnapshot,
    y: int,
) -> int:
    height = _status_height(snapshot)
    _rounded_rect(draw, (MARGIN, y, CANVAS_WIDTH - MARGIN, y + height), radius=12, fill=PANEL, outline=BORDER)
    line_y = y + 16
    for text, color in _status_lines(snapshot):
        for line in _wrap_text(text, 66):
            draw.text((MARGIN + 22, line_y), line, font=fonts.small, fill=color)
            line_y += 30
    return y + height


def _account_height(usage: Sub2APIAccountUsage) -> int:
    rows = 1
    rows += max(1, len(_wrap_text(_account_meta(usage), 62)))
    rows += max(1, len(_wrap_text(f"5h：{format_usage_window(usage.five_hour)}", 62)))
    rows += max(1, len(_wrap_text(f"7d：{format_usage_window(usage.seven_day)}", 62)))
    if usage.last_used_at:
        rows += 1
    if usage.updated_at:
        rows += 1
    if usage.error:
        rows += max(1, len(_wrap_text(f"错误：{usage.error}", 62)))
    return 28 + rows * 30 + 16


def _draw_account_panel(
    draw: ImageDraw.ImageDraw,
    fonts: _Fonts,
    usage: Sub2APIAccountUsage,
    y: int,
    height: int,
) -> None:
    _rounded_rect(draw, (MARGIN, y, CANVAS_WIDTH - MARGIN, y + height), radius=12, fill=PANEL, outline=BORDER)
    title = usage.name or f"账号 {usage.account_id}"
    draw.text((MARGIN + 22, y + 16), title, font=fonts.body_bold, fill=INK)
    text_y = y + 54
    rows = [
        (_account_meta(usage), MUTED),
        (f"5h：{format_usage_window(usage.five_hour)}", INK),
        (f"7d：{format_usage_window(usage.seven_day)}", INK),
    ]
    if usage.last_used_at:
        rows.append((f"最近使用：{usage.last_used_at}", MUTED))
    if usage.updated_at:
        rows.append((f"上游更新时间：{usage.updated_at}", MUTED))
    if usage.error:
        rows.append((f"错误：{usage.error}", ERROR))
    for text, color in rows:
        for line in _wrap_text(text, 62):
            draw.text((MARGIN + 22, text_y), line, font=fonts.small, fill=color)
            text_y += 30


def _account_meta(usage: Sub2APIAccountUsage) -> str:
    parts = []
    if usage.platform:
        parts.append(usage.platform)
    if usage.account_type:
        parts.append(usage.account_type)
    if usage.status:
        parts.append(usage.status)
    if usage.current_concurrency is not None:
        parts.append(f"并发 {usage.current_concurrency}")
    return "状态：" + (" / ".join(parts) if parts else "未提供")


def _user_table_height(users: tuple[Sub2APIUserUsage, ...]) -> int:
    return 68 + max(1, len(users)) * ROW_HEIGHT


def _draw_user_table(
    draw: ImageDraw.ImageDraw,
    fonts: _Fonts,
    users: tuple[Sub2APIUserUsage, ...],
    y: int,
) -> None:
    height = _user_table_height(users)
    _rounded_rect(draw, (MARGIN, y, CANVAS_WIDTH - MARGIN, y + height), radius=12, fill=PANEL, outline=BORDER)
    header_bottom = y + 68
    draw.rounded_rectangle((MARGIN + 1, y + 1, CANVAS_WIDTH - MARGIN - 1, header_bottom), radius=11, fill=(232, 240, 250))
    name_x = MARGIN + 28
    seven_x = 850
    thirty_x = 1020
    draw.text((name_x, y + 20), "用户", font=fonts.body_bold, fill=INK)
    draw.text((seven_x, y + 20), "7d 实际消费", font=fonts.body_bold, fill=INK)
    draw.text((thirty_x, y + 20), "30d 实际消费", font=fonts.body_bold, fill=INK)
    if not users:
        draw.text((name_x, header_bottom + 16), "暂无用户缓存。", font=fonts.body, fill=MUTED)
        return
    row_y = header_bottom
    for index, usage in enumerate(users, start=1):
        if index % 2 == 0:
            draw.rectangle((MARGIN + 1, row_y, CANVAS_WIDTH - MARGIN - 1, row_y + ROW_HEIGHT), fill=(248, 250, 253))
        label = _ellipsize(draw, fonts.body, f"#{index}  {format_sub2api_user_name(usage)}", 680)
        draw.text((name_x, row_y + 13), label, font=fonts.body, fill=INK)
        draw.text((seven_x, row_y + 13), f"${usage.seven_day_actual_cost:.2f}", font=fonts.body, fill=GOOD)
        draw.text((thirty_x, row_y + 13), f"${usage.thirty_day_actual_cost:.2f}", font=fonts.body, fill=GOOD)
        draw.line((MARGIN + 1, row_y + ROW_HEIGHT, CANVAS_WIDTH - MARGIN - 1, row_y + ROW_HEIGHT), fill=BORDER, width=1)
        row_y += ROW_HEIGHT


def _draw_empty_panel(draw: ImageDraw.ImageDraw, fonts: _Fonts, y: int, text: str) -> int:
    height = 72
    _rounded_rect(draw, (MARGIN, y, CANVAS_WIDTH - MARGIN, y + height), radius=12, fill=PANEL, outline=BORDER)
    draw.text((MARGIN + 22, y + 22), text, font=fonts.body, fill=MUTED)
    return y + height


def _wrap_text(text: str, width: int) -> list[str]:
    wrapped: list[str] = []
    for raw_line in str(text or "").splitlines() or [""]:
        line = raw_line.strip()
        if line:
            wrapped.extend(textwrap.wrap(line, width=width, break_long_words=True, replace_whitespace=False))
    return wrapped or [""]


def _ellipsize(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, text: str, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    ellipsis = "..."
    value = text
    while value and draw.textlength(value + ellipsis, font=font) > max_width:
        value = value[:-1]
    return value + ellipsis


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    radius: int,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=2)


class _Fonts:
    def __init__(self, font_path: str | None) -> None:
        self.title = _font(font_path, 46)
        self.subtitle = _font(font_path, 24)
        self.section = _font(font_path, 31)
        self.body = _font(font_path, 25)
        self.body_bold = _font(font_path, 27)
        self.small = _font(font_path, 22)


def _find_font_path() -> str | None:
    candidates = (
        os.environ.get("QQBOT_MENU_FONT", ""),
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/mnt/c/Windows/Fonts/msyh.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    )
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def _font(font_path: str | None, size: int) -> ImageFont.ImageFont:
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _save(image: Image.Image, path: Path) -> None:
    tmp_path = path.with_suffix(".tmp.png")
    image.save(tmp_path, "PNG", optimize=True)
    tmp_path.replace(path)
