from __future__ import annotations

from qqbot.config import RuntimeSettings


def build_status_lines(
    settings: RuntimeSettings,
    phase: str = "skeleton ready",
) -> list[str]:
    token_state = "configured" if settings.onebot_access_token else "empty"
    return [
        "QQBot Python skeleton is running.",
        f"OneBot V11 Reverse WS: {settings.onebot_ws_url}",
        f"Access Token: {token_state}",
        f"Migration Phase: {phase}",
        "NapCat is expected to connect as the QQ gateway.",
    ]
