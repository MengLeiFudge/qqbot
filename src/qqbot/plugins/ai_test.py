from __future__ import annotations

from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.rule import Rule

from qqbot.config import RuntimeSettings, load_settings
from qqbot.services.ai_actions import AiActionExecutor
from qqbot.services.ai_command import (
    build_ai_conversation_key,
    parse_ai_model_command,
    should_handle_ai_chat,
)
from qqbot.services.ai_conversation_store import AiConversationStore
from qqbot.services.ai_gateway import AiRequest, AiResponse
from qqbot.services.ai_group_context_store import AiGroupContextStore, AiGroupMessageRecord
from qqbot.services.chat_memory_store import ChatMemoryFact, ChatMemoryRecord, ChatMemoryStore
from qqbot.services.ai_orchestrator import AiOrchestrator, AiOrchestratorContext
from qqbot.services.ai_profile_registry import list_enabled_profiles, load_ai_profiles
from qqbot.services.ai_runtime import build_ai_gateway, get_current_ai_profile_name
from qqbot.services.admin_service import AdminService
from qqbot.services.command_guard import direct_command_rule
from qqbot.services.group_nick_store import GroupNickStore
from qqbot.services.message_delivery import COLLAPSIBLE_TEXT_THRESHOLD_CHARS, finish_split_text
from qqbot.services.message_normalizer import NormalizedMessage, normalize_onebot_event
from qqbot.services.settings_store import SettingsStore, get_settings_store


ai_model_matcher = on_regex(
    r"(?i)^(AI模型|当前AI|切换AI\s+\S+)$",
    priority=10,
    block=True,
    rule=direct_command_rule(),
)
ai_chat_matcher = on_message(
    priority=70,
    block=True,
    rule=Rule(lambda event: should_handle_ai_chat(event, event.get_plaintext())),
)


@ai_model_matcher.handle()
async def handle_ai_model(event: MessageEvent) -> None:
    settings = load_settings()
    store = get_settings_store()
    if not store.is_bot_admin(int(event.get_user_id())):
        await ai_model_matcher.finish("只有 Bot 管理员才能切换 AI 模型。")

    command = parse_ai_model_command(event.get_plaintext())
    if command is None:
        return

    profiles = load_ai_profiles(settings.ai_profile_file)
    if command.action == "switch" and command.profile is not None:
        enabled_names = {profile.name for profile in list_enabled_profiles(profiles)}
        if command.profile not in enabled_names:
            await ai_model_matcher.finish(
                "未知或未启用的 AI 模型："
                f"{command.profile}\n可用：{', '.join(sorted(enabled_names)) or '无'}"
            )
        store.set_ai_provider(command.profile)

    current_profile = get_current_ai_profile_name(settings, store, profiles)
    enabled_profiles = ", ".join(profile.name for profile in list_enabled_profiles(profiles)) or "无"
    await ai_model_matcher.finish(
        f"当前 AI 模型：{current_profile}\n可用模型：{enabled_profiles}"
    )


@ai_chat_matcher.handle()
async def handle_ai(bot: Bot, event: MessageEvent) -> None:
    settings = load_settings()
    store = get_settings_store()
    normalized_message = normalize_onebot_event(event)
    prompt = normalized_message.text or normalized_message.outline

    if not settings.ai_enabled:
        await ai_chat_matcher.finish("AI 未启用。请设置 QQBOT_AI_ENABLED=true。")

    profiles = load_ai_profiles(settings.ai_profile_file)
    profile = get_current_ai_profile_name(settings, store, profiles)
    group_context_store = AiGroupContextStore(settings.data_root)
    conversation_store = AiConversationStore(
        settings.data_root,
        max_messages=settings.ai_max_context_messages,
    )
    key = build_ai_conversation_key(conversation_store, event, profile)
    history = conversation_store.load_messages(key)
    if should_omit_ai_history_for_scope_query(event, normalized_message):
        history = ()
    context_parts = list(
        build_ai_context(
            settings,
            event,
            group_context_store,
            normalized_message,
            settings_store=store,
        )
    )

    restart_scheduler = lambda: AdminService.from_settings(settings).schedule_restart()
    orchestrator = AiOrchestrator(
        data_root=settings.data_root,
        action_executor=AiActionExecutor(
            bot=bot,
            data_root=settings.data_root,
            self_restart_scheduler=restart_scheduler,
        ),
        self_restart_scheduler=restart_scheduler,
    )
    local_result = await orchestrator.handle(
        prompt,
        AiOrchestratorContext(
            actor_user_id=event.get_user_id(),
            group_id=str(getattr(event, "group_id", "")) or None,
            is_admin=store.is_bot_admin(int(event.get_user_id())),
        ),
        normalized_message,
    )
    group_id = getattr(event, "group_id", None)
    message_id = getattr(event, "message_id", None)
    user_id = event.get_user_id()
    if local_result.handled:
        local_message = format_local_ai_result(local_result)
        if (
            isinstance(local_message, str)
            and group_id is not None
            and len(local_message) > COLLAPSIBLE_TEXT_THRESHOLD_CHARS
        ):
            await ai_chat_matcher.send(
                build_ai_reply_notice_message(
                    group_id=group_id,
                    message_id=message_id,
                    user_id=user_id,
                )
            )
        elif isinstance(local_message, str):
            local_message = build_ai_reply_message(
                local_message,
                group_id=group_id,
                message_id=message_id,
                user_id=user_id,
            )
        await finish_split_text(
            ai_chat_matcher,
            local_message,
            group_id=group_id,
            bot=bot,
            title="棉花糖的本地处理结果",
        )

    context_parts.extend(part for part in local_result.extra_context if part.strip())

    try:
        gateway = build_ai_gateway(settings, profile)
        response = await gateway.complete(
            AiRequest(
                plugin_id="ai",
                capability="chat",
                prompt=prompt,
                user_id=event.get_user_id(),
                group_id=str(getattr(event, "group_id", "")) or None,
                image_urls=collect_message_image_urls(normalized_message),
                context=tuple(context_parts),
                history=history,
            )
        )
    except ValueError as exc:
        await ai_chat_matcher.finish(str(exc))

    if not response.fallback:
        conversation_store.append_turn(key, prompt, response.text)

    response_text = format_ai_response(
        profile,
        response,
        show_metrics=settings.ai_show_metrics,
    )
    if group_id is not None and len(response_text) > COLLAPSIBLE_TEXT_THRESHOLD_CHARS:
        await ai_chat_matcher.send(
            build_ai_reply_notice_message(
                group_id=group_id,
                message_id=message_id,
                user_id=user_id,
            )
        )
        response_message = response_text
    else:
        response_message = build_ai_reply_message(
            response_text,
            group_id=group_id,
            message_id=message_id,
            user_id=user_id,
        )

    await finish_split_text(
        ai_chat_matcher,
        response_message,
        group_id=group_id,
        bot=bot,
        title="棉花糖的 AI 回复",
    )


def format_local_ai_result(result) -> str | Message:
    if result.image_path:
        return Message(
            [
                MessageSegment.image(result.image_path),
                MessageSegment.text(f"\n{result.text}"),
            ]
        )
    return result.text


def build_ai_reply_message(
    text: str,
    *,
    group_id: int | str | None,
    message_id: int | str | None,
    user_id: int | str,
) -> str | Message:
    if group_id is None or not str(user_id).isdigit():
        return text

    message = Message()
    if message_id not in {None, ""} and str(message_id).isdigit():
        message += MessageSegment.reply(int(message_id))
    message += MessageSegment.at(int(user_id))
    message += MessageSegment.text(f" {text}")
    return message


def build_ai_reply_notice_message(
    *,
    group_id: int | str | None,
    message_id: int | str | None,
    user_id: int | str,
) -> str | Message:
    return build_ai_reply_message(
        "棉花糖写得有点长，正文放在折叠消息里啦。",
        group_id=group_id,
        message_id=message_id,
        user_id=user_id,
    )


def build_ai_system_context(settings: RuntimeSettings) -> str:
    return (
        f"你是 QQ 机器人“{settings.ai_bot_name}”。"
        f"当用户问你是谁、叫什么或身份时，必须明确回答你是“{settings.ai_bot_name}”。"
        "你可以用轻松自然的语气聊天，但回答要直接、简洁。"
        "不要使用 Markdown 格式，不要使用标题、列表、加粗、引用、代码块或链接语法。"
        "段落之间不要留空行，需要分段时只使用单个换行。"
        "不要声称自己只是一个通用 AI 助手，也不要编造不能确认的身份信息。"
    )


def build_ai_context(
    settings: RuntimeSettings,
    event: MessageEvent,
    group_context_store: AiGroupContextStore,
    normalized_message: NormalizedMessage | None = None,
    *,
    settings_store: SettingsStore | None = None,
) -> tuple[str, ...]:
    normalized_message = normalized_message or normalize_onebot_event(event)
    settings_store = settings_store or SettingsStore(settings.data_root, settings.author_qq)
    identity_context = build_ai_identity_context(settings, event, settings_store)
    context = [build_ai_system_context(settings)]
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        context.append("当前对话场景：私聊。")
        context.append(build_current_sender_context(event))
        if identity_context:
            context.append(identity_context)
        message_context = build_message_structure_context(normalized_message)
        if message_context:
            context.append(message_context)
        if normalized_message.reply is not None:
            context.append(build_reply_context(normalized_message))
        return tuple(context)

    group_id = getattr(event, "group_id")
    records = group_context_store.load_messages(
        group_id,
        limit=settings.ai_group_context_messages,
    )
    records = _drop_current_group_prompt(records, event, normalized_message)
    context.append("当前对话场景：QQ群聊。用户是在群里 @ 你。")
    context.append(f"当前群号：{group_id}")
    context.append(build_current_sender_context(event))
    scope_guard_context = build_memory_scope_guard_context(normalized_message)
    if scope_guard_context:
        context.append(scope_guard_context)
    if identity_context:
        context.append(identity_context)
    message_context = build_message_structure_context(
        normalized_message,
        group_id=group_id,
        nick_store=GroupNickStore(settings.data_root / "settings" / "group_nick.json"),
    )
    if message_context:
        context.append(message_context)
    reply_context = build_reply_context(normalized_message)
    if reply_context:
        context.append(reply_context)
    if records:
        lines = [
            f"{record.sender_name}({record.user_id}): {record.text}"
            for record in records
        ]
        context.append(
            "下面是本群最近聊天记录，用户要求总结群聊内容时只能基于这些记录总结：\n"
            + "\n".join(lines)
        )
    else:
        context.append("当前没有可用的群聊历史记录。")
    memory_context = build_long_term_memory_context(
        settings,
        group_id,
        normalized_message,
        event=event,
    )
    if memory_context:
        context.append(memory_context)
    return tuple(context)


def should_omit_ai_history_for_scope_query(
    event: MessageEvent,
    normalized_message: NormalizedMessage,
) -> bool:
    if getattr(event, "message_type", "") != "group" and not hasattr(event, "group_id"):
        return False
    text = build_scope_query_text(normalized_message)
    return is_cross_group_memory_query(text) or is_private_memory_query(text)


def build_memory_scope_guard_context(normalized_message: NormalizedMessage) -> str:
    text = build_scope_query_text(normalized_message)
    if is_private_memory_query(text):
        return (
            "用户在群聊里询问私聊内容。不要在群聊里查看、复述或暗示任何私聊历史；"
            "如果用户没有主动把私聊内容贴在当前群里，只能说明不能在群里披露私聊内容。"
        )
    if is_cross_group_memory_query(text):
        return (
            "用户正在询问其他群的历史内容。当前短期会话历史和本群最近聊天记录都不是其他群证据；"
            "只能依据明确标注为“当前发言者跨群长期记忆”的内容回答。"
            "如果没有这段证据，就直接说没有记录到其他群内容，不要用当前群或私聊内容猜。"
        )
    return ""


def build_scope_query_text(normalized_message: NormalizedMessage) -> str:
    parts = [normalized_message.text, normalized_message.outline]
    if normalized_message.reply is not None:
        parts.append(normalized_message.reply.message.outline)
    return " ".join(part.strip() for part in parts if part and part.strip())


def is_cross_group_memory_query(text: str) -> bool:
    return any(keyword in text for keyword in ("另一个群", "其他群", "别的群", "跨群", "不是这个群"))


def is_private_memory_query(text: str) -> bool:
    return "私聊" in text


def build_long_term_memory_context(
    settings: RuntimeSettings,
    group_id: int | str,
    normalized_message: NormalizedMessage,
    *,
    event: MessageEvent,
) -> str:
    if not settings.ai_memory_enabled:
        return ""

    query = build_memory_query(normalized_message)
    if not query:
        return ""
    try:
        memory_store = ChatMemoryStore(settings.data_root)
        facts = memory_store.search_facts(
            group_id,
            query,
            limit=settings.ai_memory_search_limit,
        )
        records = memory_store.search_messages(
            group_id,
            query,
            limit=settings.ai_memory_search_limit,
        )
        fact_source_ids = tuple(
            dict.fromkeys(
                message_id
                for fact in facts
                for message_id in fact.source_message_ids
                if message_id
            )
        )
        if fact_source_ids:
            existing_ids = {record.message_id for record in records}
            source_records = tuple(
                record
                for record in memory_store.load_messages_by_message_ids(group_id, fact_source_ids)
                if record.message_id not in existing_ids
            )
            records = (*records, *source_records)[: settings.ai_memory_search_limit]
        user_facts, user_records = search_current_sender_memory(
            memory_store,
            settings,
            group_id,
            event,
            query,
        )
    except Exception:
        return ""
    if not facts and not records and not user_facts and not user_records:
        return ""
    group_context = format_memory_context(
        facts,
        records,
        max_chars=settings.ai_memory_context_chars,
    )
    user_context = format_current_sender_memory_context(
        user_facts,
        user_records,
        max_chars=max(200, settings.ai_memory_context_chars // 2),
    )
    return "\n".join(part for part in (group_context, user_context) if part)


def search_current_sender_memory(
    memory_store: ChatMemoryStore,
    settings: RuntimeSettings,
    group_id: int | str,
    event: MessageEvent,
    query: str,
) -> tuple[tuple[ChatMemoryFact, ...], tuple[ChatMemoryRecord, ...]]:
    user_id = event.get_user_id()
    if not str(user_id).isdigit():
        return (), ()
    aliases = build_current_sender_memory_aliases(settings, group_id, event)
    limit = max(1, settings.ai_memory_search_limit // 2)
    facts = memory_store.search_user_facts(
        current_group_id=group_id,
        user_id=user_id,
        aliases=aliases,
        query=query,
        limit=limit,
    )
    records = memory_store.search_user_messages(
        current_group_id=group_id,
        user_id=user_id,
        query=query,
        limit=limit,
    )
    fact_source_ids = tuple(
        dict.fromkeys(
            message_id
            for fact in facts
            for message_id in fact.source_message_ids
            if message_id
        )
    )
    if fact_source_ids:
        existing_ids = {record.message_id for record in records}
        source_records = tuple(
            record
            for fact in facts
            for record in memory_store.load_messages_by_message_ids(fact.group_id, fact.source_message_ids)
            if record.message_id not in existing_ids
        )
        records = (*records, *source_records)[:limit]
    return facts, records


def build_current_sender_memory_aliases(
    settings: RuntimeSettings,
    group_id: int | str,
    event: MessageEvent,
) -> tuple[str, ...]:
    user_id = event.get_user_id()
    sender = getattr(event, "sender", None)
    aliases = [
        str(getattr(sender, "card", "") or "").strip(),
        str(getattr(sender, "nickname", "") or "").strip(),
    ]
    try:
        nick_store = GroupNickStore(settings.data_root / "settings" / "group_nick.json")
        if str(group_id).isdigit() and str(user_id).isdigit():
            aliases.append(nick_store.resolve_display_name(int(group_id), int(user_id)))
    except Exception:
        pass
    return tuple(
        dict.fromkeys(
            alias
            for alias in aliases
            if alias and alias != str(user_id)
        )
    )


def build_memory_query(normalized_message: NormalizedMessage) -> str:
    parts = [
        normalized_message.text,
        normalized_message.outline,
        " ".join(normalized_message.at_user_ids),
    ]
    if normalized_message.reply is not None:
        parts.append(normalized_message.reply.message.outline)
        parts.append(normalized_message.reply.sender_name)
    return " ".join(part.strip() for part in parts if part and part.strip())


def format_memory_context(
    facts: tuple[ChatMemoryFact, ...],
    records: tuple[ChatMemoryRecord, ...],
    *,
    max_chars: int,
) -> str:
    budget = max(200, max_chars)
    lines: list[str] = []
    if facts:
        lines.append("下面是本群长期事实记忆，由历史消息抽取；低置信度内容要谨慎使用：")
        for fact in facts:
            line = (
                f"- {fact.subject} {fact.predicate} {fact.object}"
                f" [置信度：{fact.confidence:.2f}]"
            )
            if fact.source_message_ids:
                line += f" [来源消息：{','.join(fact.source_message_ids)}]"
            if sum(len(item) + 1 for item in lines) + len(line) > budget:
                break
            lines.append(line)
    source_message_ids = {
        message_id
        for fact in facts
        for message_id in fact.source_message_ids
        if message_id
    }
    ordered_records = tuple(
        sorted(
            records,
            key=lambda record: (
                record.message_id not in source_message_ids,
                -record.importance,
                -record.timestamp,
            ),
        )
    )
    if ordered_records:
        if lines:
            lines.append("下面是本群相关历史原文，可用于核对长期事实记忆：")
        else:
            lines.append(
                "下面是本群长期记忆检索结果：相关历史原文，只能作为补充证据，不能编造没有出现过的事实："
            )
    for record in ordered_records:
        line = f"- {record.sender_name}({record.user_id}): {record.text}"
        if record.tags:
            line += f" [标签：{'、'.join(record.tags)}]"
        if record.reply_outline:
            line += f" [引用：{record.reply_outline}]"
        if sum(len(item) + 1 for item in lines) + len(line) > budget:
            break
        lines.append(line)
    return "\n".join(lines)


def format_current_sender_memory_context(
    facts: tuple[ChatMemoryFact, ...],
    records: tuple[ChatMemoryRecord, ...],
    *,
    max_chars: int,
) -> str:
    if not facts and not records:
        return ""
    budget = max(200, max_chars)
    lines = [
        "下面是当前发言者跨群长期记忆，只能用于理解这个用户本人；不要把这些内容当成本群规则或其他群成员的信息："
    ]
    for fact in facts:
        line = (
            f"- {fact.subject} {fact.predicate} {fact.object}"
            f" [来自群：{fact.group_id}] [置信度：{fact.confidence:.2f}]"
        )
        if fact.source_message_ids:
            line += f" [来源消息：{','.join(fact.source_message_ids)}]"
        if sum(len(item) + 1 for item in lines) + len(line) > budget:
            break
        lines.append(line)

    source_message_ids = {
        message_id
        for fact in facts
        for message_id in fact.source_message_ids
        if message_id
    }
    ordered_records = tuple(
        sorted(
            records,
            key=lambda record: (
                record.message_id not in source_message_ids,
                -record.importance,
                -record.timestamp,
            ),
        )
    )
    for record in ordered_records:
        line = (
            f"- {record.sender_name}({record.user_id}) 在群 {record.group_id} 说："
            f" {record.text}"
        )
        if record.tags:
            line += f" [标签：{'、'.join(record.tags)}]"
        if sum(len(item) + 1 for item in lines) + len(line) > budget:
            break
        lines.append(line)
    return "\n".join(lines)


def build_current_sender_context(event: MessageEvent) -> str:
    user_id = event.get_user_id()
    sender = getattr(event, "sender", None)
    card = str(getattr(sender, "card", "") or "").strip()
    nickname = str(getattr(sender, "nickname", "") or "").strip()
    display_name = card or nickname or user_id
    return f"当前发言者：{display_name}({user_id})"


def build_ai_identity_context(
    settings: RuntimeSettings,
    event: MessageEvent,
    settings_store: SettingsStore,
) -> str:
    author_qq = int(settings.author_qq)
    if author_qq <= 0:
        return ""

    nick_store = GroupNickStore(settings.data_root / "settings" / "group_nick.json")
    author_label = format_admin_identity_label(
        author_qq,
        nick_store=nick_store,
        fallback_name=settings.author_name,
    )
    admin_ids = {
        int(qq)
        for qq, enabled in settings_store.list_bot_admins().items()
        if str(qq).isdigit() and enabled
    }
    admin_ids.add(author_qq)
    ordered_admin_ids = [author_qq] + sorted(qq for qq in admin_ids if qq != author_qq)
    admin_labels = [
        format_admin_identity_label(qq, nick_store=nick_store)
        if qq != author_qq
        else author_label
        for qq in ordered_admin_ids
    ]

    current_user_id = int(event.get_user_id()) if event.get_user_id().isdigit() else 0
    if current_user_id == author_qq:
        current_identity = "Bot 作者/主人"
    elif current_user_id and settings_store.is_bot_admin(current_user_id):
        current_identity = "Bot 管理员"
    else:
        current_identity = "普通用户"

    author_name = author_label.rsplit("(", 1)[0].strip()
    # 身份事实直接提供给普通 AI，避免模型把真实管理关系泛化成普通社交回答。
    return (
        "机器人身份事实："
        f"\nBot 作者/主人：{author_label}"
        f"\nBot 管理员列表：{'、'.join(admin_labels)}"
        f"\n当前发言者身份：{current_identity}"
        f"\n如果别人问“{author_name}是你的什么人”或类似问题，"
        f"应回答 {author_name} 是你的作者、主人和最高管理者。"
        "不要回答“大家都是主人”或否认这些身份事实。"
    )


def format_admin_identity_label(
    qq: int,
    *,
    nick_store: GroupNickStore,
    fallback_name: str = "",
) -> str:
    fallback_name = fallback_name.strip()
    name = fallback_name or nick_store.resolve_display_name(0, qq).strip()
    if not name or name == str(qq):
        return str(qq)
    return f"{name}({qq})"


def build_message_structure_context(
    normalized_message: NormalizedMessage,
    *,
    group_id: int | str | None = None,
    nick_store: GroupNickStore | None = None,
) -> str:
    lines: list[str] = []
    if normalized_message.outline:
        lines.append(f"本次消息概要：{normalized_message.outline}")
    if normalized_message.at_user_ids:
        lines.append(
            "本次消息 @ 了："
            + "、".join(
                resolve_at_display_name(group_id, user_id, nick_store)
                for user_id in normalized_message.at_user_ids
            )
        )
    if collect_message_image_urls(normalized_message):
        lines.append("用户本次消息包含图片；图片会随请求发送给当前 AI provider。")
    if normalized_message.audio_urls:
        lines.append("用户本次消息包含语音。当前链路暂未把语音发送给 provider，只能说明收到了语音。")
    if normalized_message.video_urls:
        lines.append("用户本次消息包含视频。当前链路暂未把视频发送给 provider，只能说明收到了视频。")
    return "\n".join(lines)


def resolve_at_display_name(
    group_id: int | str | None,
    user_id: str,
    nick_store: GroupNickStore | None,
) -> str:
    if group_id is None or nick_store is None or not user_id.isdigit():
        return user_id
    display_name = nick_store.resolve_display_name(int(group_id), int(user_id))
    if display_name and display_name != user_id:
        return f"{display_name}({user_id})"
    return user_id


def build_reply_context(normalized_message: NormalizedMessage) -> str:
    reply = normalized_message.reply
    if reply is None:
        return ""
    content = reply.message.outline
    if not content:
        return ""

    return (
        "用户这次消息引用了下面这条消息，请优先结合引用内容回答：\n"
        f"{reply.sender_name}({reply.user_id or '未知QQ'}): {content}"
    )


def collect_message_image_urls(normalized_message: NormalizedMessage) -> tuple[str, ...]:
    image_urls = list(normalized_message.image_urls)
    if normalized_message.reply is not None:
        image_urls.extend(normalized_message.reply.message.image_urls)
    return tuple(dict.fromkeys(image_urls))


def _drop_current_group_prompt(
    records: tuple[AiGroupMessageRecord, ...],
    event: MessageEvent,
    normalized_message: NormalizedMessage,
) -> tuple[AiGroupMessageRecord, ...]:
    if not records:
        return records

    latest = records[-1]
    if (
        latest.user_id == event.get_user_id()
        and latest.text in {normalized_message.text, normalized_message.outline}
    ):
        return records[:-1]
    return records


def format_ai_response(
    profile_name: str,
    response: AiResponse,
    *,
    show_metrics: bool = False,
) -> str:
    if not show_metrics:
        return response.text

    metrics = response.metrics
    if metrics is None:
        return f"[{profile_name}]\n{response.text}"

    first_token = "-" if metrics.first_token_seconds is None else f"{metrics.first_token_seconds:.2f}s"
    if metrics.tokens_per_second is not None:
        speed = f"{metrics.tokens_per_second:.1f} tok/s"
    else:
        speed = f"{metrics.chars_per_second:.1f} chars/s"
    return (
        f"[{profile_name}] TTFT {first_token} / total {metrics.total_seconds:.2f}s / "
        f"{speed} / {metrics.output_chars} chars\n{response.text}"
    )
