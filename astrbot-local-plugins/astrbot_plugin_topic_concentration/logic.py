from __future__ import annotations

import json
import re


DECISION_PROVIDER_ORDER_CONFIG = "decision_provider_order"


def read_decision_provider_order(config) -> tuple[str, ...]:
    return normalize_provider_order(read_config_value(config, DECISION_PROVIDER_ORDER_CONFIG, []))


def normalize_provider_order(raw_order) -> tuple[str, ...]:
    if isinstance(raw_order, str):
        text = raw_order.strip()
        if not text:
            return ()
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = []
            return normalize_provider_order(parsed)
        raw_values = re.split(r"[\n,]+", text)
    elif isinstance(raw_order, (list, tuple)):
        raw_values = raw_order
    else:
        return ()

    provider_ids: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        provider_id = str(value or "").strip()
        if not provider_id or provider_id in seen:
            continue
        provider_ids.append(provider_id)
        seen.add(provider_id)
    return tuple(provider_ids)


def build_decision_provider_ids(
    *,
    configured_order: tuple[str, ...],
    provider_settings: dict,
    current_provider_id: str,
) -> tuple[str, ...]:
    if configured_order:
        return configured_order

    raw_order: list[object] = []
    if current_provider_id:
        raw_order.append(current_provider_id)
    raw_order.append(provider_settings.get("default_provider_id", ""))
    fallback_ids = provider_settings.get("fallback_chat_models", [])
    if isinstance(fallback_ids, list):
        raw_order.extend(fallback_ids)
    return normalize_provider_order(raw_order)


async def chat_with_decision_providers(
    *,
    context,
    event,
    prompt: str,
    configured_order: tuple[str, ...],
    logger,
):
    provider_ids = build_decision_provider_ids(
        configured_order=configured_order,
        provider_settings=read_provider_settings(context, event, logger),
        current_provider_id=read_current_provider_id(context, event, logger),
    )
    if not provider_ids:
        logger.info("[TopicConcentration] no provider for active reply decision")
        return None

    attempted_provider_ids: list[str] = []
    for provider_id in provider_ids:
        provider = context.get_provider_by_id(provider_id)
        if provider is None:
            logger.warning("[TopicConcentration] decision provider not found: provider=%s", provider_id)
            continue
        attempted_provider_ids.append(provider_id)
        try:
            response = await provider.text_chat(
                prompt=prompt,
                session_id=f"topic_concentration:{event.unified_msg_origin}",
                persist=False,
            )
        except Exception as exc:
            logger.warning(
                "[TopicConcentration] AI decision provider failed: provider=%s error=%s",
                provider_id,
                exc,
            )
            continue
        logger.debug("[TopicConcentration] AI decision provider succeeded: provider=%s", provider_id)
        return response

    logger.warning(
        "[TopicConcentration] all AI decision providers failed: providers=%s",
        attempted_provider_ids or provider_ids,
    )
    return None


def read_current_provider_id(context, event, logger) -> str:
    try:
        provider = context.get_using_provider(event.unified_msg_origin)
    except Exception as exc:
        logger.warning("[TopicConcentration] failed to read current provider: %s", exc)
        return ""
    return read_provider_id(provider)


def read_provider_id(provider) -> str:
    if provider is None:
        return ""
    provider_config = getattr(provider, "provider_config", None)
    if not isinstance(provider_config, dict):
        return ""
    return str(provider_config.get("id") or "").strip()


def read_provider_settings(context, event, logger) -> dict:
    try:
        config = context.get_config(umo=event.unified_msg_origin)
    except TypeError:
        config = context.get_config()
    except Exception as exc:
        logger.warning("[TopicConcentration] failed to read provider settings: %s", exc)
        return {}
    settings = read_config_value(config, "provider_settings", {})
    return settings if isinstance(settings, dict) else {}


def read_config_value(config, key: str, default):
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    getter = getattr(config, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            pass
    try:
        return config[key]
    except Exception:
        return default
