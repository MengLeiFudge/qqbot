from __future__ import annotations

from pathlib import Path
import re

from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.rule import Rule

from qqbot.config import load_settings
from qqbot.services.arcaea_record_apk_downloader import ArcaeaRecordApkDownloader
from qqbot.services.arc_apk_update_service import ArcApkUpdateManager
from qqbot.services.arc_alias_service import load_song_titles
from qqbot.services.arc_event_service import ArcEventService, _fetch_latest_arc_version
from qqbot.services.arc_guess_service import ArcGuessService
from qqbot.services.arc_service import ArcService
from qqbot.services.arc_constant_service import ArcConstantService
from qqbot.services.async_tools import run_blocking
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.feature_catalog import get_feature_by_menu_key
from qqbot.services.message_delivery import finish_split_text, send_split_text
from qqbot.services.offline_message_gate import is_before_onebot_connect
from qqbot.services.settings_store import get_settings_store

arc_recommend_matcher = on_regex(
    r"^arctj\s*[0-9]+(\.[0-9]+)?$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
arc_guess_start_matcher = on_regex(
    r"^(arczm|zm)(\s*[1-9][0-9]*)?$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
arc_guess_art_start_matcher = on_regex(
    r"^(arcqh|qh)(\s*(?:[1-9][0-9]*|(?i:max)))?$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
arc_guess_art_tile_matcher = on_regex(
    r"^arcqh\s*(bt|补图)$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
ARC_GUESS_ANSWER_PATTERN = r"^\s*(?:猜\s*)?[1-9][0-9]*\s*.+\s*$"

arc_guess_reveal_matcher = on_regex(
    r"^(arcjx|jx)$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
arc_activity_matcher = on_regex(
    r"^arc(hd|tz)$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)
arc_apk_update_matcher = on_regex(
    r"^(xz|arcxz)$",
    priority=13,
    block=True,
    rule=direct_command_rule(),
)

_ARC_APK_UPDATE_MANAGER: ArcApkUpdateManager | None = None


def get_arc_feature():
    return get_feature_by_menu_key("Arc")


def get_arc_service() -> ArcService:
    settings = load_settings()
    return ArcService(settings.arc_assets_root)


def get_arc_constant_service() -> ArcConstantService:
    settings = load_settings()
    return ArcConstantService(settings.data_root / "data" / "arc" / "constants.json")


def load_arc_song_titles() -> list[dict[str, str]]:
    settings = load_settings()
    return load_song_titles(settings.arc_assets_root / "官谱" / "songlist")


def get_arc_guess_service() -> ArcGuessService:
    settings = load_settings()
    return ArcGuessService(
        assets_root=settings.arc_assets_root,
        alias_cache_path=settings.data_root / "data" / "arc" / "guess_aliases.json",
        state_path=settings.data_root / "data" / "arc" / "guess_sessions.json",
    )


def get_arc_event_service() -> ArcEventService:
    settings = load_settings()
    return ArcEventService(timezone=settings.timezone)


def get_arc_apk_update_manager() -> ArcApkUpdateManager:
    global _ARC_APK_UPDATE_MANAGER
    if _ARC_APK_UPDATE_MANAGER is None:
        settings = load_settings()
        _ARC_APK_UPDATE_MANAGER = ArcApkUpdateManager(
            state_path=settings.data_root / "data" / "arc" / "background_state.json",
            version_fetcher=_fetch_latest_arc_version,
            downloader=ArcaeaRecordApkDownloader(
                project_root=settings.arcaea_record_root,
                target_dir=settings.arc_assets_root,
                maven_command=settings.arcaea_record_maven,
                java_home=settings.arcaea_record_java_home,
            ),
            timezone_name=settings.timezone,
        )
    return _ARC_APK_UPDATE_MANAGER


async def call_arc_service(method, *args, **kwargs):
    return await run_blocking(method, *args, **kwargs)


def is_arc_activity_command(text: str) -> bool:
    return text.strip() in {"archd", "arctz"}


def is_arc_apk_update_command(text: str) -> bool:
    return text.strip() in {"xz", "arcxz"}


def parse_arc_recommend_ptt(text: str) -> float | None:
    match = re.fullmatch(r"arctj\s*([0-9]+(?:\.[0-9]+)?)", text.strip())
    if match is None:
        return None
    return float(match.group(1))


def parse_arc_guess_start_count(text: str) -> int | None:
    match = re.fullmatch(r"(?:arczm|zm)\s*([1-9][0-9]*)?", text.strip())
    if match is None:
        return None
    if not match.group(1):
        return 10
    return int(match.group(1))


def is_arc_guess_art_start_command(text: str) -> bool:
    return re.fullmatch(r"(arcqh|qh)(\s*(?:[1-9][0-9]*|max))?", text.strip(), re.IGNORECASE) is not None


def parse_arc_guess_art_grid_size(text: str) -> int | str | None:
    match = re.fullmatch(r"(?:arcqh|qh)\s*([1-9][0-9]*|max)", text.strip(), re.IGNORECASE)
    if match is None:
        return None
    raw_value = match.group(1).lower()
    if raw_value == "max":
        return "max"
    return int(raw_value)


def is_arc_guess_add_art_tile_command(text: str) -> bool:
    return text.strip() in {"qh", "arcqh", "arcqh bt", "arcqh补图", "arcqh 补图"}


def is_arc_guess_reveal_command(text: str) -> bool:
    return text.strip() in {"arcjx", "jx"}


def parse_arc_open_letter(text: str) -> str | None:
    match = re.fullmatch(r"开\s*(\S)", text.strip())
    if match is None:
        return None
    return match.group(1).lower()


def parse_arc_guess_submission(text: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(?:猜\s*)?([1-9][0-9]*)\s*(.+)", text.strip())
    if match is None:
        return None
    return int(match.group(1)), match.group(2).strip()


def parse_arc_guess_art_submission(text: str) -> str | None:
    stripped = text.strip()
    if re.fullmatch(ARC_GUESS_ANSWER_PATTERN, stripped):
        return None
    match = re.fullmatch(r"猜\s*(.+)", stripped)
    if match is not None:
        return match.group(1).strip()
    if stripped.startswith("猜"):
        return None
    if is_arc_guess_control_command(stripped):
        return None
    if not stripped:
        return None
    return stripped


def is_arc_guess_control_command(text: str) -> bool:
    stripped = text.strip()
    return (
        parse_arc_recommend_ptt(stripped) is not None
        or parse_arc_guess_start_count(stripped) is not None
        or is_arc_guess_art_start_command(stripped)
        or is_arc_guess_add_art_tile_command(stripped)
        or parse_arc_open_letter(stripped) is not None
        or is_arc_guess_reveal_command(stripped)
        or is_arc_activity_command(stripped)
        or is_arc_apk_update_command(stripped)
    )


async def has_active_arc_art_session(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if is_before_onebot_connect(getattr(event, "time", None)):
        return False
    text = event.get_plaintext().strip()
    if text.startswith("猜"):
        return False
    answer = parse_arc_guess_art_submission(text)
    if answer is None:
        return False
    if not await ensure_arc_enabled(event):
        return False
    service = get_arc_guess_service()
    session = service.get_session(get_arc_room_id(event))
    if session is None or session.mode != "art":
        return False
    return service.is_plausible_answer(answer, session.art_aliases or [])


async def has_active_arc_guess_mode(event: MessageEvent, mode: str) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if is_before_onebot_connect(getattr(event, "time", None)):
        return False
    if not await ensure_arc_enabled(event):
        return False
    service = get_arc_guess_service()
    session = service.get_session(get_arc_room_id(event))
    return session is not None and session.mode == mode


async def has_active_arc_letter_session(event: MessageEvent) -> bool:
    return await has_active_arc_guess_mode(event, "letters")


async def has_active_arc_letter_answer(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return False
    if parse_arc_guess_submission(event.get_plaintext()) is None:
        return False
    return await has_active_arc_guess_mode(event, "letters")


async def has_active_arc_art_game(event: MessageEvent) -> bool:
    return await has_active_arc_guess_mode(event, "art")


arc_guess_letter_matcher = on_regex(
    r"^开\s*\S$",
    priority=13,
    block=True,
    rule=Rule(has_active_arc_letter_session),
)
arc_guess_answer_matcher = on_message(
    priority=13,
    block=True,
    rule=Rule(has_active_arc_letter_answer),
)
arc_guess_art_answer_matcher = on_regex(
    r"^猜\s*.+$",
    priority=14,
    block=True,
    rule=Rule(has_active_arc_art_game),
)
arc_guess_art_plain_answer_matcher = on_message(priority=14, block=True, rule=Rule(has_active_arc_art_session))


def build_arc_guess_message(result) -> Message | str:
    image_path = getattr(result, "image_path", None)
    text = getattr(result, "text", str(result))
    if image_path is None:
        return text
    return Message([MessageSegment.image(Path(image_path).as_posix()), MessageSegment.text(f"\n{text}")])


def can_start_arc_guess(event) -> bool:
    return getattr(event, "group_id", None) is not None


def get_arc_room_id(event: MessageEvent) -> int:
    if hasattr(event, "group_id") and getattr(event, "group_id") is not None:
        return int(getattr(event, "group_id"))
    return int(event.get_user_id())


async def ensure_arc_enabled(event: MessageEvent) -> bool:
    feature = get_arc_feature()
    if feature is None:
        return False
    store = get_settings_store()
    return store.get_group_feature_state(getattr(event, "group_id", 0), feature)


def get_player_name(event: MessageEvent) -> str:
    sender = getattr(event, "sender", None)
    if sender is None:
        return event.get_user_id()
    card = str(getattr(sender, "card", "") or "").strip()
    if card:
        return card
    nickname = str(getattr(sender, "nickname", "") or "").strip()
    if nickname:
        return nickname
    return event.get_user_id()


@arc_recommend_matcher.handle()
async def handle_arc_recommend(event: MessageEvent) -> None:
    if not await ensure_arc_enabled(event):
        await arc_recommend_matcher.finish("本群还没有开启 Arc 功能哦！")

    text = event.get_plaintext().strip()
    ptt = parse_arc_recommend_ptt(text)
    if ptt is None:
        await arc_recommend_matcher.finish("用法：arctj10.5")
    service = get_arc_service()
    constant_service = get_arc_constant_service()
    await call_arc_service(constant_service.sync_missing_constants, load_arc_song_titles())
    constant_cache = await call_arc_service(constant_service.load_constant_cache)
    chart = await call_arc_service(service.recommend_chart_by_ptt, ptt, constant_cache)
    text_message = await call_arc_service(service.build_recommendation_text, ptt, chart)
    image_uri = await call_arc_service(service.build_recommendation_image_uri, chart)
    if image_uri:
        await arc_recommend_matcher.finish(
            Message([MessageSegment.image(image_uri), MessageSegment.text(f"\n{text_message}")])
        )
    await arc_recommend_matcher.finish(text_message)


@arc_guess_start_matcher.handle()
async def handle_arc_guess_start(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_start_matcher.finish("Arc 猜歌只能在群聊中开始。")
    if not await ensure_arc_enabled(event):
        await arc_guess_start_matcher.finish("本群还没有开启 Arc 功能哦！")

    count = parse_arc_guess_start_count(event.get_plaintext().strip())
    if count is None:
        await arc_guess_start_matcher.finish("用法：arczm5")

    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    message = await call_arc_service(service.start_game, room_id, count)
    await arc_guess_start_matcher.finish(message)


@arc_guess_art_start_matcher.handle()
async def handle_arc_guess_art_start(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_art_start_matcher.finish("Arc 猜歌只能在群聊中开始。")
    if not await ensure_arc_enabled(event):
        await arc_guess_art_start_matcher.finish("本群还没有开启 Arc 功能哦！")

    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    grid_size = parse_arc_guess_art_grid_size(event.get_plaintext().strip())
    result = await call_arc_service(service.start_or_open_art_tile, room_id, grid_size)
    await arc_guess_art_start_matcher.finish(build_arc_guess_message(result))


@arc_guess_art_tile_matcher.handle()
async def handle_arc_guess_art_tile(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_art_tile_matcher.finish("Arc 猜歌只能在群聊中进行。")
    if not await ensure_arc_enabled(event):
        await arc_guess_art_tile_matcher.finish("本群还没有开启 Arc 功能哦！")

    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    result = await call_arc_service(service.start_or_open_art_tile, room_id)
    await arc_guess_art_tile_matcher.finish(build_arc_guess_message(result))


@arc_guess_letter_matcher.handle()
async def handle_arc_guess_letter(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_letter_matcher.finish("Arc 猜歌只能在群聊中进行。")
    if not await ensure_arc_enabled(event):
        await arc_guess_letter_matcher.finish("本群还没有开启 Arc 功能哦！")

    letter = parse_arc_open_letter(event.get_plaintext().strip())
    if letter is None:
        await arc_guess_letter_matcher.finish("用法：开*")
    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    message = await call_arc_service(service.open_letter, room_id, letter)
    await arc_guess_letter_matcher.finish(build_arc_guess_message(message))


@arc_guess_answer_matcher.handle()
async def handle_arc_guess_answer(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_answer_matcher.finish("Arc 猜歌只能在群聊中进行。")
    if not await ensure_arc_enabled(event):
        await arc_guess_answer_matcher.finish("本群还没有开启 Arc 功能哦！")

    payload = parse_arc_guess_submission(event.get_plaintext().strip())
    if payload is None:
        await arc_guess_answer_matcher.finish("用法：猜2 骨折光")
    question_index, answer = payload
    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    player_name = get_player_name(event)
    message = await call_arc_service(service.guess, room_id, question_index, answer, player_name)
    await arc_guess_answer_matcher.finish(build_arc_guess_message(message))


async def finish_arc_guess_art_answer(matcher, event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await matcher.finish("Arc 猜歌只能在群聊中进行。")
    if not await ensure_arc_enabled(event):
        await matcher.finish("本群还没有开启 Arc 功能哦！")

    answer = parse_arc_guess_art_submission(event.get_plaintext().strip())
    if answer is None:
        await matcher.finish("用法：直接发送曲名，例如 Quon")
    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    player_name = get_player_name(event)
    result = await call_arc_service(service.guess_art, room_id, answer, player_name)
    await matcher.finish(build_arc_guess_message(result))


@arc_guess_art_answer_matcher.handle()
async def handle_arc_guess_art_answer(event: MessageEvent) -> None:
    await finish_arc_guess_art_answer(arc_guess_art_answer_matcher, event)


@arc_guess_art_plain_answer_matcher.handle()
async def handle_arc_guess_art_plain_answer(event: MessageEvent) -> None:
    await finish_arc_guess_art_answer(arc_guess_art_plain_answer_matcher, event)


@arc_guess_reveal_matcher.handle()
async def handle_arc_guess_reveal(event: MessageEvent) -> None:
    if not can_start_arc_guess(event):
        await arc_guess_reveal_matcher.finish("Arc 猜歌只能在群聊中进行。")
    if not await ensure_arc_enabled(event):
        await arc_guess_reveal_matcher.finish("本群还没有开启 Arc 功能哦！")

    service = get_arc_guess_service()
    room_id = get_arc_room_id(event)
    message = await call_arc_service(service.reveal_answers, room_id)
    await arc_guess_reveal_matcher.finish(build_arc_guess_message(message))


@arc_activity_matcher.handle()
async def handle_arc_activity(event: MessageEvent) -> None:
    if not await ensure_arc_enabled(event):
        await arc_activity_matcher.finish("本群还没有开启 Arc 功能哦！")

    service = get_arc_event_service()
    events = await call_arc_service(service.fetch_active_events)
    messages = await call_arc_service(service.render_event_messages, events)
    await send_arc_event_messages(
        arc_activity_matcher,
        messages,
        group_id=getattr(event, "group_id", None),
    )


@arc_apk_update_matcher.handle()
async def handle_arc_apk_update(event: MessageEvent) -> None:
    settings = load_settings()
    if int(event.get_user_id()) != settings.author_qq:
        await arc_apk_update_matcher.finish("只有作者可以使用这个指令。")
    manager = get_arc_apk_update_manager()
    message = await manager.query_and_update()
    await arc_apk_update_matcher.finish(message)


async def send_arc_event_messages(
    matcher,
    messages: list[str],
    *,
    group_id: int | str | None = None,
) -> None:
    if not messages:
        await finish_split_text(matcher, "当前没有活动梯子。", group_id=group_id)
        return
    if len(messages) == 1:
        await finish_split_text(matcher, messages[0], group_id=group_id)
        return
    for message in messages[:-1]:
        await send_split_text(matcher, message, group_id=group_id)
    await finish_split_text(matcher, messages[-1], group_id=group_id)
